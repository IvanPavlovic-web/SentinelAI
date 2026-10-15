# SentinelAI: Edge Video Intelligence & Incident Detection Platform

**CS50P Final Project** by Ivan Pavlović
**CS50 demo video:** _[PLACEHOLDER: add your CS50 submission video URL here]_

A self-hostable video-intelligence platform with two ways in: connect a
live camera (any RTSP source, including most home IP cameras) for
continuous monitoring, or upload a video file for one-shot analysis. Either
way it detects and tracks every person/vehicle, narrates what it sees in
plain language as it happens, shows you exactly what it found (an annotated
preview with detection boxes, track IDs, color, confidence, risk score),
and raises **explainable, scored incidents** when a tracked object's
behavior crosses a configured risk threshold, instead of a wall of raw
bounding boxes. It is an AI inference and video-intelligence pipeline, not
just an object detector: connect/upload, detect, track, narrate, alert,
all running on CPU with no GPU requirement.

Both paths (live camera and uploaded video) share one detection, tracking,
scoring, and narration core (`app/workers/tracking_pipeline.py`), so a
camera watched live and a video analyzed after the fact are scored and
described identically; only how frames arrive differs.

---

## Table of contents

1. [Problem it solves](#problem-it-solves)
2. [Features](#features)
3. [Technology stack](#technology-stack)
4. [Architecture](#architecture)
5. [Video processing pipeline, step by step](#video-processing-pipeline-step-by-step)
6. [Live cameras](#live-cameras)
7. [Risk algorithm](#risk-algorithm)
8. [The tracker](#the-tracker)
9. [Database schema](#database-schema)
10. [Authentication & RBAC](#authentication--rbac)
11. [API reference](#api-reference)
12. [Frontend](#frontend)
13. [Repository structure](#repository-structure)
14. [Environment variables](#environment-variables)
15. [Running with Docker Compose](#running-with-docker-compose)
16. [Local development without Docker](#local-development-without-docker)
17. [Tests and the CS50P CLI](#tests-and-the-cs50p-cli)
18. [Example API flow](#example-api-flow)
19. [CS50P requirement mapping](#cs50p-requirement-mapping)
20. [Known limitations](#known-limitations)
21. [Production hardening](#production-hardening)
22. [Future improvements](#future-improvements)
23. [Design decisions explained](#design-decisions-explained)
24. [License](#license)

---

## Problem it solves

Home users and small physical-security teams running cameras (a doorbell or
backyard camera at home, warehouses, retail back-of-house, construction
sites) typically have two bad options: pay for an expensive cloud VMS/AI
subscription, or have a human stare at a wall of video feeds. SentinelAI is
a third option: a platform you run yourself, with no GPU requirement, that
connects directly to a camera you already own and answers concrete
questions:

- Who or what is in front of this camera right now?
- Did a person enter a restricted area?
- Did a vehicle remain in a zone longer than allowed?
- Did an object show abnormal movement: sudden direction reversals, bursts
  of speed, or other suspicious behavior?
- Which cameras and zones generate the most incidents?
- How long did inference take, what FPS was achieved, how long did jobs wait
  in the queue?

## Features

- **Upload-based ingestion** with asynchronous background processing (Celery);
  uploading a video takes you straight into a live analysis view.
- **Multi-object tracking** via a custom, lightweight centroid/IoU tracker:
  no heavy third-party re-identification model to download or maintain.
- **Annotated AI preview**: the source video is re-rendered with detection
  boxes, track IDs, confidence and Risk burned in frame by frame, so
  the preview shows exactly what the AI found, not just a status bar.
- **Real-time detection reporting** over WebSockets: running object-class
  counts stream in while the job is still processing, not only once it
  completes.
- **Risk**: an original, explainable 0–100 risk-scoring algorithm that
  fuses zone severity, dwell time, motion anomaly, time-of-day, and
  detection-confidence persistence, with exponential smoothing and
  hysteresis against noisy duplicate alerts.
- Automatic incident creation with evidence frames, a resolve/dismiss
  workflow with analyst notes, and a full audit trail.
- Delete a video (and everything derived from it: jobs, tracks,
  observations, incidents, evidence, the annotated preview file) in one
  action.
- A role-based dashboard (admin/analyst/viewer): video library, incidents
  table with filters, performance charts, and an admin-only audit log:
  styled as a dark security-operations console.
- Full JWT authentication (short-lived access tokens + rotating, revocable
  refresh tokens) with role-based access control.

## Technology stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 / pydantic-settings |
| Auth | JWT (access + refresh), `passlib[bcrypt]`, per-route RBAC dependencies |
| Datastore / queue | PostgreSQL 16, Redis 7 |
| Background processing | Celery (Redis broker + result backend), `concurrent.futures.ProcessPoolExecutor` |
| Computer vision | OpenCV (headless), Ultralytics YOLOv8 (CPU) + a dedicated weapon-detection model, NumPy, `psutil` |
| Testing | pytest, httpx |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, React Router, TanStack Query, Recharts |
| Infrastructure | Docker, Docker Compose, named volumes, health checks |

## Architecture

```
frontend (React + Vite + TS + Tailwind)
        │  HTTP (REST) + WebSocket
        ▼
backend (FastAPI)
  routers/ → services/ → models/ (SQLAlchemy ORM)
        │  reads/writes                │ enqueues Celery task
        ▼                              ▼
   PostgreSQL                        Redis (Celery broker + result backend)
                                        │
                                        ▼
                                celery_worker (same image as backend)
                                  - detection.py: YOLOv8 + weapon-model inference
                                  - tracker.py: centroid/IoU tracking
                                  - tracking_pipeline.py: Risk scoring,
                                    zone/rule evaluation, narration, incidents
                                  - two entry points sharing the above:
                                    process_video_task      (uploaded file,
                                                              ProcessPoolExecutor
                                                              over fixed chunks)
                                    process_live_camera_task (RTSP/webcam stream,
                                                              frame by frame,
                                                              real time)
                                  - writes observations/events/incidents/metrics
```

The backend uses a strict **service-layer architecture**: `routers/` only
handle HTTP in/out, `services/` hold business logic, `models/` are the
SQLAlchemy ORM classes, `schemas/` are Pydantic validation layers,
`algorithms/` are pure functions with no database dependency (Risk, the
tracker), `workers/` are the Celery tasks, and `websocket/` manages live
connections. Route handlers never contain business logic directly: they
always delegate to the matching service.

**Key architectural decision:** `backend/app/algorithms/risk.py` does
not re-implement the scoring algorithm: it imports the exact same functions
from the repository-root `project.py` (the CS50P module) via a `sys.path`
insert, so the CS50-graded module and the production pipeline share a single
source of truth.

## Video processing pipeline, step by step

1. A user with the `analyst` or `admin` role uploads a video through the
   *Video Library* page, or directly via `POST /api/videos/upload`.
2. The backend validates the file extension/MIME type, generates a safe
   filename (UUID-based), stores it under `uploads/`, creates a
   `video_sources` row and a `processing_jobs` row (status `queued`), and
   dispatches a Celery task.
3. The worker opens the file with `cv2.VideoCapture` and reads its FPS,
   width, height and duration, persisting them on `video_sources`.
4. The video's duration is split into chunks with `split_video_chunks()`
   (e.g. a 130s video with 30s chunks → 5 chunks, the last one 10s), and
   frame sampling + YOLO inference for each chunk are distributed across a
   `ProcessPoolExecutor`: real parallelism across CPU cores.
5. YOLOv8 (CPU, `yolov8n.pt`) detects `person`, `car`, `truck`,
   `motorcycle`, and `bus`. There is no synthetic fallback: if the model
   weights can't be loaded (an offline environment, a bad
   `YOLO_MODEL_PATH`), the job fails with that error instead of
   substituting fabricated detections -- a result this pipeline produces
   is always something the model actually saw.
6. Detections from every sampled frame are replayed in timestamp order
   through a `CentroidIoUTracker`, which assigns each object a persistent
   track ID for as long as it stays visible.
7. Every observation (centroid, bounding box, confidence, speed, direction,
   whether it's inside a zone) is written to `object_observations`.
8. For each track, the active zones and rules are evaluated and a
   Risk score is computed (see below).
9. Once the hysteresis condition is satisfied, an `incidents` row is
   created along with `incident_evidence` (an annotated frame saved to
   `uploads/evidence/`).
10. Job progress (`progress_percent`) is updated in the database; the
    `/ws/jobs/{id}` endpoint polls it and pushes changes to connected
    clients over WebSocket.
11. Finally, `performance_metrics` are recorded: total duration, frames
    processed, effective FPS, average and p95 inference latency (via NumPy
    percentile), CPU/RAM usage (via `psutil`), queue wait time, and the
    number of incidents produced.

## Live cameras

Connecting a camera is the primary way to use SentinelAI: add it under
**Cameras** with a name and its RTSP stream URL, test the connection, then
press Start. Most home IP cameras (Reolink, TP-Link Tapo, Hikvision, Wyze
with RTSP firmware, and similar) expose an RTSP URL in the form
`rtsp://user:password@camera-ip:554/stream1`, usually listed in the
camera's own app under network or advanced settings. Any source
`cv2.VideoCapture` can open works, including a plain video file path, which
is how the live pipeline is tested in this repository without needing
physical camera hardware.

Starting monitoring queues `process_live_camera_task(job_id)`
(`app/workers/tasks.py`), which:

1. Opens the stream and reads one frame at a time, in real time (no
   chunking: there is no fixed duration to split, unlike an uploaded file).
   On a read failure, it reopens the capture and retries once before
   giving up on the session: this handles both a flaky RTSP reconnect and
   -- just as commonly in practice -- a snapshot-style public webcam that
   serves one refreshed JPEG per HTTP request rather than a continuous
   stream, where `cv2.VideoCapture` legitimately reports EOF after that
   one frame (see "Known limitations" and `app/seed.py`'s bundled demo
   cameras, all of which are this kind of source).
2. Samples every `FRAME_SAMPLE_RATE`-th frame for detection, exactly like
   the file-upload path (both call `app.workers.detection.detect_frame`),
   but skips re-running detection on a frame that's byte-identical to the
   last one it processed. A snapshot-style source can otherwise return the
   exact same image on every poll between its own refreshes; without this
   check, the tracker would see "the same object, still there" on every
   poll and keep accumulating `dwell_seconds` against real wall-clock
   time, inflating Risk's dwell term for an object that, as far as this
   camera can actually tell, was only ever photographed once.
3. Feeds detections through the same `CentroidIoUTracker` and the same
   `handle_tracked_detection` function the file pipeline uses
   (`app/workers/tracking_pipeline.py`), so Risk scoring, the live
   activity narration, and incident creation work identically to an
   uploaded video.
4. Continuously overwrites a snapshot JPEG
   (`uploads/live/camera_{id}_latest.jpg`) with the current frame and its
   detection boxes burned in, served at `GET /api/cameras/{id}/snapshot`.
   This is a frequently refreshed still image, not a live video stream: a
   real low-latency video stream to the browser would need WebRTC or HLS,
   a much larger addition than this project's scope calls for, and a
   snapshot refreshed roughly once per sampled frame is enough to see
   what the camera sees and confirm detection is working.
5. Runs for up to `LIVE_SESSION_MAX_SECONDS` (default 300s), then, if the
   camera is still marked active and no stop was requested, re-queues
   itself for another session rather than looping forever inside one
   Celery task. This keeps worker slots healthy and lets Celery's own
   restart/retry behavior apply normally.
6. Stops cleanly when `POST /api/cameras/{id}/stop` sets
   `processing_jobs.stop_requested`, which the loop polls for every ~2
   seconds.

The Camera Detail page shows the live snapshot (auto-refreshing, with an
"updated Xs/m/h ago" freshness indicator so a slow-refreshing public
webcam reads as current rather than frozen), the click-to-draw zone
editor, the same live activity log component as Video Detail, and
Start/Stop controls.

**No camera is ever started automatically** -- `Camera.is_active`
defaults to `False` and only becomes `True` via an explicit
`POST /api/cameras/{id}/start`; adding a camera (including the demo ones
`app/seed.py` creates) never begins monitoring it by itself.

`app/seed.py` bundles six real, individually-verified public webcams in
Bosnia and Herzegovina as demo cameras (five Bergfex-hosted ski-resort
cams -- Jahorina, Ravna Planina, Bjelašnica ×2, Igman -- plus a BIHAMK
traffic camera in Banja Luka) instead of a synthetic/fabricated source, so
the live-camera path can be exercised end to end without needing physical
camera hardware or inventing fake footage. Each one was confirmed
reachable and showing a real current image before being added, not just
assumed to work from its URL.

## Risk algorithm

An original, fully explainable risk-scoring algorithm implemented as pure
functions in `project.py` (shared with the backend), with no randomness
anywhere: every score is derived from real observation history, combining
zone severity, dwell time, motion anomaly, time-of-day, and detection
confidence into one 0–100 score.

```
raw_risk      = 100 × (0.35·Z + 0.25·D + 0.20·M + 0.10·T + 0.10·C)
smoothed_risk = alpha × raw_risk + (1 − alpha) × previous_risk     (alpha = 0.45)
```

| Component | Meaning | Formula |
|---|---|---|
| **Z**: zone severity | 0 outside any zone | `low/medium/high/critical → 0.25/0.50/0.75/1.00` |
| **D**: dwell score | time spent in the zone vs. the rule's minimum | `min(1, dwell_seconds / minimum_dwell_seconds)` |
| **M**: motion anomaly | direction reversals and sudden speed bursts | see `calculate_motion_anomaly()` |
| **T**: temporal score | outside business hours / `after_hours_only` rule | `1.0` or `0.0` |
| **C**: confidence persistence | how consistently high-confidence recent detections are | derived from the last up-to-5 detections |

`calculate_motion_anomaly()` looks at consecutive velocity vectors for two
signals: a **direction reversal** (the cosine of the angle between two
consecutive velocity vectors is negative) and a **speed burst** (the ratio
between consecutive step speeds is ≥ 2.5×). The raw anomaly count is
normalized into `[0, 1]`.

`is_incident_triggered()` implements **hysteresis**: an incident is only
raised once the **last N consecutive** evaluations clear the rule's
threshold, so a single noisy spike can never create a (false) incident on
its own. A second hysteresis rule prevents re-raising an incident for the
same track/rule pair until the score has stayed below `threshold − 20` for
5 consecutive observations.

Final priority is derived from the smoothed score: `0–39 low`, `40–59
medium`, `60–79 high`, `80–100 critical`. Every incident also gets a
human-readable explanation, e.g.: *"Person track #14 entered the High
Security Warehouse zone, remained for 22 seconds, showed two direction
reversals, and reached a Risk score of 84.3."*

The algorithm is fully unit tested: `test_project.py` contains 17 pytest
tests covering boundary conditions, invalid inputs, hysteresis behaviour,
static movement, direction reversals, and non-evenly-divisible video
durations.

## The tracker

Rather than a heavy third-party solution (DeepSORT, ByteTrack + a
re-identification network), SentinelAI implements its own lightweight
`CentroidIoUTracker` in `backend/app/algorithms/tracker.py`. On every sampled
frame, new detections are matched against existing tracks using a
combination of bounding-box overlap (IoU) and centroid distance; unmatched
detections start a new track, and a track is retired after being
unobserved for a configurable number of consecutive frames. This is fast
enough on CPU at the frame-sampling rates the pipeline uses, and: just as
importantly: simple enough to reason about and unit test, which matters
more here than chasing state-of-the-art multi-object-tracking accuracy.

## Database schema

The PostgreSQL schema is defined through SQLAlchemy 2.0 models
(`backend/app/models/`) and a chain of Alembic migrations
(`backend/alembic/versions/`, currently `0001` through `0005`), with
foreign keys, indexes on commonly filtered columns, and UTC timestamps
throughout.

| Table | Purpose | Notable fields |
|---|---|---|
| `users` | Accounts, roles, hashed passwords | `email`, `role` (admin/analyst/viewer), `hashed_password`, `is_active` |
| `refresh_tokens` | Revocable refresh tokens | `user_id`, `token_hash`, `expires_at`, `revoked_at` |
| `audit_logs` | Trail of important actions | `user_id`, `action`, `resource_type`, `resource_id`, `details` |
| `cameras` | Camera registry (live RTSP sources) | `name`, `location`, `rtsp_url`, `owner_id`, `is_active` |
| `video_sources` | Uploaded video files | `original_filename`, `stored_filename`, `duration_seconds`, `fps`, `width`, `height` |
| `processing_jobs` | One analysis run, either an uploaded video or a live-camera session | `video_source_id` or `camera_id` (exactly one set), `is_live`, `stop_requested`, `status`, `progress_percent` |
| `detection_models` | Registered detection models | `name`, `version`, `weights_path`, `is_stub` |
| `zones` | Polygon security zones per camera | `severity`, `polygon_json` (normalized `[x, y]` points), `minimum_dwell_seconds` |
| `rules` | Rules scoped to a zone | `object_classes`, `after_hours_only`, `risk_threshold`, `consecutive_required` |
| `tracked_objects` | One track within one processing job | `track_number`, `object_class`, `dominant_color`, `first_seen_at`, `last_seen_at`, `final_risk_score` |
| `object_observations` | Every single observation of a track | `frame_number`, `centroid_x/y`, `bbox_x1/y1/x2/y2`, `confidence`, `zone_id`, `risk_score` |
| `activity_events` | Live narration log entries | `event_type` (sighting/movement/anomaly/escalation/weapon/status), `severity`, `description`, `risk_score` |
| `incidents` | Created incidents | `risk_score`, `status`, `priority`, `summary`, `resolution_notes`, `resolved_by/at` |
| `incident_evidence` | Annotated evidence frames | `frame_path`, `frame_number`, `timestamp_seconds` |
| `performance_metrics` | Per-job performance data | `processing_fps`, `avg_latency_ms`, `p95_latency_ms`, `avg_cpu_percent`, `avg_ram_mb`, `queue_wait_seconds` |

## Authentication & RBAC

Passwords are hashed with `passlib[bcrypt]`: never stored in plain text.
Login returns a short-lived JWT access token and a rotating refresh token
that is persisted (and revocable) in `refresh_tokens`, so logout is a real
server-side action, not just discarding a token on the client.

| Role | Permissions |
|---|---|
| `admin` | Full control: users, all cameras/zones/rules, all incidents, audit log |
| `analyst` | Upload video, create cameras/zones/rules, resolve incidents |
| `viewer` | Read-only: video, processing progress, incidents, reports |

Every protected route uses a `require_roles(...)` FastAPI dependency.
Important actions: login, upload, zone creation, rule changes, incident
status changes, deletions: are automatically written to `audit_logs`.

## API reference

```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/refresh
POST   /api/auth/logout
GET    /api/auth/me

GET    /api/cameras
POST   /api/cameras
PATCH  /api/cameras/{id}
DELETE /api/cameras/{id}            (also removes its jobs/tracks/incidents/zones/rules)
POST   /api/cameras/test-connection (tries opening a stream URL before saving it)
POST   /api/cameras/{id}/start      (begins a live monitoring session)
POST   /api/cameras/{id}/stop       (requests the running session to stop cleanly)
GET    /api/cameras/{id}/jobs       (every monitoring session ever run for this camera)
GET    /api/cameras/{id}/snapshot   (latest frame with detection boxes, refreshed live)

GET    /api/videos
POST   /api/videos/upload
GET    /api/videos/{id}
GET    /api/videos/{id}/stream      (original upload, HTTP Range-capable, for <video src>)
POST   /api/videos/{id}/process
DELETE /api/videos/{id}             (also removes its jobs/tracks/incidents/evidence/annotated files)

GET    /api/jobs/{id}
GET    /api/jobs/{id}/metrics
GET    /api/jobs/{id}/detections       (live, works mid-processing: see below)
GET    /api/jobs/{id}/events           (live activity narration log: see below)
GET    /api/jobs/{id}/annotated-video  (detection-overlay preview, HTTP Range-capable)
GET    /api/videos/{id}/jobs           (every job ever run for a video, newest first)

GET    /api/incidents          (paginated; filters: status, priority, date, camera, object_class)
GET    /api/incidents/{id}
PATCH  /api/incidents/{id}/status

GET    /api/dashboard/summary
GET    /api/dashboard/performance
GET    /api/dashboard/analytics    (incidents by hour/day/camera/class, ?days=)
GET    /api/audit-logs         (admin-only, paginated)

WS     /ws/jobs/{job_id}       (live processing progress)
WS     /ws/incidents           (live incident feed)
```

Full interactive OpenAPI/Swagger docs are served at
`http://localhost:8000/docs` whenever the backend is running.

## Frontend

A black/white/gray "security operations" theme (no accent hue: hierarchy
comes from brightness and weight), built with React, Vite, TypeScript and
Tailwind. Pages: Login / Register, Dashboard (camera status chips, stat
tiles, incidents-by-priority chart, recent incidents), Cameras (add/remove,
test connection, start/stop monitoring, never started automatically --
every camera sits idle until you explicitly press Start), Camera Detail
(live snapshot with an "updated Xs ago" freshness indicator, click-to-draw
zone editor with severity/dwell/rule-class/threshold controls, live
activity log, linked incidents scoped to that camera), Video Library
(upload + processing status + delete), Video Detail (annotated preview,
detections panel, linked incidents scoped to that video's job, delete),
Incidents (filterable table with a resolve/dismiss workflow and an alert-
delivery column), Analytics (incidents by hour-of-day and daily trend,
broken down by camera and object class -- real aggregate queries, not
anything computed client-side), Performance (latency/FPS/queue/CPU/RAM
charts via Recharts), and an admin-only Audit Logs page. Data is fetched
with TanStack Query, navigation uses React Router, and job progress/incidents
arrive live through a WebSocket hook. Zone/rule management (the polygons
and thresholds behind Risk's zone-severity term) is drawn directly on a
camera's live view (see Camera Detail above) rather than a separate
page; the underlying `/api/zones`/`/api/rules` CRUD endpoints remain
usable directly too.

Every page is route-level code-split (`React.lazy` + a single `Suspense`
boundary in `App.tsx`): a production build used to ship one ~722KB
bundle, since every page's code -- including Login/Register, which never
touch a chart -- loaded `recharts` (the single heaviest dependency, 373KB
on its own) up front regardless of which page was actually visited.
Splitting dropped the main bundle to 255KB (84.6KB gzipped), with
recharts isolated into its own chunk fetched only by the 3 pages
(Dashboard, Performance, Analytics) that use it.

### Live annotated preview

A plain `<video>` element can't attach an `Authorization` header, so
`GET /api/videos/{id}/stream` and `GET /api/jobs/{id}/annotated-video`
accept the access token as a `?token=` query parameter as well (see
`get_current_user_for_streaming`); the frontend's `authenticatedStreamUrl()`
helper builds these URLs. Both endpoints implement real HTTP Range support
(206 Partial Content) so the browser can seek/scrub rather than downloading
the whole file up front. The Video Detail page shows the raw upload while a
job is pending/processing, then automatically switches to the annotated
preview: detection boxes, track ID, confidence and Risk score drawn
directly onto the footage: once rendering finishes (`_render_annotated_video`
in `tasks.py`; boxes persist for `FRAME_SAMPLE_RATE` frames past their last
sampled detection so playback doesn't flicker between sampled frames).

### Real-time detection reporting

Uploading a video takes you straight to its Video Detail page, which
subscribes to `/ws/jobs/{id}` immediately: no need to trigger reprocessing
first. While the job is still running, every WebSocket tick carries the
running count of detected object classes (`class_counts`,
`total_tracked_objects`), not just a percentage: `tracked_objects` and
`object_observations` rows are committed to the database incrementally as
the pipeline runs, so "what's in this footage" becomes visible within
seconds of upload rather than only after the whole job finishes. This works
**independently of whether the video's camera has any zone/rule
configured**: detection and tracking always run; zone/incident evaluation
is the separate, optional layer on top (see [Known limitations](#known-limitations)).
Once a job completes, `GET /api/jobs/{id}/detections` additionally returns
full per-track detail (class, confidence, observation count, final
Risk score).

### Live activity log: narrating what's happening, not just what's detected

Alongside the raw class counts, the pipeline generates a human-readable
narration stream (`app/workers/events.py`, the `ActivityEventGenerator`
class) as it tracks each object, written to the `activity_events` table
and rendered on the right-hand panel of the Video Detail page. Descriptions
aren't just "person track #2": every line is built from real visual
attributes extracted per detection (`app/workers/visual_attributes.py`):

- **Color**: the dominant color of each bounding-box crop, classified from
  the median HSV of a downsampled patch (robust to lighting/shadow; far
  cheaper than clustering). A track's reported color is the mode across its
  whole history, not a single noisy frame. *"A red car..."*
- **Position**: frame-relative thirds, the way a person points at a
  screen: *"...in the right side of the frame"*, *"...in the top-left of
  the frame"*, *"...in the center of the frame"*.
- **Movement**: direction and qualitative speed from the track's recent
  centroid history: *"moving quickly left"*, *"stationary"*, *"moving
  slowly downward, toward the bottom of the frame"*.

One `ActivityEventGenerator` instance runs per job, fed every observation
in temporal order, and emits a new line only when something is actually
worth saying:

- **Sighting**: the very first observation of a new track, a full scene
  description: *"A red car (#3) appeared in the right side of the frame."*
- **Movement**: only on an actual change of direction (not every tick, or
  this would be as noisy as raw coordinates): *"A red car (#3) is now
  moving quickly left in the center of the frame."*
- **Anomaly**: the first observation where a track's motion-anomaly score
  (direction reversals / speed bursts, from `calculate_motion_anomaly`)
  crosses `ANOMALY_EVENT_THRESHOLD` (default 0.5): *"A gray person (#2) is
  moving erratically in the left side of the frame (anomaly score 1.00):
  possible suspicious behavior."*
- **Escalation**: whenever a track's Risk severity bucket increases
  (low → medium → high → critical): *"...risk escalated to MEDIUM
  (Risk 40.1), moving right in the center of the frame."*
- **Weapon**: any detection whose class name matches `WEAPON_CLASS_NAMES`
  (case-insensitive; default
  `knife,gun,pistol,rifle,weapon,firearm,grenade,missile`), always
  `critical` severity, flagged once per track: *"Weapon-like object
  detected on track #4 (knife)."*
- **Status**: a heartbeat line at most every `EVENT_HEARTBEAT_SECONDS`
  (default 3s) per track when nothing else fired, so the log reads as a
  continuous narration rather than only alerts: *"...continues moving
  normally"* at low severity, *"...remains at elevated risk"* otherwise.

The same per-track dominant color is also persisted on `tracked_objects`
(shown in the Video Detail per-track table) and burned into the annotated
preview video's overlay labels, so the color mentioned in the narration is
the same one visible on screen.

**Distinguishing multiple people:** every person in frame gets its own
track ID, dominant clothing color, on-screen position, and movement
direction, scored and narrated independently (`app/algorithms/tracker.py`'s
IoU+centroid matching keeps IDs stable across frames). When several people
are visible at the same time, the first sighting of each one also states
the concurrent count, e.g. *"A red person (#3) appeared in the left side
of the frame. 3 people are in view at once, each tracked separately by ID,
color, and position."* -- so the log and the per-track table both read as
distinct individuals, not one merged blob.

Every event is persisted with its severity, timestamp, and the risk score
that produced it (`GET /api/jobs/{id}/events` replays the full log for a
completed job); the WebSocket carries only the newest ~15 at a time while
a job is processing, and the frontend accumulates/dedupes them client-side
so the panel never loses earlier lines.

**On weapon detection specifically:** the bundled `yolov8n.pt` is trained
on COCO, whose 80 classes do **not** include any weapon category, so a
second, dedicated weapon-detection model (`WEAPON_MODEL_REPO_ID` /
`WEAPON_MODEL_FILENAME` / `WEAPON_MODEL_REPO_TYPE`, default
`Dricz/Weapon_Detection_YOLOv8-4`, a 5-class YOLOv8 checkpoint covering
grenade/knife/missile/pistol/rifle) runs alongside the main model on every
sampled frame, for both uploaded video and live cameras
(`app/workers/detection.py`: `load_weapon_model` / `detect_weapons`). Its
detections are normalized into `WEAPON_CLASS_NAMES` and flow through the
exact same tracking/risk/incident/narration path as any other detection --
including Risk scoring, dwell time, zone matching, and the activity
log. It's downloaded once and cached locally (see the `model_cache` volume
in `docker-compose.yml`); if it can't be fetched (no internet, gated
repo), weapon detection is simply skipped for that session; set
`WEAPON_MODEL_ENABLED=false` to disable it outright. Swap in a different
`WEAPON_MODEL_REPO_ID`/`WEAPON_MODEL_FILENAME` to extend or replace
coverage; no other code changes needed.

Batons/sticks are **not** covered: as of this writing there is no
pretrained open-source checkpoint for baton/stick detection (checked
Hugging Face and Roboflow Universe), unlike guns/knives/grenades, which
several community YOLOv8 checkpoints already cover well. A baton swung as
a weapon still surfaces indirectly via the **Anomaly** event (erratic/
sudden motion) and Risk's motion-anomaly term, just not as its own
named weapon class, until such a model is trained or found.

## Repository structure

```
sentinelai/
├── project.py                 # CS50P: Risk algorithm + CLI (stdlib only)
├── test_project.py            # 17 pytest tests
├── requirements.txt
├── README.md
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/               # config, security (JWT/bcrypt), logging
│   │   ├── db/                 # SQLAlchemy engine/session
│   │   ├── models/              # 15 tables
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── routers/             # FastAPI route handlers (cameras, videos, jobs, incidents...)
│   │   ├── services/            # business logic (camera_service, video_service, job_service...)
│   │   ├── algorithms/          # Risk import + tracker.py
│   │   ├── workers/             # celery_app.py, tasks.py (Celery entry points),
│   │   │                        # detection.py, tracking_pipeline.py, annotate.py,
│   │   │                        # events.py, visual_attributes.py (shared pipeline core)
│   │   ├── websocket/           # connection manager
│   │   └── seed.py              # demo data
│   └── alembic/                 # migrations
├── frontend/
│   ├── src/                     # React pages, hooks, API client
│   └── package.json
├── uploads/                     # uploaded video, evidence frames, annotated previews,
│   │                            # and live/ (per-camera snapshot JPEGs)
└── docs/                        # extended HTML project documentation
```

## Environment variables

All variables live in `.env.example` (copy to `.env`). Key ones:

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg2://sentinel:sentinel@postgres:5432/sentinel` |
| `JWT_SECRET` | Signing key for JWTs: **change in production** |: |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes | `30` / `7` |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Redis connections for Celery | `redis://redis:6379/0,1` |
| `CORS_ORIGINS` | Allowed frontend origins (`http://localhost` with no port is required for the nginx entrypoint on `:80` -- see "Production hardening") | `http://localhost:5173,http://localhost:3000,http://localhost` |
| `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`, `ALLOWED_VIDEO_EXTENSIONS` | Upload validation: `MAX_UPLOAD_SIZE_MB=0` means unlimited | `/app/uploads`, `0`, `.mp4,.avi,.mov,.mkv,.ts,.mxf,.webm` |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`, `DB_POOL_RECYCLE_SECONDS` | PostgreSQL connection pool sizing | `20`, `40`, `30`, `1800` |
| `CELERY_WORKER_CONCURRENCY` | Parallel worker threads per `celery_worker` container | `8` |
| `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS` / `CELERY_TASK_TIME_LIMIT_SECONDS` | Ceiling for a single video-processing job | `21600` (6h) / `23400` (6.5h) |
| `UVICORN_WORKERS` | API process count (separate from Celery concurrency) | `2` |
| `DEFAULT_CHUNK_SECONDS`, `FRAME_SAMPLE_RATE` | Pipeline tuning | `30`, `5` |
| `LIVE_SESSION_MAX_SECONDS` | Max length of one live-camera task invocation before re-queuing | `300` |
| `YOLO_MODEL_PATH` | YOLO weights (the job fails cleanly if these can't be loaded -- no synthetic fallback) | `yolov8n.pt` |
| `INCIDENT_RISK_THRESHOLD`, `INCIDENT_CONSECUTIVE_REQUIRED` | Default rule thresholds | `70.0`, `3` |
| `VITE_API_BASE_URL`, `VITE_WS_BASE_URL` | Frontend → backend endpoints | `http://localhost:8000`, `ws://localhost:8000` |

### Scaling for large deployments

SentinelAI's defaults are tuned for a multi-camera, multi-operator
deployment rather than a single local demo:

- **Uploads are unbounded by default** (`MAX_UPLOAD_SIZE_MB=0`). The upload
  handler always streams straight to disk in 8MB chunks (`video_service.
  save_upload`): it never buffers a file fully in memory, so there's no
  practical ceiling besides the disk space backing the `uploads` volume.
  Raise/lower the cap per-deployment if you want one.
- **An `nginx` reverse proxy** (`nginx/nginx.conf`) sits in front of the
  stack on port 80 with `client_max_body_size 0` (unlimited) and 3600s
  read/send timeouts, so a reverse proxy never becomes the thing that
  silently truncates a multi-gigabyte upload or a long-lived WebSocket
  connection: a very common production gotcha. Point real traffic at port
  80 instead of hitting the backend/frontend ports directly.
  `docker compose up` already starts it alongside the rest of the stack.
- **The PostgreSQL connection pool** is sized for many concurrent
  dashboard/API/WebSocket clients (`DB_POOL_SIZE=20`, `DB_MAX_OVERFLOW=40`
  by default), not the handful of connections a single-user demo needs.
- **Celery** runs with `--pool=threads` and `CELERY_WORKER_CONCURRENCY=8`
  parallel threads (not the default "prefork" process pool: each video-
  processing task itself spawns a `ProcessPoolExecutor` to parallelize
  chunk/inference work, and CPython refuses to let a daemonic process --
  which is what a prefork pool worker is -- spawn children of its own;
  threads don't have that restriction, so `--max-tasks-per-child`, a
  prefork-only flag, doesn't apply here and is intentionally not set).
  Each concurrently-monitored live camera occupies one thread for the
  life of its session (re-queuing into a fresh thread roughly every
  `LIVE_SESSION_MAX_SECONDS`), so `CELERY_WORKER_CONCURRENCY` must be >=
  the number of cameras you want actively monitored at once, plus
  headroom for upload-processing jobs, or the extra cameras just queue
  until a thread frees up. `task_acks_late=True` means a job re-queues
  instead of being lost if a worker is killed mid-processing, and
  multi-hour soft/hard time limits keep long camera footage from being
  killed partway through. Scale
  `CELERY_WORKER_CONCURRENCY` or add more `celery_worker` replicas to
  match your camera count.
- **`uvicorn`** runs with multiple worker processes (`UVICORN_WORKERS`,
  default 2) and a 3600s keep-alive timeout for large uploads.

None of this requires a GPU or paid infrastructure: it's standard Docker
Compose scaling knobs, all exposed as environment variables so a real
deployment can be sized to its camera count and traffic without touching
code.

## Running with Docker Compose

```bash
cp .env.example .env            # adjust JWT_SECRET etc. for anything beyond local demo use
docker compose up --build
```

This starts 6 services: `postgres`, `redis`, `backend` (FastAPI, which runs
`alembic upgrade head` automatically before `uvicorn` starts),
`celery_worker`, `frontend`, and `nginx`: a reverse proxy in front of
everything with an unlimited request body size and long timeouts (see
[Scaling for large deployments](#scaling-for-large-deployments)).

- Everything through the proxy: **http://localhost** (dashboard at `/`,
  API at `/api/*`, docs at `/docs`, WebSockets at `/ws/*`)
- Backend / Swagger docs directly: **http://localhost:8000/docs**
- Frontend dashboard directly: **http://localhost:5173**

Seed the database with demo data (works without processing a real video):

```bash
docker compose exec backend python -m app.seed
```

Demo accounts: `admin@sentinelai.dev / Admin123!` and
`analyst@sentinelai.dev / Analyst123!`

## Local development without Docker

```bash
# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate      # or source .venv/bin/activate on Linux/Mac
pip install -r ../requirements.txt
alembic upgrade head          # requires a running Postgres, or a SQLite DATABASE_URL for a quick demo
python -m app.seed
uvicorn app.main:app --reload

# Celery worker (separate terminal, requires Redis)
celery -A app.workers.celery_app worker --loglevel=info

# Frontend
cd frontend
npm install
npm run dev     # http://localhost:5173
```

## Tests and the CS50P CLI

```bash
python -m pytest test_project.py -v
python project.py demo-risk
python project.py split-video --duration 130 --chunk-size 30
python project.py serve
```

`project.py` contains, alongside `main()`, four top-level functions:
`calculate_risk`, `is_incident_triggered`, `calculate_motion_anomaly`,
and `split_video_chunks`: all covered by the 17 pytest tests in
`test_project.py` (boundary cases, invalid inputs, hysteresis behaviour,
static movement, direction reversals, and a non-evenly-divisible video
duration).

## Example API flow

```bash
curl -X POST localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@sentinelai.dev","password":"Admin123!"}'
# -> {"access_token": "...", "refresh_token": "..."}

curl -X POST localhost:8000/api/videos/upload -H "Authorization: Bearer <token>" \
  -F "file=@dock_feed.mp4"
# -> creates a video_sources + processing_jobs row, dispatches the Celery task

curl localhost:8000/api/jobs/1
curl "localhost:8000/api/incidents?status=open&priority=high"
curl -X PATCH localhost:8000/api/incidents/1/status -H "Authorization: Bearer <token>" \
  -d '{"status":"resolved","resolution_notes":"Verified with site security."}'
```

## CS50P requirement mapping

| Requirement | Status |
|---|---|
| `project.py` in the root, with `main()` + 3+ custom functions | ✅ 4 functions: `calculate_risk`, `is_incident_triggered`, `calculate_motion_anomaly`, `split_video_chunks` |
| `test_project.py` with tests for 3+ functions | ✅ 17 tests, covering all four functions plus edge/invalid cases |
| `requirements.txt` | ✅ in the repo root |
| `README.md`, 500+ words | ✅ (this file) |

## Known limitations

- No GPU is required: the baseline targets CPU inference. YOLOv8n is small
  enough to run on CPU at a reduced frame-sampling rate.
- If `ultralytics` cannot download the YOLOv8 weights (an offline
  environment, a bad `YOLO_MODEL_PATH`), the job fails with that error
  instead of continuing on fabricated data. This is deliberate: a result
  this pipeline produces should always be something the model actually
  saw, never a stand-in. Have the weights available (or cached locally)
  before running a job.
- WebSocket progress uses per-connection database polling rather than
  Redis pub/sub: simple and reliable for a single backend replica, but not
  horizontally scalable as-is.
- Detection/tracking always runs on upload, but an uploaded video isn't
  linked to a camera, so zone-based incident scoring (the `Z` term in
  Risk) stays at 0 for the dashboard-uploaded path regardless of what
  zones exist. Detections, tracking, confidence and motion-anomaly-based
  risk still work fully; the zone-severity component only applies to a
  camera's live-monitoring sessions, where zones are configured from the
  Camera Detail page's zone editor (or `backend/app/seed.py` for demo
  data).
- Annotated-preview rendering re-reads every frame of the source video
  once tracking finishes, so its cost scales with total video length, not
  just the sampled frames used for detection; for very long footage this
  adds meaningfully to total job time.
- Live-camera tracking state (track IDs, each track's risk history) is
  persisted to Redis and restored across re-queued session chunks (see
  "Production hardening" below), so this is no longer a hard reset. It is
  still not a single unbroken process, though: if the Celery worker
  restarts, or Redis itself is flushed/unavailable, between two chunks
  (every `LIVE_SESSION_MAX_SECONDS`, 300s by default), that session falls
  back to a fresh tracker and loses continuity for objects that were
  mid-track at that exact moment. A fully continuous tracker would need
  one long-lived worker process per camera instead of Celery's short-task
  model; the Redis-backed approach covers the common case (normal
  operation) without that architectural change.
- A camera's live view is a frequently refreshed snapshot image, not a
  video stream; see "Live cameras" above for why.
- The default weapon-detection model
  (`WEAPON_MODEL_REPO_ID=Dricz/Weapon_Detection_YOLOv8-4`) covers
  grenade/knife/missile/pistol/rifle, but has no baton/stick class -- no
  pretrained open-source checkpoint for that exists as of this writing.
  Point `WEAPON_MODEL_REPO_ID`/`WEAPON_MODEL_FILENAME` at a different model
  to extend or replace coverage; no other code changes needed.
- **Redis has no password and is published on the host**
  (`docker-compose.yml`, port 6379, no `requirepass`). The code-execution
  path this previously enabled (an unauthenticated pickle payload) is
  fixed -- see "Security hardening" below -- but an unauthenticated Redis
  is still readable/writable/flushable by anyone who can reach that port,
  which affects the Celery broker/result backend and the live-tracker
  state key alike. Add `requirepass` (and update `REDIS_URL`/
  `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` accordingly) before
  exposing this stack beyond a trusted local network.

## Production hardening

Beyond the core detection/tracking/scoring pipeline, these exist
specifically to make the system safe and usable in a real deployment, not
just a demo:

- **Real-time alerting** (`app/services/alert_service.py`): any incident at
  or above `ALERT_MIN_PRIORITY` (default `high`) is dispatched to email
  (SMTP, stdlib `smtplib`) and/or a generic webhook (Slack/Discord/
  PagerDuty/your own endpoint all accept a plain JSON POST) the moment it's
  created -- not just logged for someone to notice later. A per-
  `(camera, object_class)` cooldown (`ALERT_COOLDOWN_SECONDS`, default
  120s) stops one lingering detection from paging someone every few
  seconds, and delivery is strictly best-effort: a bad SMTP password or an
  unreachable webhook is logged and never blocks or fails the detection
  pipeline. Each `Incident` records whether an alert was actually attempted
  and which channels succeeded (`alert_sent`, `alert_channels`), shown as a
  column on the Incidents page. `POST /api/alerts/test` (admin-only) sends
  a synthetic critical alert through every configured channel so you can
  confirm delivery works before relying on it.
- **Weapon-person association** (`app/workers/tracking_pipeline.py`
  `associate_weapons_to_people`): a weapon-class track within
  `WEAPON_PERSON_ASSOCIATION_MAX_DISTANCE_RATIO` (default 25%) of the frame
  diagonal of an active person track is treated as held by that person --
  narrated by name (*"Person #3 appears to be holding a knife (track
  #5)"*) and immediately raised as a **CRITICAL** incident with a real-time
  alert, independent of any zone/rule configuration. A weapon next to a
  person is inherently worth surfacing immediately, not gated behind
  dwell-time or a configured zone.
- **Live-camera tracker persistence** (`app/workers/tracking_pipeline.py`
  `save_live_tracking_state` / `load_live_tracking_state`): track IDs, risk
  history, and narration state for a live-camera session are serialized as
  plain JSON (not pickle -- see "Security hardening" below) to Redis at the
  end of each `LIVE_SESSION_MAX_SECONDS` chunk and restored by the next
  re-queued invocation, so a continuously-monitored camera keeps one
  stable set of track IDs for the life of the session instead of resetting
  every 300 seconds. Falls back to a fresh tracker if Redis is unreachable
  or the saved state can't be loaded, rather than failing the task; a TTL
  on the saved blob bounds how long stale state could ever linger if
  cleanup is somehow skipped (e.g. a worker crash mid-session).
- **Auth rate limiting** (`app/core/rate_limit.py`): `/api/auth/login` and
  `/api/auth/register` are rate-limited per client IP via a Redis-backed
  fixed-window counter (correct across multiple `UVICORN_WORKERS`
  processes, unlike an in-memory counter), to slow down credential-
  stuffing/brute-force attempts and registration spam. Fails open if Redis
  itself is unreachable, rather than locking every user out over an
  unrelated outage.
- **Fail-fast production config validation** (`app/core/config.py`
  `_validate_production_safety`): with `ENV=production`, the app refuses to
  start at all if `JWT_SECRET` is still the bundled dev default (or under
  32 characters) or if `DEBUG` is still `true` -- a wrong-but-running
  deployment is worse than one that won't start.
- **Global exception handler** (`app/main.py`): any exception that escapes
  a route handler is always logged in full server-side, but the client
  only ever sees a generic "Internal server error" (unless `DEBUG=true`),
  so a bug can't leak internal exception messages, stack traces, or query
  details to a caller.
- **nginx re-resolves its upstreams instead of caching them forever**
  (`nginx/nginx.conf`): nginx's static `upstream {}` block resolves a
  hostname like `backend` once, at startup, and keeps using that IP
  until nginx itself restarts. Recreating the `backend`/`frontend`
  container for any reason (a rebuild, `docker compose up`, a crash
  restart) gives it a new internal IP, which previously left nginx
  silently proxying to a dead address until someone noticed the 502s and
  restarted it by hand. `resolver 127.0.0.11 valid=10s` (Docker's
  embedded DNS) plus a `set $upstream ...; proxy_pass $upstream;`
  indirection instead of the `upstream {}` block makes nginx re-resolve
  every 10s, so it self-heals within that window with zero manual
  intervention.
- **CORS covers the nginx entrypoint, not just direct dev access**: the
  frontend's API base URL is an absolute `http://localhost:8000` baked in
  at build time (`VITE_API_BASE_URL`), so even a page served through
  nginx on `:80` still calls the backend cross-origin from the browser's
  point of view. `CORS_ORIGINS` includes `http://localhost` (no port) by
  default for exactly this reason -- without it, every API call made from
  the nginx-served page fails outright with no
  `access-control-allow-origin` header, even though the direct `:5173`
  dev path works fine.

### Query efficiency

A pass specifically looking for N+1 query patterns and redundant
round-trips, verified by counting actual SQL statements against a live
database rather than just reading the code:

- **Dashboard summary: 13 queries → 5** (`app/services/dashboard_service.py`):
  previously one `SELECT COUNT(*)` per metric (cameras, active cameras,
  videos, each of 4 job statuses, open incidents, incidents-last-24h, and
  one more per `IncidentPriority` in a Python loop). Postgres `FILTER`-
  qualified aggregates (`func.count(...).filter(...)`) compute every count
  for a table in one scan instead of rescanning it once per metric.
- **Incident list: N+1 on evidence** (`app/services/incident_service.py`):
  `IncidentRead.evidence` is a relationship with no eager-loading
  strategy, so serializing a page of incidents triggered one extra lazy-
  load query per row. `selectinload(Incident.evidence)` replaces that
  with exactly one extra query for the whole page, confirmed to stay flat
  as row count grows (not proportional to it).
- **Video deletion: the same pattern, twice** (`app/services/video_service.py`):
  one incidents query per job being deleted, then one more per incident
  for its evidence files. Collapsed to a single `selectinload` query
  across every job at once.
- **Camera list: N+1 against the API, not just the DB**
  (`Cameras.tsx`/`Dashboard.tsx`): both fetched every camera's most recent
  job via `Promise.all`, one HTTP request per camera, purely to render a
  status dot. `GET /api/cameras` now returns each camera's
  `latest_job_status` inline, computed server-side with a `ROW_NUMBER()
  OVER (PARTITION BY camera_id ...)` window query -- 2 queries total
  regardless of camera count or how many historical job rows each camera
  has accumulated (a live camera re-queues a new job row roughly every
  `LIVE_SESSION_MAX_SECONDS`, so that history grows unbounded over a
  camera's lifetime; a naive "fetch all jobs, group in Python" fix would
  have scaled badly here).
- **Rules-per-zone: the same pattern on the Camera Detail page**: fetched
  rules one zone at a time. `GET /api/rules` gained an optional
  `camera_id` filter (a join through `Zone`) so the page fetches every
  rule across all of a camera's zones in one request.

### Two correctness bugs these turned up along the way

Not just slow -- `CameraDetail.tsx` and `VideoDetail.tsx` were showing the
**wrong incidents**: both queried `/api/incidents` with no scoping filter
at all, so each page displayed the 50 most recent incidents *system-wide*,
indistinguishable from incidents actually tied to that camera or video
once more than one of either existed. Fixed by wiring the already-
existing `camera_id` filter into `CameraDetail.tsx`, and adding a new
`processing_job_id` filter (`app/routers/incidents.py`) for
`VideoDetail.tsx`, since no equivalent existed for scoping by video/job.

### Security hardening

Three issues found and fixed by a dedicated security-review pass over
this project's own code (not general advice -- each one was a concrete,
verified bug in a specific file, fixed and re-tested against the live
stack before being considered done):

- **SSRF in camera stream URLs** (`app/services/camera_service.py`
  `_validate_stream_url`): `POST /api/cameras/test-connection` and the
  live-camera pipeline opened whatever URL was supplied via
  `cv2.VideoCapture` with no validation at all -- any scheme, any host.
  An authenticated admin/analyst could point it at an internal-only
  target (`http://169.254.169.254/latest/meta-data/`, the cloud-metadata
  address every major provider uses, or the server's own loopback) and
  the `ok`/`width`/`height`/`fps` response would reveal what's reachable.
  Fixed with a scheme allowlist (`rtsp(s)`, `http(s)`, `rtmp(s)`) and a
  block on hostnames resolving to loopback or link-local addresses,
  applied everywhere a URL is accepted or reused (create, update, test,
  and again immediately before a live session actually connects).
  Deliberately does **not** block private LAN ranges
  (`192.168.x.x`/`10.x.x.x`): that's exactly where this product's real
  home/office IP cameras live (see "Live cameras" above), so blocking all
  private IPs would break the core use case, not just attacks. Verified
  against the standard SSRF bypass toolkit (decimal/hex/octal IP
  encoding, IPv4-mapped IPv6, case variation) with zero bypasses found,
  alongside confirming real camera URLs still pass.
- **Insecure deserialization in live-tracker Redis state**
  (`app/workers/tracking_pipeline.py`): `load_live_tracking_state` used
  to call `pickle.loads()` on whatever bytes were stored at
  `sentinel:live_tracker_state:{job_id}` in Redis. Redis is published on
  the host (`docker-compose.yml`, no `requirepass` configured -- see
  "Known limitations"), so anyone reachable on that port could write a
  malicious pickle payload to that key; the next time that job's session
  re-queued (routine, every `LIVE_SESSION_MAX_SECONDS`), the worker would
  deserialize and execute it. Replaced with explicit JSON
  (de)serialization of only the known, simple fields each structure
  actually has -- this doesn't just mitigate the issue, `json.loads()`
  has no code-execution primitive at all, so the vulnerability class is
  gone regardless of who else can write to that key. Verified with a
  simulated malicious pickle payload that previously would have executed
  code; it now fails safely with a decode error and falls back to a
  fresh tracker.
- **Unhandled 500 on NaN/Infinity input** (`app/main.py`,
  `app/schemas/zone.py`): two distinct crash paths. Plain float fields
  with no custom validator (`risk_threshold`, `minimum_dwell_seconds`)
  silently accepted `Infinity`/`NaN` as "valid" (Python's `float`
  supports them, and Pydantic doesn't reject them by default), which then
  reached Postgres and only crashed later when the success response tried
  to serialize it back (Starlette's `JSONResponse` enforces strict,
  spec-compliant JSON) -- an unhandled 500 on a row that had *already
  been persisted*. Fixed with `Field(allow_inf_nan=False)` so Pydantic
  itself rejects it before the handler runs. Separately, a field with a
  custom `@field_validator` (the zone polygon's `[0,1]` range check)
  already rejected the bad value correctly, but Pydantic v2 wraps a
  validator's raised `ValueError` as `ctx.error` holding the exception
  *object*, which plain `json.dumps` can't encode -- reporting the
  rejection crashed just as hard as accepting the bad value did
  elsewhere. Fixed with a `RequestValidationError` handler that
  recursively sanitizes the error payload before it's serialized.

## Future improvements

ONNX Runtime/TensorRT as an optional faster inference backend, an optional
GPU Celery queue, distributed multi-node processing, semantic search over
incident summaries (embeddings + a vector database), SMS notifications
(Twilio or similar, alongside the email/webhook alerting already in
place), and Redis pub/sub-backed WebSocket fan-out for multi-replica
deployments.

## Design decisions explained

**Why a CPU baseline:** the project should run on a laptop or a cheap VPS
without CUDA. YOLOv8n is small enough to be CPU-viable at low
frame-sampling rates, so no GPU is required for a working deployment.

**Why a custom, lightweight tracker instead of a heavy third-party one**
(e.g. DeepSORT/ByteTrack + a re-identification model): the goal of this
project is explainable zone/rule evaluation, not state-of-the-art
multi-object tracking. IoU + centroid matching is simple to reason about,
has no extra model weights to download, and is fast enough on CPU for the
frame-sampling rates this pipeline actually uses.

---

Extended technical documentation (with additional diagrams and
component-by-component explanations) lives at
[`docs/sentinelai-dokumentacija.html`](docs/sentinelai-dokumentacija.html).

## License

MIT: see `LICENSE` if present, or treat this project as MIT-licensed for
educational/demonstration purposes.
