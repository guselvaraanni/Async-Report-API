# Async Report Generation API — Senior Engineering Analysis

> A maintained, evidence-based review of this Flask backend.
> Tracked here so future iterations (refactors, UI work, interview prep) share one source of truth.
> Author voice: a senior backend engineer + system architect + recruiter, being brutally honest.

---

## 1. Project Overview

**User-facing documentation:** See **[README.md](README.md)** for setup, API reference, screenshot gallery, and troubleshooting (verified against current code).

**Stated purpose (per README):** Production-ready API for exporting massive datasets asynchronously without blocking the web tier.

**Current implementation (after stabilization):** A versioned Flask API (`/api/v1`) that **enqueues report jobs into Celery**, with **Redis as broker/result backend**, and a **Celery worker process** that streams rows from the DB in batches and writes a CSV to local storage. Report lifecycle state is persisted in MySQL (or SQLite in tests) and exposed via polling-friendly endpoints.

**TL;DR:** The project is now internally consistent and interview-defensible: **Flask (producer) → Redis (queue) → Celery workers (consumers) → DB (state) → file storage (CSV)**.

---

## 2. The Big Picture (read this first)

The single most important fact about this codebase:

> **There is now ONE real async architecture: `/api/v1` is the canonical API and Celery is the only background execution path.**  
> `/reports/*` remains as a **backward-compatibility shim** that forwards to v1 handlers.

Key files:

| File | Purpose |
|---|---|
| `app/api/v1/reports.py` | Canonical report lifecycle APIs (`/api/v1/reports/*`) |
| `app/api/v1/ops.py` | Worker/queue monitoring APIs (`/api/v1/ops/*`) |
| `app/celery_app.py` | Celery single source of truth + Flask app context task wrapper |
| `app/tasks/export_tasks.py` | Celery task (`export_transactions_task`) with chunked DB reads + cooperative cancel |
| `app/routes/legacy_reports.py` | `/reports/*` compatibility endpoints |
| `worker.py` | Celery worker entrypoint (`celery -A worker.celery worker ...`) |

---

## 3. Architecture (as it actually runs)

```
Client
  │  POST /api/v1/reports/   { user_id, rows }
  ▼
Flask API (producer)
  │
  ├── Create Report row (status=QUEUED, report_id=UUID=Celery task_id)
  ├── Enqueue Celery task to Redis queue "reports"
  └── Return 202 { report_id, task_id, status }
                  │
                  ▼
Redis (broker)  →  Celery worker process (consumer)
                  │
                  ├── report.status = PROCESSING; started_at = now()
                  ├── Stream rows with yield_per(batch_size) (bounded memory)
                  ├── Write CSV to REPORTS_FOLDER; periodically update rows_processed/progress_pct
                  ├── On cancel request: mark CANCELED and stop early (cooperative cancel)
                  ├── On success: mark COMPLETED; completed_at = now(); persist file_path
                  └── On failure: mark FAILED; persist error_message; completed_at = now()

Client polls GET /api/v1/reports/<id>/status
Client downloads GET /api/v1/reports/<id>/download

Backward compatibility:
  /reports/generate → /api/v1/reports/
  /reports/status/<id> → /api/v1/reports/<id>/status
  /reports/download/<id> → /api/v1/reports/<id>/download
```

### Folder map

```
Async-Report-API/
├── run.py                    Flask entrypoint; loads .env; app.run(debug=True)
├── worker.py                 Celery entrypoint (stable)
├── seeds_db.py               Creates user_id=1 + 50 transactions
├── seed_50k.py               Bulk-inserts 50K transactions for user_id=2
├── seed_db.sh / test_api.sh  Bash helpers (Docker-oriented)
├── init_data.sql             SQL fixture
├── docker-compose.yml        MySQL + Redis + web + worker (aspirational)
├── Dockerfile                python:3.10-slim
├── .env                      Local config (note: uses mysql+mysqlconnector — driver not installed!)
├── requirements.txt          Flask, Flask-SQLAlchemy, Celery, redis, PyMySQL, flasgger
├── Postman_Collection.json   Uses /api/reports/* — wrong prefix
├── README.md, QUICKSTART.md, PRODUCTION_CONFIG.md
├── migrations/               Alembic migrations (Flask-Migrate)
├── pytest.ini                Pytest config (tests only under /tests)
└── app/
    ├── __init__.py           create_app(); init extensions; register /api/v1 + legacy routes; init Celery
    ├── celery_app.py         Celery single source of truth + Flask context wrapper
    ├── config.py             Dev/Test/Prod config classes + Celery/SQLA hardening defaults
    ├── extensions.py         db + migrate + limiter
    ├── models/{user,report,transaction}.py
    ├── api/v1/
    │   ├── reports.py        Canonical report APIs
    │   └── ops.py            Worker/queue monitoring APIs
    ├── routes/legacy_reports.py  /reports/* compatibility shim
    ├── tasks/
    │   ├── __init__.py       Task exports
    │   └── export_tasks.py   Celery task (chunked export + cancel + retries)
    └── tests/
        ├── test_api.py            50-row happy path script
        ├── test_e2e_polling.py    50K-row polling script
        └── test_concurreny.py     5 concurrent submissions (typo in filename)
tests/
    ├── conftest.py
    ├── test_reports_v1.py
    └── test_legacy_compat.py
```

