"""
Full transit gap analysis pipeline for King County, WA.

Saves all outputs to data_king/ (parallel to data/ for Snohomish County).
Run from the project root: python run_king_pipeline.py

Steps:
  1. ACS vulnerability index (cenpy → Census API)
  2. GTFS stop frequencies (King County Metro)
  3. OSM walk network (osmnx — slow, ~10-20 min; cached to data_king/raw/osm/)
  4. Accessibility scores (pandana gravity model)
  5. Gap surface (vulnerability * (1 - log_accessibility))
"""

from pathlib import Path
import sys

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from transit_gaps import vulnerability, gtfs, network, accessibility

# ---- King County config ----
STATE_FIPS  = "53"
COUNTY_FIPS = "033"
PLACE       = "King County, Washington"
DATA        = Path("data_king")
MAX_DIST_M  = 0.75 * 1609  # reduced from 1.5mi — keeps precompute tractable for 408k-node network

PATHS = {
    "gtfs_dir":     DATA / "raw" / "gtfs",
    "osm_cache":    DATA / "raw" / "osm" / "king_walk.graphml",
    "network_h5":   DATA / "processed" / "pandana_network.h5",
    "vuln_out":     DATA / "processed" / "vulnerability_index.gpkg",
    "stops_out":    DATA / "processed" / "stop_frequencies.parquet",
    "acc_out":      DATA / "processed" / "accessibility_scores.parquet",
    "gap_out":      DATA / "processed" / "gap_surface.gpkg",
}

# Ensure dirs exist
for p in PATHS.values():
    p.parent.mkdir(parents=True, exist_ok=True)


def step1_vulnerability():
    print("\n=== Step 1: ACS Vulnerability Index ===")
    vuln_gdf = vulnerability.build_vulnerability_index(
        out_path=PATHS["vuln_out"],
        state=STATE_FIPS,
        county=COUNTY_FIPS,
    )
    print(f"Block groups: {len(vuln_gdf)}")
    return vuln_gdf


def step2_gtfs():
    print("\n=== Step 2: GTFS Stop Frequencies ===")
    feed = gtfs.load_feed(PATHS["gtfs_dir"])
    stops_gdf = gtfs.compute_stop_frequencies(feed, out_path=PATHS["stops_out"])
    print(f"Stops with frequency data: {len(stops_gdf)}")
    return stops_gdf


def step3_network(save_h5=True):
    print("\n=== Step 3: OSM Walk Network (slow — cached after first run) ===")
    net, nodes, edges = network.build_network(
        place=PLACE,
        cache_path=PATHS["osm_cache"],
        precompute_dist_m=MAX_DIST_M,
    )
    if save_h5:
        network.save_network(net, PATHS["network_h5"])
    else:
        print("Skipping HDF5 save (--skip-network-save mode)")
    return net


def step4_accessibility(net, stops_gdf, vuln_gdf):
    print("\n=== Step 4: Accessibility Scores ===")
    acc_gdf = accessibility.compute_accessibility(
        network=net,
        stops_gdf=stops_gdf,
        vuln_gdf=vuln_gdf,
        out_path=PATHS["acc_out"],
        max_dist_m=MAX_DIST_M,
    )
    return acc_gdf


def step5_gap(acc_gdf):
    print("\n=== Step 5: Gap Surface ===")
    gap_gdf = accessibility.compute_gap_surface(
        acc_gdf=acc_gdf,
        out_path=PATHS["gap_out"],
    )
    return gap_gdf


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-step", type=int, default=1,
                        help="Resume from step N (1-5). Steps before N must already have outputs.")
    parser.add_argument("--skip-network-save", action="store_true",
                        help="Skip saving pandana network to HDF5 (use if save crashes on large networks).")
    args = parser.parse_args()

    vuln_gdf = stops_gdf = net = acc_gdf = None

    if args.from_step <= 1:
        vuln_gdf = step1_vulnerability()
    else:
        import geopandas as gpd
        vuln_gdf = gpd.read_file(PATHS["vuln_out"])
        print(f"Loaded vulnerability from {PATHS['vuln_out']} ({len(vuln_gdf)} BGs)")

    if args.from_step <= 2:
        stops_gdf = step2_gtfs()
    else:
        import geopandas as gpd
        stops_gdf = gpd.read_parquet(PATHS["stops_out"])
        print(f"Loaded stop frequencies from {PATHS['stops_out']} ({len(stops_gdf)} stops)")

    if args.from_step <= 3:
        net = step3_network(save_h5=not args.skip_network_save)
    else:
        net = network.load_network(PATHS["network_h5"])

    if args.from_step <= 4:
        acc_gdf = step4_accessibility(net, stops_gdf, vuln_gdf)
    else:
        import geopandas as gpd
        acc_gdf = gpd.read_file(PATHS["gap_out"])
        print(f"Loaded gap surface from {PATHS['gap_out']} ({len(acc_gdf)} BGs)")

    if args.from_step <= 5:
        gap_gdf = step5_gap(acc_gdf)

    print("\n=== Pipeline complete ===")
    print(f"Outputs in {DATA}/")
    print("Next: python generate_web_data.py king")
