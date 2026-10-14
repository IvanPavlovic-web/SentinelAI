"""Live activity-log generation.

Turns raw per-observation signals (STAR-Risk score, motion-anomaly score,
detected object class, dominant color, on-screen position, movement
direction) into a throttled stream of human-readable ActivityEvent rows —
"A red car appeared in the right side of the frame", "Person #2 is moving
erratically", a risk-severity escalation, a weapon-class detection, a
movement-direction change, or a periodic "still visible, normal"
heartbeat. This is deliberately a small stateful class (one instance per
job, fed one observation at a time in temporal order) rather than a pure
function, since event emission depends on each track's recent history.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def classify_severity(risk_score: float) -> str:
    if risk_score >= 80:
        return "critical"
    if risk_score >= 60:
        return "high"
    if risk_score >= 40:
        return "medium"
    return "low"


def _subject(object_class: str, color: str, track_id: int) -> str:
    """'a red car (#3)' / 'a person (#1)' — color is skipped when unknown
    (e.g. a person's clothing varies too much for a single crop median to
    be meaningful) rather than ever inventing an attribute."""
    if color and color != "unknown":
        return f"a {color} {object_class} (#{track_id})"
    return f"a {object_class} (#{track_id})"


@dataclass
class _TrackState:
    last_severity: str = "low"
    last_anomaly_flagged: bool = False
    last_event_ts: float = -1_000_000.0
    weapon_already_flagged: bool = False
    seen: bool = False
    last_movement: str | None = None


@dataclass
class ActivityEventGenerator:
    """Call `observe(...)` once per tracked detection, in increasing
    timestamp order. Returns a list of (event_type, severity, description)
    tuples to persist — usually empty, since most observations don't
    warrant a new narration line."""

    track_states: dict[int, _TrackState] = field(default_factory=dict)

    def observe(
        self,
        track_id: int,
        object_class: str,
        risk_score: float,
        motion_anomaly: float,
        timestamp_seconds: float,
        dominant_color: str = "unknown",
        position: str = "the frame",
        movement: str = "stationary",
    ) -> list[tuple[str, str, str]]:
        state = self.track_states.setdefault(track_id, _TrackState())
        events: list[tuple[str, str, str]] = []
        subject = _subject(object_class, dominant_color, track_id)

        severity = classify_severity(risk_score)
        is_weapon = object_class.lower() in settings.weapon_class_names_set
        is_anomalous = motion_anomaly >= settings.ANOMALY_EVENT_THRESHOLD

        # First-ever sighting of this track: a full scene description —
        # what it is, what color, where it appeared.
        if not state.seen:
            events.append(
                (
                    "sighting",
                    severity,
                    f"{subject.capitalize()} appeared in {position}.",
                )
            )
            state.seen = True
            state.last_movement = movement

        if is_weapon and not state.weapon_already_flagged:
            events.append(
                (
                    "weapon",
                    "critical",
                    f"Weapon-like object detected on track #{track_id} ({object_class}).",
                )
            )
            state.weapon_already_flagged = True

        if is_anomalous and not state.last_anomaly_flagged:
            events.append(
                (
                    "anomaly",
                    severity if _SEVERITY_RANK[severity] >= _SEVERITY_RANK["medium"] else "medium",
                    f"{subject.capitalize()} is moving erratically in {position} "
                    f"(anomaly score {motion_anomaly:.2f}) — possible suspicious behavior.",
                )
            )
        state.last_anomaly_flagged = is_anomalous

        # Movement-direction change: "if it moves, report it" — but only
        # the transition itself (stationary -> moving, or a change of
        # direction), not every tick, or this would be as noisy as raw
        # per-frame coordinates.
        if movement != state.last_movement and state.last_movement is not None:
            events.append(
                (
                    "movement",
                    "low",
                    f"{subject.capitalize()} is now {movement} in {position}.",
                )
            )
        state.last_movement = movement

        if _SEVERITY_RANK[severity] > _SEVERITY_RANK[state.last_severity]:
            events.append(
                (
                    "escalation",
                    severity,
                    f"{subject.capitalize()} risk escalated to {severity.upper()} "
                    f"(STAR-Risk {risk_score:.1f}), {movement} in {position}.",
                )
            )
        state.last_severity = severity

        if not events and (timestamp_seconds - state.last_event_ts) >= settings.EVENT_HEARTBEAT_SECONDS:
            heartbeat_phrase = "continues moving normally" if severity == "low" else "remains at elevated risk"
            events.append(
                (
                    "status",
                    severity,
                    f"{subject.capitalize()} {heartbeat_phrase}, {movement} in {position} "
                    f"(STAR-Risk {risk_score:.1f}).",
                )
            )

        if events:
            state.last_event_ts = timestamp_seconds

        return events
