"""SWGR control area balance ingestion
source: https://www.swissgrid.ch/en/home/customers/topics/energy-data-ch.html

Modes:
  daily    - download control-area-balance-daily.csv
  backfill - download the yearly files (control-area-balance-YYYY.csv)
  all      - both

Every file lands twice:
  1. MinIO     raw/control-area-balance/date=YYYY-MM-DD/<key>.csv (untouched bytes)
  2. Postgres  raw.control_area_balance (one JSONB row per CSV row)

Idempotent: each source_key (daily, 2026, ...) is loaded as
DELETE + INSERT in a single transaction. Re-running never duplicates rows.
Daily and yearly files overlap in time; dedupe in the transform step.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup
from psycopg2.extras import Json, execute_values
from urllib.parse import urljoin

from .config import SETTINGS
from .db import IngestionRun, ensure_schema, get_conn
from .storage import ensure_bucket, get_client, upload_bytes

SOURCE = "swissgrid_balance"
PAGE_URL = SETTINGS.swgr_url_raw
WANTED = {
    "daily": "control-area-balance-daily.csv",
    "2026": "control-area-balance-2026.csv",
}
DELIMITER = ";" 

DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE TABLE IF NOT EXISTS raw.control_area_balance (
    id          BIGSERIAL PRIMARY KEY,
    source_key  TEXT NOT NULL,
    source_file TEXT NOT NULL,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload     JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS control_area_balance_source_key_idx
    ON raw.control_area_balance (source_key);
"""


def minio_key(key: str, day: date) -> str:
    return f"control-area-balance/date={day.isoformat()}/{key}.csv"


# ------------------------------------------------------------- discover

def discover_urls() -> dict[str, str]:
    response = requests.get(PAGE_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    found_url = {}
    for a in soup.find_all("a", href=True):
        for key, filename in WANTED.items():
            if filename in a["href"]:
                found_url[key] = urljoin(PAGE_URL, a["href"])

    missing = WANTED.keys() - found_url.keys()
    if missing:
        raise RuntimeError(f"Links not found: {missing}; page layout changed?")
    return found_url


def fetch_file(url: str) -> bytes:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


# ----------------------------------------------------------------- load

def parse_rows(raw_bytes: bytes) -> list[dict]:
    text = raw_bytes.decode("utf-8-sig")  # strips BOM if present
    return list(csv.DictReader(io.StringIO(text), delimiter=DELIMITER))


def run_checks(rows: list[dict]) -> str:
    """Logged, never fixed (transform comes later)."""
    notes = []
    if not rows:
        notes.append("zero rows")
    else:
        if len(rows[0]) < 2:
            notes.append(f"only {len(rows[0])} column(s): wrong delimiter?")
        empty = sum(1 for r in rows if not any(r.values()))
        if empty:
            notes.append(f"{empty} fully empty rows")
    return "; ".join(notes) if notes else "checks ok"


def load_file(key: str, url: str, mode: str) -> None:
    """Land one file in MinIO + Postgres. Raises on hard errors."""
    today = date.today()
    raw_bytes = fetch_file(url)
    source_file = url.rsplit("/", 1)[-1]

    s3 = get_client()
    ensure_bucket(s3)
    upload_bytes(s3, minio_key(key, today), raw_bytes)

    rows = parse_rows(raw_bytes)  # hard fail if unparseable
    if not rows:
        raise ValueError(f"{source_file} contains zero rows")

    conn = get_conn()
    # Raw Tables. 
    ensure_schema(conn)
    
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
        with IngestionRun(conn, SOURCE, mode, snapshot_date=today) as run:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM raw.control_area_balance WHERE source_key = %s",(key,),)
                execute_values(cur,
                    "INSERT INTO raw.control_area_balance "
                    "(source_key, source_file, payload) VALUES %s",
                    [(key, source_file, Json(r)) for r in rows], page_size=1000,
                )
            conn.commit()
            run.rows_loaded = len(rows)
            run.message = run_checks(rows)
    finally:
        conn.close()


# ---------------------------------------------------------------- modes

def mode_daily() -> None:
    urls = discover_urls()
    load_file("daily", urls["daily"], mode="daily")
    print("daily: ok")


def mode_backfill() -> None:
    """Backfill all non-daily files goes back to 2024."""
    urls = discover_urls()
    for key, url in urls.items():
        if key == "daily":
            continue
        load_file(key, url, mode="backfill")
        print(f"  {key} ok")


# ------------------------------------------------------------------ cli

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["daily", "backfill", "all"])
    args = p.parse_args()

    if args.mode in ("backfill", "all"):
        mode_backfill()
    if args.mode in ("daily", "all"):
        mode_daily()


if __name__ == "__main__":
    sys.exit(main())