---

## 4. Business Problem Solved

### The pattern

Synchronous "export" endpoints break in three ways at scale:
1. HTTP timeouts (load balancers cap connections at 30–120 s; 1M-row exports take minutes).
2. Web workers are tied up for minutes, starving other requests.
3. Loading the result set into memory causes OOM.

The fix is the **"submit → poll → download"** pattern:
- `POST /generate` returns `202 Accepted` + `task_id` instantly.
- A background worker does the heavy lifting and writes a file to durable storage.
- The client polls `GET /status/<task_id>` until `COMPLETED`.
- The client calls `GET /download/<task_id>` to fetch the file.

### Where this is used in the real world

Every B2B SaaS / data-heavy product runs this pattern:
- **Analytics / BI:** Mixpanel, Amplitude, Looker, Tableau, PowerBI exports
- **Fintech:** Stripe / Razorpay / Plaid transaction & compliance exports
- **E-commerce:** Shopify / WooCommerce order/customer exports
- **CRM:** Salesforce / HubSpot / Zoho bulk exports
- **HRIS / Payroll:** Workday / BambooHR / Zoho People payroll & tax reports
- **Cloud consoles:** AWS Cost Explorer, GCP/Azure billing exports
- **Marketing automation:** Mailchimp, SendGrid campaign reports
- **Healthcare / Government:** patient cohort exports, GST/income-tax filings

### Resume framing

> "Designed and implemented an async report-generation API. Users submit large CSV export jobs that return a `task_id` immediately, are processed in the background, tracked via a state machine in MySQL, and made available via a poll/download cycle — the same pattern used by Stripe, Shopify, and AWS Cost Explorer for long-running exports."

That framing is **honest and defensible** *if* the implementation is upgraded to match (see §7 Recommendations).

---

## 5. API Inventory

Canonical base path: `/api/v1/reports`  •  Backward-compatibility base path: `/reports`

### 5.1 Report APIs

| # | Method | Path | Purpose | Async | Auth | Notes |
|---|--------|------|---------|-------|------|-------|
| 1 | POST | `/api/v1/reports/` | Create/enqueue report job | Yes (Celery) | None | Validates `rows`; persists Report `QUEUED`; enqueues Celery task to queue `reports`. Returns 202. |
| 2 | GET | `/api/v1/reports/<id>` | Get report resource | n/a | None | Returns lifecycle fields + progress + links. |
| 3 | GET | `/api/v1/reports/<id>/status` | Poll progress | n/a | None | Polling-friendly; includes best-effort Celery state enrichment. |
| 4 | GET | `/api/v1/reports/<id>/download` | Download CSV | n/a | None | Only when `status == COMPLETED`; downloads from persisted `file_path`. |
| 5 | POST | `/api/v1/reports/<id>/cancel` | Cancel report | n/a | None | Sets `CANCEL_REQUESTED`; worker cooperatively stops and marks `CANCELED`. Best-effort revoke. |
| 6 | POST | `/api/v1/reports/<id>/retry` | Retry failed report | Yes (Celery) | None | Only allowed for `FAILED`; resets progress/error and re-enqueues. |
| 7 | DELETE | `/api/v1/reports/<id>` | Delete report | n/a | None | Best-effort deletes file + DB row. |
| 8 | GET | `/api/v1/reports/` | List reports | n/a | None | Pagination + filters: `user_id`, `status`, `q`, `page`, `page_size`, `sort`, `order`. |

