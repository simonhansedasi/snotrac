"""
GTFS loading, validation, and frequency computation.

Outputs: data/processed/stop_frequencies.parquet
  stop_id, geometry (Point, EPSG:4326), trips_per_day, trips_peak, trips_offpeak
"""

from pathlib import Path
import pandas as pd
import geopandas as gpd
import gtfs_kit as gk

GTFS_PATH = Path("data/raw/gtfs")
OUT_PATH = Path("data/processed/stop_frequencies.parquet")

PEAK_HOURS = [(6, 9), (15, 19)]  # 6-9am, 3-7pm

# Pick a representative service day. Community Transit typically has:
#   service_id patterns like "Weekday", "Saturday", "Sunday"
# We select the service_id with the most trips on a non-holiday weekday.
WEEKDAY_DOW = {0, 1, 2, 3, 4}  # Mon–Fri


def load_feed(gtfs_dir: str | Path = GTFS_PATH) -> gk.Feed:
    feed = gk.read_feed(str(gtfs_dir), dist_units="mi")
    return feed


def _select_representative_service(feed: gk.Feed) -> str:
    """Return the service_id that covers the most Mon-Fri trips."""
    cal = feed.calendar
    if cal is None or cal.empty:
        # Fall back to calendar_dates
        raise ValueError(
            "No calendar.txt found in feed; manual service_id selection required."
        )
    weekday_mask = (
        (cal["monday"] == 1)
        | (cal["tuesday"] == 1)
        | (cal["wednesday"] == 1)
        | (cal["thursday"] == 1)
        | (cal["friday"] == 1)
    )
    weekday_services = cal.loc[weekday_mask, "service_id"].tolist()
    # Count trips per service_id
    trips = feed.trips[feed.trips["service_id"].isin(weekday_services)]
    counts = trips["service_id"].value_counts()
    return counts.index[0]


def _is_peak(departure_time: str) -> bool:
    """Return True if HH:MM:SS string falls in a peak window."""
    parts = departure_time.split(":")
    hour = int(parts[0]) % 24  # GTFS allows >24 for overnight
    for start, end in PEAK_HOURS:
        if start <= hour < end:
            return True
    return False


def compute_stop_frequencies(
    feed: gk.Feed = None,
    gtfs_dir: str | Path = GTFS_PATH,
    out_path: str | Path = OUT_PATH,
) -> gpd.GeoDataFrame:
    """
    Compute per-stop trip counts for a representative weekday.

    Returns a GeoDataFrame with columns:
        stop_id, geometry, trips_per_day, trips_peak, trips_offpeak
    """
    if feed is None:
        feed = load_feed(gtfs_dir)

    service_id = _select_representative_service(feed)
    print(f"Representative service_id: {service_id}")

    # Trips active on reference service day
    active_trips = feed.trips[feed.trips["service_id"] == service_id]["trip_id"]

    # Stop times for those trips
    st = feed.stop_times[feed.stop_times["trip_id"].isin(active_trips)].copy()

    # Count total trips per stop
    trips_per_day = st.groupby("stop_id")["trip_id"].nunique().rename("trips_per_day")

    # Peak
    st["is_peak"] = st["departure_time"].apply(_is_peak)
    peak_st = st[st["is_peak"]]
    trips_peak = (
        peak_st.groupby("stop_id")["trip_id"].nunique().rename("trips_peak")
    )

    offpeak_st = st[~st["is_peak"]]
    trips_offpeak = (
        offpeak_st.groupby("stop_id")["trip_id"].nunique().rename("trips_offpeak")
    )

    freq_df = (
        pd.concat([trips_per_day, trips_peak, trips_offpeak], axis=1)
        .fillna(0)
        .astype(int)
        .reset_index()
    )

    # Join stop geometries
    stops = feed.stops[["stop_id", "stop_lat", "stop_lon"]].copy()
    freq_gdf = stops.merge(freq_df, on="stop_id", how="inner")
    freq_gdf = gpd.GeoDataFrame(
        freq_gdf,
        geometry=gpd.points_from_xy(freq_gdf["stop_lon"], freq_gdf["stop_lat"]),
        crs="EPSG:4326",
    ).drop(columns=["stop_lat", "stop_lon"])

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    freq_gdf.to_parquet(out_path)
    print(f"Saved stop frequencies → {out_path}  ({len(freq_gdf)} stops)")
    return freq_gdf
