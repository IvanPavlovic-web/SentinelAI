"""support live-camera processing jobs

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("processing_jobs", "video_source_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("processing_jobs", sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=True))
    op.add_column("processing_jobs", sa.Column("is_live", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("processing_jobs", sa.Column("stop_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_processing_jobs_camera_id", "processing_jobs", ["camera_id"])

    # SQLAlchemy Enum(PyEnum) stores the member NAME; see 0001/0003 notes.
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'STOPPED'")


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_camera_id", table_name="processing_jobs")
    op.drop_column("processing_jobs", "stop_requested")
    op.drop_column("processing_jobs", "is_live")
    op.drop_column("processing_jobs", "camera_id")
    op.alter_column("processing_jobs", "video_source_id", existing_type=sa.Integer(), nullable=False)
    # Postgres cannot remove an enum value; STOPPED is left in place on downgrade.
