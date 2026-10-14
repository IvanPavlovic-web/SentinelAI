# SentinelAI — Edge Video Intelligence & Incident Detection Platform

**CS50P Final Project** by Ivan Pavlović
**CS50 demo video:** _[PLACEHOLDER — dodati link ka CS50 submission videu]_

Samostalna (self-hosted) platforma za video-nadzor koja prima otpremljene snimke,
detektuje i prati ljude/vozila, procenjuje ih kroz konfigurabilne sigurnosne zone
i pravila, i automatski otvara objašnjive incidente kad se ponašanje objekta
oceni kao rizično. Nije samo "detektor objekata" — kompletan je pipeline od
sirovog videa do akcionabilnog alarma na dashboard-u.

---

## Sadržaj

1. [Problem koji se rešava](#problem-koji-se-rešava)
2. [Ključne funkcionalnosti](#ključne-funkcionalnosti)
3. [Tehnologije](#tehnologije)
4. [Arhitektura](#arhitektura)
5. [Tok obrade videa](#tok-obrade-videa)
6. [STAR-Risk algoritam](#star-risk-algoritam)
7. [Baza podataka](#baza-podataka)
8. [Autentikacija i uloge (RBAC)](#autentikacija-i-uloge-rbac)
9. [API rute](#api-rute)
10. [Struktura repozitorijuma](#struktura-repozitorijuma)
11. [Instalacija i pokretanje (Docker)](#instalacija-i-pokretanje-docker)
12. [Lokalni razvoj bez Dockera](#lokalni-razvoj-bez-dockera)
13. [Testovi i CS50P CLI](#testovi-i-cs50p-cli)
14. [Primer API toka](#primer-api-toka)
15. [Poznata ograničenja](#poznata-ograničenja)
16. [Planirana proširenja](#planirana-proširenja)
17. [Zašto ove inženjerske odluke](#zašto-ove-inženjerske-odluke)

---

## Problem koji se rešava

Timovi fizičkog obezbeđenja (magacini, gradilišta, retail objekti) obično imaju
dve opcije: skupe cloud VMS/AI pretplate, ili ljude koji ručno gledaju zidove
kamera. SentinelAI nudi treću opciju — platformu koju možete sami hostovati,
koja radi na CPU-u (bez potrebe za GPU-om), i koja odgovara na konkretna
bezbednosna pitanja:

- Da li je osoba ušla u zabranjenu zonu?
- Da li je vozilo ostalo u zoni duže nego što je dozvoljeno?
- Da li je objekat pokazao neuobičajeno kretanje (nagle promene pravca, skokove brzine)?
- Koje kamere/zone generišu najviše incidenata?
- Koliko dugo traje inferenca, koji je ostvareni FPS, koliko se čeka u redu za obradu?

## Ključne funkcionalnosti

- **Upload-based ingestija** videa sa asinhronom Celery obradom u pozadini.
- **Multi-object tracking** preko sopstvenog laganog centroid/IoU tracker-a (bez teških re-ID modela).
- **Poligon sigurnosne zone** sa nivoom ozbiljnosti i pravilima po zoni (klasa objekta, samo van radnog vremena, prag rizika, broj uzastopnih pogodaka).
- **STAR-Risk** — originalni, objašnjivi algoritam za skorovanje rizika 0–100 (vidi sekciju ispod), sa eksponencijalnim izglađivanjem i histerezisom protiv lažnih alarma.
- Automatsko kreiranje incidenata sa dokaznim (evidence) kadrovima, workflow za rešavanje/odbacivanje, i audit trag.
- Dashboard sa ulogama (admin/analyst/viewer): biblioteka videa, upravljanje kamerama/zonama, tabela incidenata, grafovi performansi, admin-only audit log.
- **Live ažuriranja** napretka obrade i novih incidenata preko WebSocket-a.
- Pun JWT auth sistem (access + rotirajući refresh tokeni) sa RBAC po ulogama.

## Tehnologije

| Sloj | Tehnologije |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 / pydantic-settings |
| Autentikacija | JWT (access + refresh), `passlib[bcrypt]`, RBAC zavisnosti |
| Baza / red poruka | PostgreSQL 16, Redis 7 |
| Pozadinska obrada | Celery (broker + result backend na Redis-u), `ProcessPoolExecutor` / `multiprocessing` |
| Computer vision | OpenCV (headless), Ultralytics YOLOv8 (CPU, sa stub fallback-om), NumPy, `psutil` |
| Testiranje | pytest, httpx |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, React Router, TanStack Query, Recharts |
| Infrastruktura | Docker, Docker Compose, named volumes, health checks |

## Arhitektura

```
frontend (React + Vite + TS + Tailwind)
        │  HTTP (REST) + WebSocket
        ▼
backend (FastAPI)
  routers/ → services/ → models/ (SQLAlchemy)
        │  čita/piše                 │ enqueue Celery task
        ▼                            ▼
   PostgreSQL                      Redis (broker + result backend)
                                      │
                                      ▼
                              celery_worker (isti image kao backend)
                                - OpenCV čitanje frejmova
                                - ProcessPoolExecutor (paralelni chunk-ovi)
                                - YOLOv8 inferenca (ili stub fallback)
                                - tracker.py (centroid/IoU praćenje)
                                - STAR-Risk evaluacija zona/pravila
                                - upis observations/incidents/evidence/metrics
```

Backend koristi striktan **servisni sloj**: `routers/` samo prima/vraća HTTP,
`services/` sadrži poslovnu logiku, `models/` su SQLAlchemy ORM klase,
`schemas/` su Pydantic validacije, `algorithms/` su čiste funkcije bez
zavisnosti od baze (STAR-Risk, tracker), `workers/` su Celery taskovi, a
`websocket/` upravlja live konekcijama. Rute nikad ne sadrže poslovnu logiku
direktno.

**Važna arhitekturna odluka:** `backend/app/algorithms/star_risk.py` ne
duplira algoritam — uvozi tačno iste funkcije iz korenskog `project.py` (CS50P
modula), tako da postoji samo jedan izvor istine za STAR-Risk logiku, deljen
između CS50 grading modula i produkcionog pipeline-a.

## Tok obrade videa

1. Korisnik (uloga `analyst` ili `admin`) otpremi video kroz *Video Library* ili `POST /api/videos/upload`.
2. Backend validira ekstenziju/MIME tip, generiše bezbedno ime fajla (UUID), čuva ga u `uploads/`, kreira red u `video_sources` i `processing_jobs` (status `queued`), i šalje Celery task.
3. Worker otvara video sa `cv2.VideoCapture`, čita FPS/širinu/visinu/trajanje.
4. Trajanje se deli na chunk-ove preko `split_video_chunks()`, a uzorkovanje frejmova + YOLO inferenca se paralelizuju kroz `ProcessPoolExecutor`.
5. YOLOv8 (CPU, model `yolov8n.pt`) detektuje klase `person`, `car`, `truck`, `motorcycle`, `bus`. Ako model nije dostupan offline, automatski se koristi deterministički stub detektor da pipeline i dalje radi end-to-end.
6. Detekcije se hronološki prosleđuju `CentroidIoUTracker`-u koji svakom objektu dodeljuje trajni track ID dok god je vidljiv.
7. Svako zapažanje (centroid, bbox, pouzdanost, brzina, pravac, da li je u zoni) se upisuje u `object_observations`.
8. Za svaki trag se evaluiraju aktivne zone/pravila i računa STAR-Risk skor.
9. Kad histerezis uslov bude ispunjen, kreira se `incidents` + `incident_evidence` (anotiran kadar sačuvan u `uploads/evidence/`).
10. Napredak (`progress_percent`) se ažurira u bazi; `/ws/jobs/{id}` ga gura klijentu uživo preko WebSocket-a.
11. Na kraju se upisuju `performance_metrics`: trajanje, broj frejmova, efektivni FPS, prosečna/p95 latencija (NumPy percentile), CPU/RAM (psutil), čekanje u redu, broj incidenata.

## STAR-Risk algoritam

**Spatio-Temporal Adaptive Risk Scoring** — originalni, potpuno objašnjivi
algoritam, implementiran kao čiste funkcije u `project.py` (deljene sa
backend-om), bez ijedne nasumične vrednosti — sve dolazi iz stvarne istorije
zapažanja po tragu.

```
raw_risk      = 100 * (0.35·Z + 0.25·D + 0.20·M + 0.10·T + 0.10·C)
smoothed_risk = alpha · raw_risk + (1 - alpha) · previous_risk     (alpha = 0.45)
```

| Komponenta | Opis | Formula |
|---|---|---|
| **Z** — ozbiljnost zone | 0 izvan zone | `low/medium/high/critical → 0.25/0.50/0.75/1.00` |
| **D** — zadržavanje | koliko dugo je objekat u zoni u odnosu na minimum | `min(1, dwell_seconds / minimum_dwell_seconds)` |
| **M** — anomalija kretanja | prekidi pravca i nagli skokovi brzine | vidi `calculate_motion_anomaly()` |
| **T** — vreme | van radnog vremena / `after_hours_only` pravilo | `1.0` ili `0.0` |
| **C** — postojanost pouzdanosti | koliko dosledno je detekcija pouzdana | iz poslednjih do 5 detekcija |

`calculate_motion_anomaly()` gleda uzastopne vektore brzine: **prekid pravca**
(kosinus ugla između dva uzastopna vektora < 0) i **skok brzine** (odnos ≥
2.5×), normalizovano u opseg [0, 1].

`is_incident_triggered()` implementira **histerezis** — incident se otvara tek
kada **poslednjih N uzastopnih** evaluacija pređe prag pravila, čime se
sprečava da jedan šumovit pik rizika sam po sebi napravi (lažni) incident.

Prioritet incidenta po finalnom skoru: `0–39 low`, `40–59 medium`, `60–79
high`, `80–100 critical`. Svaki incident dobija i čitljivo objašnjenje, npr.:
*"Person track #14 entered the High Security Warehouse zone, remained for 22
seconds, showed two direction reversals, and reached a STAR-Risk score of
84.3."*

## Baza podataka

PostgreSQL šema definisana kroz SQLAlchemy 2.0 modele (`backend/app/models/`)
i jednu Alembic migraciju (`backend/alembic/versions/0001_initial_schema.py`),
sa stranim ključevima, indeksima na često filtriranim kolonama i UTC
vremenskim oznakama. 14 tabela:

`users`, `refresh_tokens`, `audit_logs`, `cameras`, `video_sources`,
`processing_jobs`, `detection_models`, `zones`, `rules`, `tracked_objects`,
`object_observations`, `incidents`, `incident_evidence`, `performance_metrics`.

## Autentikacija i uloge (RBAC)

Lozinke se heširaju sa `passlib[bcrypt]` — nikad u čistom tekstu. Prijava
vraća kratkotrajni JWT access token i rotirajući refresh token koji se čuva
(i može se opozvati) u `refresh_tokens`, pa je logout stvaran.

| Uloga | Ovlašćenja |
|---|---|
| `admin` | Puna kontrola — korisnici, sve kamere/zone/pravila, svi incidenti, audit log |
| `analyst` | Otprema video, kreira kamere/zone/pravila, rešava incidente |
| `viewer` | Samo pregled — video, napredak obrade, incidenti, izveštaji |

Svaka zaštićena ruta koristi `require_roles(...)` FastAPI zavisnost. Važne
akcije (login, upload, kreiranje zone, promena pravila, promena statusa
incidenta, brisanje) automatski se upisuju u `audit_logs`.

## API rute

```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/refresh
POST   /api/auth/logout
GET    /api/auth/me

GET/POST   /api/cameras
PATCH/DELETE /api/cameras/{id}

GET    /api/videos
POST   /api/videos/upload
GET    /api/videos/{id}
POST   /api/videos/{id}/process

GET/POST   /api/zones
PATCH/DELETE /api/zones/{id}
GET/POST   /api/rules
PATCH      /api/rules/{id}

GET    /api/jobs/{id}
GET    /api/jobs/{id}/metrics

GET    /api/incidents          (paginacija + filteri: status, priority, date, camera, object_class)
GET    /api/incidents/{id}
PATCH  /api/incidents/{id}/status

GET    /api/dashboard/summary
GET    /api/dashboard/performance
GET    /api/audit-logs          (samo admin, paginirano)

WS     /ws/jobs/{job_id}        (live napredak obrade)
WS     /ws/incidents            (live feed novih incidenata)
```

Puna interaktivna OpenAPI/Swagger dokumentacija: `http://localhost:8000/docs`.

## Struktura repozitorijuma

```
sentinelai/
├── project.py                # CS50P: STAR-Risk algoritam + CLI (stdlib only)
├── test_project.py           # 17 pytest testova
├── requirements.txt
├── README.md
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/              # config, security (JWT/bcrypt), logging
│   │   ├── db/                # SQLAlchemy engine/session
│   │   ├── models/             # 14 tabela
│   │   ├── schemas/            # Pydantic sheme
│   │   ├── routers/            # FastAPI rute
│   │   ├── services/           # poslovna logika
│   │   ├── algorithms/         # STAR-Risk import + tracker.py
│   │   ├── workers/            # Celery app + process_video_task
│   │   ├── websocket/          # connection manager
│   │   └── seed.py             # demo podaci
│   └── alembic/                # migracije
├── frontend/
│   ├── src/                    # React stranice, hook-ovi, API klijent
│   └── package.json
├── uploads/                    # otpremljeni video + evidence kadrovi
└── docs/                       # detaljna HTML dokumentacija projekta
```

## Instalacija i pokretanje (Docker)

```bash
cp .env.example .env          # po potrebi izmeniti JWT_SECRET itd.
docker compose up --build
```

Ovo pokreće 5 servisa: `postgres`, `redis`, `backend` (FastAPI na portu 8000,
automatski izvršava `alembic upgrade head` pre starta), `celery_worker`
(isti image, druga komanda) i `frontend` (port 5173).

- Backend / Swagger dokumentacija: **http://localhost:8000/docs**
- Frontend dashboard: **http://localhost:5173**

Popunjavanje baze demo podacima (radi bez obrade pravog videa):

```bash
docker compose exec backend python -m app.seed
```

Demo nalozi: `admin@sentinelai.dev / Admin123!` i `analyst@sentinelai.dev / Analyst123!`

## Lokalni razvoj bez Dockera

```bash
# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate      # ili source .venv/bin/activate na Linux/Mac
pip install -r ../requirements.txt
alembic upgrade head          # treba pokrenut Postgres (ili SQLite DATABASE_URL za brzi demo)
python -m app.seed
uvicorn app.main:app --reload

# Celery worker (drugi terminal, treba Redis)
celery -A app.workers.celery_app worker --loglevel=info

# Frontend
cd frontend
npm install
npm run dev     # http://localhost:5173
```

## Testovi i CS50P CLI

```bash
python -m pytest test_project.py -v
python project.py demo-risk
python project.py split-video --duration 130 --chunk-size 30
python project.py serve
```

`project.py` sadrži (pored `main()`) četiri top-level funkcije:
`calculate_star_risk`, `is_incident_triggered`, `calculate_motion_anomaly`,
`split_video_chunks` — sve pokrivene sa 17 pytest testova u
`test_project.py` (granični slučajevi, nevalidni unosi, histerezis, statično
kretanje, promena pravca, deljenje videa koje se ne deli ravnomerno).

## Primer API toka

```bash
curl -X POST localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@sentinelai.dev","password":"Admin123!"}'
# -> {"access_token": "...", "refresh_token": "..."}

curl -X POST localhost:8000/api/videos/upload -H "Authorization: Bearer <token>" \
  -F "file=@dock_feed.mp4"
# -> kreira video_sources + processing_jobs red, pokreće Celery task

curl localhost:8000/api/jobs/1
curl "localhost:8000/api/incidents?status=open&priority=high"
curl -X PATCH localhost:8000/api/incidents/1/status -H "Authorization: Bearer <token>" \
  -d '{"status":"resolved","resolution_notes":"Verified with site security."}'
```

## Poznata ograničenja

- Ne zahteva GPU — sve cilja CPU inferencu; YOLOv8n je dovoljno mali za
  CPU pri sniženoj frekvenciji uzorkovanja frejmova.
- Ako `ultralytics` ne može da preuzme YOLOv8 težine (offline/sandboxed
  okruženje), worker loguje upozorenje i prelazi na deterministički
  stub-detektor, tako da ostatak pipeline-a (tracking, zone, STAR-Risk,
  incidenti, metrike) i dalje radi end-to-end za demonstraciju.
- WebSocket napredak koristi DB polling po konekciji, ne Redis pub/sub —
  dovoljno za jednu instancu backend-a, ali nije horizontalno skalabilno
  u trenutnom obliku.
- Reprodukcija videa na Video Detail stranici je trenutno placeholder;
  potrebno je servisiranje statičkih fajlova/potpisanih URL-ova iz `uploads/`.

## Planirana proširenja

RTSP live-stream unos, ONNX Runtime/TensorRT kao opcioni brži inference
backend, opcioni GPU Celery red, distribuirana obrada na više čvorova,
semantička pretraga incidenata (embeddings + vektorska baza), push/email/SMS
notifikacije, Redis pub/sub WebSocket fan-out za više replika backend-a.

## Zašto ove inženjerske odluke

**Zašto CPU baseline:** projekat treba da radi na laptopu ili jeftinom VPS-u
bez CUDA-e; YOLOv8n je dovoljno mali za CPU pri niskim frekvencijama
uzorkovanja, a stub-detektor fallback garantuje radnu demonstraciju čak i
potpuno offline.

**Zašto sopstveni lagani tracker umesto teškog gotovog rešenja** (npr.
DeepSORT/ByteTrack + re-ID): cilj projekta je objašnjiva evaluacija
zona/pravila, ne state-of-the-art multi-object tracking. IoU + centroid
uparivanje je jednostavno za razumevanje, nema dodatnih modela za preuzimanje,
i dovoljno je brzo na CPU-u za frekvencije uzorkovanja koje ovaj pipeline
koristi.

---

Dodatna, proširena tehnička dokumentacija (sa dijagramima toka i detaljnim
objašnjenjem svake komponente) nalazi se u [`docs/sentinelai-dokumentacija.html`](docs/sentinelai-dokumentacija.html).
