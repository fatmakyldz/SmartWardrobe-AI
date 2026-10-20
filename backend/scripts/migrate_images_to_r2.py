"""Copy photos from the `images` table to the private R2 bucket and write their wardrobe_images rows (§8).

Run while the API still has STORAGE_BACKEND=db, with DATABASE_URL (Neon) and the S3_* settings of the
bucket in the environment or backend/.env. The bucket is used whatever STORAGE_BACKEND says:

    python scripts/migrate_images_to_r2.py --dry-run   # counts only, writes nothing
    python scripts/migrate_images_to_r2.py             # copy + rows
    python scripts/migrate_images_to_r2.py --verify    # every item has a row, every row an object

Idempotent: a key already in the bucket is not uploaded again, a key that has a row keeps it, so the
script can be stopped and re-run. Pages of --page rows, each in its own session (Neon closes long
connections). items.image_key does not change. The `images` table is left alone (dropped in AI-09).
"""

import argparse
import sys
import uuid
from dataclasses import dataclass, fields
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.images import owner_hex  # noqa: E402
from app.models import Item, StoredImage, User, WardrobeImage  # noqa: E402
from app.services.images import is_shared, row  # noqa: E402
from app.storage import S3Storage  # noqa: E402


@dataclass
class Counts:
    images: int = 0
    uploaded: int = 0  # put into the bucket
    rows_written: int = 0  # new wardrobe_images rows
    already_done: int = 0  # in the bucket and with a row: nothing to do
    unattached: int = 0  # new rows with no item: orphans, removed by cleanup_orphans.py after 24 h
    no_owner: int = 0  # key of a user that no longer exists: skipped

    def __str__(self) -> str:
        return ", ".join(f"{f.name} {getattr(self, f.name)}" for f in fields(self))


def migrate(sessions: sessionmaker, bucket: S3Storage, dry_run: bool = False, page: int = 50) -> Counts:
    c, last = Counts(), ""
    while True:
        with sessions() as db:
            batch = list(db.scalars(select(StoredImage).where(StoredImage.key > last)
                                    .order_by(StoredImage.key).limit(page)))
            if not batch:
                return c
            last = batch[-1].key
            keys = [i.key for i in batch]
            rows = set(db.scalars(select(WardrobeImage.key).where(WardrobeImage.key.in_(keys))))
            items = {i.image_key: i for i in db.scalars(select(Item).where(Item.image_key.in_(keys)))}
            for img in batch:
                c.images += 1
                user_id = _owner(db, img.key)
                if user_id is None and not is_shared(img.key):
                    c.no_owner += 1
                    continue
                in_bucket = bucket.exists(db, img.key)
                if in_bucket and img.key in rows:
                    c.already_done += 1
                    continue
                if not in_bucket:
                    c.uploaded += 1
                    if not dry_run:
                        bucket.put(db, img.key, img.data, img.content_type)
                if img.key not in rows:
                    item = items.get(img.key)
                    item = item if item is not None and item.user_id == user_id else None
                    c.rows_written += 1
                    c.unattached += item is None and not is_shared(img.key)
                    if not dry_run:
                        attached = img.created_at if is_shared(img.key) else item.created_at if item else None
                        db.add(row(img.key, user_id, img.data, attached_at=attached,
                                   item_id=item.id if item else None, content_type=img.content_type))
            if not dry_run:
                db.commit()


def _owner(db: Session, key: str) -> uuid.UUID | None:
    hex_id = owner_hex(key)
    if hex_id is None:
        return None
    user_id = uuid.UUID(hex_id)
    return user_id if db.get(User, user_id) is not None else None


def verify(sessions: sessionmaker, bucket: S3Storage, page: int = 500) -> dict[str, int]:
    """The checks the README's verification query runs, plus object existence in the bucket."""
    with sessions() as db:
        out = {
            "items_without_row": db.scalar(
                select(func.count()).select_from(Item)
                .outerjoin(WardrobeImage, WardrobeImage.key == Item.image_key).where(WardrobeImage.key.is_(None))),
            "images_without_row": db.scalar(
                select(func.count()).select_from(StoredImage)
                .outerjoin(WardrobeImage, WardrobeImage.key == StoredImage.key).where(WardrobeImage.key.is_(None))),
            "rows_without_object": 0,
        }
    last = ""
    while True:
        with sessions() as db:
            keys = list(db.scalars(select(WardrobeImage.key).where(WardrobeImage.key > last)
                                   .order_by(WardrobeImage.key).limit(page)))
            if not keys:
                return out
            last = keys[-1]
            out["rows_without_object"] += sum(not bucket.exists(db, k) for k in keys)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="count only; write nothing")
    mode.add_argument("--verify", action="store_true", help="check the result; write nothing")
    parser.add_argument("--page", type=int, default=50, help="images per page (default 50)")
    args = parser.parse_args()

    from app.db import SessionLocal

    bucket = S3Storage()
    print(f"bucket: {bucket.bucket}")
    if args.verify:
        out = verify(SessionLocal, bucket)
        print(", ".join(f"{k} {v}" for k, v in out.items()))
        ok = not any(out.values())
        print("OK — safe to set STORAGE_BACKEND=s3" if ok else "NOT DONE — run the migration again, then --verify")
        sys.exit(0 if ok else 1)
    c = migrate(SessionLocal, bucket, dry_run=args.dry_run, page=args.page)
    print(c)
    print("dry run — nothing written" if args.dry_run else "done — now run with --verify")


if __name__ == "__main__":
    main()
