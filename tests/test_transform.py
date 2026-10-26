"""Tests for transform.py. Change the import below to your package name."""

import pandas as pd

from src.ingestion.transform_features import LAGS, MIN_LAG, build_clean, build_features

LOADED = pd.Timestamp("2026-10-25 12:00", tz="UTC")


def local_rows(key, grid_utc, loaded_at=LOADED):
    """Fake 2024/2025-style rows: Zurich local time, no [UTC] label."""
    local = grid_utc.tz_convert("Europe/Zurich").strftime("%d.%m.%Y %H:%M")
    return [(key, loaded_at,
            {
                "Date Time": t,
                "Total System Imbalance (Positiv = long / Negativ = short)": str(i),
                "AE-Preis per 2026": "10.5",
            },)
            for i, t in enumerate(local)]


def utc_rows(key, grid_utc, value, loaded_at=LOADED):
    """Fake 2026/daily-style rows: UTC label."""
    return [(key, loaded_at,
            {
                "Date Time [UTC]": t.strftime("%d.%m.%Y %H:%M"),
                "Total System Imbalance": str(value),
                "AE-Preis": "9.0",
            },)
        for t in grid_utc]


def test_local_time_round_trips_through_dst():
    # Covers the spring and autumn DST switches of 2025.
    grid = pd.date_range("2025-03-29 12:00", "2025-03-31 12:00", freq="15min", tz="UTC")
    grid = grid.append(pd.date_range("2025-10-25 12:00", "2025-10-27 12:00", freq="15min", tz="UTC"))
    clean = build_clean(local_rows("2025", grid))
    
    # Every original UTC timestamp comes back, and the 15-min grid has no gaps.
    assert grid.isin(clean.index).all()
    assert clean.index.is_monotonic_increasing and clean.index.is_unique


def test_dst_day_row_counts_match_real_file():
    # 92 rows on 30.03.2025 and 100 rows on 26.10.2025, as seen in the raw data.
    spring = pd.date_range("2025-03-29 23:00", "2025-03-30 22:45", freq="15min", tz="UTC")
    autumn = pd.date_range("2025-10-25 22:00", "2025-10-26 22:45", freq="15min", tz="UTC")
    rows = local_rows("2025", spring.append(autumn))
    texts = [r[2]["Date Time"] for r in rows]
    
    assert sum(t.startswith("30.03.2025") for t in texts) == 92
    assert sum(t.startswith("26.10.2025") for t in texts) == 100


def test_yearly_wins_over_daily_and_newest_daily_wins():
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
    grid = pd.date_range("2024-11-01", periods=4, freq="15min", tz="UTC")
    rows = [("2024", LOADED, {
            "Date Time": t,
            "Total System Imbalance (Positiv = long / Negativ = short)": "5",
            "AE-Preis long": "1", "AE-Preis short": "2",
        })
        for t in grid.tz_convert("Europe/Zurich").strftime("%d.%m.%Y %H:%M")]
    
    assert build_clean(rows)["price"].isna().all()


def test_lag_constants_respect_issue_time():
    assert all(lag >= MIN_LAG for lag in LAGS)


def test_features_use_only_values_known_at_issue_time():
    # Issue time T = 23:20 UTC on day D, last known value 22:45 on D.
    clean = build_clean(utc_rows("2026", pd.date_range("2026-01-01", periods=96 * 20, freq="15min", tz="UTC"), 1))
    day_d = pd.Timestamp("2026-01-15", tz="UTC")
    last_known = day_d + pd.Timedelta(hours=22, minutes=45)
    targets = pd.date_range(day_d + pd.Timedelta(days=1), periods=96, freq="15min")
    
    for lag in LAGS:
        source_times = targets - pd.Timedelta(minutes=15 * lag)
        assert (source_times <= last_known).all(), f"lag {lag} reaches past issue time"


def test_features_are_shifted_and_no_raw_inputs_present():
    grid = pd.date_range("2026-01-01", periods=96 * 20, freq="15min", tz="UTC")
    rows = [("2026", LOADED, {
            "Date Time [UTC]": t.strftime("%d.%m.%Y %H:%M"),
            "Total System Imbalance": str(i),
            "AE-Preis": str(i * 2),
        })
        for i, t in enumerate(grid)]
    
    feats = build_features(build_clean(rows))
    assert "imbalance" not in feats.columns and "price" not in feats.columns
    
    i = 96 * 10
    for lag in LAGS:
        assert feats[f"imbalance_lag{lag}"].iloc[i] == i - lag
        assert feats[f"price_lag{lag}"].iloc[i] == (i - lag) * 2
    assert feats["target"].iloc[i] == i