### 5.2 System APIs

| # | Method | Path | Purpose | Notes |
|---|--------|------|---------|-------|
| 1 | GET | `/api/v1/reports/health` | API health | Lightweight liveness. |
| 2 | GET | `/api/v1/ops/health` | Ops health | Best-effort Celery inspect/ping visibility. |
| 3 | GET | `/api/v1/ops/workers` | Worker stats | Returns Celery inspect stats + active/reserved/scheduled. |
| 4 | GET | `/api/v1/ops/queues` | Queue topology | Returns Celery active queues per worker. |
| 5 | POST | `/api/v1/ops/cleanup` | Cleanup | Best-effort delete terminal reports older than N days (supports `days` + `dry_run`). |

### 5.3 Backward compatibility (/reports/*)

Legacy endpoints remain as a shim that forwards to v1 handlers:

- `POST /reports/generate`
- `GET /reports/status/<task_id>`
- `GET /reports/download/<task_id>`
- `GET /reports/list`
- `DELETE /reports/delete/<task_id>`
- `POST /reports/cancel/<task_id>`

---

## 6. Async / Concurrency Analysis

### 6.1 Current model

> Flask enqueues jobs into a Redis-backed Celery queue; Celery workers execute the export in separate processes with Flask app context, updating DB status/progress and writing CSV artifacts to disk.

### 6.2 What's correct

- **Durable decoupling**: API request returns immediately after enqueue; heavy work runs in worker tier.\n+- **Process isolation**: workers can scale independently of web.\n+- **Chunked processing**: ORM `yield_per(batch)` avoids loading all rows in memory.\n+- **Cooperative cancellation**: `CANCEL_REQUESTED` is checked mid-loop.\n+- **Retries**: transient DB failures retry with exponential backoff (OperationalError).\n+- **Single ID**: report_id == Celery task_id for correlation.

### 6.3 What's still missing / limitations

- **Auth/AuthZ**: no authentication or report ownership checks yet.\n+- **Idempotency**: duplicate submissions create duplicate report jobs.\n+- **Storage abstraction**: still local disk (`REPORTS_FOLDER`), not S3/GCS.\n+- **Operational guardrails**: no stuck-job sweeper / DLQ.\n+- **Observability**: structured logs are present; metrics/tracing not implemented yet.\n+- **Migrations**: Flask-Migrate is set up; deployment must run `flask db upgrade`.

### 6.5 Concurrency level rating

| Tier | Description | This project |
|---|---|---|
| Beginner | Fire-and-forget threads in web process | ❌ Removed |
| Intermediate | Celery + Redis, chunked exports, retries, cancel, ops visibility | ✅ Current state |
| Senior | Priority queues, DLQ, autoscaling, S3 + pre-signed URLs, metrics/tracing, idempotency | ❌ Not yet |

---

## 7. Strengths, Weaknesses, Resume Verdict

### 7.1 Genuine strengths (use these in interviews)

- Understanding of the **async submit-poll-download pattern** at a product level.
- Clean **state machine** (`PENDING → PROCESSING → COMPLETED / FAILED / CANCELED`) persisted to MySQL.
- **Flask application factory + Blueprints + extensions** structure — production-style layout.
- Correct **HTTP semantics** (202 Accepted, UUIDs for external IDs).
- Swagger/OpenAPI documentation present.
- Docker + docker-compose definitions written (even if aspirational).
- Three integration test scripts, including a "non-blocking" concurrency check.

### 7.2 Weaknesses (a senior interviewer will find these in 10 minutes)

- No auth, no authorization (anyone with an ID can download/delete).
- Local-disk storage only (`REPORTS_FOLDER`), no cloud storage / pre-signed URLs.
- No idempotency keys (duplicate submits create duplicate jobs).
- No \"stuck job\" sweeper / DLQ (operational hardening still needed).
- Rate limiting is optional/disabled by default (needs a production policy).
- No metrics/tracing yet (Prometheus/OpenTelemetry).

### 7.3 Honest level rating

- **Pattern understanding:** intermediate.
- **Code quality:** intermediate (structured app factory + migrations + versioned API).
- **Concurrency depth:** intermediate (Celery + Redis + worker tier + cooperative cancel + retries).
- **Production readiness:** medium (still missing auth, cloud storage, metrics, DLQ).
- **Doc-vs-code alignment:** good (v1 canonical + legacy shim).

