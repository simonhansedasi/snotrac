# Snotrac Transit Gap Analysis
**Snohomish County Frequency-Weighted Transit Accessibility & Vulnerability Mapping**

---

## Project Overview

Static small-multiples map series showing the mismatch between transit-dependent populations and actual service coverage across Snohomish County. Coverage is measured as frequency-weighted network distance accessibility — not raw stop proximity. Output is a set of publication-quality maps organized by geographically contiguous zones derived from coverage gradient clustering.

**End product:** A small-multiples PDF/PNG series, one panel per zone, each showing vulnerability composite, service accessibility surface, and gap overlay on a consistent color scale.

---

## Repository Structure

```
snotrac-transit-gaps/
├── data/
│   ├── raw/
│   │   ├── gtfs/              # Community Transit GTFS feed
│   │   ├── acs/               # Census ACS block group downloads
│   │   └── osm/               # OSM network cache (auto-populated by osmnx)
│   ├── processed/             # Intermediate parquet/gpkg files
│   └── outputs/
│       └── maps/              # Final map exports
├── notebooks/
│   ├── 01_gtfs_ingestion.ipynb
│   ├── 02_acs_vulnerability.ipynb
│   ├── 03_network_accessibility.ipynb
│   ├── 04_gap_analysis.ipynb
│   ├── 05_zone_clustering.ipynb
│   └── 06_maps.ipynb
├── src/
│   └── transit_gaps/
│       ├── __init__.py
│       ├── gtfs.py            # GTFS loading, validation, frequency computation
│       ├── network.py         # OSMnx graph building, pandana network setup
│       ├── accessibility.py   # Gravity-model accessibility scoring
│       ├── vulnerability.py   # ACS composite index
│       └── viz.py             # Map styling, small multiples layout
├── environment.yml
├── setup.py
└── README.md
```

---

## Environment Setup

### 1. Create the conda environment

```bash
conda env create -f environment.yml
conda activate snotrac-gaps
pip install -e .
```

### 2. environment.yml

```yaml
name: snotrac-gaps
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - geopandas
  - pandana
  - osmnx
  - pandas
  - numpy
  - matplotlib
  - contextily
  - cenpy
  - pyarrow
  - jupyter
  - ipykernel
  - pip
  - pip:
    - gtfs-kit
    - mapclassify
```

**Dependency notes:**
- `gtfs-kit` via pip — handles GTFS feed validation, stop_times aggregation, calendar service filtering
- `pandana` — fast network accessibility computation; pin first if conda solve conflicts with osmnx
- `cenpy` — Census API wrapper for ACS pulls; requires a free Census API key
- `mapclassify` — Jenks/Fisher-Jenks classifiers for defensible choropleth breaks
- `contextily` — basemap tiles for final static maps

**If pandana/osmnx conflict on solve:**
```bash
conda install pandana --no-update-deps
conda install osmnx
```

### 3. setup.py

```python
from setuptools import setup, find_packages

setup(
    name="transit_gaps",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
)
```

### 4. Census API key

Register at https://api.census.gov/data/key_signup.html (free, instant).

```bash
export CENSUS_API_KEY="your_key_here"
# or add to .env and load with python-dotenv
```

---

## Data Sources

### Community Transit GTFS
- **URL:** https://www.communitytransit.org/docs/default-source/open-data/google_transit.zip
- **Download to:** `data/raw/gtfs/`
- **Notes:** Feed covers fixed-route service. Check feed_info.txt for validity dates. GTFS-Flex deviated routes may be absent — document this as a finding (specialized services are invisible in the public feed).

### ACS 5-Year Estimates (Block Group Level)
- **Vintage:** 2019–2023 (most recent available)
- **Geography:** Snohomish County block groups (FIPS: 53061)
- **Variables to pull:**

| Variable | ACS Table | Description |
|---|---|---|
| Total population | B01003_001E | Denominator |
| Pop 65+ | B01001 (sum age cols) | Elderly |
| Disability | B18101 | Civilian noninstitutionalized with disability |
| Zero-vehicle HH | B08201_002E | Households with no vehicle |
| Below 200% poverty | B17026 | Income-to-poverty ratio |

