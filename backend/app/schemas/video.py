from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

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
    video_source_id: int | None
    camera_id: int | None
    is_live: bool
    stop_requested: bool
    status: JobStatus
    progress_percent: float
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    # Internal filesystem path is never exposed to the client, only whether
    # an annotated preview exists, so the frontend knows whether to request
    # GET /api/jobs/{id}/annotated-video.
    annotated_path: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_annotated_video(self) -> bool:
        return bool(self.annotated_path)


class VideoUploadResponse(BaseModel):
    video_source: VideoSourceRead
    processing_job: ProcessingJobRead