**Resume verdict:** This is now a **believable async export backend** (Celery + Redis + versioned APIs + migrations + tests). To make it \"enterprise-impressive\", add auth/authorization, cloud storage + pre-signed URLs, metrics/tracing, and stronger operational controls (DLQ/sweeper/idempotency).

---

## 8. Recommendations — In Priority Order

### P0 — Completed in stabilization

These have been implemented:\n+- Celery is now the single execution path (threading removed)\n+- Orphan route files removed; `/reports/*` retained as a shim\n+- Worker boot fixed (task discovery + shared Celery init)\n+- Canonical prefix standardized to `/api/v1`\n+- `.env` uses `mysql+pymysql`\n+- Chunked processing (`yield_per`) added\n+- Migrations + pytest added

### P1 — Honesty in performance claims

6. **Batched DB reads.** Replace `.limit(rows).all()` with `query.yield_per(10_000)` (or keyset pagination). The README's batching claim becomes true.
7. **Cooperative cancellation.** Inside the writer loop, every N rows re-fetch `report.status` and bail early if `CANCELED`.
8. **Store `requested_rows`** on Report (currently only `rows_processed` exists, so progress % can't be computed without the original request).
9. **Stale-job recovery** on worker startup: any `PROCESSING` row older than X minutes → `FAILED` with reason `"interrupted_at_boot"`.

### P2 — Production hardening

10. **Auth + authorization.** Even simple JWT; restrict download/delete/cancel to the report's owner.
11. **Rate limiting** with Flask-Limiter on `/generate`.
12. **Input validation** with pydantic or marshmallow; reject out-of-range `rows`.
13. **Replace `print` with `logging`** (JSON formatter + correlation IDs).
14. **Gunicorn** (`gunicorn -w 4 -k gthread wsgi:app`) instead of `app.run`.
15. **Alembic / Flask-Migrate** instead of `db.create_all()`.
16. **DB indexes** on `reports.user_id`, `reports.status`, `reports.created_at`, `transactions.user_id`.
17. **Tuned connection pool** (`pool_size`, `max_overflow`, `pool_pre_ping`, `pool_recycle`).
18. **Pagination + filters** on `/list`.
19. **Cleanup cron / Celery beat** to delete CSV files and DB rows older than N days.

### P3 — Senior signal

20. **Idempotency keys** on `/generate`.
21. **Retry policy** (`autoretry_for`, `retry_backoff`) for transient DB errors.
22. **Dead-letter queue** for permanent failures.
23. **Storage abstraction** (`StorageBackend`) so local-disk and S3 are pluggable; produce **pre-signed download URLs** instead of routing files through Flask.
24. **Metrics** (Prometheus): jobs submitted/completed/failed counters, duration histogram, queue depth gauge.
25. **OpenTelemetry tracing** linking HTTP request → Celery task → DB queries.
26. **Notifications:** webhook or SSE/WebSocket "task completed" event, so the UI doesn't have to poll forever.
27. **Multi-format export:** XLSX / JSON / Parquet alongside CSV.

---

## 9. Scalability Review

| Bottleneck | Today | Mitigation |
|---|---|---|
| Memory per job | Loads all rows in RAM | `yield_per` + streaming CSV |
| DB connection pool | Default size 5 | Configure pool; move worker DB connections off the web pool |
| Disk | Local `/tmp/reports` | S3 / GCS / Azure Blob + pre-signed URLs |
| Process model | Single Flask process | Gunicorn web tier + separate Celery worker tier |
| Burst handling | Unbounded thread spawn | Broker-backed queue (Redis) + bounded worker concurrency |
| Long-tail jobs | No timeout | `task_soft_time_limit` / `task_time_limit` |
| Per-user fairness | None | Per-user semaphore in Redis or routing by queue |

---

## 10. Frontend Architecture (IMPLEMENTED)

The project now includes a **Flask template + vanilla JS** enterprise dashboard UI. No React/SPA — same-origin fetch to `/api/v1/*`.

### 10.1 Local Windows stack (NO Docker)

1. **Memurai** service running (Redis-compatible broker)
2. **Celery worker:** `celery -A worker.celery worker --loglevel=info -Q reports --concurrency=4`
3. **Flask API + UI:** `python run.py` → open `http://localhost:5000/`

### 10.2 UI routes (Flask templates)

| Route | Page | Purpose |
|---|---|---|
| `/` | Dashboard | Stats cards, worker health, status chart, recent activity |
| `/reports/new` | New Export | Submit async job + live job tracker with polling |
| `/reports` | Report History | Paginated table, filter/search/sort, actions |
| `/reports/<id>` | Report Detail | Lifecycle timeline, progress bar, cancel/retry/download |
| `/downloads` | Download Center | Completed exports as download cards |
| `/ops` | Queue & Workers | Worker list, queue topology, failed jobs, cleanup preview |

Legacy JSON API shim remains at `/reports/generate` etc. for scripts.

### 10.3 Frontend file map

```
app/templates/layouts/base.html   Shell: sidebar, topbar, theme toggle, toasts
app/templates/dashboard/          Dashboard home
app/templates/reports/            Create, history, detail
app/templates/downloads/          Download center
app/templates/ops/                Queue monitoring
app/static/css/app.css            Custom design system (dark/light, no Bootstrap)
app/static/js/api.js              ReportAPI client (/api/v1)
app/static/js/ui.js               Toasts, badges, progress, lifecycle HTML
app/static/js/polling.js          PollingManager + Connectivity + JobPoller
app/static/js/app.js              Theme, sidebar, topbar (PollingManager)
app/static/js/*.js                Page-specific controllers (all use PollingManager)
app/web/routes.py                 UI blueprint
```

### 10.4 API integration (frontend ↔ backend)

| UI action | API call |
|---|---|
| Dashboard stats | `GET /api/v1/reports/stats` + `GET /api/v1/ops/metrics` |
| Create export | `POST /api/v1/reports/` |
| Poll status | `GET /api/v1/reports/<id>/status` every 1.5–2s via `JobPoller` |
| History table | `GET /api/v1/reports/?page=&status=&q=` |
| Cancel / Retry / Delete | `POST .../cancel`, `POST .../retry`, `DELETE .../<id>` |
| Download | `GET /api/v1/reports/<id>/download` (anchor download) |
| Ops dashboard | `GET /api/v1/ops/metrics`, `/workers`, `/queues`, `/failed` |

### 10.5 Async visualization

- **Lifecycle component:** QUEUED → PROCESSING → COMPLETED (with failed/canceled variants)
- **Progress bars:** driven by `progress_pct` + `rows_processed / requested_rows`
- **Job polling:** `JobPoller` wraps `PollingManager`; stops on terminal states (`COMPLETED`, `FAILED`, `CANCELED`)
- **Topbar:** live queue depth + worker online indicator via `PollingManager` (15s interval)

### 10.6 Polling architecture (production-grade)

The UI no longer uses raw `setInterval`. All live refresh is centralized in `app/static/js/polling.js`.

**Components**

| Module | Role |
|---|---|
| `PollingManager` | Per-page poller: `setTimeout` chain (not `setInterval`), exponential backoff, max failure cap, `AbortController` per tick |
| `Connectivity` | Global singleton: `online` / `offline` / `reconnecting`; banner + topbar state; reconnect probe |
| `JobPoller` | Thin wrapper for single-report status polling |
| `PollerRegistry.stopAll()` | Called on `pagehide` / `beforeunload` — clears timers and aborts in-flight fetches |

**Lifecycle**

```
Page load → PollingManager.start() → _schedule(0) → _tick()
  ├─ success → Connectivity.markOnline() → schedule next tick at intervalMs
  └─ failure (network / 5xx)
       ├─ Connectivity.markOffline() → pause ALL registered pollers
       ├─ exponential backoff (intervalMs → maxIntervalMs)
       └─ after maxConsecutiveFailures → pauseDueToFailure() (no more requests)

Backend down → reconnect probe GET /api/v1/reports/health (skipConnectivitySideEffects)
  ├─ success → Connectivity.markOnline() → all pollers resumeFromConnectivity()
  └─ failure → backoff 15s → 120s, state = reconnecting

Tab hidden → pauseForVisibility() + abort in-flight
Tab visible → resumeFromVisibility() + trigger reconnect probe if offline
Page unload → stopAllPollers() + clearTimeout + AbortController.abort()
```

**UI states**

| State | Banner | Topbar |
|---|---|---|
| `online` | hidden | worker count or "Workers unavailable" (503/degraded) |
| `offline` | "Backend offline — live updates paused…" | "Backend offline" |
| `reconnecting` | "Reconnecting to backend…" | "Reconnecting…" |

Page sections (dashboard, history, ops) render `UI.offlineState()` instead of infinite spinners when fetch fails.

**Interval management**

- Default interval: 12–15s per page (dashboard, history, ops, topbar)
- Job detail/create: 1.5–2s via `JobPoller`
- Jitter: 0–500ms to avoid thundering herd
- No polling while tab is hidden or backend is offline

**Cleanup strategy**

- Every `PollingManager` registers in a `Set`; `stop()` removes itself and clears its timer
- In-flight `fetch` receives `AbortSignal` from per-tick `AbortController`
- Global reconnect timer cleared on `markOnline()` and `stopAllPollers()`
- Single offline toast (no spam on repeated failures)

### 10.7 Testing coverage

- `tests/test_web_ui.py` — all UI pages return 200, static CSS served, stats/metrics APIs
- `tests/test_reports_v1.py` — API lifecycle, pagination, validation
- `tests/test_legacy_compat.py` — backward-compatible JSON endpoints

**Total:** 16+ pytest tests (includes `/ops/failed` regression).

### 10.8 Remaining UI gaps (future)

- Authentication / per-user scoping
- SSE/WebSocket push instead of polling-only
- Idempotency key on create form
- Cloud download via pre-signed URLs

---

## 12. UI Redesign (Export Queue)

The dashboard was redesigned from an HRMS-style sidebar layout to a **compact top-nav, engineering-focused** UI:

- Brand: **Export Queue** (not "Async Reports HRMS")
- Nav: Overview · Jobs · Enqueue · Files · Infra
- Typography: Inter + IBM Plex Mono for job IDs
- Inspiration: Railway / Vercel / queue monitors — tables over giant KPI cards

Download flow: frontend uses `ReportAPI.downloadReport()` (fetch → blob) so API errors show as toasts instead of `download.htm`.

Legacy DB rows may store `/reports/download/<id>` in `file_path` — `Report.resolve_csv_path()` falls back to `./reports/report_<id>.csv`.

---

## 13. Windows + Celery (critical)

**Symptom:** Task received, then immediately:
`ValueError: not enough values to unpack (expected 3, got 0)` in `celery/app/trace.py` (`_loc`).

**Cause:** Celery’s default **prefork** pool does not work on Windows (billiard limitation).

**Fix:** Always start the worker with **`--pool=solo --concurrency=1`**:

```powershell
celery -A worker.celery worker --loglevel=info -Q reports --pool=solo --concurrency=1
# or: python worker.py
# or: .\scripts\start_worker.ps1
```

Jobs stuck in `QUEUED` with Celery state `FAILURE` are synced to `FAILED` in MySQL when you poll `/status`.

---

## 14. Beginner's Guide — How Everything Fits Together

Read this section first if you feel overwhelmed. It explains the **why**, not just the code.

### 12.1 The problem this project solves

Exporting 50,000+ database rows inside a normal web request would **block Flask** for minutes and might crash the server (memory/timeouts). Instead:

1. Flask **accepts** the job in milliseconds (returns `202 Accepted`)
2. A **background worker** builds the CSV slowly and safely
3. The browser **polls** for progress until the file is ready

### 12.2 The five moving parts

| Part | What it is | Analogy |
|---|---|---|
| **Browser (dashboard)** | HTML + JavaScript UI | A customer watching order status on a tracking page |
| **Flask API** | `python run.py` — HTTP server | The shop counter that takes orders |
| **Memurai (Redis)** | Message broker on port 6379 | The order ticket rail between counter and kitchen |
| **Celery worker** | `celery -A worker.celery worker ...` | The kitchen that actually cooks (exports CSV) |
| **MySQL** | `heavy_data_db` — stores users, transactions, reports | The ledger of every order and its status |

### 12.3 How they talk (async lifecycle)

```
YOU click "New Export"
    → Browser POST /api/v1/reports/
    → Flask writes Report row: status=QUEUED
    → Flask sends message to Memurai queue "reports"
    → Flask returns 202 immediately (does NOT wait for CSV)

Celery worker (separate process)
    → Picks message from Memurai
    → Sets status=PROCESSING, streams rows, writes CSV
    → Updates progress_pct in MySQL every batch
    → Sets status=COMPLETED or FAILED

Browser (every ~12 seconds on dashboard)
    → GET /api/v1/reports/stats  (counts + recent jobs)
    → GET /api/v1/ops/metrics    (worker health + status breakdown)
    → Updates cards and charts

YOU open report detail
    → Polls GET /api/v1/reports/<id>/status every ~2s until COMPLETED
```

### 12.4 Why `/metrics` and `/stats` repeat in DevTools

**This is normal** for a polling dashboard — but it should **not** flood forever.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/reports/stats` | Dashboard numbers: total, queue, completed, failed, **recent activity table** |
| `GET /api/v1/ops/metrics` | Worker health + **status distribution** (QUEUED, PROCESSING, etc.) |

The dashboard refreshes both about every **12 seconds** while the page is open. You also see `metrics` from the **topbar** poller (~15s) — we dedupe identical in-flight `/metrics` calls within 4 seconds to reduce noise.

**Professional behavior (now implemented):**

- Pause when tab is hidden
- Stop after repeated failures ("Backend offline")
- Slow reconnect probe when Flask is down
- Abort in-flight requests on navigation

### 12.5 Report status meanings

| Status | Meaning |
|---|---|
| **QUEUED** | Job saved in DB; waiting for a worker to pick it up |
| **PROCESSING** | Worker is actively writing the CSV |
| **COMPLETED** | CSV ready; download enabled |
| **FAILED** | Something went wrong; `error_message` explains |
| **CANCEL_REQUESTED** | User asked to stop; worker will stop cooperatively |
| **CANCELED** | Job stopped; terminal state |

**Celery state vs report status:** On the detail page you may see `status: COMPLETED` but `celery.state: PENDING`. That is because **your app's status** (MySQL) is the source of truth for the UI; Celery's internal task state can lag or differ after completion.

### 12.6 `/api/v1/ops/metrics` field reference

```json
{
  "celery": {
    "status": "ok",
    "workers_online": 1,
    "workers": ["celery@YOUR-PC"],
    "active_tasks": 0,
    "reserved_tasks": 0,
    "queue_depth_estimate": 0
  },
  "reports": {
    "total": 43,
    "by_status": {
      "QUEUED": 0,
      "PROCESSING": 0,
      "COMPLETED": 33,
      "FAILED": 1,
      "CANCELED": 0,
      "CANCEL_REQUESTED": 0
    }
  }
}
```

| Field | Meaning |
|---|---|
| `workers_online` | How many Celery worker processes answered a health ping |
| `active_tasks` | Jobs currently running on workers |
| `reserved_tasks` | Jobs prefetched by workers but not started yet |
| `queue_depth_estimate` | Rough backlog: active + reserved + DB rows still `QUEUED` |
| `reports.by_status.*` | How many report rows in each lifecycle state (from MySQL) |

### 12.7 Debugging guide

| Symptom | Likely cause | Fix |
|---|---|---|
| Dashboard "Backend offline" | Flask not running | `python run.py` |
| "Workers unavailable" but Flask up | Celery or Memurai down | Start Memurai service + `celery -A worker.celery worker -Q reports` |
| 500 on `/stats` | DB schema outdated | `flask --app run.py db upgrade` |
| 500 on `/ops/failed` | Was missing `current_app` import (fixed) | Pull latest code, restart Flask |
| Jobs stuck QUEUED | No worker consuming queue | Start Celery worker on queue `reports` |
| DevTools floods requests | Old JS cached | Hard refresh `Ctrl+Shift+R` |

### 12.8 Startup checklist (Windows, no Docker)

```powershell
# 1. Memurai running (Redis-compatible)
# 2. Terminal A — worker
celery -A worker.celery worker --loglevel=info -Q reports --concurrency=4
# 3. Terminal B — API + UI
python run.py
# 4. Browser
http://localhost:5000/
```

---

## 11. Maintenance Notes

This document and `notes.txt` are the **single source of truth** for project understanding.

- Update this file **every time** the architecture changes, an API is added/removed, or a concurrency strategy is changed.
- Update §5 (API Inventory) before merging any route change.
- Update §3 (Architecture diagram) any time the async path changes.
- The "Recommendations" section in §8 is the project's de-facto backlog — promote items into actual tickets as work begins.

