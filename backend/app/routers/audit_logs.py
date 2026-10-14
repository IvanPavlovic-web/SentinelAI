from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_roles
from app.db.base import get_db
from app.schemas.audit import PaginatedAuditLogs
from app.services import audit_service

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])


@router.get("", response_model=PaginatedAuditLogs)
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin")),
):
    items, total = audit_service.list_audit_logs(db, page, page_size)
    return PaginatedAuditLogs(items=items, total=total, page=page, page_size=page_size)
