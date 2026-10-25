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


Horizon: Next 24h at 15-min resolution, with potentially less accurate prediction for 3-7 days ahead.

Scope: Swiss control area, as published by Swissgrid. In detail, this means one single control area for all of Switzerland, without subdivisions for cantons.

Success criterion: MAE on the 24h-ahead imbalance forecast, computed as 1 N∑︁ |ˆyt − yt| over 15-min steps.

Baseline: persistence (value from the same quarter-hour one day prior), with its MAE computed directly from historical data before any model training.

Target: beat the persistence baseline of 103.105 MW by a margin of >15 percent.


## Data

- **Swissgrid Energy Balance Data:** Dataset of control area balance, activated secondary energies and tertiery energies, and international cooperation IGCC. All leading to total system imbalance and the balancing energy price. All values are quarter hourly.
  - **Source:** [Swissgrid Energy Data](https://www.swissgrid.ch/en/home/customers/topics/energy-data-ch.html)


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

## Ingestion

```
uv run python -m src.ingestion.energy_balance backfill    # all history from Swissgrid Energy Balance
uv run python -m src.ingestion.energy_balance daily       # today's energy balance

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
| pgAdmin container → PostgreSQL container | Host `postgres`, port `5432`, user `sharedUser`, pw `in .env` | 

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
5. Cloud Setup
6. Scheduled Execution (GitHub actions.)
7. ReadMe, MS1 Response


## M3 Training Pipeline

Due: 03.12.2026

## M4 Live system

Due: 10.01.2027