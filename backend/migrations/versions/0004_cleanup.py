"""cleanup: drop the images blob table and outfits.item_ids (§2, §14 C9)

Applied in AI-09c, after the R2 migration was verified (22 Oct 2026) and the bucket had been live for a week.
Refuses to run while an item has no wardrobe_images row or an outfit only has item_ids. Data loss: photo
bytes left in `images` and the JSON id lists in outfits.item_ids are gone for good; the downgrade only
recreates empty structures. Take a Neon branch/backup first.

Revision ID: 0004_cleanup
Revises: 0003_ai_estimate
Create Date: 2026-10-20

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_cleanup"
down_revision: Union[str, Sequence[str], None] = "0003_ai_estimate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Refuse while something still depends on the old paths.
    missing = bind.scalar(sa.text(
        "SELECT count(*) FROM items i LEFT JOIN wardrobe_images w ON w.key = i.image_key WHERE w.key IS NULL"
    ))
    if missing:
        raise RuntimeError(f"{missing} item(s) have no wardrobe_images row; run scripts/migrate_images_to_r2.py first")
    # An outfit with no outfit_items rows is only "unmigrated" if its item_ids still name a live piece of the
    # same user. Outfits whose pieces were all deleted also have no rows (ON DELETE CASCADE) but a stale
    # non-empty list — those are fine to lose. Checked in Python, like 0002's planner did.
    unmigrated = _outfits_still_only_in_item_ids(bind)
    if unmigrated:
        raise RuntimeError(f"{unmigrated} outfit(s) have live pieces only in item_ids; 0002's data step did not run on them")

    op.drop_table("images")
    with op.batch_alter_table("outfits") as b:
        b.drop_column("item_ids")


_outfits = sa.table("outfits", sa.column("id", sa.Uuid), sa.column("user_id", sa.Uuid), sa.column("item_ids", sa.JSON))
_links = sa.table("outfit_items", sa.column("outfit_id", sa.Uuid))
_items = sa.table("items", sa.column("id", sa.Uuid), sa.column("user_id", sa.Uuid))


def _parse(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _outfits_still_only_in_item_ids(bind) -> int:
    bare = bind.execute(
        sa.select(_outfits.c.id, _outfits.c.user_id, _outfits.c.item_ids)
        .where(~sa.exists().where(_links.c.outfit_id == _outfits.c.id))
    ).all()
    count = 0
    for o in bare:
        ids = {_parse(x) for x in (o.item_ids or [])} - {None}
        if ids and bind.scalar(sa.select(sa.func.count()).select_from(_items)
                               .where(_items.c.id.in_(ids), _items.c.user_id == o.user_id)):
            count += 1
    return count


def downgrade() -> None:
    with op.batch_alter_table("outfits") as b:
        b.add_column(sa.Column("item_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.create_table(
        "images",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
