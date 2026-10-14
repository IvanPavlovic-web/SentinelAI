"""Seed script: creates demo users, a camera, zones/rules, and sample
tracked_objects/incidents so the dashboard has data to show without first
processing a real video.

Run with:  python -m app.seed   (from the backend/ directory, with DB
migrations already applied)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.db.base import Base, SessionLocal, engine
from app.models.camera import Camera, DetectionModel, JobStatus, ProcessingJob, VideoSource
from app.models.incident import Incident, IncidentEvidence, IncidentPriority, IncidentStatus, PerformanceMetric
from app.models.tracking import ObjectObservation, TrackedObject
from app.models.user import User, UserRole
from app.models.zone import Rule, Zone, ZoneSeverity


def seed() -> None:
    # Make sure all tables exist (in dev, Alembic migrations are preferred,
    # but create_all is a harmless no-op safety net for first-run demos).
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "admin@sentinelai.dev").first():
            print("Seed data already present, skipping.")
            return

        admin = User(
            email="admin@sentinelai.dev",
            hashed_password=hash_password("Admin123!"),
            full_name="Site Admin",
            role=UserRole.ADMIN,
        )
        analyst = User(
            email="analyst@sentinelai.dev",
            hashed_password=hash_password("Analyst123!"),
            full_name="Security Analyst",
            role=UserRole.ANALYST,
        )
        db.add_all([admin, analyst])
        db.commit()
        db.refresh(admin)
        db.refresh(analyst)

        model = DetectionModel(name="YOLOv8n", version="8.3.49", weights_path="yolov8n.pt", is_stub=True)
        db.add(model)

        camera = Camera(
            name="Warehouse Dock Camera",
            location="North Warehouse - Loading Dock",
            rtsp_url="rtsp://demo:demo@127.0.0.1:8554/warehouse",
            owner_id=admin.id,
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)

        zone = Zone(
            camera_id=camera.id,
            name="High Security Warehouse",
            severity=ZoneSeverity.HIGH,
            polygon_json=json.dumps([[0.2, 0.2], [0.8, 0.2], [0.8, 0.9], [0.2, 0.9]]),
            minimum_dwell_seconds=10.0,
        )
        db.add(zone)
        db.commit()
        db.refresh(zone)

        rule = Rule(
            zone_id=zone.id,
            name="After-hours loitering",
            object_classes="person",
            after_hours_only=True,
            risk_threshold=70.0,
            consecutive_required=3,
        )
        db.add(rule)

        video_source = VideoSource(
            camera_id=camera.id,
            uploaded_by=admin.id,
            original_filename="sample_dock_feed.mp4",
            stored_filename="sample_dock_feed_seed.mp4",
            file_path="uploads/sample_dock_feed_seed.mp4",
            file_size_bytes=10_485_760,
            duration_seconds=130.0,
            fps=25.0,
            width=1280,
            height=720,
        )
        db.add(video_source)
        db.commit()
        db.refresh(video_source)

        job = ProcessingJob(
            video_source_id=video_source.id,
            detection_model_id=model.id,
            status=JobStatus.COMPLETED,
            progress_percent=100.0,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            finished_at=datetime.now(timezone.utc) - timedelta(minutes=4),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        tracked = TrackedObject(
            processing_job_id=job.id,
            track_number=14,
            object_class="person",
            final_risk_score=78.8,
        )
        db.add(tracked)
        db.commit()
        db.refresh(tracked)

        base_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
        for i, (dwell, risk) in enumerate([(2, 19.0), (6, 35.7), (11, 50.9), (14, 62.8), (18, 71.9), (24, 78.8)]):
            db.add(
                ObjectObservation(
                    tracked_object_id=tracked.id,
                    frame_number=i * 25,
                    timestamp_seconds=float(dwell),
                    bbox_x1=400.0, bbox_y1=200.0, bbox_x2=500.0, bbox_y2=450.0,
                    confidence=0.8 + i * 0.02,
                    centroid_x=450.0, centroid_y=325.0,
                    zone_id=zone.id,
                    star_risk_score=risk,
                )
            )
        db.commit()

        incident = Incident(
            processing_job_id=job.id,
            camera_id=camera.id,
            zone_id=zone.id,
            tracked_object_id=tracked.id,
            rule_id=rule.id,
            object_class="person",
            star_risk_score=78.8,
            status=IncidentStatus.OPEN,
            priority=IncidentPriority.HIGH,
            summary=(
                "Person track #14 entered the High Security Warehouse zone after "
                "hours and loitered for 24s with erratic movement, producing a "
                "STAR-Risk score of 78.8."
            ),
            detected_at=base_ts,
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)

        db.add(
            IncidentEvidence(
                incident_id=incident.id,
                frame_path="uploads/evidence/seed_incident_1.jpg",
                frame_number=600,
                timestamp_seconds=24.0,
            )
        )

        db.add(
            PerformanceMetric(
                processing_job_id=job.id,
                total_frames=3250,
                processed_frames=650,
                duration_seconds=22.4,
                processing_fps=29.0,
                avg_latency_ms=34.5,
                p95_latency_ms=58.2,
                avg_cpu_percent=42.3,
                avg_ram_mb=512.6,
                queue_wait_seconds=1.2,
                incident_count=1,
            )
        )
        db.commit()

        print("Seed data created:")
        print("  admin@sentinelai.dev / Admin123!")
        print("  analyst@sentinelai.dev / Analyst123!")
        print(f"  camera_id={camera.id}, zone_id={zone.id}, rule_id={rule.id}, incident_id={incident.id}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
