"""initial schema - all 14 SentinelAI tables

Revision ID: 0001
Revises:
Create Date: 2026-10-14

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_role = sa.Enum("ADMIN", "ANALYST", "VIEWER", name="user_role")
    job_status = sa.Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="job_status")
    zone_severity = sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="zone_severity")
    incident_status = sa.Enum("OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED", name="incident_status")
    incident_priority = sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="incident_priority")

    # 1. users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default="VIEWER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role", "users", ["role"])

    # 2. refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jti", sa.String(64), nullable=False, unique=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"])

    # 3. audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.String(2000), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # 4. cameras
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("rtsp_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cameras_owner_id", "cameras", ["owner_id"])

    # 5. detection_models
    op.create_table(
        "detection_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("weights_path", sa.String(500), nullable=True),
        sa.Column("is_stub", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 6. video_sources
    op.create_table(
        "video_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("stored_filename", sa.String(500), nullable=False, unique=True),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_video_sources_camera_id", "video_sources", ["camera_id"])
    op.create_index("ix_video_sources_created_at", "video_sources", ["created_at"])

    # 7. processing_jobs
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_source_id", sa.Integer(), sa.ForeignKey("video_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("detection_model_id", sa.Integer(), sa.ForeignKey("detection_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", job_status, nullable=False, server_default="PENDING"),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_processing_jobs_video_source_id", "processing_jobs", ["video_source_id"])
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    op.create_index("ix_processing_jobs_celery_task_id", "processing_jobs", ["celery_task_id"])
    op.create_index("ix_processing_jobs_created_at", "processing_jobs", ["created_at"])

    # 8. zones
    op.create_table(
        "zones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("severity", zone_severity, nullable=False, server_default="MEDIUM"),
        sa.Column("polygon_json", sa.Text(), nullable=False),
        sa.Column("minimum_dwell_seconds", sa.Float(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_zones_camera_id", "zones", ["camera_id"])
    op.create_index("ix_zones_severity", "zones", ["severity"])

    # 9. rules
    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("object_classes", sa.String(500), nullable=False, server_default="person"),
        sa.Column("after_hours_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_threshold", sa.Float(), nullable=False, server_default="70"),
        sa.Column("consecutive_required", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rules_zone_id", "rules", ["zone_id"])
    op.create_index("ix_rules_is_active", "rules", ["is_active"])

    # 10. tracked_objects
    op.create_table(
        "tracked_objects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processing_job_id", sa.Integer(), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_number", sa.Integer(), nullable=False),
        sa.Column("object_class", sa.String(100), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("final_risk_score", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_tracked_objects_processing_job_id", "tracked_objects", ["processing_job_id"])
    op.create_index("ix_tracked_objects_object_class", "tracked_objects", ["object_class"])

    # 11. object_observations
    op.create_table(
        "object_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tracked_object_id", sa.Integer(), sa.ForeignKey("tracked_objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("frame_number", sa.Integer(), nullable=False),
        sa.Column("timestamp_seconds", sa.Float(), nullable=False),
        sa.Column("bbox_x1", sa.Float(), nullable=False),
        sa.Column("bbox_y1", sa.Float(), nullable=False),
        sa.Column("bbox_x2", sa.Float(), nullable=False),
        sa.Column("bbox_y2", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("centroid_x", sa.Float(), nullable=False),
        sa.Column("centroid_y", sa.Float(), nullable=False),
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("star_risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_object_observations_tracked_object_id", "object_observations", ["tracked_object_id"])
    op.create_index("ix_object_observations_created_at", "object_observations", ["created_at"])

    # 12. incidents
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processing_job_id", sa.Integer(), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tracked_object_id", sa.Integer(), sa.ForeignKey("tracked_objects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("rules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("object_class", sa.String(100), nullable=False),
        sa.Column("star_risk_score", sa.Float(), nullable=False),
        sa.Column("status", incident_status, nullable=False, server_default="OPEN"),
        sa.Column("priority", incident_priority, nullable=False, server_default="MEDIUM"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_incidents_processing_job_id", "incidents", ["processing_job_id"])
    op.create_index("ix_incidents_camera_id", "incidents", ["camera_id"])
    op.create_index("ix_incidents_object_class", "incidents", ["object_class"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_priority", "incidents", ["priority"])
    op.create_index("ix_incidents_detected_at", "incidents", ["detected_at"])

    # 13. incident_evidence
    op.create_table(
        "incident_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("frame_path", sa.String(1000), nullable=False),
        sa.Column("frame_number", sa.Integer(), nullable=True),
        sa.Column("timestamp_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_incident_evidence_incident_id", "incident_evidence", ["incident_id"])

    # 14. performance_metrics
    op.create_table(
        "performance_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processing_job_id", sa.Integer(), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("total_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("processing_fps", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("p95_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_cpu_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_ram_mb", sa.Float(), nullable=False, server_default="0"),
        sa.Column("queue_wait_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("incident_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_performance_metrics_processing_job_id", "performance_metrics", ["processing_job_id"])
    op.create_index("ix_performance_metrics_created_at", "performance_metrics", ["created_at"])


def downgrade() -> None:
    op.drop_table("performance_metrics")
    op.drop_table("incident_evidence")
    op.drop_table("incidents")
    op.drop_table("object_observations")
    op.drop_table("tracked_objects")
    op.drop_table("rules")
    op.drop_table("zones")
    op.drop_table("processing_jobs")
    op.drop_table("video_sources")
    op.drop_table("detection_models")
    op.drop_table("cameras")
    op.drop_table("audit_logs")
    op.drop_table("refresh_tokens")
    op.drop_table("users")

    sa.Enum(name="incident_priority").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="incident_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="zone_severity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="job_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
