from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class IncidentPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    processing_job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    tracked_object_id: Mapped[int | None] = mapped_column(ForeignKey("tracked_objects.id", ondelete="SET NULL"), nullable=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id", ondelete="SET NULL"), nullable=True)
    object_class: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(Enum(IncidentStatus, name="incident_status"), default=IncidentStatus.OPEN, nullable=False, index=True)
    priority: Mapped[IncidentPriority] = mapped_column(Enum(IncidentPriority, name="incident_priority"), default=IncidentPriority.MEDIUM, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    # Real-time alerting (app/services/alert_service.py): whether at least
    # one channel was actually attempted for this incident (not just
    # configured), and which ones succeeded, e.g. "email,webhook".
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_channels: Mapped[str | None] = mapped_column(String(100), nullable=True)

    evidence: Mapped[list["IncidentEvidence"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    frame_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    frame_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    incident: Mapped["Incident"] = relationship(back_populates="evidence")


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    processing_job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    total_frames: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_frames: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    processing_fps: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    p95_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_cpu_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_ram_mb: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    queue_wait_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    incident_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    processing_job: Mapped["ProcessingJob"] = relationship(back_populates="performance_metrics")  # noqa: F821
