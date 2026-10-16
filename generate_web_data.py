"""
Export gap_surface.gpkg → web/<county>/data.geojson for the interactive map.

Usage:
  python generate_web_data.py snohomish   (default)
  python generate_web_data.py king

Adds:
  - place_name  (TIGER spatial join, cached)
  - display_name (place_name + tract/BG label)
  - equity_distance, priority, priority_rank
  - rounds floats to 4dp, simplifies geometry
"""

import sys
from pathlib import Path
import numpy as np
import geopandas as gpd

COUNTY_CONFIGS = {
    "snohomish": {
        "data_dir":    Path("data"),
        "county_fips": "061",
        "fallback":    "Snohomish County (unincorporated)",
    },
    "king": {
        "data_dir":    Path("data_king"),
        "county_fips": "033",
        "fallback":    "King County (unincorporated)",
    },
}

TIGER = Path("data/raw/tiger")

KEEP_COLS = [
    "GEOID", "display_name", "total_pop",
    "pct_elderly", "pct_unemployed", "pct_novehicle", "pct_lowincome",
    "vulnerability_index", "norm_accessibility",
    "gap_score", "equity_distance", "priority", "priority_rank",
]

FLOAT_COLS = [
    "pct_elderly", "pct_unemployed", "pct_novehicle", "pct_lowincome",
    "vulnerability_index", "norm_accessibility",
    "gap_score", "equity_distance", "priority",
]


def parse_tract(geoid: str) -> str:
    tract_raw = geoid[5:11]
    bg = geoid[11]
    major = tract_raw[:4].lstrip("0") or "0"
    minor = tract_raw[4:]
    tract_str = f"{major}.{minor}" if minor != "00" else major
    return f"Tract {tract_str}, BG {bg}"


def load_tiger_places(county_fips: str):
    places = gpd.read_file(TIGER / "tl_2023_53_place.shp")[["NAME", "geometry"]].to_crs("EPSG:4326")
    cousub = gpd.read_file(TIGER / "tl_2023_53_cousub.shp")
    cousub = cousub[cousub["COUNTYFP"] == county_fips][["NAME", "geometry"]].to_crs("EPSG:4326")
    cousub = cousub.rename(columns={"NAME": "COUSUB_NAME"})
    return places, cousub


def add_place_names(gdf: gpd.GeoDataFrame, county_fips: str, fallback_label: str) -> gpd.GeoDataFrame:
    print("Building block group centroids...")
    centroids = gpd.GeoDataFrame(
        gdf[["GEOID"]], geometry=gdf.geometry.centroid, crs="EPSG:4326"
    )

    places, cousub = load_tiger_places(county_fips)

    joined = gpd.sjoin(centroids, places, how="left", predicate="within")
    joined = joined[["GEOID", "NAME"]].rename(columns={"NAME": "place_name"})
    joined = joined.drop_duplicates("GEOID")

    unmatched_ids = joined[joined["place_name"].isna()]["GEOID"]
    unmatched_pts = centroids[centroids["GEOID"].isin(unmatched_ids)]
    fallback = gpd.sjoin(unmatched_pts, cousub, how="left", predicate="within")
    fallback = fallback[["GEOID", "COUSUB_NAME"]].drop_duplicates("GEOID")
    fallback = fallback.rename(columns={"COUSUB_NAME": "place_name"})

    joined = joined.set_index("GEOID")
    joined.update(fallback.set_index("GEOID"))
    joined = joined.reset_index()
    joined["place_name"] = joined["place_name"].fillna(fallback_label)

    gdf = gdf.merge(joined, on="GEOID", how="left")
    gdf["display_name"] = gdf.apply(
        lambda r: f"{r['place_name']} — {parse_tract(r['GEOID'])}", axis=1
    )
    return gdf


def compute_priority(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    vuln_n = (gdf["vulnerability_index"] - gdf["vulnerability_index"].min()) / \
             (gdf["vulnerability_index"].max() - gdf["vulnerability_index"].min())
    acc_n = gdf["norm_accessibility"]

    gdf = gdf.copy()
    gdf["equity_distance"] = (vuln_n - acc_n) / np.sqrt(2)

    under_mask = gdf["equity_distance"] > 0
    under = gdf[under_mask].copy()

    gap_n = (under["gap_score"] - under["gap_score"].min()) / \
            (under["gap_score"].max() - under["gap_score"].min())
    ed_n = (under["equity_distance"] - under["equity_distance"].min()) / \
           (under["equity_distance"].max() - under["equity_distance"].min())
    under["priority"] = (gap_n + ed_n) / 2

    gdf["priority"] = np.nan
    gdf.loc[under_mask, "priority"] = under["priority"]

    gdf["priority_rank"] = np.nan
    ranks = under["priority"].rank(ascending=False, method="min").astype(int)
    gdf.loc[under_mask, "priority_rank"] = ranks.values

    return gdf


def main(county: str = "snohomish"):
    cfg = COUNTY_CONFIGS[county]
    out_path = Path("web") / county / "data.geojson"

    print(f"Loading gap surface for {county}...")
    gdf = gpd.read_file(cfg["data_dir"] / "processed" / "gap_surface.gpkg")

    print("Computing priority scores...")
    gdf = compute_priority(gdf)

    print("Adding place names from TIGER...")
    gdf = add_place_names(gdf, cfg["county_fips"], cfg["fallback"])

    print("Trimming and rounding...")
    out = gdf[KEEP_COLS + ["geometry"]].copy()
    for col in FLOAT_COLS:
        out[col] = out[col].round(4)
    out["priority"] = out["priority"].round(4)
    out["priority_rank"] = out["priority_rank"].where(out["priority_rank"].notna(), other=None)
    out["total_pop"] = out["total_pop"].astype(int)

    out = out.to_crs("EPSG:32610")
    out["geometry"] = out.geometry.simplify(tolerance=10, preserve_topology=True)
    out = out.to_crs("EPSG:4326")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(out_path, driver="GeoJSON")

    size_mb = out_path.stat().st_size / 1e6
    print(f"Wrote {out_path}  ({size_mb:.2f} MB, {len(out)} features)")


if __name__ == "__main__":
    county = sys.argv[1] if len(sys.argv) > 1 else "snohomish"
    if county not in COUNTY_CONFIGS:
        print(f"Unknown county '{county}'. Options: {list(COUNTY_CONFIGS.keys())}")
        sys.exit(1)
    main(county)
