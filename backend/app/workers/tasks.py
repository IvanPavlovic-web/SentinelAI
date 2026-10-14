"""Celery tasks implementing the SentinelAI video-intelligence pipeline.

Two entry points, sharing one detection/tracking/scoring/narration core
(app/workers/detection.py, tracking_pipeline.py, annotate.py, events.py):

- process_video_task(job_id): an uploaded file, known duration, processed
  in parallel chunks, producing a batch annotated-preview video at the end.
- process_live_camera_task(job_id): a camera's live stream (RTSP, or any
  source cv2.VideoCapture can open), processed frame by frame in real time
  for a bounded session length, continuously refreshing a snapshot preview
  image and re-queuing itself while the camera is still meant to be live.

YOLO availability: both paths try `from ultralytics import YOLO` via
app.workers.detection.load_yolo_model, and fall back to a deterministic
synthetic-detection stub if the weights cannot be loaded (e.g. an offline
sandboxed environment), so the rest of the pipeline (tracking, zones,
Risk, incidents, narration, metrics) still runs end to end.

Weapon detection: COCO (the default YOLO_MODEL_PATH) has no gun/knife
classes, so both paths also load a second, dedicated weapon-detection
model (app.workers.detection.load_weapon_model) and run it alongside the
main model on every sampled frame. Unavailable (no internet, etc.) simply
means no weapon detections for that session, same graceful-degradation
approach as the stub detector.
"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil

from app.algorithms.risk import split_video_chunks
from app.algorithms.tracker import CentroidIoUTracker, Detection
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.db.base import SessionLocal
from app.models.camera import Camera, JobStatus, ProcessingJob, VideoSource
from app.models.incident import PerformanceMetric
from app.workers.annotate import render_annotated_video, write_live_snapshot
from app.workers.celery_app import celery_app
from app.workers.detection import RawDetection, detect_frame, load_weapon_model, load_yolo_model, process_chunk
from app.workers.tracking_pipeline import (
    TrackingState,
    associate_weapons_to_people,
    clear_live_tracking_state,
    handle_tracked_detection,
    load_live_tracking_state,
    load_zones_and_rules,
    save_live_tracking_state,
)

logger = get_logger(__name__)


@celery_app.task(bind=True, name="app.workers.tasks.process_video_task")
def process_video_task(self, job_id: int) -> dict:
    import cv2

    db = SessionLocal()
    start_time = time.time()
    latencies_ms: list[float] = []

    try:
        job: ProcessingJob | None = db.get(ProcessingJob, job_id)
        if job is None:
            logger.error("ProcessingJob %s not found", job_id)
            return {"status": "error", "detail": "job not found"}

        video: VideoSource = db.get(VideoSource, job.video_source_id)
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        job.celery_task_id = self.request.id
        db.commit()

        cap = cv2.VideoCapture(video.file_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        duration = (frame_count / fps) if fps > 0 and frame_count > 0 else 10.0
        cap.release()

        video.fps = fps
        video.width = width
        video.height = height
        video.duration_seconds = duration
        db.commit()

        chunks = split_video_chunks(max(duration, 1.0), settings.DEFAULT_CHUNK_SECONDS)
        all_detections: list[RawDetection] = []
        total = len(chunks)

        # Celery's default "prefork" pool runs each task inside a daemonic
        # worker process, and CPython forbids a daemonic process from
        # spawning children, so ProcessPoolExecutor.submit() raises
        # AssertionError there even though the code itself is correct (see
        # docker-compose.yml, which runs celery_worker with --pool=threads
        # specifically to avoid this). If some other deployment still runs
        # prefork, degrade to sequential in-process execution instead of
        # failing the whole job outright.
        try:
            with ProcessPoolExecutor(max_workers=min(4, max(1, total))) as executor:
                futures = [
                    executor.submit(process_chunk, video.file_path, start, end, fps, settings.FRAME_SAMPLE_RATE, settings.YOLO_MODEL_PATH)
                    for start, end in chunks
                ]
                for i, future in enumerate(futures):
                    t0 = time.time()
                    chunk_results = future.result()
                    latencies_ms.append((time.time() - t0) * 1000)
                    all_detections.extend(RawDetection(**d) for d in chunk_results)
                    job.progress_percent = round(((i + 1) / total) * 90.0, 2)  # reserve last 10% for post-processing
                    db.commit()
        except (AssertionError, OSError) as exc:
            logger.warning(
                "ProcessPoolExecutor unavailable (%s); falling back to sequential chunk processing. "
                "Run the celery worker with --pool=threads to get real parallel chunk processing.",
                exc,
            )
            all_detections = []
            for i, (start, end) in enumerate(chunks):
                t0 = time.time()
                chunk_results = process_chunk(video.file_path, start, end, fps, settings.FRAME_SAMPLE_RATE, settings.YOLO_MODEL_PATH)
                latencies_ms.append((time.time() - t0) * 1000)
                all_detections.extend(RawDetection(**d) for d in chunk_results)
                job.progress_percent = round(((i + 1) / total) * 90.0, 2)
                db.commit()

        all_detections.sort(key=lambda d: d.timestamp)

        tracker = CentroidIoUTracker()
        state = TrackingState()
        zone_polygons, rules_by_zone = load_zones_and_rules(db, video.camera_id)
        annotations_by_frame: dict[int, list[dict]] = {}

        by_timestamp: dict[float, list[RawDetection]] = {}
        for d in all_detections:
            by_timestamp.setdefault(d.timestamp, []).append(d)

        for ts in sorted(by_timestamp.keys()):
            dets = [
                Detection(x1=d.x1, y1=d.y1, x2=d.x2, y2=d.y2, confidence=d.confidence, object_class=d.object_class, dominant_color=d.dominant_color)
                for d in by_timestamp[ts]
            ]
            matches = tracker.update(dets, ts)
            class_counts = {cls: sum(1 for t in tracker.tracks.values() if t.active and t.object_class == cls) for cls in {d.object_class for d in dets}}
            weapon_holders = associate_weapons_to_people(tracker, matches, width, height)

            for track_id, det in matches.items():
                track = tracker.tracks[track_id]
                frame_number = int(ts * fps)
                risk = handle_tracked_detection(
                    db, job, video.camera_id, zone_polygons, rules_by_zone,
                    det, track, track_id, ts, frame_number, width, height, state,
                    concurrent_count=class_counts.get(det.object_class),
                    holder_person_track_id=weapon_holders.get(track_id),
                )
                annotations_by_frame.setdefault(frame_number, []).append(
                    {
                        "x1": det.x1, "y1": det.y1, "x2": det.x2, "y2": det.y2,
                        "object_class": det.object_class, "track_id": track_id,
                        "confidence": det.confidence, "risk": risk, "color": track.dominant_color,
                    }
                )

        job.progress_percent = 95.0
        db.commit()

        annotated_path = Path(settings.UPLOAD_DIR) / "annotated" / f"job_{job.id}.mp4"
        hold_frames = max(int(settings.FRAME_SAMPLE_RATE), 1)
        try:
            rendered = render_annotated_video(video.file_path, annotated_path, annotations_by_frame, fps, width, height, hold_frames)
        except Exception as exc:  # noqa: BLE001 - annotated preview is best-effort, never fails the job
            logger.warning("Annotated preview rendering raised for job %s: %s", job.id, exc)
            rendered = False
        if rendered:
            job.annotated_path = str(annotated_path)
            db.commit()
        else:
            logger.warning("Annotated preview not produced for job %s (no codec available?)", job.id)

        elapsed = time.time() - start_time
        latencies = np.array(latencies_ms) if latencies_ms else np.array([0.0])
        db.add(
            PerformanceMetric(
                processing_job_id=job.id,
                total_frames=frame_count,
                processed_frames=len(all_detections),
                duration_seconds=elapsed,
                processing_fps=(len(all_detections) / elapsed) if elapsed > 0 else 0.0,
                avg_latency_ms=float(np.mean(latencies)),
                p95_latency_ms=float(np.percentile(latencies, 95)),
                avg_cpu_percent=psutil.cpu_percent(interval=0.1),
                avg_ram_mb=psutil.Process().memory_info().rss / (1024 * 1024),
                queue_wait_seconds=(job.started_at - job.created_at).total_seconds() if job.started_at and job.created_at else 0.0,
                incident_count=state.incident_count,
            )
        )

        job.status = JobStatus.COMPLETED
        job.progress_percent = 100.0
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

        return {"status": "completed", "job_id": job.id, "incidents": state.incident_count}

    except Exception as exc:  # noqa: BLE001
        logger.exception("process_video_task failed for job %s", job_id)
        db.rollback()
        job = db.get(ProcessingJob, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        return {"status": "error", "detail": str(exc)}
    finally:
        db.close()


@celery_app.task(bind=True, name="app.workers.tasks.process_live_camera_task")
def process_live_camera_task(self, job_id: int) -> dict:
    """Processes a camera's live stream in real time for up to
    LIVE_SESSION_MAX_SECONDS, then (if the camera is still active and no
    stop was requested) re-queues itself to keep monitoring continuously.
    Tracking state (track IDs, risk history, event-narration history) is
    persisted to Redis (app.workers.tracking_pipeline save/load/clear_
    live_tracking_state) and restored by the next re-queued invocation, so
    a continuously-monitored camera keeps stable track IDs across that
    boundary instead of restarting dwell/risk history every
    LIVE_SESSION_MAX_SECONDS."""
    import cv2

    db = SessionLocal()
    redis_client = get_redis()
    start_time = time.time()
    frames_processed = 0
    latencies_ms: list[float] = []

    try:
        job: ProcessingJob | None = db.get(ProcessingJob, job_id)
        if job is None:
            logger.error("ProcessingJob %s not found", job_id)
            return {"status": "error", "detail": "job not found"}

        camera: Camera | None = db.get(Camera, job.camera_id)
        if camera is None or not camera.rtsp_url:
            job.status = JobStatus.FAILED
            job.error_message = "Camera has no stream URL configured"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            clear_live_tracking_state(redis_client, job.id)
            return {"status": "error", "detail": "no stream URL"}

        job.status = JobStatus.PROCESSING
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.celery_task_id = self.request.id
        db.commit()

        cap = cv2.VideoCapture(camera.rtsp_url)
        if not cap.isOpened():
            job.status = JobStatus.FAILED
            job.error_message = f"Could not connect to camera stream: {camera.rtsp_url}"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            clear_live_tracking_state(redis_client, job.id)
            return {"status": "error", "detail": "camera unreachable"}

        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0  # many RTSP sources misreport fps; a sane default keeps timestamps usable
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        model, is_stub = load_yolo_model(settings.YOLO_MODEL_PATH)
        weapon_model = (
            load_weapon_model(settings.WEAPON_MODEL_REPO_ID, settings.WEAPON_MODEL_FILENAME, settings.WEAPON_MODEL_REPO_TYPE)
            if settings.WEAPON_MODEL_ENABLED
            else None
        )

        tracker, state = load_live_tracking_state(redis_client, job.id)
        if tracker is None or state is None:
            tracker = CentroidIoUTracker()
            state = TrackingState()
        zone_polygons, rules_by_zone = load_zones_and_rules(db, camera.id)
        snapshot_path = Path(settings.UPLOAD_DIR) / "live" / f"camera_{camera.id}_latest.jpg"

        frame_number = 0
        session_deadline = start_time + settings.LIVE_SESSION_MAX_SECONDS
        last_db_check = 0.0
        last_processed_frame = None

        while time.time() < session_deadline:
            ok, frame = cap.read()
            if not ok:
                # A continuous stream (RTSP) exhausting itself here is
                # usually a real disconnect. But plenty of real-world
                # public cameras -- including every one of the BiH demo
                # cameras seeded by app/seed.py -- aren't a continuous
                # stream at all, just a single refreshed JPEG served per
                # HTTP request: cv2.VideoCapture reads that one frame
                # successfully, then legitimately reports EOF on every
                # read after. Reopening the capture and retrying once
                # handles both cases: a snapshot-style source gets its
                # next refreshed frame, and a flaky RTSP source gets a
                # reconnect attempt, before this session is given up on.
                cap.release()
                cap = cv2.VideoCapture(camera.rtsp_url)
                ok, frame = cap.read()
                if not ok:
                    logger.warning("Live camera %s: stream read failed even after reconnect, ending this session early", camera.id)
                    break
                time.sleep(1.0)  # be polite to snapshot-style HTTP sources instead of hammering them

            now = time.time()
            if now - last_db_check > 2.0:  # poll for a stop request every ~2s, not every frame
                db.refresh(job)
                if job.stop_requested:
                    break
                last_db_check = now

            if frame_number % max(settings.FRAME_SAMPLE_RATE, 1) == 0:
                # Snapshot-style public webcams (see the reconnect comment
                # above) only actually refresh every so often; in between
                # refreshes, every read here returns the exact same image.
                # Running detection/tracking on that repeatedly isn't just
                # wasted CPU -- it's actively wrong: the tracker would see
                # the same object "still there" on every poll and keep
                # accumulating dwell_seconds against real wall-clock time,
                # inflating risk for an object that (as far as this camera
                # can tell) hasn't actually been continuously present, just
                # photographed once. Skipping unchanged frames keeps dwell
                # tied to real elapsed presence instead of polling interval.
                unchanged = (
                    last_processed_frame is not None
                    and frame.shape == last_processed_frame.shape
                    and bool(np.array_equal(frame, last_processed_frame))
                )
                if not unchanged:
                    last_processed_frame = frame.copy()
                    ts = now - start_time
                    t0 = time.time()
                    detections = detect_frame(model, is_stub, frame, frame_number, ts, weapon_model=weapon_model)
                    latencies_ms.append((time.time() - t0) * 1000)
                    frames_processed += 1

                    live_dets = [
                        Detection(x1=d.x1, y1=d.y1, x2=d.x2, y2=d.y2, confidence=d.confidence, object_class=d.object_class, dominant_color=d.dominant_color)
                        for d in detections
                    ]
                    matches = tracker.update(live_dets, ts)
                    class_counts = {cls: sum(1 for t in tracker.tracks.values() if t.active and t.object_class == cls) for cls in {d.object_class for d in live_dets}}
                    weapon_holders = associate_weapons_to_people(tracker, matches, width, height)

                    boxes_for_snapshot: list[dict] = []
                    for track_id, det in matches.items():
                        track = tracker.tracks[track_id]
                        risk = handle_tracked_detection(
                            db, job, camera.id, zone_polygons, rules_by_zone,
                            det, track, track_id, ts, frame_number, width, height, state,
                            live_frame=frame, concurrent_count=class_counts.get(det.object_class),
                            holder_person_track_id=weapon_holders.get(track_id),
                        )
                        boxes_for_snapshot.append(
                            {
                                "x1": det.x1, "y1": det.y1, "x2": det.x2, "y2": det.y2,
                                "object_class": det.object_class, "track_id": track_id,
                                "confidence": det.confidence, "risk": risk, "color": track.dominant_color,
                            }
                        )

                    write_live_snapshot(frame, boxes_for_snapshot, snapshot_path)
                    job.progress_percent = 100.0  # a live session has no fixed end; 100 just means "actively monitoring"
                    db.commit()

            frame_number += 1

        cap.release()

        elapsed = time.time() - start_time
        latencies = np.array(latencies_ms) if latencies_ms else np.array([0.0])
        db.add(
            PerformanceMetric(
                processing_job_id=job.id,
                total_frames=frame_number,
                processed_frames=frames_processed,
                duration_seconds=elapsed,
                processing_fps=(frames_processed / elapsed) if elapsed > 0 else 0.0,
                avg_latency_ms=float(np.mean(latencies)),
                p95_latency_ms=float(np.percentile(latencies, 95)),
                avg_cpu_percent=psutil.cpu_percent(interval=0.1),
                avg_ram_mb=psutil.Process().memory_info().rss / (1024 * 1024),
                queue_wait_seconds=0.0,
                incident_count=state.incident_count,
            )
        )
        db.commit()

        db.refresh(job)
        if job.stop_requested:
            clear_live_tracking_state(redis_client, job.id)
            job.status = JobStatus.STOPPED
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return {"status": "stopped", "job_id": job.id}

        db.refresh(camera)
        if camera.is_active:
            # Still meant to be live: hand off to a fresh invocation rather
            # than looping forever in one task (keeps worker slots healthy,
            # lets Celery's own restart/retry machinery apply normally).
            # Tracker/state are saved first so that next invocation picks
            # up the same track IDs and risk history instead of resetting.
            save_live_tracking_state(redis_client, job.id, tracker, state)
            process_live_camera_task.delay(job.id)
            return {"status": "continuing", "job_id": job.id}

        clear_live_tracking_state(redis_client, job.id)
        job.status = JobStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "completed", "job_id": job.id}

    except Exception as exc:  # noqa: BLE001
        logger.exception("process_live_camera_task failed for job %s", job_id)
        db.rollback()
        job = db.get(ProcessingJob, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            clear_live_tracking_state(redis_client, job.id)
        return {"status": "error", "detail": str(exc)}
    finally:
        db.close()
