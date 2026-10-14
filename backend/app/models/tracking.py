from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EventSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrackedObject(Base):
    __tablename__ = "tracked_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    processing_job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    track_number: Mapped[int] = mapped_column(Integer, nullable=False)  # tracker-assigned id, scoped to the job
    object_class: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    final_risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    dominant_color: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)

    processing_job: Mapped["ProcessingJob"] = relationship()  # noqa: F821
    observations: Mapped[list["ObjectObservation"]] = relationship(back_populates="tracked_object", cascade="all, delete-orphan")


class ObjectObservation(Base):
    __tablename__ = "object_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracked_object_id: Mapped[int] = mapped_column(ForeignKey("tracked_objects.id", ondelete="CASCADE"), nullable=False, index=True)
    frame_number: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_x1: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y1: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_x2: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y2: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_x: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_y: Mapped[float] = mapped_column(Float, nullable=False)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    star_risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    tracked_object: Mapped["TrackedObject"] = relationship(back_populates="observations")


class ActivityEvent(Base):
    """A human-readable, timestamped narration entry generated live while a
    video is analyzed — "Person #2 is moving erratically", "Weapon-like
    object detected", a periodic "still visible, normal" heartbeat, and
    risk-severity escalations. This is what the Video Detail page's live
    activity panel renders, and what GET /api/jobs/{id}/events replays for
    a completed job."""

    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    processing_job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    tracked_object_id: Mapped[int | None] = mapped_column(ForeignKey("tracked_objects.id", ondelete="SET NULL"), nullable=True)
    track_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    object_class: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    timestamp_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # status|anomaly|escalation|weapon
    severity: Mapped[EventSeverity] = mapped_column(Enum(EventSeverity, name="event_severity"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
