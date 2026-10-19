"""ai_requests.estimated_input_tokens: the gateway's pre-call estimate, for calibration

Revision ID: 0003_ai_estimate
Revises: 0002_ai_foundation
Create Date: 2026-10-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ai_estimate"
down_revision: Union[str, Sequence[str], None] = "0002_ai_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_requests") as b:
        b.add_column(sa.Column("estimated_input_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_requests") as b:
        b.drop_column("estimated_input_tokens")
