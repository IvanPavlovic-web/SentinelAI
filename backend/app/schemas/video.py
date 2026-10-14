from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.camera import JobStatus


class VideoSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int | None
    original_filename: str
    stored_filename: str
    file_size_bytes: int | None
    duration_seconds: float | None
    fps: float | None
    width: int | None
    height: int | None
    created_at: datetime


class ProcessingJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_source_id: int
    status: JobStatus
    progress_percent: float
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class VideoUploadResponse(BaseModel):
    video_source: VideoSourceRead
    processing_job: ProcessingJobRead
