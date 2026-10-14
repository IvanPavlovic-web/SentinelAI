"""add annotated_path to processing_jobs

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("annotated_path", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_jobs", "annotated_path")
