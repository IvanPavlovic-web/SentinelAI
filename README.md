# SentinelAI — Edge Video Intelligence & Incident Detection Platform

**CS50P Final Project** by Ivan Pavlović
**CS50 demo video:** _[PLACEHOLDER — add your CS50 submission video URL here]_

A self-hostable video-analysis platform: upload a video, and it detects and
tracks every person/vehicle in it, shows you exactly what it found with an
annotated preview (detection boxes, track IDs, confidence, risk score burned
into the footage), and raises **explainable, scored incidents** when a
tracked object's behavior crosses a configured risk threshold — instead of
a wall of raw bounding boxes. It is an AI inference and video-processing
pipeline, not just an object detector: upload → detect → track → preview →
alert, end to end, running entirely on CPU.

The product surface is deliberately narrow: **upload a video, watch it get
analyzed in real time, see exactly what the AI saw, delete it when you're
done.** Camera/zone/rule management exists underneath (zones feed the
STAR-Risk scoring formula and the seed script creates one demo zone+rule),
but there's no UI for managing them — this is a video analysis tool, not a
camera-fleet management console.

---

## Table of contents

1. [Problem it solves](#problem-it-solves)
2. [Features](#features)
3. [Technology stack](#technology-stack)
4. [Architecture](#architecture)
5. [Video processing pipeline, step by step](#video-processing-pipeline-step-by-step)
6. [STAR-Risk algorithm](#star-risk-algorithm)
7. [The tracker](#the-tracker)
8. [Database schema](#database-schema)
9. [Authentication & RBAC](#authentication--rbac)
10. [API reference](#api-reference)
11. [Frontend](#frontend)
12. [Repository structure](#repository-structure)
13. [Environment variables](#environment-variables)
14. [Running with Docker Compose](#running-with-docker-compose)
15. [Local development without Docker](#local-development-without-docker)
16. [Tests and the CS50P CLI](#tests-and-the-cs50p-cli)
17. [Example API flow](#example-api-flow)
18. [CS50P requirement mapping](#cs50p-requirement-mapping)
19. [Known limitations](#known-limitations)
20. [Future improvements](#future-improvements)
21. [Design decisions explained](#design-decisions-explained)
22. [License](#license)

---

## Problem it solves

Physical-security teams running camera networks (warehouses, retail
back-of-house, construction sites) typically have two bad options: pay for an
expensive cloud VMS/AI subscription, or have humans stare at a wall of video
feeds. SentinelAI is a third option — a platform you run yourself, with no
GPU requirement, that answers concrete security questions:

- Did a person enter a restricted area?
- Did a vehicle remain in a zone longer than allowed?
- Did an object show abnormal movement — sudden direction reversals, bursts
  of speed?
- Which cameras and zones generate the most incidents?
- How long did inference take, what FPS was achieved, how long did jobs wait
  in the queue?

## Features

- **Upload-based ingestion** with asynchronous background processing (Celery);
  uploading a video takes you straight into a live analysis view.
- **Multi-object tracking** via a custom, lightweight centroid/IoU tracker —
  no heavy third-party re-identification model to download or maintain.
- **Annotated AI preview** — the source video is re-rendered with detection
  boxes, track IDs, confidence and STAR-Risk burned in frame by frame, so
  the preview shows exactly what the AI found, not just a status bar.
- **Real-time detection reporting** over WebSockets: running object-class
  counts stream in while the job is still processing, not only once it
  completes.
- **STAR-Risk** — an original, explainable 0–100 risk-scoring algorithm that
  fuses zone severity, dwell time, motion anomaly, time-of-day, and
  detection-confidence persistence, with exponential smoothing and
  hysteresis against noisy duplicate alerts.
- Automatic incident creation with evidence frames, a resolve/dismiss
  workflow with analyst notes, and a full audit trail.
- Delete a video (and everything derived from it — jobs, tracks,
  observations, incidents, evidence, the annotated preview file) in one
  action.
- A role-based dashboard (admin/analyst/viewer): video library, incidents
  table with filters, performance charts, and an admin-only audit log —
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
| Computer vision | OpenCV (headless), Ultralytics YOLOv8 (CPU, with a stub-detector fallback), NumPy, `psutil` |
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
                                  - OpenCV frame reading
                                  - ProcessPoolExecutor (parallel chunks)
                                  - YOLOv8 inference (or stub fallback)
                                  - tracker.py (centroid/IoU tracking)
                                  - STAR-Risk zone/rule evaluation
                                  - writes observations/incidents/evidence/metrics
```

The backend uses a strict **service-layer architecture**: `routers/` only
handle HTTP in/out, `services/` hold business logic, `models/` are the
SQLAlchemy ORM classes, `schemas/` are Pydantic validation layers,
`algorithms/` are pure functions with no database dependency (STAR-Risk, the
tracker), `workers/` are the Celery tasks, and `websocket/` manages live
connections. Route handlers never contain business logic directly — they
always delegate to the matching service.

**Key architectural decision:** `backend/app/algorithms/star_risk.py` does
not re-implement the scoring algorithm — it imports the exact same functions
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
   `ProcessPoolExecutor` — real parallelism across CPU cores.
5. YOLOv8 (CPU, `yolov8n.pt`) detects `person`, `car`, `truck`,
   `motorcycle`, and `bus`. If the model weights are unavailable (an
   offline/sandboxed environment), the worker automatically falls back to a
   deterministic stub detector so the rest of the pipeline keeps working
   end to end for demo purposes.
6. Detections from every sampled frame are replayed in timestamp order
   through a `CentroidIoUTracker`, which assigns each object a persistent
   track ID for as long as it stays visible.
7. Every observation (centroid, bounding box, confidence, speed, direction,
   whether it's inside a zone) is written to `object_observations`.
8. For each track, the active zones and rules are evaluated and a
   STAR-Risk score is computed (see below).
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

## STAR-Risk algorithm

**Spatio-Temporal Adaptive Risk Scoring** — an original, fully explainable
algorithm implemented as pure functions in `project.py` (shared with the
backend), with no randomness anywhere: every score is derived from real
observation history.

```
raw_risk      = 100 × (0.35·Z + 0.25·D + 0.20·M + 0.10·T + 0.10·C)
smoothed_risk = alpha × raw_risk + (1 − alpha) × previous_risk     (alpha = 0.45)
```

| Component | Meaning | Formula |
|---|---|---|
| **Z** — zone severity | 0 outside any zone | `low/medium/high/critical → 0.25/0.50/0.75/1.00` |
| **D** — dwell score | time spent in the zone vs. the rule's minimum | `min(1, dwell_seconds / minimum_dwell_seconds)` |
| **M** — motion anomaly | direction reversals and sudden speed bursts | see `calculate_motion_anomaly()` |
| **T** — temporal score | outside business hours / `after_hours_only` rule | `1.0` or `0.0` |
| **C** — confidence persistence | how consistently high-confidence recent detections are | derived from the last up-to-5 detections |

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
reversals, and reached a STAR-Risk score of 84.3."*

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
enough on CPU at the frame-sampling rates the pipeline uses, and — just as
importantly — simple enough to reason about and unit test, which matters
more here than chasing state-of-the-art multi-object-tracking accuracy.

## Database schema

The PostgreSQL schema is defined through SQLAlchemy 2.0 models
(`backend/app/models/`) and a single Alembic migration
(`backend/alembic/versions/0001_initial_schema.py`), with foreign keys,
indexes on commonly filtered columns, and UTC timestamps throughout.

| Table | Purpose | Notable fields |
|---|---|---|
| `users` | Accounts, roles, hashed passwords | `email`, `role` (admin/analyst/viewer), `hashed_password`, `is_active` |
| `refresh_tokens` | Revocable refresh tokens | `user_id`, `token_hash`, `expires_at`, `revoked_at` |
| `audit_logs` | Trail of important actions | `user_id`, `action`, `resource_type`, `resource_id`, `details` |
| `cameras` | Camera registry | `name`, `location`, `rtsp_url`, `owner_id`, `is_active` |
| `video_sources` | Uploaded video files | `original_filename`, `stored_filename`, `duration_seconds`, `fps`, `width`, `height` |
| `processing_jobs` | Status/progress of one video's processing | `status`, `progress_percent`, `celery_task_id`, `error_message` |
| `detection_models` | Registered detection models | `name`, `version`, `weights_path`, `is_stub` |
| `zones` | Polygon security zones per camera | `severity`, `polygon_json` (normalized `[x, y]` points), `minimum_dwell_seconds` |
| `rules` | Rules scoped to a zone | `object_classes`, `after_hours_only`, `risk_threshold`, `consecutive_required` |
| `tracked_objects` | One track within one processing job | `local_track_id`, `object_class`, `first_seen`, `last_seen`, `max_risk_score` |
| `object_observations` | Every single observation of a track | `frame_number`, `centroid_x/y`, `bounding_box_json`, `confidence`, `speed`, `direction_degrees`, `inside_zone` |
| `incidents` | Created incidents | `star_risk_score`, `status`, `priority`, `summary`, `resolution_notes`, `resolved_by/at` |
| `incident_evidence` | Annotated evidence frames | `frame_path`, `frame_number`, `timestamp_seconds` |
| `performance_metrics` | Per-job performance data | `processing_fps`, `avg_latency_ms`, `p95_latency_ms`, `avg_cpu_percent`, `avg_ram_mb`, `queue_wait_seconds` |

## Authentication & RBAC

Passwords are hashed with `passlib[bcrypt]` — never stored in plain text.
Login returns a short-lived JWT access token and a rotating refresh token
that is persisted (and revocable) in `refresh_tokens`, so logout is a real
server-side action, not just discarding a token on the client.

| Role | Permissions |
|---|---|
| `admin` | Full control — users, all cameras/zones/rules, all incidents, audit log |
| `analyst` | Upload video, create cameras/zones/rules, resolve incidents |
| `viewer` | Read-only — video, processing progress, incidents, reports |

Every protected route uses a `require_roles(...)` FastAPI dependency.
Important actions — login, upload, zone creation, rule changes, incident
status changes, deletions — are automatically written to `audit_logs`.

## API reference

```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/refresh
POST   /api/auth/logout
GET    /api/auth/me

GET    /api/videos
POST   /api/videos/upload
GET    /api/videos/{id}
GET    /api/videos/{id}/stream      (original upload, HTTP Range-capable, for <video src>)
POST   /api/videos/{id}/process
DELETE /api/videos/{id}             (also removes its jobs/tracks/incidents/evidence/annotated files)

GET    /api/jobs/{id}
GET    /api/jobs/{id}/metrics
GET    /api/jobs/{id}/detections       (live, works mid-processing — see below)
GET    /api/jobs/{id}/annotated-video  (detection-overlay preview, HTTP Range-capable)
GET    /api/videos/{id}/jobs           (every job ever run for a video, newest first)

GET    /api/incidents          (paginated; filters: status, priority, date, camera, object_class)
GET    /api/incidents/{id}
PATCH  /api/incidents/{id}/status

GET    /api/dashboard/summary
GET    /api/dashboard/performance
GET    /api/audit-logs         (admin-only, paginated)

WS     /ws/jobs/{job_id}       (live processing progress)
WS     /ws/incidents           (live incident feed)
```

Full interactive OpenAPI/Swagger docs are served at
`http://localhost:8000/docs` whenever the backend is running.

## Frontend

A black/white/gray "security operations" theme (no accent hue — hierarchy
comes from brightness and weight), built with React, Vite, TypeScript and
Tailwind. Pages: Login / Register, Dashboard (stat tiles, incidents-by-priority
chart, recent incidents, queue status), Video Library (upload + processing
status + delete), Video Detail (live annotated preview, detections panel,
linked incidents, delete), Incidents (filterable table with a resolve/dismiss
workflow), Performance (latency/FPS/queue/CPU/RAM charts via Recharts), and
an admin-only Audit Logs page. Data is fetched with TanStack Query,
navigation uses React Router, and job progress/incidents arrive live through
a WebSocket hook. Camera/zone/rule management has no UI by design (see
"Problem it solves" above) — the product surface is upload → analyze →
preview → delete.

### Live annotated preview

A plain `<video>` element can't attach an `Authorization` header, so
`GET /api/videos/{id}/stream` and `GET /api/jobs/{id}/annotated-video`
accept the access token as a `?token=` query parameter as well (see
`get_current_user_for_streaming`); the frontend's `authenticatedStreamUrl()`
helper builds these URLs. Both endpoints implement real HTTP Range support
(206 Partial Content) so the browser can seek/scrub rather than downloading
the whole file up front. The Video Detail page shows the raw upload while a
job is pending/processing, then automatically switches to the annotated
preview — detection boxes, track ID, confidence and STAR-Risk score drawn
directly onto the footage — once rendering finishes (`_render_annotated_video`
in `tasks.py`; boxes persist for `FRAME_SAMPLE_RATE` frames past their last
sampled detection so playback doesn't flicker between sampled frames).

### Real-time detection reporting

Uploading a video takes you straight to its Video Detail page, which
subscribes to `/ws/jobs/{id}` immediately — no need to trigger reprocessing
first. While the job is still running, every WebSocket tick carries the
running count of detected object classes (`class_counts`,
`total_tracked_objects`), not just a percentage: `tracked_objects` and
`object_observations` rows are committed to the database incrementally as
the pipeline runs, so "what's in this footage" becomes visible within
seconds of upload rather than only after the whole job finishes. This works
**independently of whether the video's camera has any zone/rule
configured** — detection and tracking always run; zone/incident evaluation
is the separate, optional layer on top (see [Known limitations](#known-limitations)).
Once a job completes, `GET /api/jobs/{id}/detections` additionally returns
full per-track detail (class, confidence, observation count, final
STAR-Risk score).

## Repository structure

```
sentinelai/
├── project.py                 # CS50P: STAR-Risk algorithm + CLI (stdlib only)
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
│   │   ├── models/              # 14 tables
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── routers/             # FastAPI route handlers
│   │   ├── services/            # business logic
│   │   ├── algorithms/          # STAR-Risk import + tracker.py
│   │   ├── workers/             # Celery app + process_video_task
│   │   ├── websocket/           # connection manager
│   │   └── seed.py              # demo data
│   └── alembic/                 # migrations
├── frontend/
│   ├── src/                     # React pages, hooks, API client
│   └── package.json
├── uploads/                     # uploaded video + evidence frames
└── docs/                        # extended HTML project documentation
```

## Environment variables

All variables live in `.env.example` (copy to `.env`). Key ones:

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg2://sentinel:sentinel@postgres:5432/sentinel` |
| `JWT_SECRET` | Signing key for JWTs — **change in production** | — |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes | `30` / `7` |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Redis connections for Celery | `redis://redis:6379/0,1` |
| `CORS_ORIGINS` | Allowed frontend origins | `http://localhost:5173,http://localhost:3000` |
| `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`, `ALLOWED_VIDEO_EXTENSIONS` | Upload validation — `MAX_UPLOAD_SIZE_MB=0` means unlimited | `/app/uploads`, `0`, `.mp4,.avi,.mov,.mkv,.ts,.mxf,.webm` |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`, `DB_POOL_RECYCLE_SECONDS` | PostgreSQL connection pool sizing | `20`, `40`, `30`, `1800` |
| `CELERY_WORKER_CONCURRENCY` | Parallel worker subprocesses per `celery_worker` container | `4` |
| `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS` / `CELERY_TASK_TIME_LIMIT_SECONDS` | Ceiling for a single video-processing job | `21600` (6h) / `23400` (6.5h) |
| `UVICORN_WORKERS` | API process count (separate from Celery concurrency) | `2` |
| `DEFAULT_CHUNK_SECONDS`, `FRAME_SAMPLE_RATE` | Pipeline tuning | `30`, `5` |
| `YOLO_MODEL_PATH` | YOLO weights (falls back to stub detector if unavailable) | `yolov8n.pt` |
| `INCIDENT_RISK_THRESHOLD`, `INCIDENT_CONSECUTIVE_REQUIRED` | Default rule thresholds | `70.0`, `3` |
| `VITE_API_BASE_URL`, `VITE_WS_BASE_URL` | Frontend → backend endpoints | `http://localhost:8000`, `ws://localhost:8000` |

### Scaling for large deployments

SentinelAI's defaults are tuned for a multi-camera, multi-operator
deployment rather than a single local demo:

- **Uploads are unbounded by default** (`MAX_UPLOAD_SIZE_MB=0`). The upload
  handler always streams straight to disk in 8MB chunks (`video_service.
  save_upload`) — it never buffers a file fully in memory, so there's no
  practical ceiling besides the disk space backing the `uploads` volume.
  Raise/lower the cap per-deployment if you want one.
- **An `nginx` reverse proxy** (`nginx/nginx.conf`) sits in front of the
  stack on port 80 with `client_max_body_size 0` (unlimited) and 3600s
  read/send timeouts, so a reverse proxy never becomes the thing that
  silently truncates a multi-gigabyte upload or a long-lived WebSocket
  connection — a very common production gotcha. Point real traffic at port
  80 instead of hitting the backend/frontend ports directly.
  `docker compose up` already starts it alongside the rest of the stack.
- **The PostgreSQL connection pool** is sized for many concurrent
  dashboard/API/WebSocket clients (`DB_POOL_SIZE=20`, `DB_MAX_OVERFLOW=40`
  by default), not the handful of connections a single-user demo needs.
- **Celery** runs with `CELERY_WORKER_CONCURRENCY=4` parallel subprocesses,
  `--max-tasks-per-child=50` (recycles workers so long-running batches of
  heavy video jobs can't accumulate memory), `task_acks_late=True` (a job
  re-queues instead of being lost if a worker is killed mid-processing),
  and multi-hour soft/hard time limits so long camera footage isn't killed
  partway through. Scale `CELERY_WORKER_CONCURRENCY` or add more
  `celery_worker` replicas to match your camera count.
- **`uvicorn`** runs with multiple worker processes (`UVICORN_WORKERS`,
  default 2) and a 3600s keep-alive timeout for large uploads.

None of this requires a GPU or paid infrastructure — it's standard Docker
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
`celery_worker`, `frontend`, and `nginx` — a reverse proxy in front of
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
`calculate_star_risk`, `is_incident_triggered`, `calculate_motion_anomaly`,
and `split_video_chunks` — all covered by the 17 pytest tests in
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
| `project.py` in the root, with `main()` + 3+ custom functions | ✅ 4 functions: `calculate_star_risk`, `is_incident_triggered`, `calculate_motion_anomaly`, `split_video_chunks` |
| `test_project.py` with tests for 3+ functions | ✅ 17 tests, covering all four functions plus edge/invalid cases |
| `requirements.txt` | ✅ in the repo root |
| `README.md`, 500+ words | ✅ (this file) |

## Known limitations

- No GPU is required — the baseline targets CPU inference. YOLOv8n is small
  enough to run on CPU at a reduced frame-sampling rate.
- If `ultralytics` cannot download the YOLOv8 weights (an offline or
  sandboxed environment), the worker logs a warning and switches to a
  deterministic stub detector, so the rest of the pipeline (tracking,
  zones, STAR-Risk, incidents, metrics) still runs end to end for
  demonstration purposes.
- WebSocket progress uses per-connection database polling rather than
  Redis pub/sub — simple and reliable for a single backend replica, but not
  horizontally scalable as-is.
- Detection/tracking always runs on upload, but since there's no
  camera/zone management UI, uploaded videos aren't linked to a camera —
  so zone-based incident scoring (the `Z` term in STAR-Risk) stays at 0 and
  incidents will rarely fire from the dashboard-uploaded path. Detections,
  tracking, confidence and motion-anomaly-based risk still work fully; only
  the zone-severity component of STAR-Risk needs the (currently
  API-only, unexposed in the UI) camera/zone/rule tables to be populated —
  see `backend/app/seed.py` for how the demo data does this.
- Annotated-preview rendering re-reads every frame of the source video
  once tracking finishes, so its cost scales with total video length, not
  just the sampled frames used for detection; for very long footage this
  adds meaningfully to total job time.

## Future improvements

RTSP live-stream ingestion, ONNX Runtime/TensorRT as an optional faster
inference backend, an optional GPU Celery queue, distributed multi-node
processing, semantic search over incident summaries (embeddings + a vector
database), push/email/SMS notifications, and Redis pub/sub-backed
WebSocket fan-out for multi-replica deployments.

## Design decisions explained

**Why a CPU baseline:** the project should run on a laptop or a cheap VPS
without CUDA. YOLOv8n is small enough to be CPU-viable at low
frame-sampling rates, and the stub-detector fallback guarantees a working
demo even fully offline.

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

MIT — see `LICENSE` if present, or treat this project as MIT-licensed for
educational/demonstration purposes.
