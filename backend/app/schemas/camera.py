from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CameraCreate(BaseModel):
    name: str
    location: str | None = None
    rtsp_url: str | None = None


class CameraUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    rtsp_url: str | None = None
    is_active: bool | None = None


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str | None
    rtsp_url: str | None
    is_active: bool
    owner_id: int | None
    created_at: datetime
    updated_at: datetime
    # Status of this camera's most recent monitoring/upload job, if any.
    # Lets the camera list render a status chip (idle/live/error) from the
    # single GET /api/cameras response instead of one extra GET .../jobs
    # call per camera.
    latest_job_status: str | None = None


class CameraTestConnectionRequest(BaseModel):
    rtsp_url: str


class CameraSnapshotInfo(BaseModel):
    """Freshness metadata for the live snapshot, separate from the image
    bytes themselves so the frontend can show "updated Xs ago" without
    re-fetching/decoding the image just to read a timestamp. Many public
    webcams (see app/seed.py) only refresh their source every few minutes,
    so this tells the operator whether they're looking at something
    current or a stale frame, instead of a view that just looks frozen."""

    exists: bool
    last_updated: datetime | None = None
