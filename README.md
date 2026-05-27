# Async Report Export API

A production-ready, scalable API for exporting massive datasets (1M+ rows) without blocking the main thread. Built with Flask, Celery, Redis, and MySQL.

## Why This Architecture?

### The Problem
When users request large exports (1M+ transactions), processing them in the main Flask thread causes:
- **HTTP 504 Gateway Timeout** (browser gives up)
- **Server Freeze** (Flask can't handle other requests)
- **Memory Crash** (loading 1M rows into RAM)

### The Solution
This API uses **asynchronous task processing**:

1. User requests report → API instantly returns `202 Accepted` with `task_id`
2. Celery Worker (separate process) picks up task from Redis queue
3. Worker connects to MySQL, processes data, saves CSV file
4. User polls `/status/<task_id>` until completion
5. Download link appears when ready

**Result:** Flask stays responsive, workers handle heavy lifting in parallel.

## Tech Stack

- **API Framework:** Flask 3.0
- **Database:** MySQL 8.0
- **Message Broker:** Redis 7
- **Task Queue:** Celery 5.3
- **ORM:** Flask-SQLAlchemy
- **Containerization:** Docker & Docker Compose

## Architecture

```
async-report-api/
├── app/
│   ├── __init__.py          # Flask app factory, Celery init
│   ├── config.py            # Configuration (MySQL, Redis URIs)
│   ├── extensions.py        # SQLAlchemy instance
│   ├── models/
│   │   ├── user.py          # User model
│   │   ├── report.py        # Report tracking model
│   │   └── transaction.py   # Sample transaction data
│   ├── routes/
│   │   └── reports.py       # API endpoints
│   └── tasks/
│       └── export_tasks.py  # Celery task definitions
├── worker.py                # Celery worker entry point
├── run.py                   # Flask server entry point
├── docker-compose.yml       # Multi-container orchestration
├── Dockerfile               # Container image definition
└── requirements.txt         # Python dependencies
```

## Installation & Setup

### Prerequisites
- Docker & Docker Compose
- Or: Python 3.10+, MySQL 8.0, Redis 7

### Quick Start (Docker Recommended)

1. **Clone and navigate:**
   ```bash
   cd async-report-api
   ```

2. **Start all services:**
   ```bash
   docker-compose up -d
   ```

   This spins up:
   - MySQL database (port 3306)
   - Redis cache (port 6379)
   - Flask API (port 5000)
   - Celery worker (background)

3. **Wait for services to be healthy:**
   ```bash
   docker-compose ps
   # All should show "healthy" or "running"
   ```

4. **Test the API:**
   ```bash
   curl http://localhost:5000/api/reports/health
   # Response: {"status": "healthy"}
   ```

### Manual Setup (Without Docker)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   ```bash
   export DATABASE_URL="mysql+pymysql://root:password@localhost:3306/async_reports"
   export CELERY_BROKER_URL="redis://localhost:6379/0"
   export CELERY_RESULT_BACKEND="redis://localhost:6379/0"
   export FLASK_ENV="development"
   ```

3. **Create MySQL database:**
   ```sql
   CREATE DATABASE async_reports;
   ```

4. **Run Flask app:**
   ```bash
   python run.py
   ```

5. **In another terminal, start Celery worker:**
   ```bash
   celery -A worker.celery worker --loglevel=info
   ```

## API Endpoints

### 1. Health Check
```
GET /api/reports/health
```
**Response:** `{"status": "healthy"}`

---

### 2. Generate Report (Start Export)
```
POST /api/reports/generate
Content-Type: application/json

{
    "user_id": 1,
    "rows": 50000
}
```

**Response (202 Accepted):**
```json
{
    "task_id": "a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6",
    "status": "PENDING",
    "message": "Report generation started. Poll /status/<task_id> to check progress."
}
```

**Usage in cURL:**
```bash
curl -X POST http://localhost:5000/api/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "rows": 50000}'
```

---

### 3. Check Report Status
```
GET /api/reports/status/<task_id>
```

**Response (while processing):**
```json
{
    "task_id": "a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6",
    "status": "PROCESSING",
    "rows_processed": 12500,
    "created_at": "2024-01-15T10:30:00",
    "started_at": "2024-01-15T10:30:02",
    "completed_at": null
}
```

**Response (completed):**
```json
{
    "task_id": "a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6",
    "status": "COMPLETED",
    "rows_processed": 50000,
    "created_at": "2024-01-15T10:30:00",
    "started_at": "2024-01-15T10:30:02",
    "completed_at": "2024-01-15T10:35:45",
    "download_url": "/api/reports/download/a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6",
    "file_url": "/reports/download/a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6"
}
```

---

### 4. Download Report (CSV File)
```
GET /api/reports/download/<task_id>
```

**Response:** Binary CSV file download

**Usage in cURL:**
```bash
curl -O http://localhost:5000/api/reports/download/a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6
# Saves as report_a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6.csv
```

---

### 5. List All Reports for User
```
GET /api/reports/list?user_id=1
```

**Response:**
```json
{
    "user_id": 1,
    "count": 3,
    "reports": [
        {
            "id": 1,
            "task_id": "a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6",
            "status": "COMPLETED",
            "file_url": "/reports/download/a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6",
            "rows_processed": 50000,
            "created_at": "2024-01-15T10:30:00",
            "completed_at": "2024-01-15T10:35:45"
        }
    ]
}
```

---

### 6. Delete Report
```
DELETE /api/reports/delete/<task_id>
```

**Response:**
```json
{
    "message": "Report a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6 deleted successfully"
}
```

---

### 7. Test Celery Connectivity
```
GET /api/reports/test-celery
```

**Response:**
```json
{
    "task_id": "celery-task-id",
    "message": "Dummy task triggered. Check status in 10 seconds.",
    "celery_status": "PENDING"
}
```

## Testing Workflow

### 1. Create Sample Data

Access MySQL container and insert dummy transactions:

```bash
docker exec -it async-reports-db mysql -u appuser -p async_reports

# In MySQL shell:
USE async_reports;

-- Insert sample user
INSERT INTO users (username, email) VALUES ('testuser', 'test@example.com');

-- Insert 50,000 dummy transactions
INSERT INTO transactions (user_id, amount, currency, status)
SELECT 1, ROUND(RAND() * 1000, 2), 'USD', 'COMPLETED'
FROM (
    SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t1, (
    SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t2, (
    SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t3, (
    SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t4
LIMIT 50000;
```

### 2. Trigger Multiple Reports

```bash
# Request 1
TASK_ID_1=$(curl -s -X POST http://localhost:5000/api/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "rows": 50000}' | jq -r '.task_id')

# Request 2
TASK_ID_2=$(curl -s -X POST http://localhost:5000/api/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "rows": 50000}' | jq -r '.task_id')

echo "Task 1: $TASK_ID_1"
echo "Task 2: $TASK_ID_2"
```

### 3. Poll Status

```bash
# Check status (while processing)
curl http://localhost:5000/api/reports/status/$TASK_ID_1 | jq

# Keep polling until status = COMPLETED
while true; do
  STATUS=$(curl -s http://localhost:5000/api/reports/status/$TASK_ID_1 | jq -r '.status')
  echo "Status: $STATUS"
  if [ "$STATUS" = "COMPLETED" ]; then
    break
  fi
  sleep 2
done
```

### 4. Download Report

```bash
curl -O http://localhost:5000/api/reports/download/$TASK_ID_1

# View first 10 lines
head -10 report_*.csv
```

### 5. Watch Celery Worker Logs

```bash
docker logs -f async-reports-worker

# You should see:
# [tasks.export_tasks.export_transactions_task: ...] STARTED
# [tasks.export_tasks.export_transactions_task: ...] Progress: 10000 rows
# [tasks.export_tasks.export_transactions_task: ...] SUCCESS
```

## Key Design Patterns

### 1. Async Request → Task ID Response
```python
# User sends request
POST /api/reports/generate → Returns 202 Accepted with task_id

# API does this:
report = Report(task_id=str(uuid.uuid4()), status='PENDING')
db.session.add(report)
db.session.commit()
export_transactions_task.delay(task_id, user_id, rows)
return {'task_id': task_id}, 202
```

### 2. Celery Task with Flask Context
```python
@shared_task(bind=True)
def export_transactions_task(self, task_id, user_id, limit=1000000):
    # Task runs in separate process
    # BUT has access to Flask app context via our ContextTask wrapper
    report = Report.query.filter_by(task_id=task_id).first()
    report.status = 'PROCESSING'
    db.session.commit()
    
    # Heavy processing...
    
    report.status = 'COMPLETED'
    db.session.commit()
```

### 3. Polling for Completion
```javascript
// Client-side (JavaScript)
const taskId = "...";
let completed = false;

const poll = setInterval(async () => {
  const response = await fetch(`/api/reports/status/${taskId}`);
  const data = await response.json();
  
  console.log(`Progress: ${data.rows_processed} rows`);
  
  if (data.status === 'COMPLETED') {
    clearInterval(poll);
    // Download available at: data.download_url
    completed = true;
  } else if (data.status === 'FAILED') {
    clearInterval(poll);
    console.error(data.error_message);
  }
}, 2000); // Poll every 2 seconds
```

## Performance & Scalability

### Batch Processing
The task processes data in **10,000-row batches** to avoid loading 1M rows into RAM:
```python
batch_size = 10000
offset = 0
while offset < limit:
    transactions = Transaction.query.limit(batch_size).offset(offset).all()
    # Process and write to CSV
    offset += batch_size
```

### Parallel Workers
By default, 4 Celery workers run in parallel:
```yaml
# docker-compose.yml
command: celery -A worker.celery worker --concurrency=4
```

To scale:
```bash
# Start more workers
docker-compose up -d --scale worker=10
```

### Connection Pooling
Flask-SQLAlchemy uses connection pooling (default 5 connections). Adjust:
```python
# app/config.py
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True,
}
```

## Error Handling

### Task Failures
If Celery task fails, status updates to `FAILED`:
```python
except Exception as e:
    report.status = 'FAILED'
    report.error_message = str(e)
    db.session.commit()
```

Check via API:
```bash
curl http://localhost:5000/api/reports/status/$TASK_ID | jq '.error_message'
```

### Timeout Protection
Tasks have a 30-minute timeout:
```python
# app/config.py
CELERY_TASK_TIME_LIMIT = 30 * 60
```

### Graceful Degradation
- Missing user → HTTP 404
- Missing report → HTTP 404
- Not yet complete → HTTP 400 with current status
- File not on disk → HTTP 404

## Monitoring & Debugging

### View Celery Tasks
```bash
# Inside container
docker exec -it async-reports-worker celery -A worker.celery inspect active
# Lists all currently running tasks

docker exec -it async-reports-worker celery -A worker.celery inspect stats
# Worker statistics
```

### View Database
```bash
docker exec -it async-reports-db mysql -u appuser -p async_reports

# Check report status
SELECT id, task_id, status, rows_processed FROM reports;

# Check transactions
SELECT COUNT(*) FROM transactions;
```

### View Redis Queue
```bash
docker exec -it async-reports-redis redis-cli

# See pending tasks
KEYS *
LLEN celery

# Monitor in real-time
MONITOR
```

### Application Logs
```bash
# Flask API logs
docker logs -f async-reports-web

# Celery worker logs
docker logs -f async-reports-worker

# MySQL logs
docker logs -f async-reports-db
```

## Stopping & Cleanup

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v

# Rebuild images
docker-compose build --no-cache
```

## Production Deployment Checklist

- [ ] Use strong passwords for MySQL/Redis
- [ ] Set `SECRET_KEY` environment variable
- [ ] Enable HTTPS/SSL
- [ ] Use separate Redis instances for broker and result backend
- [ ] Implement authentication on API endpoints
- [ ] Add rate limiting to prevent abuse
- [ ] Use persistent volumes for database and reports
- [ ] Configure log aggregation (ELK, Datadog, etc.)
- [ ] Set up monitoring & alerts (Prometheus, Grafana)
- [ ] Use managed services (AWS RDS, ElastiCache) in production
- [ ] Implement request validation & sanitization
- [ ] Add pagination to `/list` endpoint
- [ ] Use environment-specific configurations

## Troubleshooting

### Celery Tasks Not Running
```bash
# 1. Check if worker is running
docker-compose ps | grep worker

# 2. Check Redis connectivity
docker exec -it async-reports-redis redis-cli ping
# Should return: PONG

# 3. Restart worker
docker-compose restart worker
```

### MySQL Connection Errors
```bash
# Verify database exists
docker exec -it async-reports-db mysql -u appuser -p -e "SHOW DATABASES;"

# Check connection string
echo $DATABASE_URL
```

### Reports Directory Permissions
```bash
# Ensure directory exists and is writable
docker exec async-reports-web mkdir -p /tmp/reports
docker exec async-reports-web chmod 777 /tmp/reports
```

## License

MIT License - Feel free to use for personal and commercial projects.

## Support

For issues or questions:
1. Check logs: `docker logs async-reports-*`
2. Verify all services are running: `docker-compose ps`
3. Test connectivity to each service
4. Review the API endpoints documentation above
