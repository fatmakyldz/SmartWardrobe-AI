"""cleanup: drop the images blob table and outfits.item_ids (§2, §14 C9)

NOT APPLIED YET — lives in migrations/deferred/ until AI-09; see the README there for the checklist.
Data loss: photo bytes left in `images` and the JSON id lists in outfits.item_ids are gone for good;
the downgrade only recreates empty structures.

Revision ID: 0004_cleanup
Revises: 0003_ai_estimate
Create Date: 2026-10-20

"""
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
    unmigrated = bind.scalar(sa.text(
        "SELECT count(*) FROM outfits o WHERE NOT EXISTS (SELECT 1 FROM outfit_items oi WHERE oi.outfit_id = o.id)"
        " AND o.item_ids IS NOT NULL AND CAST(o.item_ids AS TEXT) NOT IN ('[]', 'null')"
    ))
    if unmigrated:
        raise RuntimeError(f"{unmigrated} outfit(s) still only have item_ids")

    op.drop_table("images")
    with op.batch_alter_table("outfits") as b:
        b.drop_column("item_ids")


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
