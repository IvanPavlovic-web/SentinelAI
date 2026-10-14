"""add activity_events table

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy's Enum(PythonEnumClass) stores the member NAME by default
    # (not .value) — see job_status/incident_status/etc. in 0001, which are
    # all uppercase for the same reason. event_severity must match that
    # convention or every INSERT fails with "invalid input value".
    #
    # Separately: generic sa.Enum's create_type kwarg doesn't reliably
    # suppress the implicit CREATE TYPE that create_table() issues for an
    # inline enum column — only the Postgres-specific ENUM type honors it,
    # which is why this uses postgresql.ENUM explicitly for both the
    # standalone create() and the column definition below.
    event_severity = postgresql.ENUM("LOW", "MEDIUM", "HIGH", "CRITICAL", name="event_severity")
    event_severity.create(op.get_bind(), checkfirst=True)
    event_severity_col = postgresql.ENUM("LOW", "MEDIUM", "HIGH", "CRITICAL", name="event_severity", create_type=False)

    op.create_table(
        "activity_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processing_job_id", sa.Integer(), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tracked_object_id", sa.Integer(), sa.ForeignKey("tracked_objects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("track_number", sa.Integer(), nullable=True),
        sa.Column("object_class", sa.String(length=100), nullable=False),
        sa.Column("timestamp_seconds", sa.Float(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("severity", event_severity_col, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_activity_events_processing_job_id", "activity_events", ["processing_job_id"])
    op.create_index("ix_activity_events_object_class", "activity_events", ["object_class"])
    op.create_index("ix_activity_events_event_type", "activity_events", ["event_type"])
    op.create_index("ix_activity_events_severity", "activity_events", ["severity"])
    op.create_index("ix_activity_events_created_at", "activity_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("activity_events")
    postgresql.ENUM(name="event_severity").drop(op.get_bind(), checkfirst=True)
