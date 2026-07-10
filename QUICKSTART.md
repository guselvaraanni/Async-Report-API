# Quick Start Guide

## 5-Minute Setup (Windows / local)

### Prerequisites
- Python 3.10+
- MySQL 8.0
- Memurai or Redis on `localhost:6379`

### Setup

```powershell
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and edit environment variables
copy .env.example .env

# 3. Run migrations
$env:FLASK_ENV = "development"
flask --app run.py db upgrade

# 4. Seed sample data (optional)
python scripts/seeds/seeds_db.py

# 5. Terminal 1 — Celery worker (Windows: use solo pool)
.\scripts\start_worker.ps1

# 6. Terminal 2 — Flask API + dashboard
python run.py
```

Open [http://localhost:5000/](http://localhost:5000/)

---

## Test the API in 30 Seconds

### Step 1: Generate a Report
```powershell
curl -X POST http://localhost:5000/api/v1/reports/ `
  -H "Content-Type: application/json" `
  -d "{\"user_id\": 1, \"rows\": 50}"
```

### Step 2: Poll Status
```powershell
curl http://localhost:5000/api/v1/reports/<report_id>/status
```

### Step 3: Download (when complete)
```powershell
curl -O http://localhost:5000/api/v1/reports/<report_id>/download
```

---

## Key Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/reports/health` | Health check |
| POST | `/api/v1/reports/` | Start async report |
| GET | `/api/v1/reports/<id>/status` | Check progress |
| GET | `/api/v1/reports/<id>/download` | Download CSV |
| GET | `/api/v1/reports/?user_id=1` | List reports |
| POST | `/api/v1/reports/<id>/cancel` | Cancel report |
| POST | `/api/v1/reports/<id>/retry` | Retry failed report |
| DELETE | `/api/v1/reports/<id>` | Delete report |

---

## What's Happening?

1. **POST /api/v1/reports/** → Returns `202 Accepted` with `task_id` (instant)
2. **Celery Worker** → Picks up task, processes data in background
3. **GET /api/v1/reports/<id>/status** → Shows `QUEUED`, then `PROCESSING`, then terminal state
4. **GET /api/v1/reports/<id>/download** → Available only when status = `COMPLETED`

**Flask API stays responsive the entire time!**

---

## Common Commands

```powershell
# Run automated tests
$env:FLASK_ENV = "testing"
pytest -q

# Manual smoke test (Flask must be running)
python scripts/manual_tests/test_api.py

# curl examples
bash scripts/API_EXAMPLES.sh
```

---

## Troubleshooting

### Celery prefork error on Windows
Use `--pool=solo --concurrency=1` (see `scripts/start_worker.ps1`).

### Job stuck QUEUED
- Check Memurai/Redis is running on port 6379
- Check Celery worker is running with `-Q reports`

### Database errors
```powershell
flask --app run.py db upgrade
```

---

## Next Steps

1. Review `README.md` for full documentation
2. Explore the dashboard at `http://localhost:5000/`
3. Run `python scripts/seeds/seed_50k.py` for large export demos

**Happy exporting!**
