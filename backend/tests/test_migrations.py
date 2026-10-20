"""0002_ai_foundation: parity with the models, up/down/up, and the data step.

Runs against the test database (SQLite, or Postgres when TEST_DATABASE_URL is set).
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.db import Base, engine

BACKEND = Path(__file__).resolve().parents[1]
REV_0001 = "9d38cab9fd49"
NEW_TABLES = {
    "outfit_items", "ai_requests", "ai_request_attempts", "feedback_events", "wardrobe_images",
    "refresh_tokens", "auth_tokens", "subscriptions", "usage_counters", "entitlement_grants",
}


@pytest.fixture
def migrate():
    """Empty database; yields run(cmd, rev) that applies Alembic commands on it."""
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))

    def run(cmd, rev):
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        with engine.connect() as conn:
            cfg.attributes["connection"] = conn
            getattr(command, cmd)(cfg, rev)
            conn.commit()

    yield run
    run("downgrade", "base")
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))


def _diff() -> list:
    with engine.connect() as conn:
        return compare_metadata(MigrationContext.configure(conn), Base.metadata)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def test_upgrade_head_matches_models(migrate):
    migrate("upgrade", "head")
    assert _diff() == []
    assert NEW_TABLES <= set(sa.inspect(engine).get_table_names())


def test_downgrade_restores_0001_then_upgrade_again(migrate):
    migrate("upgrade", REV_0001)
    before = {t: _columns(t) for t in ("users", "items", "outfits", "images")}

    migrate("upgrade", "head")
    migrate("downgrade", REV_0001)
    assert not NEW_TABLES & set(sa.inspect(engine).get_table_names())
    assert {t: _columns(t) for t in before} == before

    migrate("upgrade", "head")
    assert _diff() == []


def _uid() -> uuid.UUID:
    return uuid.uuid4()


def _table(name: str, **types) -> sa.Table:
    """Reflect a table, overriding column types (SQLite reflects UUID columns as plain CHAR)."""
    pk = set(sa.inspect(engine).get_pk_constraint(name)["constrained_columns"])
    cols = [sa.Column(c, ty, primary_key=c in pk) for c, ty in types.items()]
    return sa.Table(name, sa.MetaData(), *cols, autoload_with=engine)


TS = sa.DateTime(timezone=True)


def _tables():
    return {
        "users": _table("users", id=sa.Uuid, created_at=TS),
        "items": _table("items", id=sa.Uuid, user_id=sa.Uuid, created_at=TS),
        "outfits": _table("outfits", id=sa.Uuid, user_id=sa.Uuid, item_ids=sa.JSON, created_at=TS),
    }


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def test_data_step_moves_item_ids_and_ratings(migrate):
    migrate("upgrade", REV_0001)
    t = _tables()
    created = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    me, other = _uid(), _uid()
    top, bottom, shoes, gone, foreign = _uid(), _uid(), _uid(), _uid(), _uid()
    o_plain, o_missing, o_rated = _uid(), _uid(), _uid()

    def user(uid, email):
        return dict(id=uid, email=email, password_hash="x", name="", locale="en", city="", lat=None, lon=None,
                    is_demo=False, created_at=created)

    def item(iid, owner, cat):
        return dict(id=iid, user_id=owner, image_key=f"u/{owner.hex}/{iid.hex}.webp", name="", category=cat,
                    subcategory="", colors=[], pattern="solid", warmth=3, formality=2, seasons=[], created_at=created)

    def outfit(oid, ids, rating):
        return dict(id=oid, user_id=me, occasion="casual", note="", weather={}, item_ids=[str(i) for i in ids],
                    title="t", reason="r", lang="en", rating=rating, created_at=created)

    with engine.begin() as conn:
        conn.execute(t["users"].insert(), [user(me, "me@example.com"), user(other, "other@example.com")])
        conn.execute(t["items"].insert(), [item(top, me, "top"), item(bottom, me, "bottom"), item(shoes, me, "shoes"),
                                           item(foreign, other, "top")])
        conn.execute(t["outfits"].insert(), [
            outfit(o_plain, [top, bottom], 0),
            # a deleted item, someone else's item, a repeat and a non-UUID are skipped; order of the rest is kept
            outfit(o_missing, [shoes, gone, foreign, top, shoes, "not-a-uuid"], 0),
            outfit(o_rated, [bottom, top], 1),
        ])

    # Dry run on the 0001 database (what production runs before merging): counts by reason, no writes.
    sys.path.insert(0, str(BACKEND / "scripts"))
    import preview_0002_data_step as preview

    with engine.connect() as conn:
        assert preview.preview(conn) == {
            "outfits": 3, "outfit_items": 6, "feedback_events": 1,
            "deleted_item": 1, "foreign_item": 1, "duplicate_id": 1, "invalid_id": 1,
        }
    assert "outfit_items" not in sa.inspect(engine).get_table_names()

    migrate("upgrade", "head")

    links_t = _table("outfit_items", outfit_id=sa.Uuid, item_id=sa.Uuid)
    events_t = _table("feedback_events", id=sa.Uuid, user_id=sa.Uuid, outfit_id=sa.Uuid, item_id=sa.Uuid, created_at=TS)
    users_t = _table("users", id=sa.Uuid, created_at=TS, updated_at=TS, email_verified_at=TS)
    outfits_t = _table("outfits", id=sa.Uuid, item_ids=sa.JSON)

    with engine.connect() as conn:
        got = {}
        for r in conn.execute(sa.select(links_t)):
            got.setdefault(r.outfit_id, []).append((r.position, r.item_id, r.slot))
        assert {k: sorted(v) for k, v in got.items()} == {
            o_plain: [(0, top, "top"), (1, bottom, "bottom")],
            o_missing: [(0, shoes, "shoes"), (1, top, "top")],
            o_rated: [(0, bottom, "bottom"), (1, top, "top")],
        }

        events = conn.execute(sa.select(events_t)).all()
        assert [(e.user_id, e.outfit_id, e.item_id, e.kind) for e in events] == [(me, o_rated, None, "like")]
        assert _utc(events[0].created_at) == created

        users = conn.execute(sa.select(users_t)).all()
        assert [(u.plan, u.token_version, u.email_verified_at) for u in users] == [("free", 0, None)] * 2
        assert all(u.updated_at == u.created_at for u in users)
        assert conn.execute(sa.text("SELECT DISTINCT source FROM outfits")).scalars().all() == ["ai"]
        # item_ids is untouched — still the read path
        raw = conn.execute(sa.select(outfits_t.c.item_ids).where(outfits_t.c.id == o_missing)).scalar_one()
        assert raw == [str(shoes), str(gone), str(foreign), str(top), str(shoes), "not-a-uuid"]


def test_mark_existing_verified_script(migrate):
    sys.path.insert(0, str(BACKEND / "scripts"))
    import mark_existing_verified as script

    migrate("upgrade", "head")
    users = _table("users", id=sa.Uuid, created_at=TS, updated_at=TS, email_verified_at=TS)
    created = datetime(2026, 9, 1, tzinfo=timezone.utc)
    base = dict(password_hash="x", name="", locale="en", city="", is_demo=False, created_at=created,
                updated_at=created, token_version=0, plan="free")
    with engine.begin() as conn:
        conn.execute(users.insert(), [
            {**base, "id": _uid(), "email": "a@example.com"},
            {**base, "id": _uid(), "email": "demo@example.com", "is_demo": True},
        ])
        assert script.run(conn, apply=False) == {"users": 2, "demo": 1, "to_mark": 1}
    with engine.connect() as conn:  # dry run wrote nothing
        assert conn.scalar(sa.text("SELECT count(*) FROM users WHERE email_verified_at IS NOT NULL")) == 0
    with engine.begin() as conn:
        script.run(conn, apply=True)
        assert script.run(conn, apply=False)["to_mark"] == 0
        rows = conn.execute(sa.select(users.c.email, users.c.email_verified_at, users.c.created_at)).all()
    marked = {r.email: r.email_verified_at for r in rows}
    assert marked["demo@example.com"] is None
    assert _utc(marked["a@example.com"]) == created


# ── 0004_cleanup: written in AI-05, applied in AI-09 ──────────────────────

def test_cleanup_revision_is_deferred(migrate):
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    assert ScriptDirectory.from_config(cfg).get_current_head() == "0003_ai_estimate"  # head is untouched

    # With the deferred folder added it upgrades and downgrades cleanly.
    def run(cmd, rev):
        c = Config(str(BACKEND / "alembic.ini"))
        c.set_main_option("script_location", str(BACKEND / "migrations"))
        folders = [str(BACKEND / "migrations" / d) for d in ("versions", "deferred")]
        c.set_main_option("version_locations", os.pathsep.join(folders))  # path_separator = os
        with engine.connect() as conn:
            c.attributes["connection"] = conn
            getattr(command, cmd)(c, rev)
            conn.commit()

    migrate("upgrade", "head")
    run("upgrade", "0004_cleanup")
    assert "images" not in sa.inspect(engine).get_table_names() and "item_ids" not in _columns("outfits")
    run("downgrade", "0003_ai_estimate")
    assert "images" in sa.inspect(engine).get_table_names() and "item_ids" in _columns("outfits")
