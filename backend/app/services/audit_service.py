from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.auth import AuditLog


def log_action(
    db: Session,
    user_id: int | None,
    action: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    details: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_audit_logs(db: Session, page: int = 1, page_size: int = 25) -> tuple[list[AuditLog], int]:
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total