### OSM Road Network
- Pulled programmatically via `osmnx.graph_from_place("Snohomish County, Washington")`
- Cached to `data/raw/osm/` — do this once, it's slow
- Use `network_type="walk"` for pedestrian access modeling to stops

---

## Methodology

### Step 1 — GTFS Frequency Computation (`src/transit_gaps/gtfs.py`)

For each stop, compute `F_j` = trips per stop per day, filtered to a representative weekday using the GTFS calendar.

```python
# Pseudocode — flesh out in gtfs.py
feed = gk.read_feed("data/raw/gtfs/", dist_units="mi")
# Filter to typical weekday service
# Explode stop_times to get per-stop trip counts
# F_j = count of trip_ids calling at stop_j on reference day
# Optionally split: peak (6-9am, 3-7pm) vs. off-peak
```

**Output:** `data/processed/stop_frequencies.parquet` — stop_id, geometry, trips_per_day, trips_peak, trips_offpeak

### Step 2 — ACS Vulnerability Index (`src/transit_gaps/vulnerability.py`)

Composite index combining four normalized sub-indicators into a single 0–1 score per block group.

```python
# Per block group:
# pct_elderly   = pop_65_plus / total_pop
# pct_disabled  = disabled / total_pop
# pct_novehicle = zero_vehicle_hh / total_hh
# pct_lowincome = below_200pct_poverty / total_pop

# Normalize each to 0-1 across county
# Composite = equal-weight mean (adjustable)
# vulnerability_index = (norm_elderly + norm_disabled + norm_novehicle + norm_lowincome) / 4
```

**Output:** `data/processed/vulnerability_index.gpkg` — block group geometries + vulnerability_index

### Step 3 — Network Accessibility (`src/transit_gaps/network.py` + `accessibility.py`)

Build pandana network from OSM graph, then compute gravity-model accessibility score for each block group centroid.

```python
# Build pandana network
import pandana as pdna
import osmnx as ox

G = ox.graph_from_place("Snohomish County, Washington", network_type="walk")
nodes, edges = ox.graph_to_gdfs(G)
network = pdna.Network(
    nodes["x"], nodes["y"],
    edges["u"], edges["v"], edges[["length"]]
)
```

**Accessibility formula:**

```
A_i = Σ_j [ F_j * exp(-β * d_ij) ]
```

Where:
- `A_i` = accessibility score at block group centroid `i`
- `F_j` = trips/day at stop `j`
- `d_ij` = network distance in miles from `i` to `j`
- `β` = decay parameter (recommend β=4.0, giving ~50% weight decay at 0.25mi — calibrated for elderly/disabled walking tolerance)
- Search radius cap: 1.5 miles (beyond this, contribution is negligible and computation is expensive)

```python
# Preload stop locations onto network
network.precompute(1.5 * 1609)  # convert miles to meters

# For each stop, set frequency as POI variable
network.set_pois("stops", max_dist=1.5*1609, max_items=20,
                 x_col=stops_gdf["geometry"].x,
                 y_col=stops_gdf["geometry"].y)

# Query accessibility per node, then aggregate to block group centroids
```

**Output:** `data/processed/accessibility_scores.parquet` — block_group_id, accessibility_score (raw + normalized)

### Step 4 — Gap Surface (`src/transit_gaps/accessibility.py`)

```python
# Join vulnerability index and accessibility score on block group ID
# gap_score = vulnerability_index * (1 - norm_accessibility)
# High gap_score = high need, low service = priority zone
```

**Output:** `data/processed/gap_surface.gpkg`

### Step 5 — Zone Clustering (`notebooks/05_zone_clustering.ipynb`)

Derive zones from the gap surface using spatial clustering — do not use administrative boundaries.

