"""
Gravity-model accessibility scoring and gap surface computation.

A_i = Σ_j [ F_j * exp(-β * d_ij) ]

  A_i  = accessibility score at block group centroid i
  F_j  = trips/day at stop j
  d_ij = network distance in miles from centroid i to stop j
  β    = 4.0  (50% decay at 0.25 mi, calibrated for elderly/disabled walking tolerance)

Outputs:
  data/processed/accessibility_scores.parquet
  data/processed/gap_surface.gpkg
"""

from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import pandana as pdna

BETA = 4.0
MAX_DIST_M = 1.5 * 1609  # 1.5 miles in meters
MAX_STOPS = 20           # pandana max_items per POI query
METERS_PER_MILE = 1609.344

ACC_OUT = Path("data/processed/accessibility_scores.parquet")
GAP_OUT = Path("data/processed/gap_surface.gpkg")


def _normalize(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - mn) / (mx - mn)


def compute_accessibility(
    network: pdna.Network,
    stops_gdf: gpd.GeoDataFrame,
    vuln_gdf: gpd.GeoDataFrame,
    beta: float = BETA,
    max_dist_m: float = MAX_DIST_M,
    max_stops: int = MAX_STOPS,
    out_path: str | Path = ACC_OUT,
) -> gpd.GeoDataFrame:
    """
    Compute frequency-weighted gravity-model accessibility for each block group centroid.

    Parameters
    ----------
    network    : pandana Network (must already have precompute() called)
    stops_gdf  : GeoDataFrame from gtfs.compute_stop_frequencies()
    vuln_gdf   : GeoDataFrame from vulnerability.build_vulnerability_index()
    beta       : distance decay parameter
    max_dist_m : search radius cap in meters
    max_stops  : max stops to consider per node

    Returns GeoDataFrame with accessibility_score and norm_accessibility added.
    """
    stops_proj = stops_gdf.to_crs("EPSG:4326")

    # Snap stop locations onto the network
    network.set_pois(
        category="stops",
        maxdist=max_dist_m,
        maxitems=max_stops,
        x_col=stops_proj.geometry.x,
        y_col=stops_proj.geometry.y,
    )

    # For each node in the network, get distances to nearest MAX_STOPS stops
    # Returns DataFrame: rows=network nodes, cols=0..MAX_STOPS-1 (distance in meters)
    distances_m = network.nearest_pois(
        distance=max_dist_m,
        category="stops",
        num_pois=max_stops,
        include_poi_ids=True,
    )
    # distances_m columns: 1..MAX_STOPS (distance), then poi_ids
    dist_cols = [c for c in distances_m.columns if isinstance(c, int)]
    id_cols = [c for c in distances_m.columns if not isinstance(c, int)]

    # Build a lookup: pandana poi index → trips_per_day
    # pandana assigns poi indices in the order set_pois received them
    freq_lookup = stops_proj["trips_per_day"].reset_index(drop=True)

    # Compute gravity score per network node
    scores = pd.Series(0.0, index=distances_m.index)
    for rank_col, id_col in zip(dist_cols, id_cols):
        d_m = distances_m[rank_col].values
        poi_idx = distances_m[id_col].values.astype(int)

        # Mask invalid entries (distance == max_dist means no stop found)
        valid = d_m < max_dist_m

        d_mi = d_m / METERS_PER_MILE
        freq = np.where(
            valid & (poi_idx >= 0) & (poi_idx < len(freq_lookup)),
            freq_lookup.values[np.clip(poi_idx, 0, len(freq_lookup) - 1)],
            0.0,
        )
        decay = np.exp(-beta * d_mi)
        scores += pd.Series(freq * decay * valid, index=distances_m.index)

    node_scores = scores.rename("accessibility_score")

    # Snap block group centroids to nearest network nodes
    vuln_proj = vuln_gdf.to_crs("EPSG:4326")
    centroids = vuln_proj.geometry.centroid

    nearest_nodes = network.get_node_ids(
        centroids.x.values, centroids.y.values
    )

    result = vuln_proj.copy()
    result["accessibility_score"] = node_scores.reindex(nearest_nodes).values
    result["accessibility_score"] = result["accessibility_score"].fillna(0)
    result["norm_accessibility"] = _normalize(result["accessibility_score"])

    # Log-normalize for gap formula: log(1+score)/log(1+max) stretches the
    # low end where 95% of block groups sit, giving the gap formula real
    # discrimination power. Linear norm collapses everything to ~0.
    max_score = result["accessibility_score"].max()
    if max_score > 0:
        result["log_accessibility"] = (
            np.log1p(result["accessibility_score"]) / np.log1p(max_score)
        )
    else:
        result["log_accessibility"] = 0.0

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    result[["GEOID", "accessibility_score", "norm_accessibility", "log_accessibility"]].to_parquet(out_path)
    print(f"Saved accessibility scores → {out_path}  ({len(result)} block groups)")
    return result


def compute_gap_surface(
    acc_gdf: gpd.GeoDataFrame,
    out_path: str | Path = GAP_OUT,
) -> gpd.GeoDataFrame:
    """
    gap_score = vulnerability_index * (1 - log_accessibility)

    Uses log-normalized accessibility so the formula has real discrimination
    power. Linear norm_accessibility is near 0 for ~95% of block groups,
    making (1 - norm_acc) ≈ 1 everywhere and gap ≈ vulnerability.
    Log-normalization stretches the low end where variation actually lives.

    High gap_score = high need, low service = priority zone.

    Parameters
    ----------
    acc_gdf : GeoDataFrame output of compute_accessibility()
              must contain vulnerability_index and log_accessibility columns.
    """
    gdf = acc_gdf.copy()

    if "log_accessibility" not in gdf.columns:
        if "accessibility_score" not in gdf.columns:
            raise KeyError(
                "acc_gdf must contain either 'log_accessibility' or 'accessibility_score'"
            )
        max_score = gdf["accessibility_score"].max()
        if max_score > 0:
            gdf["log_accessibility"] = (
                np.log1p(gdf["accessibility_score"]) / np.log1p(max_score)
            )
        else:
            gdf["log_accessibility"] = 0.0

    gdf["gap_score"] = gdf["vulnerability_index"] * (1 - gdf["log_accessibility"])

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GPKG")
    print(f"Saved gap surface → {out_path}  ({len(gdf)} block groups)")
    return gdf
