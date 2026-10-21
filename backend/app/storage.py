"""Image storage behind one small interface: a local folder (local runs / tests) or a private S3-compatible bucket (R2)."""

import mimetypes
from collections.abc import Iterator
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from .config import get_settings


def cache_control() -> str:
    """Objects are private and links short-lived: browsers keep a copy only as long as a link lives."""
    return f"private, max-age={get_settings().image_url_seconds}"


class Storage(Protocol):
    def put(self, db: Session, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, db: Session, key: str) -> tuple[bytes, str] | None: ...
    def exists(self, db: Session, key: str) -> bool: ...
    def copy(self, db: Session, src: str, dst: str) -> None: ...
    def delete(self, db: Session, keys: list[str]) -> None: ...
    def delete_prefix(self, db: Session, prefix: str) -> None: ...
    def list_keys(self, db: Session, prefix: str = "") -> Iterator[tuple[str, datetime]]: ...
    def url(self, key: str) -> str: ...


class LocalStorage:
    """Files under LOCAL_STORAGE_DIR (local runs, tests), served by GET /images/{key} to the signed-in owner.
    Keys are the same shape as in the bucket (u/{user}/{file}.webp, demo/{file}.webp)."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or get_settings().local_storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not key or path == self.root or self.root not in path.parents:
            raise ValueError(f"bad key {key!r}")
        return path

    def put(self, db: Session, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic: a reader never sees a half-written file

    def get(self, db: Session, key: str) -> tuple[bytes, str] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    def exists(self, db: Session, key: str) -> bool:
        return self._path(key).is_file()

    def copy(self, db: Session, src: str, dst: str) -> None:
        found = self.get(db, src)
        if found is None:
            raise KeyError(src)
        self.put(db, dst, found[0], found[1])

    def delete(self, db: Session, keys: list[str]) -> None:
        for key in keys:
            path = self._path(key)
            if path.is_file():
                path.unlink()

    def delete_prefix(self, db: Session, prefix: str) -> None:
        self.delete(db, [key for key, _ in self.list_keys(db, prefix)])

    def list_keys(self, db: Session, prefix: str = "") -> Iterator[tuple[str, datetime]]:
        for path in sorted(p for p in self.root.rglob("*") if p.is_file() and p.suffix != ".tmp"):
            key = path.relative_to(self.root).as_posix()
            if key.startswith(prefix):
                yield key, datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    def url(self, key: str) -> str:
        base = get_settings().public_base_url.rstrip("/")
        return f"{base}/images/{key}"


class S3Storage:
    """A private bucket. Nothing is public: the app gets a presigned GET link per response."""

    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        s = get_settings()
        if not (s.s3_bucket and s.s3_access_key_id and s.s3_secret_access_key):
            raise RuntimeError("STORAGE_BACKEND=s3 needs S3_BUCKET, S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY.")
        self.bucket = s.s3_bucket
        self.url_seconds = s.image_url_seconds
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url or None,
            aws_access_key_id=s.s3_access_key_id,
            aws_secret_access_key=s.s3_secret_access_key,
            region_name=s.s3_region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )

    def put(self, db: Session, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, CacheControl=cache_control(),
        )

    def get(self, db: Session, key: str) -> tuple[bytes, str] | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.NoSuchKey:
            return None
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")

    def exists(self, db: Session, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def copy(self, db: Session, src: str, dst: str) -> None:
        self.client.copy_object(
            Bucket=self.bucket, Key=dst, CopySource={"Bucket": self.bucket, "Key": src},
            MetadataDirective="REPLACE", ContentType="image/webp", CacheControl=cache_control(),
        )

    def delete(self, db: Session, keys: list[str]) -> None:
        for i in range(0, len(keys), 1000):
            chunk = keys[i : i + 1000]
            if chunk:
                out = self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": [{"Key": k} for k in chunk]})
                if out.get("Errors"):
                    raise RuntimeError(f"delete failed for {len(out['Errors'])} object(s)")

    def delete_prefix(self, db: Session, prefix: str) -> None:
        self.delete(db, [key for key, _ in self.list_keys(db, prefix)])

    def list_keys(self, db: Session, prefix: str = "") -> Iterator[tuple[str, datetime]]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for o in page.get("Contents", []):
                yield o["Key"], o["LastModified"]

    def url(self, key: str) -> str:
        # Signed locally (no network call), so every response can carry fresh links (§14 C4).
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=self.url_seconds,
        )


@lru_cache
def get_storage() -> Storage:
    return S3Storage() if get_settings().storage_backend == "s3" else LocalStorage()
