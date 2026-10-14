from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rtsp_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    video_sources: Mapped[list["VideoSource"]] = relationship(back_populates="camera", cascade="all, delete-orphan")
    zones: Mapped[list["Zone"]] = relationship(back_populates="camera", cascade="all, delete-orphan")  # noqa: F821


class VideoSource(Base):
    __tablename__ = "video_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    camera: Mapped["Camera"] = relationship(back_populates="video_sources")
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="video_source", cascade="all, delete-orphan")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_source_id: Mapped[int] = mapped_column(ForeignKey("video_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    detection_model_id: Mapped[int | None] = mapped_column(ForeignKey("detection_models.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), default=JobStatus.PENDING, nullable=False, index=True)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    video_source: Mapped["VideoSource"] = relationship(back_populates="processing_jobs")
    detection_model: Mapped["DetectionModel"] = relationship(back_populates="processing_jobs")
    performance_metrics: Mapped[list["PerformanceMetric"]] = relationship(back_populates="processing_job", cascade="all, delete-orphan")  # noqa: F821


class DetectionModel(Base):
    __tablename__ = "detection_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    weights_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_stub: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="detection_model")
