# Snotrac Transit Gap Analysis

**Frequency-weighted transit accessibility and vulnerability mapping for Snohomish County, WA**

Built as a volunteer data contribution to [Snotrac](https://www.gosnotrac.org), a community transit advocacy organization in Snohomish County.

---

## What This Does

Identifies census block groups where residents who most need transit (elderly, carless, unemployed, low-income) have the least access to it. Produces a county-wide map showing vulnerability, accessibility, and gap score side-by-side at block group resolution.

**Final outputs:** county map, equity scatter, equity spine plot, 2D priority ranking, and a one-page policy brief with named neighborhoods (`data/outputs/policy_brief.md`).

---

## Repository Structure

```
snotrac/
├── data/
│   ├── raw/
│   │   ├── gtfs/                   # Community Transit GTFS feed (auto-downloaded)
│   │   └── osm/                    # OSMnx walk network cache (auto-populated)
│   ├── processed/                  # Intermediate parquet/gpkg files
│   └── outputs/
│       ├── maps/                   # Final map PNGs
│       └── snohomish_transit_gap_summary.md   # Non-technical one-pager
├── notebooks/
│   ├── 01_gtfs_ingestion.ipynb     # Download GTFS, compute stop frequencies
│   ├── 02_acs_vulnerability.ipynb  # Pull ACS data, build vulnerability index
│   ├── 03_network_accessibility.ipynb  # Build OSM network, compute accessibility
│   ├── 04_gap_analysis.ipynb       # Compute gap surface, QA plots
│   ├── 05_zone_clustering.ipynb    # K-means zone clustering, label zones
│   ├── 06_maps.ipynb               # Generate final county map
│   └── 07_brief.ipynb              # Geocode priority BGs → named places, write policy brief
├── src/transit_gaps/
│   ├── gtfs.py                     # GTFS loading and frequency computation
│   ├── network.py                  # OSMnx/pandana network build and cache
│   ├── accessibility.py            # Gravity-model scoring and gap formula
│   ├── vulnerability.py            # ACS pull and composite index
│   └── viz.py                      # Map generation (plot_county_map)
├── environment.yml
├── setup.py
├── README.md
└── INSTRUCTIONS.md
```

---

## Notebook Run Order

Run in sequence — each notebook reads the outputs of the previous one.

| # | Notebook | Key Output |
|---|---|---|
| 01 | `01_gtfs_ingestion` | `stop_frequencies.parquet` (1,680 stops) |
| 02 | `02_acs_vulnerability` | `vulnerability_index.gpkg` (575 block groups) |
| 03 | `03_network_accessibility` | `accessibility_scores.parquet` |
| 04 | `04_gap_analysis` | `gap_surface.gpkg` |
| 05 | `05_zone_clustering` | `zones.gpkg` (4 labeled zones) |
| 06 | `06_maps` | `snohomish_transit_gaps.png` |
| 07 | `07_brief` | `policy_brief.md` — named priority neighborhoods (Nominatim reverse geocode + TIGER fallback) + one-page non-technical brief |

**Slow steps:** notebook 03 downloads the full Snohomish County OSM walk network (~5–10 min, cached after first run).

---

## Methodology

### Vulnerability Index

Four ACS 5-year 2023 indicators at block group level, each normalized county-wide to [0,1] and averaged with equal weights:

| Indicator | ACS Variable | Notes |
|---|---|---|
| % elderly (65+) | B01001 age cols | Sum of 12 age-group columns |
| Unemployment rate | B23025 | Unemployed / in labor force |
| Zero-vehicle households | B25044 | Renter + owner no-vehicle / total occupied units |
| Below poverty | C17002 | Under 1.0 income-to-poverty ratio / universe |

> **Note on variable availability:** B18101 (disability), B08201 (vehicles), and B17026 (poverty ratio) are not available at block group level in the 2023 5-year ACS — they return null. The above variables are confirmed available at block group level.

### Accessibility Score

Gravity model computed via pandana on the OSM pedestrian network:

```
A_i = Σ_j [ F_j × exp(−β × d_ij) ]
```

- `F_j` = trips/day at stop j (GTFS representative weekday)
- `d_ij` = network walk distance in miles from block group centroid i to stop j
- `β = 4.0` (50% decay at 0.25 mi — calibrated for elderly/disabled walking tolerance)
- Search radius: 1.5 miles

### Gap Score

```
gap_score = vulnerability_index × (1 − log_accessibility)
```

`log_accessibility = log(1 + raw_score) / log(1 + max_score)` — log-normalized rather than linearly normalized because the raw accessibility distribution is extremely right-skewed. Linear normalization collapses ~95% of block groups to near-zero, making the gap formula reduce to just the vulnerability index.

### Equity Analysis (Notebook 04)

Both axes are min-max normalized to [0,1] for plotting (X = vulnerability, Y = accessibility). The **equity line** is the diagonal y = x — points below it are underserved (high need, low service).

**Equity distance** — signed perpendicular distance from the equity line:

```
equity_distance = (vuln_n − acc_n) / √2
```

Positive = below the line = underserved. Negative = above the line = over-served.

**Combined priority score** — for campaign targeting, block groups are ranked by the mean of two normalized metrics: `gap_score` (absolute unmet need) and `equity_distance` (structural misalignment). These can disagree — a block group with high absolute need may sit closer to the equity line than one with moderate need but disproportionately low service. The combined score captures both dimensions.

### Zone Clustering

K-means on `[gap_score, centroid_x, centroid_y]`, k=4 selected by silhouette score (best: 0.40 at k=4). Zones labeled by rank on mean gap score, accessibility, and vulnerability — not by fixed thresholds, which fail when absolute values are below the threshold.

---

## Key Data Sources

| Source | Detail |
|---|---|
| Community Transit GTFS | March 2026 feed — 40 routes, 1,680 stops, 9,993 trips |
| ACS 5-Year 2023 | Snohomish County block groups (FIPS 53061) via Census API |
| OSM pedestrian network | Pulled via osmnx, cached to `data/raw/osm/snohomish_walk.graphml` |
| TIGER/Web block group geometries | Via cenpy.tiger `tigerWMS_ACS2023`, layer `Census Block Groups` |

---

## Known Limitations

- **No GTFS-Flex / specialized services** — Homage Senior Services shuttles, volunteer driver programs, and deviated route services are absent from the public GTFS feed. The gap analysis is conservative; actual coverage in some areas may be slightly higher.
- **Weekday snapshot only** — service frequency is computed from a representative weekday. No weekend or evening analysis.
- **Disability dropped from vulnerability index** — B18101 (disability) is not available at block group level from the Census API. Unemployment is used as a partial proxy for economic vulnerability.
- **Static analysis** — no temporal trend, no before/after comparison.

---

## Contact

Suleiny — suleiny@gosnotrac.org — [gosnotrac.org](https://www.gosnotrac.org)
