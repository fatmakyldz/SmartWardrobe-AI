"""AI foundation: users/items/outfits fields, ten new tables, item_ids → outfit_items

See docs/AI-00-foundation.md §2. outfits.item_ids and images stay until 0003_cleanup.

Revision ID: 0002_ai_foundation
Revises: 9d38cab9fd49
Create Date: 2026-10-19

"""
import logging
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_ai_foundation"
down_revision: Union[str, Sequence[str], None] = "9d38cab9fd49"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # ── AI telemetry first: items/outfits point at ai_requests ─────────────
    op.create_table(
        "ai_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),  # no FK on purpose (pseudonymous)
        sa.Column("feature", sa.String(length=40), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("final_provider", sa.String(length=40), nullable=True),
        sa.Column("final_model", sa.String(length=120), nullable=True),
        sa.Column("final_model_class", sa.String(length=40), nullable=True),
        sa.Column("input_tokens_total", sa.Integer(), nullable=False),
        sa.Column("output_tokens_total", sa.Integer(), nullable=False),
        sa.Column("cost_usd_micro_total", sa.Integer(), nullable=False),
        sa.Column("latency_ms_total", sa.Integer(), nullable=False),
        sa.Column("attempts_count", sa.Integer(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_requests_subject_id_created_at", "ai_requests", ["subject_id", "created_at"])
    op.create_index("ix_ai_requests_feature_created_at", "ai_requests", ["feature", "created_at"])

    op.create_table(
        "ai_request_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd_micro", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["ai_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "attempt_no"),
    )
    op.create_index("ix_ai_request_attempts_provider_created_at", "ai_request_attempts", ["provider", "created_at"])

    # ── new fields on existing tables ─────────────────────────────────────
    # updated_at is added nullable, back-filled from created_at, then made NOT NULL (below).
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("email_verified_at", TS, nullable=True))
        b.add_column(sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
        b.add_column(sa.Column("style_profile", sa.JSON(), nullable=True))
        b.add_column(sa.Column("style_summary", sa.Text(), nullable=True))
        b.add_column(sa.Column("style_summary_at", TS, nullable=True))
        b.add_column(sa.Column("plan", sa.String(length=20), server_default="free", nullable=False))
        b.add_column(sa.Column("onboarding_completed_at", TS, nullable=True))
        b.add_column(sa.Column("timezone", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("updated_at", TS, nullable=True))

    with op.batch_alter_table("items") as b:
        b.add_column(sa.Column("brand", sa.String(length=80), server_default="", nullable=False))
        b.add_column(sa.Column("material", sa.String(length=40), server_default="", nullable=False))
        b.add_column(sa.Column("is_favorite", sa.Boolean(), server_default=sa.text("false"), nullable=False))
        b.add_column(sa.Column("wear_count", sa.Integer(), server_default="0", nullable=False))
        b.add_column(sa.Column("last_worn_at", TS, nullable=True))
        b.add_column(sa.Column("archived_at", TS, nullable=True))
        b.add_column(sa.Column("ai_tags_raw", sa.JSON(), nullable=True))
        b.add_column(sa.Column("ai_confidence", sa.Float(), nullable=True))
        b.add_column(sa.Column("ai_request_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("updated_at", TS, nullable=True))
        b.create_foreign_key("items_ai_request_id_fkey", "ai_requests", ["ai_request_id"], ["id"], ondelete="SET NULL")

    with op.batch_alter_table("outfits") as b:
        b.add_column(sa.Column("source", sa.String(length=20), server_default="ai", nullable=False))
        b.add_column(sa.Column("prompt_version", sa.String(length=40), nullable=True))
        b.add_column(sa.Column("ai_request_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("worn_at", TS, nullable=True))
        b.add_column(sa.Column("updated_at", TS, nullable=True))
        b.create_foreign_key("outfits_ai_request_id_fkey", "ai_requests", ["ai_request_id"], ["id"], ondelete="SET NULL")

    # ── new tables ────────────────────────────────────────────────────────
    op.create_table(
        "outfit_items",
        sa.Column("outfit_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("slot", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["outfit_id"], ["outfits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("outfit_id", "item_id"),
    )
    op.create_index("ix_outfit_items_item_id", "outfit_items", ["item_id"])

    op.create_table(
        "feedback_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("outfit_id", sa.Uuid(), nullable=True),
        sa.Column("item_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["outfit_id"], ["outfits.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_events_user_id_created_at", "feedback_events", ["user_id", "created_at"])

    op.create_table(
        "wardrobe_images",
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),  # NULL = shared system object (demo images)
        sa.Column("item_id", sa.Uuid(), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("attached_at", TS, nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_wardrobe_images_user_id", "wardrobe_images", ["user_id"])
    # Partial on Postgres; plain index on SQLite.
    op.create_index(
        "ix_wardrobe_images_attached_at",
        "wardrobe_images",
        ["attached_at"],
        postgresql_where=sa.text("attached_at IS NULL"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("device_label", sa.String(length=120), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS, nullable=True),
        sa.Column("replaced_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_used_at", TS, nullable=True),
        sa.ForeignKeyConstraint(["replaced_by"], ["refresh_tokens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("used_at", TS, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_tokens_user_id_purpose", "auth_tokens", ["user_id", "purpose"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("provider_ref", sa.String(length=200), nullable=True),
        sa.Column("current_period_end", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_user_id_status", "subscriptions", ["user_id", "status"])
    op.create_index(
        "uq_subscriptions_provider_ref",
        "subscriptions",
        ["provider", "provider_ref"],
        unique=True,
        postgresql_where=sa.text("provider_ref IS NOT NULL"),
    )

    op.create_table(
        "usage_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("feature", sa.String(length=40), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "feature", "period_start"),
    )

    op.create_table(
        "entitlement_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan_override", sa.String(length=20), nullable=True),
        sa.Column("feature", sa.String(length=40), nullable=True),
        sa.Column("limits", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("starts_at", TS, nullable=False),
        sa.Column("ends_at", TS, nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint(
            "plan_override IS NOT NULL OR feature IS NOT NULL OR limits IS NOT NULL",
            name="ck_entitlement_grants_grants_something",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entitlement_grants_user_id_ends_at", "entitlement_grants", ["user_id", "ends_at"])

    # ── data ──────────────────────────────────────────────────────────────
    migrate_data(op.get_bind())

    for table in ("users", "items", "outfits"):
        with op.batch_alter_table(table) as b:
            b.alter_column("updated_at", existing_type=TS, nullable=False)


# Lightweight table definitions (Core): the data step must not depend on app.models,
# which will keep changing after this revision.
_users = sa.table("users", sa.column("plan", sa.String), sa.column("token_version", sa.Integer),
                  sa.column("created_at", TS), sa.column("updated_at", TS))
_items = sa.table("items", sa.column("id", sa.Uuid), sa.column("user_id", sa.Uuid), sa.column("category", sa.String),
                  sa.column("created_at", TS), sa.column("updated_at", TS))
_outfits = sa.table("outfits", sa.column("id", sa.Uuid), sa.column("user_id", sa.Uuid), sa.column("item_ids", sa.JSON),
                    sa.column("rating", sa.Integer), sa.column("source", sa.String),
                    sa.column("created_at", TS), sa.column("updated_at", TS))
_outfit_items = sa.table("outfit_items", sa.column("outfit_id", sa.Uuid), sa.column("item_id", sa.Uuid),
                         sa.column("position", sa.Integer), sa.column("slot", sa.String))
_feedback = sa.table("feedback_events", sa.column("id", sa.Uuid), sa.column("user_id", sa.Uuid),
                     sa.column("outfit_id", sa.Uuid), sa.column("item_id", sa.Uuid), sa.column("kind", sa.String),
                     sa.column("created_at", TS))

PAGE = 500
SKIP_REASONS = ("deleted_item", "foreign_item", "duplicate_id", "invalid_id")


def _parse(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def plan_outfit_data(conn):
    """Read-only: yield (outfit_items rows, feedback_events rows, skipped counts) per page of outfits.

    Only reads columns that exist since 0001, so scripts/preview_0002_data_step.py can run it on the
    production database before the migration.
    """
    last_id = None
    while True:
        q = sa.select(_outfits.c.id, _outfits.c.user_id, _outfits.c.item_ids, _outfits.c.rating, _outfits.c.created_at)
        if last_id is not None:
            q = q.where(_outfits.c.id > last_id)
        page = conn.execute(q.order_by(_outfits.c.id).limit(PAGE)).all()
        if not page:
            return
        last_id = page[-1].id

        wanted = {i for o in page for i in map(_parse, o.item_ids or []) if i is not None}
        items = {}
        if wanted:
            rows = conn.execute(sa.select(_items.c.id, _items.c.user_id, _items.c.category).where(_items.c.id.in_(wanted)))
            items = {r.id: r for r in rows}

        links, events = [], []
        skipped = dict.fromkeys(SKIP_REASONS, 0)
        for o in page:
            seen: set[uuid.UUID] = set()
            for raw in o.item_ids or []:
                item_id = _parse(raw)
                item = items.get(item_id)
                if item_id is None:
                    skipped["invalid_id"] += 1
                elif item is None:
                    skipped["deleted_item"] += 1
                elif item.user_id != o.user_id:
                    skipped["foreign_item"] += 1
                elif item_id in seen:
                    skipped["duplicate_id"] += 1
                else:
                    seen.add(item_id)
                    links.append({"outfit_id": o.id, "item_id": item_id, "position": len(seen) - 1,
                                  "slot": item.category})
            if o.rating:
                events.append({"id": uuid.uuid4(), "user_id": o.user_id, "outfit_id": o.id, "item_id": None,
                               "kind": "like" if o.rating > 0 else "dislike", "created_at": o.created_at})
        yield len(page), links, events, skipped


def summarize(conn, write: bool = False) -> dict[str, int]:
    """Walk the plan; insert the rows when write=True. Returns totals (outfits, links, events, skips)."""
    totals = dict.fromkeys(("outfits", "outfit_items", "feedback_events", *SKIP_REASONS), 0)
    for n, links, events, skipped in plan_outfit_data(conn):
        if write and links:
            conn.execute(sa.insert(_outfit_items), links)
        if write and events:
            conn.execute(sa.insert(_feedback), events)
        totals["outfits"] += n
        totals["outfit_items"] += len(links)
        totals["feedback_events"] += len(events)
        for reason, count in skipped.items():
            totals[reason] += count
    return totals


def migrate_data(conn) -> None:
    """item_ids → outfit_items, rating → feedback_events, plan/token_version, updated_at back-fill."""
    conn.execute(sa.update(_users).values(plan="free", token_version=0))
    for t in (_users, _items, _outfits):
        conn.execute(sa.update(t).where(t.c.updated_at.is_(None)).values(updated_at=t.c.created_at))
    conn.execute(sa.update(_outfits).values(source="ai"))
    totals = summarize(conn, write=True)
    logging.getLogger("alembic.runtime.migration").info("0002 data step: %s", totals)


def downgrade() -> None:
    op.drop_index("ix_entitlement_grants_user_id_ends_at", table_name="entitlement_grants")
    op.drop_table("entitlement_grants")
    op.drop_table("usage_counters")
    op.drop_index("uq_subscriptions_provider_ref", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id_status", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("ix_auth_tokens_user_id_purpose", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_wardrobe_images_attached_at", table_name="wardrobe_images")
    op.drop_index("ix_wardrobe_images_user_id", table_name="wardrobe_images")
    op.drop_table("wardrobe_images")
    op.drop_index("ix_feedback_events_user_id_created_at", table_name="feedback_events")
    op.drop_table("feedback_events")
    op.drop_index("ix_outfit_items_item_id", table_name="outfit_items")
    op.drop_table("outfit_items")

    with op.batch_alter_table("outfits") as b:
        b.drop_constraint("outfits_ai_request_id_fkey", type_="foreignkey")
        for col in ("updated_at", "worn_at", "ai_request_id", "prompt_version", "source"):
            b.drop_column(col)
    with op.batch_alter_table("items") as b:
        b.drop_constraint("items_ai_request_id_fkey", type_="foreignkey")
        for col in ("updated_at", "ai_request_id", "ai_confidence", "ai_tags_raw", "archived_at", "last_worn_at",
                    "wear_count", "is_favorite", "material", "brand"):
            b.drop_column(col)
    with op.batch_alter_table("users") as b:
        for col in ("updated_at", "timezone", "onboarding_completed_at", "plan", "style_summary_at", "style_summary",
                    "style_profile", "token_version", "email_verified_at"):
            b.drop_column(col)

    op.drop_index("ix_ai_request_attempts_provider_created_at", table_name="ai_request_attempts")
    op.drop_table("ai_request_attempts")
    op.drop_index("ix_ai_requests_feature_created_at", table_name="ai_requests")
    op.drop_index("ix_ai_requests_subject_id_created_at", table_name="ai_requests")
    op.drop_table("ai_requests")
