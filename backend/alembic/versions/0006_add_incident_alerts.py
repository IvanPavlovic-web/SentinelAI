"""add alert_sent/alert_channels to incidents

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("alert_sent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("incidents", sa.Column("alert_channels", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "alert_channels")
    op.drop_column("incidents", "alert_sent")
