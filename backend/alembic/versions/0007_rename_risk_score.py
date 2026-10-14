"""rename star_risk_score -> risk_score (STAR-Risk branding dropped)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("object_observations", "star_risk_score", new_column_name="risk_score")
    op.alter_column("incidents", "star_risk_score", new_column_name="risk_score")


def downgrade() -> None:
    op.alter_column("incidents", "risk_score", new_column_name="star_risk_score")
    op.alter_column("object_observations", "risk_score", new_column_name="star_risk_score")
