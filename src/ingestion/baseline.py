"""Persistence baselines on the out-of-time split.

Baseline for quarter-hour t = the imbalance at t - lag. Only lags >= MIN_LAG
exist at issue time (see transform.py): lag 192 = same quarter-hour 2 days
ago, lag 672 = same quarter-hour 7 days ago. t-1 style persistence is not
possible at this issue time, so the old 103.105 MW number is not comparable.

All baselines are scored on the same rows: test period, target and every
feature present. A model must be scored on exactly these rows too.
"""

from __future__ import annotations

import pandas as pd

from .transform_energy_balance import LAGS

TEST_START = "2026-07-01"  # everything before = training period, from here = test


def persistence_mae(features: pd.DataFrame, test_start: str = TEST_START) -> dict:
    test = features.loc[features.index >= pd.Timestamp(test_start, tz="UTC")].dropna()
    return {
        "test_start": test_start,
        "rows": len(test),
        **{
            f"mae_lag{lag}": float((test["target"] - test[f"imbalance_lag{lag}"]).abs().mean())
            for lag in LAGS
        },
    }


def main() -> None:
    from .db import get_conn

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM features.control_area_features ORDER BY ts_utc")
            columns = [c.name for c in cur.description]
            features = pd.DataFrame(cur.fetchall(), columns=columns)
    finally:
        conn.close()
    features["ts_utc"] = pd.to_datetime(features["ts_utc"], utc=True)
    print(persistence_mae(features.set_index("ts_utc")))


if __name__ == "__main__":
    main()