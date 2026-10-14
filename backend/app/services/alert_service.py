"""Real-time alert delivery for incidents: email (SMTP) and a generic
webhook (Slack/Discord/PagerDuty/etc. all accept a plain JSON POST).

Delivery is strictly best-effort: a bad SMTP password, an unreachable
webhook, or alerting being entirely unconfigured must never fail or
delay the detection pipeline that calls `send_alert`. Every failure is
caught, logged, and reported back in the returned dict instead of
raised, and the incident itself is already committed to the database by
the time this runs.
"""
from __future__ import annotations

import smtplib
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.incident import Incident

logger = get_logger(__name__)

_PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# In-process cooldown tracker: (camera_or_job_id, object_class) -> last
# alert time. Lives only in this worker process's memory and resets on
# restart -- that's fine, since its only job is to stop one continuously
# re-detected object from paging someone every few seconds, not to be a
# durable record (the Incident rows themselves are the durable record).
_last_alert_at: dict[tuple, float] = {}


def _priority_value(priority) -> str:
    return getattr(priority, "value", priority)


def _cooldown_key(incident: Incident) -> tuple:
    return (incident.camera_id or incident.processing_job_id, incident.object_class)


def _passes_cooldown(incident: Incident) -> bool:
    key = _cooldown_key(incident)
    last = _last_alert_at.get(key, 0.0)
    if time.time() - last < settings.ALERT_COOLDOWN_SECONDS:
        return False
    _last_alert_at[key] = time.time()
    return True


def should_alert(incident: Incident) -> bool:
    """Whether this incident clears the configured severity threshold and
    per-(camera, class) cooldown. Does not check channel configuration --
    send_alert itself no-ops per-channel if a channel has no config."""
    if not settings.ALERT_ENABLED:
        return False
    if _PRIORITY_RANK.get(_priority_value(incident.priority), 0) < _PRIORITY_RANK.get(settings.ALERT_MIN_PRIORITY, 2):
        return False
    return _passes_cooldown(incident)


def _build_message(incident: Incident) -> tuple[str, str, dict]:
    priority = _priority_value(incident.priority)
    detected_at = incident.detected_at.isoformat() if incident.detected_at else datetime.now(timezone.utc).isoformat()
    subject = f"[SentinelAI] {priority.upper()} incident: {incident.object_class}"
    body = (
        f"{incident.summary}\n\n"
        f"Priority: {priority}\n"
        f"Risk: {incident.risk_score:.1f}\n"
        f"Camera ID: {incident.camera_id or 'n/a'}\n"
        f"Detected at: {detected_at}\n"
        f"Incident ID: {incident.id}\n"
    )
    payload = {
        "incident_id": incident.id,
        "priority": priority,
        "object_class": incident.object_class,
        "risk_score": incident.risk_score,
        "camera_id": incident.camera_id,
        "summary": incident.summary,
        "detected_at": detected_at,
    }
    return subject, body, payload


def _send_email(subject: str, body: str) -> bool:
    if not (settings.ALERT_SMTP_HOST and settings.ALERT_EMAIL_TO):
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.ALERT_EMAIL_FROM
        msg["To"] = settings.ALERT_EMAIL_TO
        with smtplib.SMTP(settings.ALERT_SMTP_HOST, settings.ALERT_SMTP_PORT, timeout=10) as server:
            if settings.ALERT_SMTP_USE_TLS:
                server.starttls()
            if settings.ALERT_SMTP_USER:
                server.login(settings.ALERT_SMTP_USER, settings.ALERT_SMTP_PASSWORD)
            server.sendmail(settings.ALERT_EMAIL_FROM, [settings.ALERT_EMAIL_TO], msg.as_string())
        return True
    except Exception as exc:  # noqa: BLE001 - alert delivery is best-effort
        logger.warning("Alert email delivery failed: %s", exc)
        return False


def _send_webhook(payload: dict) -> bool:
    if not settings.ALERT_WEBHOOK_URL:
        return False
    try:
        resp = httpx.post(settings.ALERT_WEBHOOK_URL, json=payload, timeout=10.0)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - alert delivery is best-effort
        logger.warning("Alert webhook delivery failed: %s", exc)
        return False


def send_alert(incident: Incident, force: bool = False) -> dict:
    """Sends `incident` to every configured channel. Returns
    {"attempted": bool, "email": bool|None, "webhook": bool|None} --
    None means that channel isn't configured (not that it failed).
    `force=True` skips the severity/cooldown gate (used by the manual
    POST /api/alerts/test endpoint so an admin can verify delivery
    without needing to manufacture a real critical incident)."""
    if not force and not should_alert(incident):
        return {"attempted": False, "email": None, "webhook": None}

    subject, body, payload = _build_message(incident)
    email_result = _send_email(subject, body) if settings.ALERT_SMTP_HOST else None
    webhook_result = _send_webhook(payload) if settings.ALERT_WEBHOOK_URL else None
    result = {"attempted": True, "email": email_result, "webhook": webhook_result}
    logger.info("Alert dispatched for incident %s: %s", incident.id, result)
    return result


def channels_summary(result: dict) -> str:
    """'email,webhook' for the channels that were actually attempted and
    succeeded, for persisting on Incident.alert_channels."""
    return ",".join(name for name in ("email", "webhook") if result.get(name) is True)
