# Quick Start Guide

## 5-Minute Setup

### Prerequisites
- Docker & Docker Compose installed
- OR Python 3.10+, MySQL 8.0, Redis 7

### Option 1: Docker (Recommended - 2 minutes)

```bash
# 1. Start all services
docker-compose up -d

# 2. Wait for services (30-60 seconds)
docker-compose ps
# All should show "running" or "healthy"

# 3. Test
curl http://localhost:5000/api/reports/health
```

### Option 2: Manual Setup (5 minutes)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
export DATABASE_URL="mysql+pymysql://user:pass@localhost:3306/async_reports"
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/0"

# 3. Terminal 1: Start Flask API
python run.py

# 4. Terminal 2: Start Celery Worker
celery -A worker.celery worker --loglevel=info
```

---

## Test the API in 30 Seconds

### Step 1: Generate a Report
```bash
TASK_ID=$(curl -s -X POST http://localhost:5000/api/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "rows": 10000}' | jq -r '.task_id')

echo "Task ID: $TASK_ID"
```

### Step 2: Poll Status
```bash
curl http://localhost:5000/api/reports/status/$TASK_ID | jq
```

### Step 3: Download (when complete)
```bash
curl -O http://localhost:5000/api/reports/download/$TASK_ID
```

---

## Key Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| POST | `/generate` | Start async report |
| GET | `/status/<task_id>` | Check progress |
| GET | `/download/<task_id>` | Download CSV |
| GET | `/list?user_id=1` | List all reports |
| DELETE | `/delete/<task_id>` | Delete report |

---

## What's Happening?

1. **POST /generate** → Returns `202 Accepted` with `task_id` (instant)
2. **Celery Worker** → Picks up task, processes data in background
3. **GET /status** → Shows `PENDING`, then `PROCESSING`, then `COMPLETED`
4. **GET /download** → Available only when status = `COMPLETED`

**Flask API stays responsive the entire time!**

---

## Project Structure

```
async-report-api/
├── app/
│   ├── models/        # User, Report, Transaction models
│   ├── routes/        # API endpoints
│   ├── tasks/         # Celery background tasks
│   └── config.py      # Configuration
├── worker.py          # Celery entry point
├── run.py             # Flask entry point
├── docker-compose.yml # All services in one go
└── README.md          # Full documentation
```

---

## Common Commands

### Docker

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f web        # Flask API
docker-compose logs -f worker     # Celery worker
docker-compose logs -f db         # MySQL

# Stop services
docker-compose down

# Clean everything
docker-compose down -v
```

### Testing

```bash
# Run all examples
bash API_EXAMPLES.sh

# Seed database with dummy data
bash seed_db.sh
```

### Database

```bash
# Connect to MySQL
docker exec -it async-reports-db mysql -u appuser -p

# View tables
USE async_reports;
SHOW TABLES;
SELECT * FROM reports;
```

---

## Troubleshooting

### "Connection refused"
```bash
# Wait for services to start
docker-compose ps
sleep 10
```

### "No such table: reports"
```bash
# Tables are created automatically when Flask starts
# If not, restart Flask
docker-compose restart web
```

### "Celery task not running"
```bash
# Check worker is running
docker-compose ps worker

# View worker logs
docker-compose logs worker

# Restart worker
docker-compose restart worker
```

---

## Next Steps

1. **Review** `README.md` for complete documentation
2. **Explore** API endpoints with cURL or Postman
3. **Modify** `app/tasks/export_tasks.py` to customize logic
4. **Scale** by adjusting `concurrency=4` in `docker-compose.yml`

---

## Performance Tips

- **Batch Processing**: Task processes 10K rows at a time (no memory overload)
- **Parallel Workers**: 4 workers by default, scale with `--scale worker=10`
- **Connection Pooling**: Flask-SQLAlchemy uses pooling by default
- **Streaming CSV**: Writes to disk in chunks (not all in RAM)

---

## Production Checklist

- [ ] Change MySQL/Redis passwords
- [ ] Set `SECRET_KEY` environment variable
- [ ] Use persistent volumes for data
- [ ] Enable HTTPS/SSL
- [ ] Add authentication to API
- [ ] Setup monitoring & alerts
- [ ] Use managed services (AWS RDS, ElastiCache)

---

## Need Help?

1. Check `README.md` for detailed docs
2. Review `API_EXAMPLES.sh` for cURL examples
3. Check logs: `docker-compose logs`
4. Test connectivity: `docker-compose ps`

**Happy exporting! 🚀**
