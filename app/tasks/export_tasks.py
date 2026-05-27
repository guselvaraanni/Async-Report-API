"""
Celery worker task: export transactions to CSV.

QUEUE FLOW (beginner summary):
  1. Flask receives POST /api/v1/reports/ and saves a row with status=QUEUED
  2. Flask puts a message on Redis/Memurai queue named "reports"
  3. This function runs inside the Celery worker process (NOT inside Flask)
  4. Worker updates the same MySQL row: PROCESSING -> progress -> COMPLETED/FAILED
  5. Browser polls GET /status until it sees a terminal state
"""
from __future__ import annotations

import csv
import os
import time
from datetime import datetime

from celery import shared_task
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models.report import Report
from app.models.transaction import Transaction


@shared_task(
    bind=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def export_transactions_task(self, report_id: str, user_id: int, requested_rows: int):
    """
    Generate a CSV export of a user's transactions.

    This runs in a Celery worker process and updates the Report row for progress tracking.
    """
    report = Report.query.filter_by(task_id=report_id).first()
    if not report:
        return

    try:
        # If cancellation was requested before worker started
        if report.status in (
            Report.Status.CANCEL_REQUESTED.value,
            Report.Status.CANCELED.value,
        ):
            report.status = Report.Status.CANCELED.value
            report.completed_at = datetime.utcnow()
            db.session.commit()
            return

        report.status = Report.Status.PROCESSING.value
        report.started_at = datetime.utcnow()
        report.rows_processed = 0
        report.progress_pct = 0.0
        db.session.commit()

        os.makedirs(report.reports_folder(), exist_ok=True)
        file_path = report.build_file_path()
        report.file_path = file_path
        db.session.commit()

        batch_size = report.export_batch_size()

        q = (
            Transaction.query.filter_by(user_id=user_id)
            .order_by(Transaction.id.asc())
            .limit(requested_rows)
            .yield_per(batch_size)
        )

        processed = 0
        last_commit = time.time()

        with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["id", "user_id", "amount", "currency", "status", "created_at"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for tx in q:
                # Cooperative cancel: refresh status periodically
                if processed % batch_size == 0:
                    db.session.refresh(report)
                    if report.status == Report.Status.CANCEL_REQUESTED.value:
                        report.status = Report.Status.CANCELED.value
                        report.completed_at = datetime.utcnow()
                        db.session.commit()
                        return

                writer.writerow(
                    {
                        "id": tx.id,
                        "user_id": tx.user_id,
                        "amount": tx.amount,
                        "currency": tx.currency,
                        "status": tx.status,
                        "created_at": tx.created_at.isoformat() if tx.created_at else "",
                    }
                )
                processed += 1

                now = time.time()
                if now - last_commit >= 1.0:
                    report.rows_processed = processed
                    report.progress_pct = report.compute_progress_pct()
                    db.session.commit()
                    last_commit = now

        report.rows_processed = processed
        report.progress_pct = 100.0
        report.status = Report.Status.COMPLETED.value
        report.completed_at = datetime.utcnow()
        db.session.commit()

    except Exception as e:
        # If user requested cancellation, don't overwrite it with FAILED
        db.session.rollback()
        report = Report.query.filter_by(task_id=report_id).first()
        if not report:
            return

        if report.status == Report.Status.CANCEL_REQUESTED.value:
            report.status = Report.Status.CANCELED.value
        else:
            report.status = Report.Status.FAILED.value
            report.error_message = str(e)
        report.completed_at = datetime.utcnow()
        db.session.commit()