"""§8 storage: presigned links on a private bucket (moto), wardrobe_images lifecycle, orphans, demo
pictures, image access, account deletion, and the blob → bucket migration script."""

import io
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from moto import mock_aws
from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Item, StoredImage, User, WardrobeImage
from app.services import images
from app.storage import DbStorage, get_storage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import migrate_images_to_r2  # noqa: E402

BUCKET = "smartwardrobe-media"
TAGS = {"is_clothing": True, "category": "top"}


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def webp() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 6), (1, 2, 3)).save(buf, "WEBP")
    return buf.getvalue()


@pytest.fixture
def s3(monkeypatch):
    """STORAGE_BACKEND=s3 against an in-memory bucket."""
    s = get_settings()
    with mock_aws():
        for name, value in (("storage_backend", "s3"), ("s3_bucket", BUCKET), ("s3_access_key_id", "k"),
                            ("s3_secret_access_key", "s"), ("s3_endpoint_url", ""), ("s3_region", "us-east-1")):
            monkeypatch.setattr(s, name, value)
        get_storage.cache_clear()
        storage = get_storage()
        storage.client.create_bucket(Bucket=BUCKET)
        yield storage
    get_storage.cache_clear()


def bucket_keys(storage) -> set[str]:
    return {k for k, _ in storage.list_keys(None)}


