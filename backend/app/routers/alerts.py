from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import require_roles
from app.models.incident import Incident, IncidentPriority
from app.services.alert_service import send_alert

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.post("/test")
def test_alert(current_user=Depends(require_roles("admin"))):
    """Sends a synthetic critical-priority alert through every configured
    channel (email/webhook), bypassing the severity/cooldown gate that
    normally applies, so an admin can confirm alert delivery is actually
    wired up (SMTP creds, webhook URL) before relying on it in production.
    Nothing is persisted; the Incident object exists only to format the
    message the same way a real one would."""
    fake = Incident(
        id=0,
        processing_job_id=0,
        camera_id=None,
        object_class="test",
        risk_score=99.9,
        priority=IncidentPriority.CRITICAL,
        summary=(
            "This is a test alert from SentinelAI. If you received this, "
            "alert delivery (email and/or webhook) is configured correctly."
        ),
    )
    return {"result": send_alert(fake, force=True)}