```python
# Compute gap_score per block group
# Use HDBSCAN or k-means (k=5 starting point) on:
#   [gap_score, centroid_x, centroid_y]
# Dissolve contiguous block groups of same cluster into zone polygons
# Label zones by dominant character (high-coverage urban, suburban fringe, etc.)
# Let data determine labels — don't pre-assign
```

Expected zone count: 4–6. If k-means, evaluate silhouette scores for k=3 through k=7.

**Output:** `data/processed/zones.gpkg` — zone polygons with zone_id, zone_label, mean_gap_score

### Step 6 — Maps (`src/transit_gaps/viz.py` + `notebooks/06_maps.ipynb`)

Small multiples layout — one column per zone, three rows:
1. Vulnerability composite choropleth
2. Accessibility surface (frequency-weighted)
3. Gap overlay

**Design rules:**
- Consistent color scale across all zone panels (normalize to county-wide min/max, not per-panel)
- Vulnerability: sequential yellow→red (ColorBrewer YlOrRd)
- Accessibility: sequential blue (higher = better served)
- Gap: diverging, with high-gap in red
- Route lines overlaid on accessibility panel in light gray
- Contextily basemap: `CartoDB.Positron` or `Stamen.TonerLite`
- County inset map showing zone extents in each panel corner

```python
import matplotlib.pyplot as plt
import contextily as ctx
import mapclassify

fig, axes = plt.subplots(nrows=3, ncols=n_zones, figsize=(5*n_zones, 14))
# Loop zones, plot each panel, enforce shared normalization
# fig.savefig("data/outputs/maps/snohomish_transit_gaps.png", dpi=200, bbox_inches="tight")
```

---

## Key Methodological Decisions to Document

These should be written up explicitly — they'll matter if Snotrac or a grant reviewer asks:

1. **Why frequency-weighted, not raw stop count** — a stop served twice a day is not equivalent to one served every 15 minutes for someone who needs to reach a medical appointment
2. **Why network distance, not Euclidean** — terrain and road network in eastern Snohomish makes straight-line buffers systematically overstate rural coverage
3. **Why β=4.0** — cite pedestrian accessibility literature (e.g., Curl et al. 2011 on walking distance decay for older adults); adjust if local data suggests otherwise
4. **GTFS-Flex absence** — specialized services (Homage shuttles, volunteer driver programs) are likely absent from the public GTFS feed; this means the gap analysis is conservative — actual coverage may be slightly higher in some areas, but these services are also the least discoverable, which is a gap of a different kind
5. **Equal-weight vulnerability composite** — defensible starting point; sensitivity test with different weights is worth doing in v2

---

## Known Limitations & v2 Extensions

| Limitation | v2 Fix |
|---|---|
| Specialized/GTFS-Flex services absent | Digitize from Snotrac provider inventory |
| Static weekday snapshot | Add weekend service panel |
| Equal-weight vulnerability composite | Sensitivity analysis, potentially PCA-derived weights |
| No temporal dimension | Service frequency by time of day |
| Walking network only | Add driving network for rural zero-transit zones |

---

## Claude Code Workflow Notes

- Build and test each `src/transit_gaps/` module before wiring notebooks
- Store all intermediate outputs as `.parquet` (tabular) or `.gpkg` (spatial) — not CSV or shapefile
- The OSM network download is the longest single operation (~5–10 min for county scale) — cache aggressively, don't re-pull
- Run the pandana precompute step once and checkpoint it
- Keep notebooks thin — logic lives in `src/`, notebooks are for orchestration and QA visualization

---

## Reference Links

- Community Transit GTFS: https://www.communitytransit.org/opendata
- Census ACS API: https://www.census.gov/data/developers/data-sets/acs-5year.html
- Pandana docs: https://udst.github.io/pandana/
- OSMnx docs: https://osmnx.readthedocs.io/
- gtfs-kit docs: https://mrcagney.github.io/gtfs_kit_docs/
- GTFS-Flex spec: https://gtfs.org/extensions/flex/
- Snotrac: https://www.gosnotrac.org
- Find a Ride (KC/Snotrac One-Call-One-Click): https://www.kcmobility.org/ococ
