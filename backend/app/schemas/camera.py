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
