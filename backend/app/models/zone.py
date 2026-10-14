from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ZoneSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[ZoneSeverity] = mapped_column(Enum(ZoneSeverity, name="zone_severity"), default=ZoneSeverity.MEDIUM, nullable=False, index=True)
    # Polygon stored as JSON-encoded list of normalized [x, y] points (0..1 relative to frame size).
    polygon_json: Mapped[str] = mapped_column(Text, nullable=False)
    minimum_dwell_seconds: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    camera: Mapped["Camera"] = relationship(back_populates="zones")  # noqa: F821
    rules: Mapped[list["Rule"]] = relationship(back_populates="zone", cascade="all, delete-orphan")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_classes: Mapped[str] = mapped_column(String(500), default="person", nullable=False)  # comma-separated
    after_hours_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_threshold: Mapped[float] = mapped_column(Float, default=70.0, nullable=False)
    consecutive_required: Mapped[int] = mapped_column(default=3, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    zone: Mapped["Zone"] = relationship(back_populates="rules")
