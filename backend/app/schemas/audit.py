from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    action: str
    resource_type: str | None
    resource_id: int | None
    details: str | None
    ip_address: str | None
    created_at: datetime


class PaginatedAuditLogs(BaseModel):
    items: list[AuditLogRead]
    total: int
    page: int
    page_size: int
