# Advanced Configuration Guide

## Production Configuration

### 1. Environment Variables (.env)
```bash
# Security
SECRET_KEY=your-very-secure-random-key-here-min-32-chars
FLASK_ENV=production

# Database
DATABASE_URL=mysql+pymysql://user:secure_password@prod-db-server:3306/async_reports
SQLALCHEMY_ECHO=False
SQLALCHEMY_POOL_SIZE=20
SQLALCHEMY_POOL_RECYCLE=3600
SQLALCHEMY_POOL_PRE_PING=True

# Redis (use separate instances for broker and result backend in production)
CELERY_BROKER_URL=redis://:redis_password@prod-redis-broker:6379/0
CELERY_RESULT_BACKEND=redis://:redis_password@prod-redis-result:6379/0

# Celery
CELERY_ACCEPT_CONTENT=json
CELERY_TASK_SERIALIZER=json
CELERY_RESULT_SERIALIZER=json
CELERY_TIMEZONE=UTC
CELERY_TASK_TIME_LIMIT=1800  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT=1700  # 28 minutes (before hard limit)

# Application
REPORTS_FOLDER=/mnt/reports
MAX_ROWS_PER_REPORT=5000000
LOG_LEVEL=INFO
```

### 2. Production Docker Compose
```yaml
version: '3.8'

services:
  web:
    build:
      context: .
      dockerfile: Dockerfile.prod
    container_name: async-reports-api-prod
    command: gunicorn --workers 4 --worker-class sync --bind 0.0.0.0:5000 --timeout 120 wsgi:app
    environment:
      FLASK_ENV: production
      DATABASE_URL: mysql+pymysql://user:pass@db:3306/async_reports
      CELERY_BROKER_URL: redis://redis-broker:6379/0
      CELERY_RESULT_BACKEND: redis://redis-result:6379/0
    ports:
      - "5000:5000"
    volumes:
      - reports_volume:/mnt/reports
    depends_on:
      - db
      - redis-broker
      - redis-result
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/api/reports/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  worker:
    build:
      context: .
      dockerfile: Dockerfile.prod
    container_name: async-reports-worker-prod
    command: celery -A worker.celery worker --loglevel=info --concurrency=8 --max-tasks-per-child=100
    environment:
      FLASK_ENV: production
      DATABASE_URL: mysql+pymysql://user:pass@db:3306/async_reports
      CELERY_BROKER_URL: redis://redis-broker:6379/0
      CELERY_RESULT_BACKEND: redis://redis-result:6379/0
    volumes:
      - reports_volume:/mnt/reports
    depends_on:
      - db
      - redis-broker
      - redis-result
    restart: always
    deploy:
      replicas: 3  # Run 3 worker instances

  db:
    image: mysql:8.0
    container_name: async-reports-db-prod
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
      MYSQL_DATABASE: async_reports
      MYSQL_USER: ${DB_USER}
      MYSQL_PASSWORD: ${DB_PASSWORD}
    volumes:
      - db_volume:/var/lib/mysql
    restart: always
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      timeout: 20s
      retries: 10

  redis-broker:
    image: redis:7-alpine
    container_name: async-reports-redis-broker-prod
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes:
      - redis_broker_volume:/data
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      timeout: 10s
      retries: 5

  redis-result:
    image: redis:7-alpine
    container_name: async-reports-redis-result-prod
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes:
      - redis_result_volume:/data
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      timeout: 10s
      retries: 5

volumes:
  db_volume:
    driver: local
  reports_volume:
    driver: local
  redis_broker_volume:
    driver: local
  redis_result_volume:
    driver: local
```

### 3. Gunicorn Production Configuration (wsgi.py)
```python
"""
WSGI entry point for production (Gunicorn).
Run with: gunicorn --config gunicorn_config.py wsgi:app
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
```

### 4. Gunicorn Config File (gunicorn_config.py)
```python
import multiprocessing

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
loglevel = "info"

# Process naming
proc_name = "async-reports-api"

# Server mechanics
daemon = False
pidfile = None
tmp_upload_dir = None

# SSL
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Server hooks
def post_fork(server, worker):
    """Called after worker fork."""
    pass

def pre_exec(server):
    """Called before server exec."""
    pass
```

### 5. Nginx Reverse Proxy Configuration
```nginx
upstream flask_app {
    server web:5000;
}

server {
    listen 80;
    server_name api.example.com;
    client_max_body_size 100M;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;
    
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://flask_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 120s;
        
        # Buffering
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }

    location /reports/download/ {
        # Increase timeout for large file downloads
        proxy_read_timeout 600s;
        proxy_pass http://flask_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Deny access to sensitive files
    location ~ /\. {
        deny all;
    }
}
```

