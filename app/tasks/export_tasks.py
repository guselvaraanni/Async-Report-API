"""Thin Celery task wrapper; logic lives in services."""
from __future__ import annotations

import logging

from celery import shared_task
from sqlalchemy.exc import OperationalError

from app.services.export_service import run_export

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="app.tasks.export_tasks.export_transactions_task",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def export_transactions_task(self, report_id: str, user_id: int, requested_rows: int):
    """Celery entrypoint for CSV export jobs."""
    run_export(report_id, user_id, requested_rows)
