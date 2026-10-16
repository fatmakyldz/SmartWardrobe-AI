"""Image storage behind one small interface: Postgres (default) or an S3-compatible bucket."""

from functools import lru_cache
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .config import get_settings
from .models import StoredImage


class Storage(Protocol):
    def put(self, db: Session, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, db: Session, key: str) -> tuple[bytes, str] | None: ...
    def delete(self, db: Session, keys: list[str]) -> None: ...
    def delete_prefix(self, db: Session, prefix: str) -> None: ...
    def url(self, key: str) -> str: ...


class DbStorage:
    def put(self, db: Session, key: str, data: bytes, content_type: str) -> None:
        db.merge(StoredImage(key=key, data=data, content_type=content_type))

    def get(self, db: Session, key: str) -> tuple[bytes, str] | None:
        img = db.get(StoredImage, key)
        return (img.data, img.content_type) if img else None

    def delete(self, db: Session, keys: list[str]) -> None:
        if keys:
            db.execute(delete(StoredImage).where(StoredImage.key.in_(keys)))

    def delete_prefix(self, db: Session, prefix: str) -> None:
        db.execute(delete(StoredImage).where(StoredImage.key.startswith(prefix)))

    def url(self, key: str) -> str:
        base = get_settings().public_base_url.rstrip("/")
        return f"{base}/images/{key}"


class S3Storage:
    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.public_base = s.s3_public_base_url.rstrip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url or None,
            aws_access_key_id=s.s3_access_key_id,
            aws_secret_access_key=s.s3_secret_access_key,
            region_name=s.s3_region,
        )

    def put(self, db: Session, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )

    def get(self, db: Session, key: str) -> tuple[bytes, str] | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.NoSuchKey:
            return None
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")

    def delete(self, db: Session, keys: list[str]) -> None:
        for i in range(0, len(keys), 1000):
            chunk = keys[i : i + 1000]
            if chunk:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": [{"Key": k} for k in chunk]})

    def delete_prefix(self, db: Session, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys = [o["Key"] for o in page.get("Contents", [])]
            self.delete(db, keys)

    def url(self, key: str) -> str:
        return f"{self.public_base}/{key}"


@lru_cache
def get_storage() -> Storage:
    return S3Storage() if get_settings().storage_backend == "s3" else DbStorage()
