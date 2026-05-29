"""
Celery worker entry point.

Windows (Memurai, no Docker) — REQUIRED flags:
  celery -A worker.celery worker --loglevel=info -Q reports --pool=solo --concurrency=1

Or run:
  python worker.py

Linux/macOS:
  celery -A worker.celery worker --loglevel=info -Q reports --concurrency=4
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.celery_app import IS_WINDOWS
from app.celery_app import make_celery

flask_app = create_app()
celery = make_celery(flask_app)

# Ensure tasks are registered on this Celery app instance
import app.tasks.export_tasks  # noqa: E402, F401


def _default_worker_argv():
    argv = [
        "worker",
        "--loglevel=info",
        "-Q",
        "reports",
    ]
    if IS_WINDOWS:
        argv.extend(["--pool=solo", "--concurrency=1"])
    else:
        argv.extend(["--concurrency", str(flask_app.config.get("CELERY_WORKER_CONCURRENCY", 4))])
    return argv


if __name__ == "__main__":
    print("Starting Celery worker...")
    if IS_WINDOWS:
        print("Windows detected: using --pool=solo --concurrency=1")
    celery.worker_main(argv=_default_worker_argv())
