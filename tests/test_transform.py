"""Tests for transform.py."""

import pandas as pd
from pathlib import Path
from datetime import date
from src.ingestion.transform import LAGS, MIN_LAG, build_clean, build_features

LOADED = pd.Timestamp("2026-10-25 12:00", tz="UTC")
PARENTFOLDER = Path(__file__).parent
DATADIR = Path(f'{PARENTFOLDER}/data/swissgrid-2025.csv')


def real_rows():
    df = pd.read_csv(DATADIR, dtype=str, delimiter=";", encoding="utf-8") 
    return [("2025", LOADED, rec) for rec in df.to_dict("records")]


def test_2025_file_grid_and_dst_days():
    """Real 2025 file: Zurich local time converts to a full UTC grid with no gaps
    or duplicates, and the DST days have 92 (spring) and 100 (autumn) rows."""
    clean = build_clean(real_rows())
    assert len(clean) == 35040  # 365 days x 96, the DST days cancel out
    assert clean.index.is_unique and clean.index.is_monotonic_increasing
    per_day = pd.Series(clean.index.tz_convert("Europe/Zurich").date).value_counts()
    assert per_day[date(2025, 3, 30)] == 92
    assert per_day[date(2025, 10, 26)] == 100


def test_features_use_earlier_values_only():
    """Real 2025 file: each lag feature equals the value from exactly that many
    steps earlier, the target is the unshifted value, and no raw inputs remain."""
    clean = build_clean(real_rows())
    feats = build_features(clean)
    t = pd.Timestamp("2025-06-15 12:00", tz="UTC")
    for lag in LAGS:
        earlier = t - pd.Timedelta(minutes=15 * lag)
        assert feats.loc[t, f"imbalance_lag{lag}"] == clean.loc[earlier, "imbalance"]
    assert feats.loc[t, "target"] == clean.loc[t, "imbalance"]
    assert "imbalance" not in feats.columns and "price" not in feats.columns



def utc_rows(key, grid_utc, value, loaded_at=LOADED):
    """Fake 2026/daily-style rows: UTC label."""
    return [(key, loaded_at,
            {
                "Date Time [UTC]": t.strftime("%d.%m.%Y %H:%M"),
                "Total System Imbalance": str(value),
                "AE-Preis": "9.0",
            },)
        for t in grid_utc]


def test_yearly_wins_over_daily_and_newest_daily_wins():
    """Same timestamps from three sources: the corrected yearly file beats daily
    snapshots, and among daily snapshots the newest one wins."""
    grid = pd.date_range("2026-01-01", periods=10, freq="15min", tz="UTC")
    old, new = LOADED - pd.Timedelta(days=1), LOADED
    rows = (
        utc_rows("2026", grid, 1, LOADED)                 # corrected yearly
        + utc_rows("daily-2026-10-24", grid, 2, old)       # older snapshot
        + utc_rows("daily-2026-10-25", grid, 3, new)       # newer snapshot
    )
    
    assert (build_clean(rows)["imbalance"] == 1).all()
    
    daily_only = utc_rows("daily-2026-10-24", grid, 2, old) + utc_rows("daily-2026-10-25", grid, 3, new)
    assert (build_clean(daily_only)["imbalance"] == 3).all()


def test_2024_without_single_price_gives_nan_price():
    """The 2024 file has only long/short prices and no single price, so the
    price column must be NaN instead of raising an error."""
    grid = pd.date_range("2024-11-01", periods=4, freq="15min", tz="UTC")
    rows = [("2024", LOADED, {
            "Date Time": t,
            "Total System Imbalance (Positiv = long / Negativ = short)": "5",
            "AE-Preis long": "1", "AE-Preis short": "2",
        })
        for t in grid.tz_convert("Europe/Zurich").strftime("%d.%m.%Y %H:%M")]
    
    assert build_clean(rows)["price"].isna().all()


def test_lag_constants_respect_issue_time():
    """Every configured lag is at least MIN_LAG (100 steps), the distance from the
    last known value (22:45) to the last forecast step (23:45 on D+1)."""
    assert all(lag >= MIN_LAG for lag in LAGS)


def test_features_use_only_values_known_at_issue_time():
    """For all 96 steps of D+1, the source value of each lag was published before
    the issue time (23:20 UTC on D, last known value 22:45)."""
    # Issue time T = 23:20 UTC on day D, last known value 22:45 on D.
    clean = build_clean(utc_rows("2026", pd.date_range("2026-01-01", periods=96 * 20, freq="15min", tz="UTC"), 1))
    day_d = pd.Timestamp("2026-01-15", tz="UTC")
    last_known = day_d + pd.Timedelta(hours=22, minutes=45)
    targets = pd.date_range(day_d + pd.Timedelta(days=1), periods=96, freq="15min")
    
    for lag in LAGS:
        source_times = targets - pd.Timedelta(minutes=15 * lag)
        assert (source_times <= last_known).all(), f"lag {lag} reaches past issue time"