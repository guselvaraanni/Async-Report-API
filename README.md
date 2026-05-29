# Export Queue — Async Report Generation Platform

A production-style **async CSV export system** built with **Flask**, **Celery**, **Redis/Memurai**, and **MySQL**. The API accepts large export requests without blocking HTTP threads; a background worker streams rows in batches, writes CSV files to disk, and exposes progress through a built-in **Export Queue** web dashboard.

Designed for portfolios and interviews: demonstrates app factory pattern, versioned REST APIs, queue-based workers, polling UX, operational monitoring, and Windows-friendly local development (Memurai, no Docker required).

---

## Table of Contents

- [Why This Project Exists](#why-this-project-exists)
- [Key Features](#key-features)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Data Seeding](#data-seeding)
- [Web Dashboard](#web-dashboard)
- [API Reference](#api-reference)
- [Report Lifecycle](#report-lifecycle)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Related Documentation](#related-documentation)

---

## Why This Project Exists

Exporting hundreds of thousands of database rows inside a single HTTP request causes:

- **504 Gateway Timeout** — clients give up waiting  
- **Blocked web workers** — Flask cannot serve other traffic  
- **Memory pressure** — loading entire result sets into RAM  

**Export Queue** solves this by:

1. Returning **`202 Accepted`** immediately with a `report_id`  
2. Enqueuing work on **Redis/Memurai** (`reports` queue)  
3. Processing in a **Celery worker** with `yield_per` batching  
4. Letting clients **poll status** until `COMPLETED`, then **download** the CSV  

---

## Key Features

### Backend

- **Flask app factory** with environment-based config (`Development`, `Testing`, `Production`)
- **Canonical REST API** under `/api/v1/reports` and `/api/v1/ops`
- **Legacy compatibility** shim at `/reports/*` for older clients
- **Celery** as the only background execution path (`export_transactions_task`)
- **Cooperative cancel**, retry, delete, and paginated list/filter/search
- **Flask-Migrate** migrations + legacy schema upgrade path
- **Structured JSON logging** and consistent API error payloads
- **19 automated tests** (pytest, in-memory SQLite + Celery eager mode)

### Frontend (built-in dashboard)

- **Export Queue** UI — top navigation, dark/light theme, engineering-focused layout
- Pages: **Overview**, **Jobs**, **Enqueue**, **Files**, **Infrastructure**
- **PollingManager** — backoff, retry limits, tab visibility pause, offline banner
- **Blob-based downloads** with toast errors (no broken `download.htm` files)
- **Partial export warnings** when DB has fewer rows than requested
- Live job tracker with lifecycle stepper and progress bar

### Operations

- Worker/queue metrics, failed job list, dry-run cleanup
- Celery inspect integration (workers, queues, depth estimate)
- Windows + **Memurai** documented (`--pool=solo` for Celery)

---

## Screenshots

Screenshots live in [`screenshots/`](screenshots/). They are grouped by feature (not by filename order).

### Overview — live pipeline & worker health

Dashboard home: job totals, worker status, status distribution, and recent jobs. Polls `/api/v1/reports/stats` and `/api/v1/ops/metrics` on an interval.

![Overview dashboard](screenshots/Screenshot%202026-05-29%20073536.png)

---

### Enqueue — submit a new export

Create a job with **User ID** and **row limit**. The right panel **Live tracker** polls status via `JobPoller` until the job reaches a terminal state.

**Successful small export** (user 1, 50 rows — matches seeded data):

![Enqueue — completed 50/50 rows](screenshots/Screenshot%202026-05-29%20072902.png)

**Large export in progress** (user 2, 50k requested — streams from MySQL):

![Enqueue — processing 6%](screenshots/Screenshot%202026-05-29%20073127.png)

![Enqueue — processing 13%](screenshots/Screenshot%202026-05-29%20073134.png)

**Partial completion** — all available rows exported; toast explains when DB has fewer rows than requested:

![Enqueue — partial export toast](screenshots/Screenshot%202026-05-29%20073151.png)

---

### Jobs — history, filter, actions

Paginated table with status badges, progress, cancel/retry/delete, and download (`DL`) when the CSV exists on disk. Legacy jobs may show **File unavailable**.

![Jobs table](screenshots/Screenshot%202026-05-29%20073602.png)

---

### Report detail — single job lifecycle

Full metadata, Celery state, lifecycle stepper, download/delete/retry/cancel actions.

**Completed with partial-export warning** (10,000 of 50,000 requested for user 2):

![Report detail — partial export](screenshots/Screenshot%202026-05-29%20073333.png)

**Failed job** — typical Windows Celery prefork error; UI suggests `--pool=solo`:

![Report detail — Celery FAILURE](screenshots/Screenshot%202026-05-29%20072543.png)

---

### Files — download center

Table of `COMPLETED` exports: **READY** (CSV on disk) vs **MISSING** (legacy rows or deleted files). Uses `ReportAPI.downloadReport()` (fetch → blob).

![Files — READY and MISSING](screenshots/Screenshot%202026-05-29%20073628.png)

---

### Infrastructure — workers, queues, failed jobs

Celery worker nodes, queue topology JSON, failed job table with retry, maintenance dry-run cleanup.

![Infrastructure — healthy worker](screenshots/Screenshot%202026-05-29%20073644.png)

![Infrastructure — failed jobs list](screenshots/Screenshot%202026-05-29%20072603.png)

---

### Generated CSV output

Example export opened in Excel — columns: `id`, `user_id`, `amount`, `currency`, `status`, `created_at`.

**~10,000 rows** (user 2 partial/large export):

![CSV export ~10k rows](screenshots/Screenshot%202026-05-29%20073509.png)

**50 rows** (user 1 seed data):

![CSV export 50 rows](screenshots/Screenshot%202026-05-29%20072229.png)

---

## Architecture

```
┌─────────────┐     POST /api/v1/reports/      ┌──────────────┐
│   Browser   │ ───────────────────────────► │  Flask API   │
│  (Dashboard)│ ◄── poll stats/status/metrics │  (producer)  │
└─────────────┘                               └──────┬───────┘
                                                     │
                     ┌───────────────────────────────┼───────────────────────────────┐
                     │                               │                               │
                     ▼                               ▼                               ▼
              ┌─────────────┐                 ┌─────────────┐                 ┌─────────────┐
              │   MySQL     │                 │   Memurai   │                 │  ./reports/ │
              │ report rows │                 │   (Redis)   │                 │  CSV files  │
              │ + progress  │                 │ queue:reports│                 └─────────────┘
              └─────────────┘                 └──────┬──────┘
                                                     │
                                                     ▼
                                              ┌─────────────┐
                                              │   Celery    │
                                              │   worker    │
                                              │ (consumer)  │
                                              └─────────────┘
```

| Component | Role |
|-----------|------|
| **Flask** | HTTP API + Jinja templates + static dashboard |
| **MySQL** | Users, transactions, report job state |
| **Memurai/Redis** | Celery broker & result backend |
| **Celery worker** | Runs `export_transactions_task` — streams rows, writes CSV |
| **REPORTS_FOLDER** | On-disk CSV storage (`report_<uuid>.csv`) |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | Flask 3.0, Flask-SQLAlchemy, Flask-Migrate, Flask-Limiter |
| Task queue | Celery 5.3 |
| Broker | Redis 7 or **Memurai** (Windows) |
| Database | MySQL 8 (SQLite in tests) |
| Frontend | Jinja2 templates, vanilla JS, custom CSS |
| API docs | Flasgger (OpenAPI) |
| Testing | pytest, pytest-flask |
| Optional | Docker Compose |

---

## Project Structure

```
Async-Report-API/
├── app/
│   ├── __init__.py              # App factory, Celery init, blueprints
│   ├── config.py                # Dev / Test / Prod configuration
│   ├── celery_app.py            # Celery + Flask app context tasks
│   ├── extensions.py            # db, migrate, limiter
│   ├── api/v1/
│   │   ├── reports.py           # Report lifecycle API
│   │   ├── ops.py               # Metrics, workers, failed jobs, cleanup
│   │   └── helpers.py           # Pagination, JSON errors
│   ├── models/                  # User, Transaction, Report
│   ├── tasks/export_tasks.py    # Celery export task
│   ├── routes/legacy_reports.py # /reports/* compatibility
│   ├── web/routes.py            # Dashboard page routes
│   ├── templates/               # Jinja HTML
│   └── static/                  # CSS, JS (api, polling, ui, pages)
├── worker.py                    # Celery worker entry (Windows-safe defaults)
├── run.py                       # Flask entrypoint
├── scripts/start_worker.ps1     # Windows worker helper
├── migrations/                  # Alembic migrations
├── tests/                       # pytest suite
├── seeds_db.py                  # 50 transactions for user 1
├── seed_50k.py                  # 50,000 transactions for user 2
├── screenshots/                 # UI screenshots for README
├── PROJECT_ANALYSIS.md          # Deep engineering analysis
├── TESTING_GUIDE.md             # Manual test checklist
├── QUICKSTART.md                # Short quick start
└── requirements.txt
```

---

## Prerequisites

- **Python 3.8+** (3.10+ recommended)
- **MySQL 8** (local instance, e.g. `heavy_data_db`)
- **Memurai** or Redis on `localhost:6379`
- **No Docker required** for local development on Windows

---

## Installation & Setup

### 1. Clone and install dependencies

```powershell
cd Async-Report-API
pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file (or export variables):

```env
FLASK_ENV=development
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost:3306/heavy_data_db
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
REPORTS_FOLDER=./reports
```

### 3. Database migrations

```powershell
$env:FLASK_ENV = "development"
flask --app run.py db upgrade
```

If you have an **old database** from before migrations, see `notes.txt` for the legacy stamp + upgrade path.

### 4. Start Memurai

Ensure the Memurai (Redis-compatible) service is running on port **6379**.

### 5. Start Celery worker

**Windows — required flags** (`--pool=solo`):

```powershell
.\scripts\start_worker.ps1
```

Or:

```powershell
celery -A worker.celery worker --loglevel=info -Q reports --pool=solo --concurrency=1
```

Or:

```powershell
python worker.py
```

**Linux/macOS:**

```bash
celery -A worker.celery worker --loglevel=info -Q reports --concurrency=4
```

### 6. Start Flask

```powershell
python run.py
```

### 7. Open the dashboard

[http://localhost:5000/](http://localhost:5000/)

---

## Data Seeding

| Script | What it does |
|--------|----------------|
| `python seeds_db.py` | Creates **user 1** with **~50 transactions** |
| `python seed_50k.py` | Adds **50,000 transactions** for **user 2** |

**Important:** Requesting `50,000` rows for **user 1** only exports ~50 rows (all that exist). The job still **completes** — the UI shows a **partial export** warning. For a full 50k demo:

```powershell
python seed_50k.py
# Then enqueue with user_id=2, rows=50000
```

---

## Web Dashboard

| Route | Page | Description |
|-------|------|-------------|
| `/` | Overview | Metrics, worker health, recent jobs |
| `/reports/new` | Enqueue | Submit job + live tracker |
| `/reports` | Jobs | History, filter, cancel, retry, download |
| `/reports/<id>` | Report detail | Lifecycle, progress, actions |
| `/downloads` | Files | Completed exports download center |
| `/ops` | Infrastructure | Workers, queues, failed jobs, cleanup |

**Top bar** shows queue depth and worker count (polled from `/api/v1/ops/metrics`).

---

## API Reference

Base path: **`/api/v1`**

### Reports (`/api/v1/reports`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | API health |
| POST | `/` | Create/enqueue export (`user_id`, `rows`) → **202** |
| GET | `/stats` | Dashboard aggregates + recent jobs |
| GET | `/?page=&status=&q=&sort=` | Paginated list |
| GET | `/<report_id>` | Full report |
| GET | `/<report_id>/status` | Status + progress + Celery state |
| GET | `/<report_id>/download` | Download CSV (`text/csv`) |
| POST | `/<report_id>/cancel` | Request cooperative cancel |
| POST | `/<report_id>/retry` | Re-queue **FAILED** job |
| DELETE | `/<report_id>` | Delete report + file |

**Create job example:**

```bash
curl -X POST http://localhost:5000/api/v1/reports/ \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": 2, \"rows\": 1000}"
```

**Response (202):**

```json
{
  "report_id": "uuid-here",
  "task_id": "uuid-here",
  "status": "QUEUED",
  "created_at": "2026-05-29T01:58:36"
}
```

**Poll status:**

```bash
curl http://localhost:5000/api/v1/reports/<report_id>/status
```

**Download:**

```bash
curl -O http://localhost:5000/api/v1/reports/<report_id>/download
```

### Operations (`/api/v1/ops`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Celery ping / broker visibility |
| GET | `/metrics` | Workers + report counts by status |
| GET | `/workers` | Celery inspect stats |
| GET | `/queues` | Active queue topology |
| GET | `/failed?page=&page_size=` | Paginated failed reports |
| POST | `/cleanup?days=7&dry_run=true` | Preview/delete old terminal jobs |

### Legacy (`/reports/*`)

| Legacy | Forwards to |
|--------|-------------|
| `POST /reports/generate` | `POST /api/v1/reports/` |
| `GET /reports/status/<id>` | `GET /api/v1/reports/<id>/status` |
| `GET /reports/download/<id>` | `GET /api/v1/reports/<id>/download` |

---

## Report Lifecycle

```
QUEUED → PROCESSING → COMPLETED
                   ↘ FAILED
        CANCEL_REQUESTED → CANCELED
```

| Status | Meaning |
|--------|---------|
| **QUEUED** | Saved in DB; waiting for worker |
| **PROCESSING** | Worker writing CSV |
| **COMPLETED** | CSV ready (if file on disk) |
| **FAILED** | Error in `error_message` |
| **CANCEL_REQUESTED** | User asked to stop |
| **CANCELED** | Stopped (cooperative) |

- `report_id` equals Celery `task_id` (UUID).  
- Progress: `rows_processed`, `progress_pct`, timestamps.  
- `download_available` in API when CSV exists (`resolve_csv_path()`).  
- Legacy DB rows may store URL paths in `file_path` — downloads resolve canonical `./reports/report_<id>.csv`.

---

## Testing

```powershell
$env:FLASK_ENV = "testing"
pytest -q
```

Tests use **in-memory SQLite** and **Celery eager mode** — they do not touch your development MySQL database.

See **[TESTING_GUIDE.md](TESTING_GUIDE.md)** for a manual checklist.

---

## Troubleshooting

### Celery: `not enough values to unpack (expected 3, got 0)`

**Cause:** Default **prefork** pool on Windows.  
**Fix:** Restart worker with `--pool=solo --concurrency=1` (see [Installation](#installation--setup)).

### Job stuck QUEUED, Celery shows FAILURE

- Worker not running or wrong pool  
- Memurai not running  
- Open job detail — UI syncs Celery FAILURE → DB FAILED  

### COMPLETED but only 0.1% progress (50 / 50000)

**Not a stuck job** — user 1 only has ~50 transactions. Use `seed_50k.py` and **user_id=2**, or request `rows=50` for user 1.

### Download shows "File unavailable" / MISSING

- Old jobs before file storage stored URL paths, not files  
- CSV deleted from `REPORTS_FOLDER`  
- Run a **new** export after worker is healthy  

### Dashboard keeps polling after Flask stops

Hard-refresh (`Ctrl+Shift+R`). Polling should pause with **Backend offline** banner (`PollingManager` + `Connectivity`).

### More help

- **[PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md)** — architecture deep dive  
- **[notes.txt](notes.txt)** — internal engineering notes  
- **[QUICKSTART.md](QUICKSTART.md)** — minimal quick start  
- **[PRODUCTION_CONFIG.md](PRODUCTION_CONFIG.md)** — production settings  

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) | Full system analysis, API inventory, beginner guide |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | Step-by-step verification |
| [QUICKSTART.md](QUICKSTART.md) | 5-minute API test |
| [API_EXAMPLES.sh](API_EXAMPLES.sh) | curl examples |
| [Postman_Collection.json](Postman_Collection.json) | Postman collection |

---

## License

MIT License — free for personal and commercial use.
