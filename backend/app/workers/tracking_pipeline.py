"""The shared per-detection pipeline: zone matching, dwell/motion-anomaly/
Risk scoring, persistence (tracked_objects/object_observations),
activity-log narration, and incident creation.

This is the one place that logic lives. Both the file-upload task
(process_video_task, replaying pre-collected detections in timestamp order)
and the live-camera task (process_live_camera_task, handling one real-time
frame at a time) call `handle_tracked_detection` per matched detection, so
a camera connected live and a video uploaded from disk are scored,
tracked, and narrated identically. Only how detections arrive differs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.algorithms.risk import calculate_motion_anomaly, calculate_risk, is_incident_triggered
from app.algorithms.tracker import CentroidIoUTracker, Detection, Track, centroid_distance
from app.core.config import settings
from app.core.logging import get_logger
from app.models.camera import ProcessingJob
from app.models.incident import Incident, IncidentEvidence, IncidentPriority
from app.models.tracking import ActivityEvent, EventSeverity, ObjectObservation, TrackedObject
from app.models.zone import Rule, Zone
from app.services.alert_service import channels_summary, send_alert
from app.workers.events import ActivityEventGenerator, _TrackState
from app.workers.visual_attributes import frame_position_label, movement_label

logger = get_logger(__name__)

LIVE_TRACKER_STATE_KEY_PREFIX = "sentinel:live_tracker_state:"
# Safety-net TTL on the persisted live-tracker-state blob: if a job's
# cleanup path is somehow never reached (worker crash mid-session), this
# still bounds how long the stale state sits in Redis, rather than forever.
LIVE_TRACKER_STATE_TTL_SECONDS = 3600


def associate_weapons_to_people(
    tracker: CentroidIoUTracker,
    matches: dict[int, Detection],
    width: int,
    height: int,
) -> dict[int, int]:
    """Returns {weapon_track_id: person_track_id} for every weapon-class
    track in this frame's matches that has an active person track within
    WEAPON_PERSON_ASSOCIATION_MAX_DISTANCE_RATIO of the frame diagonal.
    This is what turns two independent detections ("person", "knife") into
    one actionable fact ("this specific person is holding a knife") without
    needing re-ID or pose estimation -- just proximity between the two
    tracks' current centroids, which is enough at the distances CCTV/webcam
    footage typically operates at."""
    weapon_classes = settings.weapon_class_names_set
    person_tracks = [(pid, t) for pid, t in tracker.tracks.items() if t.active and t.object_class == "person" and t.centroids]
    if not person_tracks:
        return {}

    max_distance = settings.WEAPON_PERSON_ASSOCIATION_MAX_DISTANCE_RATIO * ((width**2 + height**2) ** 0.5)
    associations: dict[int, int] = {}
    for weapon_track_id, det in matches.items():
        if det.object_class not in weapon_classes:
            continue
        best_person_id, best_distance = None, None
        for person_id, person_track in person_tracks:
            distance = centroid_distance(det.centroid, person_track.centroids[-1])
            if best_distance is None or distance < best_distance:
                best_person_id, best_distance = person_id, distance
        if best_person_id is not None and best_distance <= max_distance:
            associations[weapon_track_id] = best_person_id
    return associations


def _tracker_to_jsonable(tracker: CentroidIoUTracker) -> dict:
    return {
        "iou_threshold": tracker.iou_threshold,
        "max_centroid_distance": tracker.max_centroid_distance,
        "max_missed_frames": tracker.max_missed_frames,
        "next_id": tracker._next_id,  # noqa: SLF001 - this module and tracker.py are the same subsystem
        "tracks": {
            str(track_id): {
                "track_id": t.track_id,
                "object_class": t.object_class,
                "last_bbox": list(t.last_bbox),
                "centroids": [list(c) for c in t.centroids],
                "timestamps": t.timestamps,
                "confidences": t.confidences,
                "colors": t.colors,
                "missed_frames": t.missed_frames,
                "active": t.active,
            }
            for track_id, t in tracker._tracks.items()  # noqa: SLF001
        },
    }


def _tracker_from_jsonable(data: dict) -> CentroidIoUTracker:
    tracker = CentroidIoUTracker(
        iou_threshold=data["iou_threshold"],
        max_centroid_distance=data["max_centroid_distance"],
        max_missed_frames=data["max_missed_frames"],
    )
    tracker._next_id = data["next_id"]  # noqa: SLF001
    for track_id_str, t in data["tracks"].items():
        tracker._tracks[int(track_id_str)] = Track(  # noqa: SLF001
            track_id=t["track_id"],
            object_class=t["object_class"],
            last_bbox=tuple(t["last_bbox"]),
            centroids=[tuple(c) for c in t["centroids"]],
            timestamps=t["timestamps"],
            confidences=t["confidences"],
            colors=t["colors"],
            missed_frames=t["missed_frames"],
            active=t["active"],
        )
    return tracker


def _state_to_jsonable(state: "TrackingState") -> dict:
    return {
        "track_db_ids": state.track_db_ids,
        "first_seen_by_track": state.first_seen_by_track,
        "risk_history_by_track": state.risk_history_by_track,
        "track_rule_triggered": list(state.track_rule_triggered),
        "incident_count": state.incident_count,
        "event_track_states": {
            str(track_id): {
                "last_severity": s.last_severity,
                "last_anomaly_flagged": s.last_anomaly_flagged,
                "last_event_ts": s.last_event_ts,
                "weapon_already_flagged": s.weapon_already_flagged,
                "seen": s.seen,
                "last_movement": s.last_movement,
            }
            for track_id, s in state.event_generator.track_states.items()
        },
    }


def _state_from_jsonable(data: dict) -> "TrackingState":
    state = TrackingState(
        track_db_ids={int(k): v for k, v in data["track_db_ids"].items()},
        first_seen_by_track={int(k): v for k, v in data["first_seen_by_track"].items()},
        risk_history_by_track={int(k): v for k, v in data["risk_history_by_track"].items()},
        track_rule_triggered=set(data["track_rule_triggered"]),
        incident_count=data["incident_count"],
    )
    for track_id_str, s in data["event_track_states"].items():
        state.event_generator.track_states[int(track_id_str)] = _TrackState(
            last_severity=s["last_severity"],
            last_anomaly_flagged=s["last_anomaly_flagged"],
            last_event_ts=s["last_event_ts"],
            weapon_already_flagged=s["weapon_already_flagged"],
            seen=s["seen"],
            last_movement=s["last_movement"],
        )
    return state


def save_live_tracking_state(redis_client, job_id: int, tracker: CentroidIoUTracker, state: "TrackingState") -> None:
    """Persists tracker+state to Redis so a re-queued live-camera session
    (app/workers/tasks.py process_live_camera_task re-queues itself every
    LIVE_SESSION_MAX_SECONDS) picks up exactly where the previous
    invocation left off, instead of resetting every track ID and risk
    history at that boundary. Serialized as plain JSON of only the known,
    simple fields (ints/floats/strings/lists/dicts) rather than pickle:
    Redis holds this blob and is reachable well beyond this process (see
    docker-compose.yml), so deserializing it must never be able to
    execute arbitrary code regardless of who else can write to that key.
    Best-effort: if this fails (Redis down), the session just falls back
    to a fresh tracker on the next invocation rather than crashing the
    task."""
    try:
        blob = json.dumps({"tracker": _tracker_to_jsonable(tracker), "state": _state_to_jsonable(state)})
        redis_client.set(f"{LIVE_TRACKER_STATE_KEY_PREFIX}{job_id}", blob, ex=LIVE_TRACKER_STATE_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist live tracker state for job %s: %s", job_id, exc)


def load_live_tracking_state(redis_client, job_id: int) -> tuple[CentroidIoUTracker | None, "TrackingState | None"]:
    """Returns (tracker, state) saved by a previous invocation of the same
    live-camera session, or (None, None) if there is none / it couldn't be
    loaded -- the caller should then start a fresh tracker+state, same as
    the very first invocation of a session. Malformed/unexpected JSON
    (whether corrupted or written by something else entirely) is treated
    the same as "no saved state", never evaluated or executed."""
    try:
        blob = redis_client.get(f"{LIVE_TRACKER_STATE_KEY_PREFIX}{job_id}")
        if not blob:
            return None, None
        data = json.loads(blob)
        return _tracker_from_jsonable(data["tracker"]), _state_from_jsonable(data["state"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load live tracker state for job %s: %s", job_id, exc)
        return None, None


def clear_live_tracking_state(redis_client, job_id: int) -> None:
    try:
        redis_client.delete(f"{LIVE_TRACKER_STATE_KEY_PREFIX}{job_id}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not clear live tracker state for job %s: %s", job_id, exc)


def after_hours(ts: datetime) -> bool:
    return ts.hour >= 22 or ts.hour < 6


def zone_contains_point(polygon: list[tuple[float, float]], point: tuple[float, float]) -> bool:
    """Standard ray-casting point-in-polygon test (normalized coordinates)."""
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def load_zones_and_rules(db, camera_id: int | None) -> tuple[dict[int, tuple[Zone, list[tuple[float, float]]]], dict[int, list[Rule]]]:
    """Active zones for a camera (none if the job has no camera) and their
    active rules, pre-parsed once per job/session rather than per frame."""
    zones = db.query(Zone).filter(Zone.camera_id == camera_id, Zone.is_active.is_(True)).all() if camera_id else []
    zone_polygons = {z.id: (z, [tuple(p) for p in json.loads(z.polygon_json)]) for z in zones}
    rules_by_zone: dict[int, list[Rule]] = {
        z.id: db.query(Rule).filter(Rule.zone_id == z.id, Rule.is_active.is_(True)).all() for z in zones
    }
    return zone_polygons, rules_by_zone


@dataclass
class TrackingState:
    """Per-job/per-session mutable state threaded through every call to
    handle_tracked_detection. One instance lives for the whole file-upload
    job, or for one live-camera task invocation (a live session's tracking
    resets on each re-chained invocation -- see README "Known limitations"
    for why)."""

    track_db_ids: dict[int, int] = field(default_factory=dict)
    first_seen_by_track: dict[int, float] = field(default_factory=dict)
    risk_history_by_track: dict[int, list[float]] = field(default_factory=dict)
    track_rule_triggered: set[int] = field(default_factory=set)
    event_generator: ActivityEventGenerator = field(default_factory=ActivityEventGenerator)
    incident_count: int = 0


def handle_tracked_detection(
    db,
    job: ProcessingJob,
    camera_id: int | None,
    zone_polygons: dict[int, tuple[Zone, list[tuple[float, float]]]],
    rules_by_zone: dict[int, list[Rule]],
    det: Detection,
    track: Track,
    track_id: int,
    ts: float,
    frame_number: int,
    width: int,
    height: int,
    state: TrackingState,
    live_frame=None,
    concurrent_count: int | None = None,
    holder_person_track_id: int | None = None,
) -> float:
    """Scores, persists, and narrates one tracked detection. Returns the
    computed Risk score. `live_frame`, when given (the live-camera
    path only), is used as real incident-evidence imagery instead of the
    blank-box placeholder used for file uploads (whose original frame
    pixels aren't available this far from the file-reading step).
    `concurrent_count`, when given, is how many other active tracks of the
    same object_class are visible at this same timestamp -- used to call
    out "N people in view" in the narration so multiple simultaneous
    people read as distinguished individuals, not one merged sighting.
    `holder_person_track_id`, when given (see associate_weapons_to_people),
    means this detection is a weapon-class track located right next to
    that person track: this always force-creates a CRITICAL incident and
    sends a real-time alert, independent of any zone/rule configuration --
    a weapon next to a person is inherently worth surfacing immediately."""
    import cv2

    if track_id not in state.track_db_ids:
        tracked_obj = TrackedObject(processing_job_id=job.id, track_number=track_id, object_class=det.object_class)
        db.add(tracked_obj)
        db.commit()
        db.refresh(tracked_obj)
        state.track_db_ids[track_id] = tracked_obj.id
        state.first_seen_by_track[track_id] = ts
        state.risk_history_by_track[track_id] = []

    centroid = det.centroid
    matched_zone_id = None
    matched_zone = None
    for zid, (zone_obj, polygon) in zone_polygons.items():
        norm_point = (centroid[0] / max(width, 1), centroid[1] / max(height, 1))
        if zone_contains_point(polygon, norm_point):
            matched_zone_id = zid
            matched_zone = zone_obj
            break

    dwell_seconds = ts - state.first_seen_by_track[track_id]
    motion_anomaly = calculate_motion_anomaly(track.centroids, track.timestamps)
    is_after_hours = after_hours(datetime.now(timezone.utc))

    risk = calculate_risk(
        zone_severity=matched_zone.severity.value if matched_zone else None,
        dwell_seconds=dwell_seconds,
        minimum_dwell_seconds=matched_zone.minimum_dwell_seconds if matched_zone else 10.0,
        motion_anomaly=motion_anomaly,
        after_hours=is_after_hours,
        confidence_history=track.confidences,
        previous_risk=state.risk_history_by_track[track_id][-1] if state.risk_history_by_track[track_id] else 0.0,
    )
    state.risk_history_by_track[track_id].append(risk)

    db.add(
        ObjectObservation(
            tracked_object_id=state.track_db_ids[track_id],
            frame_number=frame_number,
            timestamp_seconds=ts,
            bbox_x1=det.x1, bbox_y1=det.y1, bbox_x2=det.x2, bbox_y2=det.y2,
            confidence=det.confidence,
            centroid_x=centroid[0], centroid_y=centroid[1],
            zone_id=matched_zone_id,
            risk_score=risk,
        )
    )

    tracked_obj_row = db.get(TrackedObject, state.track_db_ids[track_id])
    tracked_obj_row.final_risk_score = risk
    tracked_obj_row.dominant_color = track.dominant_color
    db.commit()

    position = frame_position_label(centroid[0], centroid[1], width, height)
    movement = movement_label(track.centroids, track.timestamps)
    for event_type, severity, description in state.event_generator.observe(
        track_id, det.object_class, risk, motion_anomaly, ts,
        dominant_color=track.dominant_color, position=position, movement=movement,
        concurrent_count=concurrent_count,
    ):
        db.add(
            ActivityEvent(
                processing_job_id=job.id,
                tracked_object_id=state.track_db_ids[track_id],
                track_number=track_id,
                object_class=det.object_class,
                timestamp_seconds=ts,
                event_type=event_type,
                severity=EventSeverity(severity),
                description=description,
                risk_score=risk,
            )
        )
        db.commit()

    is_weapon = det.object_class in settings.weapon_class_names_set
    if is_weapon and holder_person_track_id is not None and track_id not in state.track_rule_triggered:
        # A weapon-class track located right next to an active person
        # track is inherently an incident, regardless of whether any
        # zone/rule is even configured for this camera -- unlike the
        # dwell/zone-based path below, this doesn't wait for
        # is_incident_triggered's consecutive-frames threshold either,
        # since a single confirmed weapon-near-person frame already
        # warrants immediate attention.
        state.track_rule_triggered.add(track_id)
        _create_incident_and_alert(
            db, job, camera_id, state,
            zone_id=matched_zone_id, tracked_object_db_id=state.track_db_ids[track_id], rule_id=None,
            object_class=det.object_class, risk=risk, priority=IncidentPriority.CRITICAL,
            summary=(
                f"Person #{holder_person_track_id} appears to be holding a {det.object_class} "
                f"(track #{track_id}), Risk {risk:.1f}."
            ),
            det=det, live_frame=live_frame, width=width, height=height, ts=ts,
        )
    elif matched_zone_id is not None and track_id not in state.track_rule_triggered:
        for rule in rules_by_zone.get(matched_zone_id, []):
            allowed_classes = [c.strip() for c in rule.object_classes.split(",")]
            if det.object_class not in allowed_classes:
                continue
            if rule.after_hours_only and not is_after_hours:
                continue
            if not is_incident_triggered(state.risk_history_by_track[track_id], rule.risk_threshold, rule.consecutive_required):
                continue

            state.track_rule_triggered.add(track_id)
            priority = (
                IncidentPriority.CRITICAL if risk >= 90
                else IncidentPriority.HIGH if risk >= 75
                else IncidentPriority.MEDIUM if risk >= 50
                else IncidentPriority.LOW
            )
            _create_incident_and_alert(
                db, job, camera_id, state,
                zone_id=matched_zone_id, tracked_object_db_id=state.track_db_ids[track_id], rule_id=rule.id,
                object_class=det.object_class, risk=risk, priority=priority,
                summary=(
                    f"{det.object_class.capitalize()} track #{track_id} triggered rule "
                    f"'{rule.name}' in zone '{matched_zone.name}' with Risk {risk:.1f}."
                ),
                det=det, live_frame=live_frame, width=width, height=height, ts=ts,
            )
            break

    return risk


def _create_incident_and_alert(
    db,
    job: ProcessingJob,
    camera_id: int | None,
    state: "TrackingState",
    *,
    zone_id: int | None,
    tracked_object_db_id: int,
    rule_id: int | None,
    object_class: str,
    risk: float,
    priority: IncidentPriority,
    summary: str,
    det: Detection,
    live_frame,
    width: int,
    height: int,
    ts: float,
) -> Incident:
    """Shared by both incident paths above (zone/rule-triggered, and the
    weapon-next-to-a-person path): creates the Incident row, writes an
    evidence frame with the triggering box burned in, dispatches a
    real-time alert (app/services/alert_service.send_alert) if this
    incident clears the configured severity/cooldown gate, and persists
    whether that alert actually went out."""
    import cv2

    incident = Incident(
        processing_job_id=job.id,
        camera_id=camera_id,
        zone_id=zone_id,
        tracked_object_id=tracked_object_db_id,
        rule_id=rule_id,
        object_class=object_class,
        risk_score=risk,
        priority=priority,
        summary=summary,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    state.incident_count += 1

    evidence_dir = Path(settings.UPLOAD_DIR) / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"incident_{incident.id}.jpg"
    try:
        frame_img = live_frame.copy() if live_frame is not None else np.zeros((height, width, 3), dtype=np.uint8)
        cv2.rectangle(frame_img, (int(det.x1), int(det.y1)), (int(det.x2), int(det.y2)), (0, 0, 255), 3)
        cv2.imwrite(str(evidence_path), frame_img)
        db.add(IncidentEvidence(incident_id=incident.id, frame_path=str(evidence_path), timestamp_seconds=ts))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not write evidence frame: %s", exc)

    try:
        alert_result = send_alert(incident)
        if alert_result["attempted"]:
            incident.alert_sent = True
            incident.alert_channels = channels_summary(alert_result) or None
            db.commit()
    except Exception as exc:  # noqa: BLE001 - alerting must never break the detection pipeline
        logger.warning("Alert dispatch raised for incident %s: %s", incident.id, exc)

    return incident
