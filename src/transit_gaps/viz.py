"""
Full-county transit gap map.

Layout: 1 row × 3 panels
  Panel 0: Vulnerability Index        (YlOrRd)
  Panel 1: Transit Accessibility      (Blues, PowerNorm)
  Panel 2: Gap Score                  (RdYlGn_r)

Shared color scales fixed to county-wide min/max.
City labels annotated on every panel.
CartoDB Positron basemap via contextily.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import geopandas as gpd
import contextily as ctx
import numpy as np
from shapely.geometry import Point

OUT_PATH = Path("data/outputs/maps/snohomish_transit_gaps.png")
DPI = 200
BASEMAP = ctx.providers.CartoDB.Positron

CMAP_VULN = "YlOrRd"
CMAP_ACC  = "seismic"
CMAP_GAP  = "RdYlGn_r"

# Major Snohomish County cities (lat, lon)
CITIES = {
    "Everett":       (47.979, -122.202),
    "Lynnwood":      (47.821, -122.315),
    "Marysville":    (48.051, -122.177),
    "Edmonds":       (47.811, -122.378),
    "Mukilteo":      (47.913, -122.305),
    "Monroe":        (47.855, -121.972),
    "Snohomish":     (47.913, -122.099),
    "Arlington":     (48.198, -122.125),
    "Stanwood":      (48.240, -122.378),
    "Granite Falls": (48.083, -121.976),
    "Sultan":        (47.864, -121.816),
    "Gold Bar":      (47.848, -121.694),
    "Darrington":    (48.253, -121.900),
    "Index":         (47.824, -121.551),
}


def _add_basemap(ax, crs):
    try:
        ctx.add_basemap(ax, crs=crs.to_string(), source=BASEMAP, zoom="auto")
    except Exception as e:
        print(f"  Basemap fetch failed: {e}")


def _make_city_gdf(crs="EPSG:3857"):
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    rows = []
    for name, (lat, lon) in CITIES.items():
        x, y = transformer.transform(lon, lat)
        rows.append({"name": name, "geometry": Point(x, y)})
    return gpd.GeoDataFrame(rows, crs=crs)


def _add_city_labels(ax, cities_gdf, bounds):
    minx, miny, maxx, maxy = bounds
    for _, row in cities_gdf.iterrows():
        x, y = row.geometry.x, row.geometry.y
        if minx <= x <= maxx and miny <= y <= maxy:
            ax.plot(x, y, "k.", markersize=3.5, zorder=5)
            ax.annotate(
                row["name"], xy=(x, y),
                xytext=(4, 4), textcoords="offset points",
                fontsize=7, color="#111111", zorder=6,
                bbox=dict(boxstyle="round,pad=0.15", fc="white",
                          alpha=0.65, ec="none"),
            )


def plot_county_map(
    gap_gdf: gpd.GeoDataFrame,
    out_path: str | Path = OUT_PATH,
    dpi: int = DPI,
) -> plt.Figure:
    """
    Single full-county map: vulnerability | accessibility | gap score.

    Parameters
    ----------
    gap_gdf  : block group GeoDataFrame with vulnerability_index,
               norm_accessibility, gap_score columns
    out_path : output PNG path
    dpi      : output resolution
    """
    crs = "EPSG:3857"
    bg = gap_gdf.to_crs(crs)
    cities = _make_city_gdf(crs)
    bounds = bg.total_bounds  # (minx, miny, maxx, maxy)

    vuln_norm = mcolors.Normalize(
        vmin=bg["vulnerability_index"].min(),
        vmax=bg["vulnerability_index"].max(),
    )
    acc_norm = mcolors.PowerNorm(
        gamma=0.4,
        vmin=bg["norm_accessibility"].min(),
        vmax=bg["norm_accessibility"].max(),
    )
    gap_norm = mcolors.Normalize(
        vmin=bg["gap_score"].min(),
        vmax=bg["gap_score"].max(),
    )

    panels = [
        ("vulnerability_index", CMAP_VULN, vuln_norm, "Vulnerability Index"),
        ("norm_accessibility",  CMAP_ACC,  acc_norm,  "Transit Accessibility"),
        ("gap_score",           CMAP_GAP,  gap_norm,  "Gap Score"),
    ]

    fig, axes = plt.subplots(3, 1, figsize=(9, 21), constrained_layout=True)

    for ax, (col, cmap, norm, title) in zip(axes, panels):
        bg.plot(
            column=col, cmap=cmap, norm=norm,
            ax=ax, linewidth=0.15, edgecolor="white", alpha=0.88,
        )
        _add_basemap(ax, bg.crs)

        minx, miny, maxx, maxy = bounds
        padx = (maxx - minx) * 0.02
        pady = (maxy - miny) * 0.02
        ax.set_xlim(minx - padx, maxx + padx)
        ax.set_ylim(miny - pady, maxy + pady)
        ax.set_axis_off()
        ax.set_title(title, fontsize=13, fontweight="bold", pad=8)

        _add_city_labels(ax, cities, bounds)

        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        fig.colorbar(sm, ax=ax, orientation="horizontal",
                     shrink=0.7, pad=0.02, label=title)

    fig.suptitle(
        "Snohomish County — Transit Accessibility & Vulnerability Gap Analysis",
        fontsize=15, fontweight="bold", y=0.98,
    )

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    print(f"Map saved → {out_path}")
    return fig


# Backward-compat aliases
def plot_quadrant_maps(gap_gdf, out_path=OUT_PATH, dpi=DPI):
    return plot_county_map(gap_gdf, out_path=out_path, dpi=dpi)

def plot_small_multiples(gap_gdf, zones_gdf=None, route_lines=None,
                         out_path=OUT_PATH, dpi=DPI):
    return plot_county_map(gap_gdf, out_path=out_path, dpi=dpi)
