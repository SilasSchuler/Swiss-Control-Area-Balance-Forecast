CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS clean;
CREATE SCHEMA IF NOT EXISTS features;

-- Backend-store database for the MLflow service (model-registry).
CREATE DATABASE mlflow;
