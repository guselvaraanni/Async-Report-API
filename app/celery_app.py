from __future__ import annotations

import logging
import sys
from datetime import datetime

from celery import Celery

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


def make_celery(flask_app) -> Celery:
    """
    Create a Celery app that runs tasks inside Flask app context.

    Redis/Memurai role:
      - Flask writes job messages to the broker (queue)
      - Celery worker reads messages and executes tasks
      - Both Flask and worker must point at the same CELERY_BROKER_URL

    Windows: prefork pool is broken (billiard _loc error). Use pool=solo.
    """
    celery = Celery(flask_app.import_name)
    celery.conf.update(flask_app.config.get("CELERY_CONFIG") or _build_celery_config(flask_app))

    class ContextTask(celery.Task):
        """Runs each task inside Flask app context; syncs DB on hard failures."""

        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

        def on_failure(self, exc, task_id, args, kwargs, einfo):
            with flask_app.app_context():
                from app.extensions import db
                from app.models.report import Report

                report_id = task_id or (args[0] if args else None)
                if not report_id:
                    return

                report = Report.query.filter_by(task_id=report_id).first()
                if not report:
                    return

                if report.status in (
                    Report.Status.QUEUED.value,
                    Report.Status.PROCESSING.value,
                ):
                    report.status = Report.Status.FAILED.value
                    report.error_message = (str(exc) or "Celery task failed")[:2000]
                    report.completed_at = datetime.utcnow()
                    db.session.commit()
                    logger.error(
                        "celery_task_failed report_id=%s error=%s",
                        report_id,
                        report.error_message,
                    )

    celery.Task = ContextTask
    celery.set_default()

    # Route export jobs to the reports queue
    celery.conf.task_routes = {
        "app.tasks.export_tasks.export_transactions_task": {"queue": "reports"},
    }
    celery.conf.task_default_queue = "reports"

    celery.autodiscover_tasks(["app.tasks"])
    import app.tasks.export_tasks  # noqa: F401 — ensure task module is loaded

    if IS_WINDOWS:
        logger.info(
            "Celery on Windows: use worker pool 'solo' (see scripts/start_worker.ps1)"
        )

    return celery


def _build_celery_config(flask_app) -> dict:
    """Map Flask config keys to Celery 5 settings."""
    cfg = flask_app.config
    conf = {
        "broker_url": cfg.get("CELERY_BROKER_URL"),
        "result_backend": cfg.get("CELERY_RESULT_BACKEND"),
        "accept_content": cfg.get("CELERY_ACCEPT_CONTENT"),
        "task_serializer": cfg.get("CELERY_TASK_SERIALIZER"),
        "result_serializer": cfg.get("CELERY_RESULT_SERIALIZER"),
        "timezone": cfg.get("CELERY_TIMEZONE"),
        "task_track_started": cfg.get("CELERY_TASK_TRACK_STARTED"),
        "task_time_limit": cfg.get("CELERY_TASK_TIME_LIMIT"),
        "task_soft_time_limit": cfg.get("CELERY_TASK_SOFT_TIME_LIMIT"),
        "task_acks_late": cfg.get("CELERY_TASK_ACKS_LATE"),
        "worker_prefetch_multiplier": cfg.get("CELERY_WORKER_PREFETCH_MULTIPLIER"),
        "task_always_eager": cfg.get("CELERY_TASK_ALWAYS_EAGER", False),
        "task_eager_propagates": cfg.get("CELERY_TASK_EAGER_PROPAGATES", False),
        "worker_pool": cfg.get("CELERY_WORKER_POOL"),
    }
    return {k: v for k, v in conf.items() if v is not None}
