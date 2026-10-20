"""Photo objects and their wardrobe_images metadata (§8): upload, attach, release, demo, cleanup.

Order is always storage first on the way in (an object without a row is found by `reconcile`) and
DB first on the way out (a row whose object could not be deleted is marked as an orphan).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..images import dimensions, new_key, normalize
from ..models import Item, User, WardrobeImage
from ..storage import get_storage
from .errors import bad_request

log = logging.getLogger(__name__)

ASSETS = Path(__file__).parent.parent / "demo_assets"
DEMO_PREFIX = "demo/"
ORPHAN_AGE = timedelta(hours=24)
CONTENT_TYPE = "image/webp"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_shared(key: str) -> bool:
    """Shared system objects (demo images): never deleted with an item or an account."""
    return key.startswith(DEMO_PREFIX)


def can_view(user: User, key: str) -> bool:
    """Same rule as WardrobeImage.visible_to, by key: own prefix, or a shared picture for a demo account."""
    return key.startswith(f"u/{user.id.hex}/") or (user.is_demo and is_shared(key))


def row(key: str, user_id: uuid.UUID | None, data: bytes, attached_at: datetime | None = None,
        item_id: uuid.UUID | None = None, content_type: str = CONTENT_TYPE) -> WardrobeImage:
    width, height = dimensions(data)
    return WardrobeImage(key=key, user_id=user_id, item_id=item_id, content_type=content_type, bytes=len(data),
                         width=width, height=height, attached_at=attached_at)


# ── a user's photos ───────────────────────────────────────────────────────

def store_upload(db: Session, user: User, raw: bytes, max_mb: int) -> tuple[str, bytes]:
    """Validate and store a photo as an orphan until POST /items attaches it.
    Returns (image_key, small JPEG for the vision model)."""
    stored, small = normalize(raw, max_mb)
    key = new_key(user.id)
    get_storage().put(db, key, stored, CONTENT_TYPE)
    db.add(row(key, user.id, stored))
    db.commit()
    return key, small


def claim_upload(db: Session, user: User, key: str) -> WardrobeImage:
    """The image for a new item: uploaded by this user via /items/analyze and not on an item yet."""
    img = db.get(WardrobeImage, key) if key.startswith(f"u/{user.id.hex}/") else None
    if img is None or img.user_id != user.id or img.attached_at is not None:
        raise bad_request("invalid_image")
    return img


def attach(img: WardrobeImage, item: Item) -> None:
    img.item_id = item.id
    img.attached_at = _now()


def release(db: Session, key: str) -> None:
    """After an item's DB row is gone (and committed): delete the object, then its metadata.
    If the bucket refuses, the row stays as an orphan and cleanup_orphans retries later."""
    if is_shared(key):
        return
    storage = get_storage()
    try:
        storage.delete(db, [key])
    except Exception:
        log.warning("image delete failed; marked as orphan", exc_info=True)
        db.rollback()
        img = db.get(WardrobeImage, key)
        if img is not None:
            img.item_id, img.attached_at = None, None
            db.commit()
        return
    db.execute(delete(WardrobeImage).where(WardrobeImage.key == key))
    db.commit()


def delete_user_objects(db: Session, user_id: uuid.UUID) -> None:
    """Account deletion, after the user row (and with it the wardrobe_images rows) is committed away.
    Failure is logged, not raised: reconcile() later removes objects that have no row."""
    try:
        get_storage().delete_prefix(db, f"u/{user_id.hex}/")
        db.commit()
    except Exception:
        log.warning("account image cleanup failed; reconcile will retry", exc_info=True)
        db.rollback()


# ── shared demo images (§14 C5) ───────────────────────────────────────────

def demo_key(file: str) -> str:
    return f"{DEMO_PREFIX}{file}.webp"


def ensure_demo_images(db: Session, files: list[str]) -> None:
    """Upload each demo picture once, as a system object (user_id NULL, attached so never an orphan)."""
    keys = {demo_key(f): f for f in files}
    have = set(db.scalars(select(WardrobeImage.key).where(WardrobeImage.key.in_(keys))))
    missing = [k for k in keys if k not in have]
    if not missing:
        return
    storage = get_storage()
    for key in missing:
        stored, _ = normalize((ASSETS / f"{keys[key]}.png").read_bytes(), 10)
        storage.put(db, key, stored, CONTENT_TYPE)
        db.add(row(key, None, stored, attached_at=_now()))
    try:
        db.commit()
    except IntegrityError:  # another request uploaded them at the same moment
        db.rollback()


def copy_shared_image(db: Session, user: User, item: Item) -> None:
    """Give an item that points at a shared demo image its own copy (demo → real account, decision 15).
    Run inside the claim transaction; the caller commits."""
    if not is_shared(item.image_key):
        return
    storage = get_storage()
    found = storage.get(db, item.image_key)
    if found is None:
        raise bad_request("invalid_image")
    data, content_type = found
    key = new_key(user.id)
    storage.copy(db, item.image_key, key)
    db.add(row(key, user.id, data, attached_at=_now(), item_id=item.id, content_type=content_type))
    item.image_key = key


# ── maintenance (scripts/cleanup_orphans.py) ──────────────────────────────

@dataclass
class CleanupReport:
    orphan_rows: list[str] = field(default_factory=list)  # unattached > 24 h: object + row deleted
    stray_objects: list[str] = field(default_factory=list)  # in the bucket, no row: object deleted
    missing_objects: list[str] = field(default_factory=list)  # row, no object: reported only
    failed: list[str] = field(default_factory=list)


def cleanup_orphans(db: Session, now: datetime | None = None, dry_run: bool = False,
                    batch: int = 500) -> CleanupReport:
    """Rows never attached to an item (or released after a failed delete) for more than 24 h."""
    now, report = now or _now(), CleanupReport()
    cutoff = now - ORPHAN_AGE
    storage = get_storage()
    last = ""
    while True:
        keys = list(db.scalars(
            select(WardrobeImage.key)
            .where(WardrobeImage.attached_at.is_(None), WardrobeImage.created_at < cutoff, WardrobeImage.key > last)
            .order_by(WardrobeImage.key).limit(batch)
        ))
        if not keys:
            return report
        last = keys[-1]
        keys = [k for k in keys if not is_shared(k)]
        if dry_run:
            report.orphan_rows += keys
            continue
        try:
            storage.delete(db, keys)
        except Exception:
            log.warning("orphan delete failed", exc_info=True)
            db.rollback()
            report.failed += keys
            continue
        db.execute(delete(WardrobeImage).where(WardrobeImage.key.in_(keys)))
        db.commit()
        report.orphan_rows += keys


def reconcile(db: Session, now: datetime | None = None, dry_run: bool = False) -> CleanupReport:
    """Both directions: bucket objects without a row (older than 24 h, so uploads in flight are safe)
    are deleted; rows whose object is gone are reported. An object an item still points at is never
    treated as stray, even without a row (e.g. before migrate_images_to_r2.py has run)."""
    now, report = now or _now(), CleanupReport()
    cutoff = now - ORPHAN_AGE
    storage = get_storage()
    rows = set(db.scalars(select(WardrobeImage.key)))
    known = rows | set(db.scalars(select(Item.image_key)))
    seen: set[str] = set()
    for prefix in ("u/", DEMO_PREFIX):
        for key, modified in storage.list_keys(db, prefix):
            seen.add(key)
            if key not in known and _aware(modified) < cutoff:
                report.stray_objects.append(key)
    report.missing_objects = sorted(rows - seen)
    if report.stray_objects and not dry_run:
        try:
            storage.delete(db, report.stray_objects)
            db.commit()
        except Exception:
            log.warning("stray object delete failed", exc_info=True)
            db.rollback()
            report.failed += report.stray_objects
    return report