## Scaling Strategies

### Horizontal Scaling (Multiple Worker Nodes)

```bash
# Scale to 10 worker containers
docker-compose up -d --scale worker=10

# For Kubernetes
kubectl scale deployment async-reports-worker --replicas=10
```

### Vertical Scaling (Larger Instances)

Adjust Celery configuration for larger machines:

```python
# config.py - for high-memory servers
class ProductionConfig:
    CELERY_WORKER_PREFETCH_MULTIPLIER = 4
    CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
    CELERY_WORKER_CONCURRENCY = 32  # For 64-core servers
```

## Database Optimization

### MySQL Configuration (my.cnf)
```ini
[mysqld]
# Connection handling
max_connections = 1000
max_allowed_packet = 256M

# InnoDB optimization
innodb_buffer_pool_size = 4G
innodb_log_file_size = 512M
innodb_flush_log_at_trx_commit = 2

# Query cache
query_cache_size = 64M
query_cache_type = 1

# Slow query logging
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow.log
long_query_time = 2
```

### Add Indexes
```sql
-- In app/models/report.py migration or init script
CREATE INDEX idx_task_id ON reports(task_id);
CREATE INDEX idx_user_id ON reports(user_id);
CREATE INDEX idx_status ON reports(status);
CREATE INDEX idx_created_at ON reports(created_at);
CREATE INDEX idx_transaction_user ON transactions(user_id);
CREATE INDEX idx_transaction_created ON transactions(created_at);
```

## Monitoring & Logging

### Prometheus Metrics (app/metrics.py)
```python
from prometheus_client import Counter, Histogram, Gauge
import time

# Metrics
report_generation_requests = Counter(
    'report_generation_requests_total',
    'Total report generation requests'
)

report_generation_duration = Histogram(
    'report_generation_duration_seconds',
    'Time spent generating reports',
    buckets=(10, 30, 60, 300, 600, 1800)
)

active_tasks = Gauge(
    'active_celery_tasks',
    'Number of active Celery tasks'
)

rows_processed = Counter(
    'rows_processed_total',
    'Total rows processed across all reports'
)
```

### ELK Stack Integration (Logstash Config)
```json
{
  "input": {
    "docker": {
      "hosts": ["unix:///var/run/docker.sock"]
    }
  },
  "filter": {
    "json": {
      "source": "message"
    }
  },
  "output": {
    "elasticsearch": {
      "hosts": ["elasticsearch:9200"],
      "index": "logs-%{+YYYY.MM.dd}"
    }
  }
}
```

## Security Hardening

### API Authentication (JWT)
```python
from flask_jwt_extended import JWTManager, jwt_required

jwt = JWTManager()

# In app/__init__.py
jwt.init_app(app)

# In routes/reports.py
@reports_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_report():
    current_user = get_jwt_identity()
    # ... rest of code
```

### Rate Limiting
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# In app/__init__.py
limiter.init_app(app)

# In routes/reports.py
@reports_bp.route('/generate', methods=['POST'])
@limiter.limit("10 per minute")
def generate_report():
    # ... code
```

### CORS Configuration
```python
from flask_cors import CORS

# In app/__init__.py
CORS(app, resources={
    r"/api/*": {
        "origins": ["https://app.example.com"],
        "methods": ["GET", "POST", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})
```

## Backup & Recovery

### Database Backup Script
```bash
#!/bin/bash
BACKUP_DIR="/backups/mysql"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p $BACKUP_DIR

docker exec async-reports-db mysqldump \
  -u appuser -p$DB_PASSWORD \
  async_reports > $BACKUP_DIR/backup_$TIMESTAMP.sql

# Keep last 30 days
find $BACKUP_DIR -name "backup_*.sql" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/backup_$TIMESTAMP.sql"
```

### Schedule with Crontab
```bash
# Backup daily at 2 AM
0 2 * * * /scripts/backup_database.sh
```

## Performance Tuning

### Connection Pooling
```python
# In config.py
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 20,
    'pool_recycle': 3600,
    'pool_pre_ping': True,
    'max_overflow': 40,
}
```

### Batch Size Optimization
```python
# In tasks/export_tasks.py
# Tune based on available memory
BATCH_SIZE = 10000  # Adjust if memory constrained
```

### Redis Memory Management
```bash
# Monitor Redis memory
docker exec async-reports-redis redis-cli INFO memory

# Set max memory with eviction policy
docker exec async-reports-redis redis-cli CONFIG SET maxmemory 2gb
docker exec async-reports-redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```
