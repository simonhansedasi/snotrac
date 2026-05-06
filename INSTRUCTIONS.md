# Setup and Run Instructions

Practical guide including known gotchas from initial setup.

---

## Prerequisites

- Linux or macOS
- ~8 GB free disk space (OSM network cache is large)
- A free Census API key — register at https://api.census.gov/data/key_signup.html

---

## 1. Install Miniforge

**Do not use Anaconda/conda for this project.** The old conda solver cannot resolve the geospatial dependency tree and will freeze your machine. Use Miniforge instead, which ships with mamba and uses conda-forge by default.

```bash
wget "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
bash Miniforge3-Linux-x86_64.sh
```

Follow the installer prompts. Open a **new terminal** after installation completes.

If you have an existing Anaconda installation, run miniforge directly by path rather than via `conda`:

```bash
~/miniforge3/bin/mamba env create -f environment.yml
```

---

## 2. Create the Environment

```bash
~/miniforge3/bin/mamba env create -f environment.yml
```

This installs Python 3.11 plus all geospatial dependencies. Takes 5–10 minutes.

---

## 3. Add the Environment as a Jupyter Kernel

Activate the environment and register it:

```bash
/home/$USER/miniforge3/envs/snotrac-gaps/bin/python -m ipykernel install --user --name snotrac-gaps --display-name "snotrac-gaps"
```

> **Note:** If you have two conda installations (Anaconda + Miniforge), `conda activate snotrac-gaps` may fail with "Run conda init first." Use the full path above instead of activating.

---

## 4. Install the Package in Editable Mode

From the repo root:

```bash
/home/$USER/miniforge3/envs/snotrac-gaps/bin/pip install -e .
```

---

## 5. Configure the Census API Key

Create a `.env` file in the repo root:

```bash
echo 'CENSUS_API_KEY=your_key_here' > .env
```

Replace `your_key_here` with your actual key. The `.env` file is gitignored.

> **IPv6 gotcha:** The Census API (`api.census.gov`) may be unreachable from Python even when `curl` works fine. If you get `[Errno 101] Network is unreachable`, run this cell before calling `fetch_acs()`:
>
> ```python
> import socket
> _orig = socket.getaddrinfo
> def _ipv4(host, port, family=0, type=0, proto=0, flags=0):
>     return _orig(host, port, socket.AF_INET, type, proto, flags)
> socket.getaddrinfo = _ipv4
> ```

---

## 6. Open JupyterLab and Select the Kernel

```bash
~/miniforge3/bin/jupyter lab
```

In each notebook, select the `snotrac-gaps` kernel (Kernel → Change Kernel).

---

## 7. Run the Notebooks in Order

Run all cells in each notebook top-to-bottom before moving to the next.

### Notebook 01 — GTFS Ingestion

Downloads the Community Transit GTFS feed automatically on first run. If the download URL returns 404, the feed URL may have changed — check https://www.communitytransit.org/open-data for the current link and update `GTFS_URL` in the notebook.

### Notebook 02 — ACS Vulnerability

Pulls block group data from the Census API. Takes ~2–5 seconds.

**Known issue:** Several ACS variables are not available at block group level and return null — this is expected. The following variables are confirmed unavailable at BG level and have been replaced:
- B18101 (disability) → not available
- B08201 (vehicles) → not available  
- B17026 (poverty ratio) → not available

The code uses confirmed BG-level alternatives (C17002, B25044, B23025).

### Notebook 03 — Network Accessibility

Downloads the full Snohomish County pedestrian street network from OpenStreetMap on first run. **This takes 5–10 minutes and requires internet.** The result is cached to `data/raw/osm/snohomish_walk.graphml` — subsequent runs load from cache in seconds.

You will see a PROJ warning (`Open of .../share/proj failed`) — this is harmless, the computation proceeds correctly.

### Notebook 04 — Gap Analysis

Computes gap surface, equity distance, and priority rankings. Also generates three plots saved to `data/outputs/`:
- `vulnerability_accessibility.png` — scatter of all 575 BGs with equity diagonal (X = vulnerability, Y = accessibility; underserved fall below the line)
- `equity_spines.png` — top 10 underserved and over-served BGs with perpendicular spines to the equity line
- `priority_targets.png` — 2D priority scatter (gap score vs equity distance) with top 15 ranked

### Notebooks 05, 06

These run quickly from cached data. No external downloads required.

### Notebook 07 — Brief

Requires internet (Nominatim reverse geocoding + Census TIGER download on first run; both are cached after).

Downloads TIGER place and county subdivision boundaries, spatially joins block group centroids to named places, then reverse-geocodes the top 15 priority block groups via Nominatim to get sub-city neighborhood names. Falls back to `"City — Tract XXXX, BG N"` for areas with no OSM neighborhood polygon.

Writes `data/outputs/policy_brief.md` — a one-page non-technical brief with real data values, the scatter plot, and a named priority table suitable for Snotrac or Community Transit outreach.

**Nominatim rate limit:** 1 request/second (enforced by `time.sleep(1.1)`). Do not remove this sleep.

---

## 8. Output Files

After running all notebooks:

```
data/processed/
  stop_frequencies.parquet       # 1,680 stops with trip counts
  vulnerability_index.gpkg       # 575 block groups with vulnerability scores
  accessibility_scores.parquet   # accessibility + log_accessibility per BG
  gap_surface.gpkg               # full gap analysis with zone assignments
  zones.gpkg                     # 4 dissolved zone polygons with labels

data/outputs/
  maps/snohomish_transit_gaps.png        # final 3-panel county map
  snohomish_transit_gap_summary.md       # non-technical one-page summary
  vulnerability_accessibility.png        # equity scatter (all BGs)
  equity_spines.png                      # top 10 underserved/over-served with spines
  priority_targets.png                   # 2D priority ranking scatter
  policy_brief.md                        # one-page brief with named neighborhoods
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `mamba: command not found` | Use full path: `~/miniforge3/bin/mamba` |
| `conda activate` fails with "run conda init" | Use full path to Python/pip instead of activating |
| Census API `Network is unreachable` | Apply the IPv6 socket patch (see step 5) |
| `TigerConnection` KeyError | Pass a dataset name: `TigerConnection('tigerWMS_ACS2023')` |
| ACS variables all return null/zero | Variable not available at BG level — see notebook 02 notes |
| `assess_quality` or `validate` not found on feed | gtfs-kit v12+ uses `feed.assess_quality()` not `gk.validate()` |
| Basemap tiles missing / blank | contextily requires internet; run with network access |
| PROJ warning in notebook 05 | Harmless — ignore |
| Nominatim returns only city name (no neighbourhood) | Normal for rural/exurban BGs — falls back to tract/BG label automatically |
| `tabulate` not found in notebook 07 | `pip install tabulate` in the snotrac-gaps environment |
