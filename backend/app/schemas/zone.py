from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.zone import ZoneSeverity


class ZoneCreate(BaseModel):
    camera_id: int
    name: str
    severity: ZoneSeverity = ZoneSeverity.MEDIUM
    polygon: list[tuple[float, float]]  # normalized [0,1] points
    minimum_dwell_seconds: float = 10.0

    @field_validator("polygon")
    @classmethod
    def validate_polygon(cls, v: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(v) < 3:
            raise ValueError("polygon must have at least 3 points")
        for x, y in v:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError("polygon points must be normalized to [0, 1]")
        return v


class ZoneUpdate(BaseModel):
    name: str | None = None
    severity: ZoneSeverity | None = None
    polygon: list[tuple[float, float]] | None = None
    minimum_dwell_seconds: float | None = None
    is_active: bool | None = None


class ZoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int
    name: str
    severity: ZoneSeverity
    polygon: list[tuple[float, float]]
    minimum_dwell_seconds: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RuleCreate(BaseModel):
    zone_id: int
    name: str
    object_classes: str = "person"
    after_hours_only: bool = False
    risk_threshold: float = 70.0
    consecutive_required: int = 3


class RuleUpdate(BaseModel):
    name: str | None = None
    object_classes: str | None = None
    after_hours_only: bool | None = None
    risk_threshold: float | None = None
    consecutive_required: int | None = None
    is_active: bool | None = None


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    zone_id: int
    name: str
    object_classes: str
    after_hours_only: bool
    risk_threshold: float
    consecutive_required: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
