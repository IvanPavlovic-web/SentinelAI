"""add dominant_color to tracked_objects

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tracked_objects",
        sa.Column("dominant_color", sa.String(length=50), nullable=False, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_column("tracked_objects", "dominant_color")