def upload(client, headers) -> str:
    r = client.post("/items/analyze", files={"image": ("d.png", png(), "image/png")}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["image_key"]


def register(client, email="other@example.com") -> dict:
    r = client.post("/auth/register", json={"email": email, "password": "supersecret1"})
    return {"Authorization": f"Bearer {r.json()['access']}"}


def wi(key: str) -> WardrobeImage | None:
    with SessionLocal() as db:
        return db.get(WardrobeImage, key)


# ── presigned links on the private bucket ─────────────────────────────────

def test_presigned_url_and_lifetime(client, auth, s3, fake_ai):
    fake_ai.respond = lambda call, model: TAGS
    key = upload(client, auth)
    head = s3.client.head_object(Bucket=BUCKET, Key=key)
    assert head["CacheControl"] == "private, max-age=900" and head["ContentType"] == "image/webp"

    item = client.post("/items", json={"image_key": key, "category": "top"}, headers=auth).json()
    assert item["image_key"] == key
    url = urlparse(item["image_url"])
    q = parse_qs(url.query)
    assert url.path.endswith(f"/{BUCKET}/{key}") or url.path == f"/{key}"
    assert q["X-Amz-Expires"] == ["900"] and "X-Amz-Signature" in q
    # a fresh link on every response (§14 C4), same image_key
    again = client.get("/items", headers=auth).json()[0]
    assert again["image_key"] == key and again["image_url"].startswith(f"{url.scheme}://{url.netloc}")
    # the API no longer serves bytes in bucket mode
    assert client.get(f"/images/{key}", headers=auth).status_code == 404


def test_presigned_url_lifetime_is_a_setting(s3, monkeypatch):
    monkeypatch.setattr(get_settings(), "image_url_seconds", 120)
    get_storage.cache_clear()
    assert parse_qs(urlparse(get_storage().url("u/x/y.webp")).query)["X-Amz-Expires"] == ["120"]


# ── wardrobe_images lifecycle ─────────────────────────────────────────────

def test_analyze_writes_an_orphan_row_that_create_attaches(client, auth, fake_ai):
    fake_ai.respond = lambda call, model: TAGS
    key = upload(client, auth)
    row = wi(key)
    assert row.attached_at is None and row.item_id is None and row.content_type == "image/webp"
    assert row.bytes > 0 and max(row.width, row.height) == 400  # 300×400, under the 1024 cap

    item = client.post("/items", json={"image_key": key, "category": "top"}, headers=auth).json()
    row = wi(key)
    assert row.attached_at is not None and str(row.item_id) == item["id"]

    assert client.delete(f"/items/{item['id']}", headers=auth).status_code == 204
    assert wi(key) is None
    with SessionLocal() as db:
        assert db.get(StoredImage, key) is None


def test_failed_bucket_delete_leaves_an_orphan_for_cleanup(client, auth, s3, fake_ai):
    fake_ai.respond = lambda call, model: TAGS
    key = upload(client, auth)
    item = client.post("/items", json={"image_key": key, "category": "top"}, headers=auth).json()

    def boom(db, keys):
        raise RuntimeError("bucket down")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(s3, "delete", boom)
        assert client.delete(f"/items/{item['id']}", headers=auth).status_code == 204  # the item is gone anyway
    assert client.get("/items", headers=auth).json() == []
    row = wi(key)
    assert row is not None and row.attached_at is None and row.item_id is None
    assert key in bucket_keys(s3)


def test_cleanup_removes_only_orphans_older_than_24h(client, auth, s3, fake_ai):
    fake_ai.respond = lambda call, model: TAGS
    old, fresh, kept = upload(client, auth), upload(client, auth), upload(client, auth)
    client.post("/items", json={"image_key": kept, "category": "top"}, headers=auth)
    with SessionLocal() as db:
        for key in (old, kept):  # kept is attached: age doesn't matter
            db.get(WardrobeImage, key).created_at = datetime.now(timezone.utc) - timedelta(hours=25)
        db.commit()
        dry = images.cleanup_orphans(db, dry_run=True)
        assert dry.orphan_rows == [old] and old in bucket_keys(s3)
        report = images.cleanup_orphans(db)
    assert report.orphan_rows == [old]
    assert wi(old) is None and old not in bucket_keys(s3)
    assert wi(fresh) is not None and fresh in bucket_keys(s3)
    assert wi(kept) is not None and kept in bucket_keys(s3)


def test_cleanup_picks_up_a_failed_delete_a_day_later(client, auth, fake_ai):
    fake_ai.respond = lambda call, model: TAGS
    key = upload(client, auth)
    item = client.post("/items", json={"image_key": key, "category": "top"}, headers=auth).json()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(DbStorage, "delete", lambda self, db, keys: (_ for _ in ()).throw(RuntimeError("down")))
        client.delete(f"/items/{item['id']}", headers=auth)
    with SessionLocal() as db:
        assert images.cleanup_orphans(db).orphan_rows == []  # uploaded just now
        assert images.cleanup_orphans(db, now=datetime.now(timezone.utc) + timedelta(hours=25)).orphan_rows == [key]
        assert db.get(StoredImage, key) is None and db.get(WardrobeImage, key) is None


def test_reconcile_both_ways(client, auth, s3, fake_ai):
    fake_ai.respond = lambda call, model: TAGS
    key = upload(client, auth)
    client.post("/items", json={"image_key": key, "category": "top"}, headers=auth)
    s3.put(None, "u/" + "a" * 32 + "/stray.webp", webp(), "image/webp")  # no row, no item
    with SessionLocal() as db:
        user = db.scalar(select(User))
        legacy = f"u/{user.id.hex}/legacy.webp"  # an item, no row yet (before the migration script)
        db.add(Item(user_id=user.id, image_key=legacy, category="top"))
        db.add(images.row(f"u/{user.id.hex}/lost.webp", user.id, webp(), attached_at=datetime.now(timezone.utc)))
        db.commit()
        s3.put(db, legacy, webp(), "image/webp")

        assert images.reconcile(db).stray_objects == []  # everything is younger than 24 h
        later = datetime.now(timezone.utc) + timedelta(hours=25)
        report = images.reconcile(db, now=later)
    assert report.stray_objects == ["u/" + "a" * 32 + "/stray.webp"]
    assert report.missing_objects == [f"u/{user.id.hex}/lost.webp"]
    assert bucket_keys(s3) == {key, legacy}


# ── shared demo pictures ──────────────────────────────────────────────────

def test_demo_pictures_are_uploaded_once_and_never_deleted(client, s3):
    a = {"Authorization": f"Bearer {client.post('/auth/demo', json={}).json()['access']}"}
    b = {"Authorization": f"Bearer {client.post('/auth/demo', json={}).json()['access']}"}
    assert len(bucket_keys(s3)) == 17 and all(k.startswith("demo/") for k in bucket_keys(s3))
    with SessionLocal() as db:
        rows = db.scalars(select(WardrobeImage)).all()
        assert len(rows) == 17 and all(r.user_id is None and r.attached_at is not None for r in rows)

    items = client.get("/items", headers=a).json()
    assert client.delete(f"/items/{items[0]['id']}", headers=a).status_code == 204
    assert client.delete("/me", headers=b).status_code == 204
    with SessionLocal() as db:
        assert images.cleanup_orphans(db, now=datetime.now(timezone.utc) + timedelta(days=30)).orphan_rows == []
        assert images.reconcile(db, now=datetime.now(timezone.utc) + timedelta(days=30)).stray_objects == []
        assert db.query(WardrobeImage).count() == 17
    assert len(bucket_keys(s3)) == 17


def test_copy_shared_image_gives_the_item_its_own_object(client, s3):
    client.post("/auth/demo", json={})
    with SessionLocal() as db:
        demo_item = db.scalar(select(Item))
        owner = User(email="real@example.com", password_hash="x")
        db.add(owner)
        db.flush()
        item = Item(user_id=owner.id, image_key=demo_item.image_key, category=demo_item.category)
        db.add(item)
        db.flush()
        images.copy_shared_image(db, owner, item)
        db.commit()
        assert item.image_key.startswith(f"u/{owner.id.hex}/")
        row = db.get(WardrobeImage, item.image_key)
        assert row.user_id == owner.id and row.item_id == item.id and row.attached_at is not None
        assert row.width > 0 and row.content_type == "image/webp"
    assert item.image_key in bucket_keys(s3) and demo_item.image_key in bucket_keys(s3)


# ── who may see an image (db storage mode) ────────────────────────────────

def test_unauthorized_image_access(client, auth, fake_ai):
    fake_ai.respond = lambda call, model: TAGS
    key = upload(client, auth)
    assert client.get(f"/images/{key}").status_code == 401
    assert client.get(f"/images/{key}", headers=auth).status_code == 200
    other = register(client)
    assert client.get(f"/images/{key}", headers=other).status_code == 404  # not "forbidden": no hint it exists
    demo = {"Authorization": f"Bearer {client.post('/auth/demo', json={}).json()['access']}"}
    assert client.get("/images/demo/white-tee.webp", headers=demo).status_code == 200
    assert client.get("/images/demo/white-tee.webp", headers=other).status_code == 404
    assert client.get(f"/images/{key}", headers=demo).status_code == 404


# ── account deletion ──────────────────────────────────────────────────────

def test_account_deletion_clears_the_users_prefix(client, auth, s3, fake_ai):
    fake_ai.respond = lambda call, model: TAGS
    other = register(client)
    mine = [upload(client, auth) for _ in range(2)]
    client.post("/items", json={"image_key": mine[0], "category": "top"}, headers=auth)
    theirs = upload(client, other)
    assert client.delete("/me", headers=auth).status_code == 204
    assert bucket_keys(s3) == {theirs}
    with SessionLocal() as db:
        assert set(db.scalars(select(WardrobeImage.key))) == {theirs}


def test_account_deletion_survives_a_bucket_outage(client, auth, s3, fake_ai, monkeypatch):
    fake_ai.respond = lambda call, model: TAGS
    key = upload(client, auth)
    monkeypatch.setattr(s3, "delete_prefix", lambda db, prefix: (_ for _ in ()).throw(RuntimeError("down")))
    assert client.delete("/me", headers=auth).status_code == 204
    assert client.get("/me", headers=auth).status_code == 401
    with SessionLocal() as db:
        assert db.get(WardrobeImage, key) is None
        # reconcile removes the leftover object later
        assert images.reconcile(db, now=datetime.now(timezone.utc) + timedelta(hours=25)).stray_objects == [key]


# ── scripts/migrate_images_to_r2.py ───────────────────────────────────────

def test_migrate_images_to_r2(client, auth, fake_ai):
    fake_ai.respond = lambda call, model: TAGS
    # db mode, as production is today: a saved item, an unsaved upload, a pre-05a blob without a row,
    # shared demo pictures, and a blob of a user who no longer exists
    saved = upload(client, auth)
    client.post("/items", json={"image_key": saved, "category": "top"}, headers=auth)
    unsaved = upload(client, auth)
    client.post("/auth/demo", json={})
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.is_demo.is_(False)))
        legacy = f"u/{user.id.hex}/legacy.webp"
        db.add(StoredImage(key=legacy, data=webp(), content_type="image/webp"))
        db.add(Item(user_id=user.id, image_key=legacy, category="bottom"))
        db.add(StoredImage(key=f"u/{uuid.uuid4().hex}/gone.webp", data=webp(), content_type="image/webp"))
        db.commit()

    s = get_settings()
    with mock_aws(), pytest.MonkeyPatch.context() as mp:
        for name, value in (("s3_bucket", BUCKET), ("s3_access_key_id", "k"), ("s3_secret_access_key", "s"),
                            ("s3_region", "us-east-1")):
            mp.setattr(s, name, value)
        bucket = migrate_images_to_r2.S3Storage()  # whatever STORAGE_BACKEND says
        bucket.client.create_bucket(Bucket=BUCKET)

        dry = migrate_images_to_r2.migrate(SessionLocal, bucket, dry_run=True, page=4)
        assert bucket_keys(bucket) == set()
        assert (dry.images, dry.uploaded, dry.rows_written, dry.no_owner, dry.unattached) == (21, 20, 1, 1, 0)
        assert migrate_images_to_r2.verify(SessionLocal, bucket)["rows_without_object"] == 19

        done = migrate_images_to_r2.migrate(SessionLocal, bucket, page=4)
        assert (done.uploaded, done.rows_written, done.no_owner) == (20, 1, 1)
        assert len(bucket_keys(bucket)) == 20
        with SessionLocal() as db:
            row = db.get(WardrobeImage, legacy)
            assert row.user_id == user.id and row.item_id is not None and row.attached_at is not None
            assert db.get(WardrobeImage, unsaved).attached_at is None  # still an orphan: cleanup's job
        head = bucket.client.head_object(Bucket=BUCKET, Key=saved)
        assert head["CacheControl"] == "private, max-age=900"
        assert migrate_images_to_r2.verify(SessionLocal, bucket) == {
            "items_without_row": 0, "images_without_row": 1, "rows_without_object": 0,  # 1 = the gone user's blob
        }

        again = migrate_images_to_r2.migrate(SessionLocal, bucket, page=4)  # idempotent
        assert (again.uploaded, again.rows_written, again.already_done) == (0, 0, 20)
