"""Transform raw.control_area_balance -> clean + features tables.

Issue time T = 23:20 UTC on day D. The model forecasts all 96 quarter-hours
of D+1 in one pass. The last value known at T is about 22:45 on D, so the
last step of D+1 (23:45) is 100 quarter-hours later. Every feature lag must
therefore be >= MIN_LAG, or it would use a value that does not exist at T.

Tables written (full refresh, safe to re-run):
  clean.control_area_balance      ts_utc, imbalance, price
  features.control_area_features  ts_utc, target, lagged values, calendar
"""

from __future__ import annotations

from datetime import datetime, timezone
from .db import IngestionRun, get_conn

import pandas as pd

LOCAL_TZ = "Europe/Zurich"
FREQ = "15min"

MIN_LAG = 100          # quarter-hours, see module docstring
LAGS = (192, 672)      # 2 days and 7 days, both >= MIN_LAG

# Column names differ between the yearly files, pick the first one present.
TS_COLUMNS = ["Date Time [UTC]", "Date Time"]
IMBALANCE_COLUMNS = [
    "Total System Imbalance",
    "Total System Imbalance (Positiv = long / Negativ = short)",
]
PRICE_COLUMNS = ["AE-Preis", "AE-Preis per 2026"]  # 2024 has only long/short -> no price


def _first_present(keys, candidates: list[str]) -> str | None:
    for name in candidates:
        if name in keys:
            return name
    return None


def canonicalise(raw_rows: list[tuple]) -> pd.DataFrame:
    """raw_rows: (source_key, loaded_at, payload dict), in file order.

    Returns one row per raw row: ts_utc, imbalance, price, loaded_at, is_daily.
    """
    by_key: dict[str, list[tuple]] = {}
    for source_key, loaded_at, payload in raw_rows:
        by_key.setdefault(source_key, []).append((loaded_at, payload))

    frames = []
    for source_key, items in by_key.items():
        keys = items[0][1].keys()
        ts_col = _first_present(keys, TS_COLUMNS)
        imb_col = _first_present(keys, IMBALANCE_COLUMNS)
        price_col = _first_present(keys, PRICE_COLUMNS)
        if ts_col is None or imb_col is None:
            raise ValueError(f"{source_key}: timestamp or imbalance column not found")

        ts = pd.to_datetime(
            pd.Series([p[ts_col] for _, p in items]), format="%d.%m.%Y %H:%M"
        )
        if ts_col == "Date Time [UTC]":
            ts = ts.dt.tz_localize("UTC")
        else:
            # No [UTC] label: Zurich local time. 'infer' resolves the time shift double hour in October because rows are in file order.
            ts = ts.dt.tz_localize(LOCAL_TZ, ambiguous="infer").dt.tz_convert("UTC")

        def num(col: str | None) -> pd.Series:
            if col is None:
                return pd.Series(float("nan"), index=ts.index)
            return pd.to_numeric(pd.Series([p[col] for _, p in items]), errors="coerce").astype(float)

        frames.append(pd.DataFrame(
                {
                    "ts_utc": ts,
                    "imbalance": num(imb_col),
                    "price": num(price_col),
                    "loaded_at": [loaded for loaded, _ in items],
                    "is_daily": source_key.startswith("daily"),
                }))
    return pd.concat(frames, ignore_index=True)


def build_clean(raw_rows: list[tuple]) -> pd.DataFrame:
    """One row per quarter-hour on a complete 15-min UTC grid (gaps become NaN)."""
    df = canonicalise(raw_rows)
    
    # Yearly files hold corrected values, so they win over daily snapshots.
    # Among daily snapshots the newest wins. Raw snapshots stay in raw.* 
    # the first-published values can always be reconstructed.
    df = df.sort_values(["ts_utc", "is_daily", "loaded_at"], ascending=[True, False, True])
    df = df.drop_duplicates("ts_utc", keep="last").set_index("ts_utc")
    grid = pd.date_range(df.index.min(), df.index.max(), freq=FREQ)
    return df[["imbalance", "price"]].reindex(grid).rename_axis("ts_utc")


def build_features(clean: pd.DataFrame) -> pd.DataFrame:
    """Only lagged values (>= MIN_LAG) and calendar features. No unshifted inputs."""
    if min(LAGS) < MIN_LAG:
        raise ValueError(f"LAGS must all be >= MIN_LAG ({MIN_LAG})")
    out = pd.DataFrame(index=clean.index)
    out["target"] = clean["imbalance"]
    for lag in LAGS:
        out[f"imbalance_lag{lag}"] = clean["imbalance"].shift(lag)
        out[f"price_lag{lag}"] = clean["price"].shift(lag)
    local = clean.index.tz_convert(LOCAL_TZ)
    out["quarter_of_day"] = local.hour * 4 + local.minute // 15
    out["day_of_week"] = local.dayofweek
    out["month"] = local.month
    return out


def replace_table(conn, table: str, df: pd.DataFrame) -> None:
    """Full refresh: drop, create from the DataFrame dtypes, insert."""
    from psycopg2.extras import execute_values

    df = df.reset_index()
    kind_to_sql = {"M": "TIMESTAMPTZ", "f": "DOUBLE PRECISION"}
    columns = ", ".join(f'"{c}" {kind_to_sql.get(t.kind, "INTEGER")}' for c, t in df.dtypes.items())
    names = ", ".join(f'"{c}"' for c in df.columns)
    data = df.astype(object).where(df.notna(), None)
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(f"CREATE TABLE {table} ({columns}, PRIMARY KEY (ts_utc))")
        execute_values(
            cur,
            f"INSERT INTO {table} ({names}) VALUES %s",
            list(data.itertuples(index=False, name=None)),
            page_size=5000,
        )
    conn.commit()


def main() -> None:
    conn = get_conn()
    
    try:
        today = datetime.now(timezone.utc).date()
        
        with IngestionRun(conn, "swissgrid_transform", "full", snapshot_date=today) as run:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT source_key, loaded_at, payload "
                    "FROM raw.control_area_balance ORDER BY id"
                )
                raw_rows = cur.fetchall()
                cur.execute("CREATE SCHEMA IF NOT EXISTS clean")
                cur.execute("CREATE SCHEMA IF NOT EXISTS features")
            conn.commit()

            clean = build_clean(raw_rows)
            features = build_features(clean)
            replace_table(conn, "clean.control_area_balance", clean)
            replace_table(conn, "features.control_area_features", features)

            run.rows_loaded = len(features)
            run.message = (
                f"{clean.index.min()} to {clean.index.max()}; "
                f"missing imbalance: {int(clean['imbalance'].isna().sum())}, "
                f"missing price: {int(clean['price'].isna().sum())}"
            )
        print(f"transform: ok, {len(features)} rows, {run.message}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
