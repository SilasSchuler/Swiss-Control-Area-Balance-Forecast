# Swiss-Control-Area-Balance-Forecast
HSLU H26 Machine Learning Operations Project.

The task is to build a complete data ingestion pipeline to train a machine learning model. Everything has to be built to withstand a producitve system on the cloud.



## Use Case

A modern problem of electric grids is no longer the production, which has countless options
to be sustained, but rather system imbalance. Internal photovoltaic energy production spikes during
the day and needs to be sustained at night and during winter. On the external side, neighbouring
countries have their own energy overflow, which needs to be contained within an acceptable range to
maintain net stability. Energy companies have their internal observations, but normal people do not
have a way to predict net stability.


Prediction: Swiss control area imbalance (Total System Imbalance, MW)

Issue time: every night at T = 23:20 UTC on day D, one forecast for all 96
quarter-hours of D+1 (non-recursive). Only values published before T are used.

Success criterion: MAE = (1/N) * sum(|y_hat_t - y_t|) over 15-min steps.

Baseline: persistence with a lag that exists at issue time. A lag of one day
(t-96) is not available for the last steps of D+1, so the baselines are
t-192 (96.09 MW) and t-672 (94.26 MW), see "Calculate Baseline".
The 103.105 MW from the proposal used an unavailable lag and is superseded.

Target: MAE below 80.1 MW, which is 15 percent better than the best baseline
(t-672, 94.26 MW).


## What is known when

Issue time T = 23:20 UTC on day D. The last value known at T is about 22:45 UTC
on D, so the last step of D+1 (23:45) is 100 quarter-hours later. Every lag
must be at least 100 steps (MIN_LAG in `transform_features.py`).

| Input | Published | Time zone | Used at T |
|---|---|---|---|
| Total System Imbalance (label) | Daily file, every 15 min, lag at most 10 min | UTC (yearly 2024 and 2025 files: Zurich local time, converted) | Only as lags 192 and 672 |
| AE-Preis | Same row as the label, so it would leak the label if unlagged | same | Only as lags 192 and 672 |
| Calendar features | Known in advance | Zurich local time | Yes |

Daily file: rolling window of about 24 hours (99 rows on 25.10.2026).
Yearly files: corrected values, used for backfill. In the transform they win
over daily snapshots. Swissgrid revises values for up to six months.
Not used: lags t-1 to t-4 and all other short lags.


## Data

- **Swissgrid Energy Balance Data:** Dataset of control area balance, activated secondary energies and tertiery energies, and international cooperation IGCC. All leading to total system imbalance and the balancing energy price. All values are quarter hourly.
  - **Source:** [Swissgrid Energy Data](https://www.swissgrid.ch/en/home/customers/topics/energy-data-ch.html)

- **Volume:** 69,463 quarter-hours since 01.11.2024 (Zurich time), growing by 96 rows per day.
- **Access:** the pipeline reads the download links from the Swissgrid energy data page, so a changed file URL does not break it. Terms of use: Non-binding data offer not falling under copyright. Since information is intended for general information purposes only, there is no gurantee as to the correctness or accessibility. 
- **Fallback:** ENTSO-E imbalance data (not implemented yet).

## Architecture

*To be added*

# Setup

## UV Environment

UV is generous on both Windows and Mac devices, which makes it more generous for a group project.

```
uv init

# On every update.
uv sync

# Add a new library to the project.
uv add {library}

# Run python scripts
uv run {script}
```


## Docker Containers

Build docker containers
```
docker compose up -d

# When finished
docker compose down
```

## Calculate Baseline

```
uv run python -m src.ingestion.baseline

```


Baseline result: persistence MAE on 11,187 test rows (01.07.2026 onward):
Recalculated for MS2, due to issues with the MAE Assumption in proposal.

| Baseline	| MAE (MW) |
|---|---|
| t-192 (same quarter-hour 2 days ago) |	96.09 |
| t-672 (same quarter-hour 7 days ago) |	94.26 |


## Ingestion

```
uv run python -m src.ingestion.energy_balance backfill    # all history from Swissgrid Energy Balance
uv run python -m src.ingestion.energy_balance daily       # today's energy balance

```

## Data flow

| Layer | Location | Content |
|---|---|---|
| Raw files | MinIO `control-area-balance/date=YYYY-MM-DD/<key>.csv` | Untouched downloads, one dated copy per run |
| Raw rows | Postgres `raw.control_area_balance` | One JSONB row per CSV row, daily snapshots keyed `daily-YYYY-MM-DD` |
| Clean | Postgres `clean.control_area_balance` | Unified columns, UTC, gap-free 15-min grid |
| Features | Postgres `features.control_area_features` | Target, lags 192 and 672, calendar features |

## Transformation

```
uv run python -m src.ingestion.transform_features

```


### Servers
| Server | url |
|---|---|
| PostgresSQL | postgres:5432|
| PGAdmin | localhost:8085 |
| Minio Objectstore | localhost:9000 |
| MLFlow | localhost:5001 |
| development | VS Code, servers are accessible. With above links. |

### Login PGAdmin

Server needs to be loaded manually, if interaction with PostgresSQL DB is required.

| Connection | Address used |
|---|---|
| Your laptop's browser → pgAdmin | `http://localhost:8085` | 
| pgAdmin container → PostgreSQL container | Host `postgres`, port `5432`, user `sharedUser`, password `in .env` | 

# Tests

Run Unit tests to check if transformation of file data happens correctly.

```
uv run python -m pytest tests -q
```


# Milestones

## M1 Proposal

Due: 01.10.2026

All docs are in the docs. Folder.


## M2 Feature Pipeline

Due: 29.10.2026

**Deliverable** — working feature pipeline:
1.  Automated data ingestion from a live source (+backfill)
2.  Feature engineering & storage (feature store or versioned Parquet/GCS)
3. Scheduled execution (GitHub Actions / Airflow) — not manual
4. Docker image, pinned deps, informative README

*ALSO IN THE REPO*
– Summary of what you have achieved in this milestone
– Response to MS1 reviewer comments

**Working Summary** (Updated as tasks are completed)
1. Environment Setup
2. Docker Compose for the development environment. 
    - PostgreSQL (Cloud SQL later, for feature table)
    - PGAdmin (Development connection to PostgreSQL)
    - Local Minio Storage (GCS later)
    - MLFlow local, but not yet used.
3. Ingestion Scripts 
4. Feature Engineering
5. Cloud Setup - (moved to M3)
6. Scheduled Execution (GitHub actions)
7. ReadMe, MS1 Response


## M3 Training Pipeline

Due: 03.12.2026

## M4 Live system

Due: 10.01.2027