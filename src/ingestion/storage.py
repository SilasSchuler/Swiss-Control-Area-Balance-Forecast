"""Object storage for raw downloads: MinIO locally, GCS in the cloud.

STORAGE_BACKEND picks the backend (see config.py):
- minio (default): local Docker Compose, S3 API through boto3.
- gcs: Google Cloud Storage. Credentials come from Application Default
  Credentials (GitHub Actions: google-github-actions/auth; laptop:
  `gcloud auth application-default login`), so no key lives in the repo.

MinIO has one bucket per layer (raw, features, artifacts). GCS bucket names
are global, so the GCS backend uses one bucket (GCS_BUCKET) and turns the
logical bucket name into a prefix: raw/<key>.
"""

from __future__ import annotations

from typing import Protocol

from .config import RAW_BUCKET, SETTINGS


class ObjectStore(Protocol):
    def ensure_bucket(self, bucket: str) -> None: ...
    def put(self, bucket: str, key: str, data: bytes) -> None: ...


class MinioStore:
    def __init__(self) -> None:
        import boto3

        self._s3 = boto3.client(
            "s3",
            endpoint_url=SETTINGS.minio_endpoint,
            aws_access_key_id=SETTINGS.minio_admin,
            aws_secret_access_key=SETTINGS.minio_secret,
        )

    def ensure_bucket(self, bucket: str) -> None:
        existing = {b["Name"] for b in self._s3.list_buckets().get("Buckets", [])}
        if bucket not in existing:
            self._s3.create_bucket(Bucket=bucket)

    def put(self, bucket: str, key: str, data: bytes) -> None:
        self._s3.put_object(Bucket=bucket, Key=key, Body=data)


class GcsStore:
    def __init__(self) -> None:
        from google.cloud import storage

        if not SETTINGS.gcs_bucket:
            raise RuntimeError("STORAGE_BACKEND=gcs needs GCS_BUCKET")
        self._bucket = storage.Client().bucket(SETTINGS.gcs_bucket)

    def ensure_bucket(self, bucket: str) -> None:
        # The bucket is created once with gcloud (region, versioning, IAM).
        # The pipeline's service account may only write objects, not buckets.
        return None

    def put(self, bucket: str, key: str, data: bytes) -> None:
        self._bucket.blob(f"{bucket}/{key}").upload_from_string(data, content_type="text/csv")


def get_client() -> ObjectStore:
    if SETTINGS.storage_backend == "gcs":
        return GcsStore()
    return MinioStore()


def ensure_bucket(client: ObjectStore, bucket: str = RAW_BUCKET) -> None:
    client.ensure_bucket(bucket)


def upload_bytes(client: ObjectStore, key: str, data: bytes, bucket: str = RAW_BUCKET) -> None:
    """Upload raw bytes. Overwriting an identical snapshot is intentional
    (keeps re-runs idempotent)."""
    client.put(bucket, key, data)