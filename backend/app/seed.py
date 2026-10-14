"""Seed script: creates demo users, the detection-model row, and real
camera(s) you can actually start monitoring immediately -- no fabricated
video/incident history, since none of that would correspond to anything
that actually happened.

Camera sources are real, publicly reachable webcams in Bosnia and
Herzegovina (not RTSP -- see the comment on BIH_WEBCAMS below for why
that's fine). Point your own camera's RTSP URL at a Camera row (via the
UI or API) the same way; nothing about these is special-cased. Each one
was individually verified (image actually downloaded and inspected, URL
opened with cv2.VideoCapture) before being added here -- do not add
another "live webcam" URL to this list without doing the same; most
public webcam sites only expose a JS player with no fetchable underlying
image/stream, and guessing at one produces a URL that looks plausible but
doesn't work.

Five are hosted by Bergfex (images.bergfex.at); one (the Banja Luka
traffic camera) is a BIHAMK (Bosnia-Herzegovina Automobile Club) camera
re-served through Windy's imgproxy. All are periodically-refreshed JPEG
snapshots, not continuous RTSP/HLS streams (true of the overwhelming
majority of public-facing "live webcams" worldwide, BiH included --
they're built for an <img> tag that re-requests every so often, not for a
monitoring pipeline). app/workers/tasks.py's live-camera loop reopens the
capture and retries on every read failure specifically to make this kind
of source work continuously: each retry just fetches the latest refresh.

Run with:  python -m app.seed   (from the backend/ directory, with DB
migrations already applied)
"""
from __future__ import annotations

from app.core.security import hash_password
from app.db.base import Base, SessionLocal, engine
from app.models.camera import Camera, DetectionModel
from app.models.user import User, UserRole
from app.models.zone import Rule, Zone, ZoneSeverity
import json

# (name, location, snapshot URL). The first is the one with a demo
# zone/rule attached below; the rest are added as plain cameras so there
# are several real feeds to switch between.
BIH_WEBCAMS = [
    (
        "Jahorina (BiH public webcam)",
        "Jahorina, Republika Srpska, Bosnia and Herzegovina",
        "https://images.bergfex.at/webcams/?id=24861&2&format=11",
    ),
    (
        "Ravna Planina (BiH public webcam)",
        "Ravna Planina Ski Centar, near Jahorina, Republika Srpska, BiH",
        "https://images.bergfex.at/webcams/?id=24857&2&format=44",
    ),
    (
        "Bjelasnica - Ski Jump (BiH public webcam)",
        "Bjelasnica, Federation of BiH",
        "https://images.bergfex.at/webcams/?id=16722&2&format=44",
    ),
    (
        "Bjelasnica - Hotel View (BiH public webcam)",
        "Bjelasnica, Federation of BiH",
        "https://images.bergfex.at/webcams/?id=16732&2&format=44",
    ),
    (
        "Igman - Olympic Monument (BiH public webcam)",
        "Igman, near Sarajevo, Federation of BiH",
        "https://images.bergfex.at/webcams/?id=16730&2&format=44",
    ),
    (
        "Banja Luka - Lazarevo (BIHAMK traffic cam)",
        "Lazarevo intersection, Banja Luka, Republika Srpska, BiH",
        "https://imgproxy.windy.com/_/full/plain/current/1634472035/original.jpg?v=2",
    ),
]


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

        db.add(DetectionModel(name="YOLOv8n", version="8.3.49", weights_path="yolov8n.pt", is_stub=False))

        cameras = []
        for name, location, url in BIH_WEBCAMS:
            camera = Camera(name=name, location=location, rtsp_url=url, owner_id=admin.id)
            db.add(camera)
            db.commit()
            db.refresh(camera)
            cameras.append(camera)

        # A working example of zone/rule configuration (currently API-only;
        # see README "Known limitations"), on the first camera, covering
        # the full frame since these are wide panoramas rather than a
        # fixed security-camera angle with a specific area to flag.
        zone = Zone(
            camera_id=cameras[0].id,
            name="Full frame",
            severity=ZoneSeverity.MEDIUM,
            polygon_json=json.dumps([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]),
            minimum_dwell_seconds=10.0,
        )
        db.add(zone)
        db.commit()
        db.refresh(zone)

        db.add(
            Rule(
                zone_id=zone.id,
                name="Loitering",
                object_classes="person",
                after_hours_only=False,
                risk_threshold=70.0,
                consecutive_required=3,
            )
        )
        db.commit()

        print("Seed data created:")
        print("  admin@sentinelai.dev / Admin123!")
        print("  analyst@sentinelai.dev / Analyst123!")
        for camera in cameras:
            print(f"  camera_id={camera.id} ({camera.name})")
        print("Start monitoring any of them from the Cameras page.")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
