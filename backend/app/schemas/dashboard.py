from __future__ import annotations

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_cameras: int
    active_cameras: int
    total_videos: int
    jobs_pending: int
    jobs_processing: int
    jobs_completed: int
    jobs_failed: int
    open_incidents: int
    incidents_last_24h: int
    incidents_by_priority: dict[str, int]


class PerformancePoint(BaseModel):
    job_id: int
    created_at: str
    processing_fps: float
    avg_latency_ms: float
    p95_latency_ms: float
    avg_cpu_percent: float
    avg_ram_mb: float
    incident_count: int


class DashboardPerformance(BaseModel):
    points: list[PerformancePoint]


class HourlyIncidentCount(BaseModel):
    hour: int  # 0-23, UTC
    count: int


class CameraIncidentCount(BaseModel):
    camera_id: int
    camera_name: str
    count: int
    avg_risk_score: float


class ObjectClassIncidentCount(BaseModel):
    object_class: str
    count: int


class DailyIncidentCount(BaseModel):
    date: str  # YYYY-MM-DD, UTC
    count: int


class IncidentAnalytics(BaseModel):
    by_hour: list[HourlyIncidentCount]
    by_camera: list[CameraIncidentCount]
    by_object_class: list[ObjectClassIncidentCount]
    by_day: list[DailyIncidentCount]
