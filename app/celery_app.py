from __future__ import annotations

from celery import Celery


def make_celery(flask_app) -> Celery:
    """
    Create a Celery app that runs tasks inside Flask app context.

    Redis/Memurai role:
      - Flask writes job messages to the broker (queue)
      - Celery worker reads messages and executes tasks
      - Both Flask and worker must point at the same CELERY_BROKER_URL
    """
    celery = Celery(flask_app.import_name)

    # Celery config normalization: accept existing CELERY_* Flask config keys.
    cfg = flask_app.config
    celery.conf.update(
        broker_url=cfg.get("CELERY_BROKER_URL"),
        result_backend=cfg.get("CELERY_RESULT_BACKEND"),
        accept_content=cfg.get("CELERY_ACCEPT_CONTENT"),
        task_serializer=cfg.get("CELERY_TASK_SERIALIZER"),
        result_serializer=cfg.get("CELERY_RESULT_SERIALIZER"),
        timezone=cfg.get("CELERY_TIMEZONE"),
        task_track_started=cfg.get("CELERY_TASK_TRACK_STARTED"),
        task_time_limit=cfg.get("CELERY_TASK_TIME_LIMIT"),
        task_soft_time_limit=cfg.get("CELERY_TASK_SOFT_TIME_LIMIT"),
        task_acks_late=cfg.get("CELERY_TASK_ACKS_LATE"),
        worker_prefetch_multiplier=cfg.get("CELERY_WORKER_PREFETCH_MULTIPLIER"),
        task_always_eager=cfg.get("CELERY_TASK_ALWAYS_EAGER", False),
        task_eager_propagates=cfg.get("CELERY_TASK_EAGER_PROPAGATES", False),
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    # Ensure tasks get discovered
    celery.autodiscover_tasks(["app.tasks"])

    return celery

