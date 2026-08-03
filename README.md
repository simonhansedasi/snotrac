# WA Transit Gap Analysis

**Frequency-weighted transit accessibility and vulnerability mapping for Washington State counties**

Live at **[snotrac.uniquefier.us](https://snotrac.uniquefier.us)** — interactive choropleth map with four analytical lenses (vulnerability, accessibility, gap score, priority) and click-to-inspect block group cards.

Originally built as a volunteer data contribution to [Gosnotrac](https://www.gosnotrac.org), a community transit advocacy organization in Snohomish County.

---

## Counties

| County | Block Groups | Transit Feed | Top Priority Areas |
|---|---|---|---|
| Snohomish | 575 | Community Transit GTFS | Everett, Stanwood, Darrington |
| King | 1,545 | King County Metro GTFS | Auburn, Kent, Federal Way |

---

## Repository Structure

```
snotrac/
├── src/transit_gaps/
│   ├── gtfs.py                     # GTFS loading and frequency computation
│   ├── network.py                  # OSMnx/pandana network build and cache
│   ├── accessibility.py            # Gravity-model scoring and gap formula
│   ├── vulnerability.py            # ACS pull and composite index
│   └── viz.py                      # Map generation
├── notebooks/
│   ├── 01_gtfs_ingestion.ipynb     # Download GTFS, compute stop frequencies
│   ├── 02_acs_vulnerability.ipynb  # Pull ACS data, build vulnerability index
│   ├── 03_network_accessibility.ipynb
│   ├── 04_gap_analysis.ipynb
│   ├── 05_zone_clustering.ipynb
│   ├── 06_maps.ipynb
│   └── 07_brief.ipynb              # Geocode priority BGs → policy brief
├── data/                           # Snohomish County data
├── data_king/                      # King County data
├── web/
│   ├── index.html                  # Landing page
│   ├── snohomish/                  # Snohomish County map + data.geojson
│   └── king/                       # King County map + data.geojson
├── run_king_pipeline.py            # Full pipeline runner for King County
├── generate_web_data.py            # Export gap_surface → web GeoJSON (any county)
├── deploy_do.sh                    # rsync web/ to DO droplet + reload nginx
├── environment.yml
└── setup.py
```

---

## Running the Pipeline

### Snohomish County (notebooks)

Requires `CENSUS_API_KEY` in `.env`. Run notebooks 01–07 in order using the `snotrac-gaps` conda env:

```bash
conda activate snotrac-gaps   # or: miniforge3/envs/snotrac-gaps/bin/python
jupyter notebook
```

### King County (script)

```bash
/home/simonhans/miniforge3/envs/snotrac-gaps/bin/python run_king_pipeline.py
```

Resume from a specific step if earlier steps already ran:

```bash
python run_king_pipeline.py --from-step 3 --skip-network-save
```

`--skip-network-save` is required for King County — pandana crashes saving the HDF5 for a 408k-node network. The in-memory network is used directly for accessibility computation.

### Adding a new county

1. Download GTFS feed and extract to `data_<county>/raw/gtfs/`
2. Add county config to `COUNTY_CONFIGS` in `generate_web_data.py`
3. Copy and adapt `run_king_pipeline.py` with the correct FIPS codes and place name
4. Run pipeline → `generate_web_data.py <county>` → `deploy_do.sh`

---

## Generating Web Data + Deploying

```bash
# Re-export GeoJSON for one or both counties
/home/simonhans/miniforge3/envs/snotrac-gaps/bin/python generate_web_data.py snohomish
/home/simonhans/miniforge3/envs/snotrac-gaps/bin/python generate_web_data.py king

# Deploy web/ to snotrac.uniquefier.us
./deploy_do.sh
```

---

## Methodology

### Vulnerability Index

Four ACS 5-year 2023 indicators at block group level, normalized county-wide to [0,1] and averaged with equal weights:

| Indicator | ACS Variable |
|---|---|
| % elderly (65+) | B01001 age cols |
| Unemployment rate | B23025 |
| Zero-vehicle households | B25044 |
| Below poverty | C17002 |

### Accessibility Score

Gravity model via pandana on the OSM pedestrian network:

```
A_i = Σ_j [ F_j × exp(−β × d_ij) ]
```

- `F_j` = trips/day at stop j (GTFS representative weekday)
- `d_ij` = walk distance in miles from block group centroid i to stop j
- `β = 4.0` (50% decay at 0.25 mi)
- Search radius: 1.5 mi (Snohomish), 0.75 mi (King — reduced for memory)

### Gap Score

```
gap_score = vulnerability_index × (1 − log_accessibility)
```

Log-normalized accessibility is used because the raw distribution is extremely right-skewed.

### Priority Score

Combined rank of normalized gap score and equity distance below the y=x service-equity line:

```
equity_distance = (vuln_n − acc_n) / √2   (positive = underserved)
priority = mean(gap_score_n, equity_dist_n)
```

---

## Known Limitations

- No GTFS-Flex / specialized services (Homage, volunteer drivers)
- Weekday snapshot only — no weekend or evening analysis
- Disability excluded from vulnerability index (B18101 not available at block group level)
- King County uses 0.75 mi search radius vs 1.5 mi for Snohomish due to network size

---

## Deployment

- **URL:** [snotrac.uniquefier.us](https://snotrac.uniquefier.us)
- **Host:** DO droplet `68.183.130.60`, nginx static file serve from `/var/www/snotrac/`
- **TLS:** Cloudflare Full (Strict), wildcard cert `*.uniquefier.us`
- **DNS:** Cloudflare A record `snotrac.uniquefier.us → 68.183.130.60`
