import os
import sys
from datetime import timedelta

IS_WINDOWS = sys.platform == "win32"


class Config:
    """Base configuration."""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-prod'
    JSON_SORT_KEYS = False
    
    # Database — credentials must come from .env
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite+pysqlite:///instance/local_dev.db'

    # Celery
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SQLAlchemy engine hardening (safe defaults; can override via env)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": os.environ.get("SQLALCHEMY_POOL_PRE_PING", "true").lower() == "true",
        "pool_recycle": int(os.environ.get("SQLALCHEMY_POOL_RECYCLE", "3600")),
        "pool_size": int(os.environ.get("SQLALCHEMY_POOL_SIZE", "10")),
        "max_overflow": int(os.environ.get("SQLALCHEMY_MAX_OVERFLOW", "20")),
    }

    # Celery config (Celery 5 expects lower-case keys too; we map in celery_app.py)
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = 'UTC'
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
    CELERY_TASK_SOFT_TIME_LIMIT = 28 * 60  # 28 minutes
    CELERY_TASK_ACKS_LATE = True
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1

    # Windows: prefork pool crashes with billiard "_loc" error — use solo pool
    CELERY_WORKER_POOL = os.environ.get("CELERY_WORKER_POOL") or (
        "solo" if IS_WINDOWS else "prefork"
    )
    CELERY_WORKER_CONCURRENCY = int(
        os.environ.get("CELERY_WORKER_CONCURRENCY", "1" if IS_WINDOWS else "4")
    )
    # SIGUSR1 soft timeouts are not supported on Windows
    CELERY_TASK_SOFT_TIME_LIMIT = (
        None if IS_WINDOWS else 28 * 60
    )

    # Report settings
    REPORTS_FOLDER = os.environ.get('REPORTS_FOLDER') or os.path.join(os.getcwd(), 'reports')
    MAX_ROWS_PER_REPORT = 1000000
    EXPORT_BATCH_SIZE = int(os.environ.get("EXPORT_BATCH_SIZE", "10000"))

    # API
    API_V1_PREFIX = "/api/v1"

    # Rate limiting (disabled by default)
    RATELIMIT_ENABLED = os.environ.get("RATELIMIT_ENABLED", "false").lower() == "true"
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "")

    SWAGGER = {
        'title': 'Heavy Data Export API',
        'uiversion': 3,
        'openapi': '3.0.0',
        'description': 'An asynchronous API for generating massive data reports using Celery and Redis.'
    }


class DevelopmentConfig(Config):
    ENV = "development"
    DEBUG = True


class TestingConfig(Config):
    ENV = "testing"
    TESTING = True
    DEBUG = False
    # Default to SQLite for tests unless overridden
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or "sqlite+pysqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
    # Eager execution for unit tests
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True


class ProductionConfig(Config):
    ENV = "production"
    DEBUG = False