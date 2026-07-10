"""CSV export business logic for Celery workers."""
from __future__ import annotations

import csv
import logging
import os
import time
from datetime import datetime

from app.extensions import db
from app.models.report import Report
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


def run_export(report_id: str, user_id: int, requested_rows: int) -> None:
    """Stream transactions to CSV; update report progress."""
    logger.info("export_start report_id=%s user_id=%s rows=%s", report_id, user_id, requested_rows)

    report = Report.query.filter_by(task_id=report_id).first()
    if not report:
        logger.error("export_missing_report report_id=%s", report_id)
        return

    try:
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
        query = (
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

            for tx in query:
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
        if processed < requested_rows:
            report.error_message = (
                f"Exported all {processed} available transaction(s) for user_id={user_id}. "
                f"Requested {requested_rows:,} — add more data or use a user with a larger dataset."
            )
            logger.warning(
                "export_partial report_id=%s exported=%s requested=%s",
                report_id,
                processed,
                requested_rows,
            )
        db.session.commit()
        logger.info("export_done report_id=%s rows=%s", report_id, processed)

    except Exception as exc:
        logger.exception("export_error report_id=%s", report_id)
        db.session.rollback()
        report = Report.query.filter_by(task_id=report_id).first()
        if not report:
            return
        if report.status == Report.Status.CANCEL_REQUESTED.value:
            report.status = Report.Status.CANCELED.value
        else:
            report.status = Report.Status.FAILED.value
            report.error_message = str(exc)
        report.completed_at = datetime.utcnow()
        db.session.commit()
