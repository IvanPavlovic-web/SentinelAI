from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.incident import IncidentPriority, IncidentStatus


class IncidentEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    frame_path: str
    frame_number: int | None
    timestamp_seconds: float | None
    created_at: datetime


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    processing_job_id: int
    camera_id: int | None
    zone_id: int | None
    tracked_object_id: int | None
    rule_id: int | None
    object_class: str
    risk_score: float
    status: IncidentStatus
    priority: IncidentPriority
    summary: str
    resolution_notes: str | None
    resolved_by: int | None
    resolved_at: datetime | None
    detected_at: datetime
    alert_sent: bool
    alert_channels: str | None
    evidence: list[IncidentEvidenceRead] = []


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus
    resolution_notes: str | None = None


class PaginatedIncidents(BaseModel):
    items: list[IncidentRead]
    total: int
    page: int
    page_size: int
