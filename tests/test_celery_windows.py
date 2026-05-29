"""Celery configuration guards for Windows development."""
import sys

from app.config import DevelopmentConfig


def test_windows_uses_solo_pool_by_default():
    if sys.platform != "win32":
        return
    assert DevelopmentConfig.CELERY_WORKER_POOL == "solo"
    assert DevelopmentConfig.CELERY_WORKER_CONCURRENCY == 1
    assert DevelopmentConfig.CELERY_TASK_SOFT_TIME_LIMIT is None
