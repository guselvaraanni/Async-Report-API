# Testing Guide — Async Report Export Platform

## Startup (Windows, Memurai, no Docker)

```powershell
# Terminal 1 — Celery worker (Windows MUST use --pool=solo)
.\scripts\start_worker.ps1
# OR:
celery -A worker.celery worker --loglevel=info -Q reports --pool=solo --concurrency=1
# OR:
python worker.py

# Terminal 2 — Flask API + UI
python run.py
```

### Windows Celery error?

If you see `ValueError: not enough values to unpack (expected 3, got 0)` in `celery/app/trace.py`,
you are using the **prefork** pool on Windows. **Stop the worker** and restart with `--pool=solo`.

Open: http://localhost:5000/

## Manual test checklist

| Step | URL / action | Expected |
|------|----------------|----------|
| 1 | http://localhost:5000/ | Overview loads, metrics populate |
| 2 | Enqueue → user 1, 100 rows | 202, tracker shows QUEUED → PROCESSING → COMPLETED |
| 3 | Files | New job shows **Ready**, Download saves `.csv` |
| 4 | Jobs | Table lists job, DL works for new exports |
| 5 | Infra | Workers ≥ 1 when Celery running |
| 6 | Stop Flask | Banner "Backend offline", polling stops |
| 7 | Restart Flask | Reconnect, polling resumes |

## Automated tests

```powershell
$env:FLASK_ENV = "testing"
pytest -q
```

Tests use **in-memory SQLite** only (`TestingConfig`). They never touch `heavy_data_db`.

## Download troubleshooting

- **Legacy jobs** (before Celery file storage): status COMPLETED but file **Missing** — CSV was never written. Run a **new export**.
- Files live under `./reports/report_<uuid>.csv` (or `REPORTS_FOLDER` env).
- UI uses `ReportAPI.downloadReport()` — errors show as toasts, not `download.htm`.
