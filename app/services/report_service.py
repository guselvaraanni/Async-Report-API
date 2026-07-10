"""Report job lifecycle: create, poll, cancel, download."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from celery.result import AsyncResult
from flask import current_app
from sqlalchemy import asc, desc

from app import celery
from app.extensions import db
from app.models.report import Report
from app.models.user import User
from app.tasks.export_tasks import export_transactions_task
from app.utils.responses import json_error

logger = logging.getLogger(__name__)


class ReportService:
    """Business logic for async report exports."""

    @staticmethod
    def create_job(user_id: int, requested_rows: int) -> tuple[Optional[dict], Optional[tuple], int]:
        """Persist QUEUED report and enqueue Celery task."""
        user = db.session.get(User, user_id)
        if not user:
            return None, json_error("USER_NOT_FOUND", f"User {user_id} not found", 404), 404

        task_id = str(uuid.uuid4())
        report = Report(
            user_id=user_id,
            task_id=task_id,
            status=Report.Status.QUEUED.value,
            requested_rows=requested_rows,
            created_at=datetime.utcnow(),
        )
        db.session.add(report)
        db.session.commit()

        try:
            async_result = export_transactions_task.apply_async(
                args=[task_id, user_id, requested_rows],
                task_id=task_id,
                queue="reports",
            )
            logger.info("report_enqueued report_id=%s celery_id=%s", task_id, async_result.id)
        except Exception as exc:
            logger.exception("report_enqueue_failed report_id=%s", task_id)
            report.status = Report.Status.FAILED.value
            report.error_message = f"Failed to enqueue Celery task: {exc}"
            report.completed_at = datetime.utcnow()
            db.session.commit()
            return None, json_error(
                "QUEUE_UNAVAILABLE",
                "Could not enqueue job — is Redis running? Use pool=solo on Windows.",
                503,
                details={"report_id": task_id},
            ), 503

        return {
            "report_id": task_id,
            "task_id": task_id,
            "status": report.status,
            "created_at": report.created_at.isoformat(),
        }, None, 202

    @staticmethod
    def get_report(report_id: str) -> tuple[Optional[dict], Optional[tuple]]:
        """Fetch full report payload by public task id."""
        report = Report.query.filter_by(task_id=report_id).first()
        if not report:
            return None, json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)
        prefix = current_app.config["API_V1_PREFIX"]
        return report.to_dict_v1(prefix), None

    @staticmethod
    def sync_report_from_celery(report: Report, ar: AsyncResult) -> None:
        """Align DB status when Celery shows FAILURE or REVOKED."""
        celery_state = ar.state
        if celery_state == "FAILURE" and report.status in (
            Report.Status.QUEUED.value,
            Report.Status.PROCESSING.value,
        ):
            err = ar.result
            if report.status != Report.Status.FAILED.value:
                report.status = Report.Status.FAILED.value
                report.error_message = str(err) if err else "Celery task failed"
                report.completed_at = datetime.utcnow()
                db.session.commit()
        elif celery_state == "REVOKED" and report.status in (
            Report.Status.QUEUED.value,
            Report.Status.PROCESSING.value,
            Report.Status.CANCEL_REQUESTED.value,
        ):
            report.status = Report.Status.CANCELED.value
            report.completed_at = datetime.utcnow()
            db.session.commit()

    @staticmethod
    def get_status(report_id: str) -> tuple[Optional[dict], Optional[tuple]]:
        """Return status payload enriched with Celery state."""
        report = Report.query.filter_by(task_id=report_id).first()
        if not report:
            return None, json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

        ar = None
        try:
            ar = AsyncResult(report_id, app=celery)
            ReportService.sync_report_from_celery(report, ar)
            db.session.refresh(report)
        except Exception:
            ar = None

        prefix = current_app.config["API_V1_PREFIX"]
        payload = report.to_status_v1(prefix)
        if ar:
            try:
                payload["celery"] = {"state": ar.state}
                if ar.state == "FAILURE" and ar.result:
                    payload["celery"]["error"] = str(ar.result)[:500]
            except Exception:
                payload["celery"] = {"state": "UNKNOWN"}
        else:
            payload["celery"] = {"state": "UNKNOWN"}
        return payload, None

    @staticmethod
    def resolve_download(report_id: str) -> tuple[Optional[str], Optional[tuple]]:
        """Resolve CSV path for a completed report."""
        report = Report.query.filter_by(task_id=report_id).first()
        if not report:
            return None, json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

        if report.status != Report.Status.COMPLETED.value:
            return None, json_error(
                "REPORT_NOT_READY",
                f"Report not ready. Current status: {report.status}",
                400,
            )

        csv_path = report.resolve_csv_path()
        if not csv_path:
            return None, json_error(
                "FILE_NOT_FOUND",
                "CSV file is not on disk. Create a new export.",
                404,
                details={
                    "expected_path": report.build_file_path(),
                    "legacy_path": report.file_path,
                },
            )

        if report.file_path != csv_path:
            report.file_path = csv_path
            db.session.commit()
        return csv_path, None

    @staticmethod
    def cancel(report_id: str) -> tuple[Optional[dict], Optional[tuple]]:
        """Request cooperative cancel for an in-flight report."""
        report = Report.query.filter_by(task_id=report_id).first()
        if not report:
            return None, json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

        if report.status in (
            Report.Status.COMPLETED.value,
            Report.Status.FAILED.value,
            Report.Status.CANCELED.value,
        ):
            return None, json_error(
                "INVALID_STATE",
                f"Cannot cancel report in state {report.status}",
                400,
            )

        report.status = Report.Status.CANCEL_REQUESTED.value
        report.cancel_requested_at = datetime.utcnow()
        db.session.commit()

        try:
            celery.control.revoke(report_id, terminate=False)
        except Exception:
            pass

        return {"report_id": report_id, "status": report.status}, None

    @staticmethod
    def retry(report_id: str) -> tuple[Optional[dict], int, Optional[tuple]]:
        """Re-queue a failed report with the same task id."""
        report = Report.query.filter_by(task_id=report_id).first()
        if not report:
            return None, 404, json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

        if report.status != Report.Status.FAILED.value:
            return None, 400, json_error("INVALID_STATE", "Only FAILED reports can be retried", 400)

        report.status = Report.Status.QUEUED.value
        report.error_message = None
        report.rows_processed = 0
        report.progress_pct = 0.0
        report.started_at = None
        report.completed_at = None
        report.cancel_requested_at = None
        db.session.commit()

        export_transactions_task.apply_async(
            args=[report_id, report.user_id, report.requested_rows],
            task_id=report_id,
            queue="reports",
        )
        return {"report_id": report_id, "status": report.status}, 202, None

    @staticmethod
    def delete(report_id: str) -> tuple[Optional[dict], Optional[tuple]]:
        """Delete report row and CSV file."""
        report = Report.query.filter_by(task_id=report_id).first()
        if not report:
            return None, json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

        report.delete_files_best_effort()
        db.session.delete(report)
        db.session.commit()
        return {"message": f"Report {report_id} deleted"}, None

    @staticmethod
    def list_reports(filters: dict[str, Any]) -> dict:
        """Paginated report list with optional filters."""
        user_id = filters.get("user_id")
        status = filters.get("status")
        q = filters.get("q")
        page = filters.get("page", 1)
        page_size = filters.get("page_size", 20)
        sort = filters.get("sort", "created_at")
        order = filters.get("order", "desc")

        query = Report.query
        if user_id is not None:
            query = query.filter(Report.user_id == user_id)
        if status:
            query = query.filter(Report.status == status)
        if q:
            query = query.filter(Report.task_id.like(f"%{q}%"))

        sort_col = getattr(Report, sort, Report.created_at)
        query = query.order_by(asc(sort_col) if order == "asc" else desc(sort_col))

        items = query.offset((page - 1) * page_size).limit(page_size).all()
        total = query.count()
        prefix = current_app.config["API_V1_PREFIX"]
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [r.to_dict_v1(prefix) for r in items],
        }

    @staticmethod
    def stats() -> dict:
        """Dashboard aggregate counts and recent jobs."""
        total = Report.query.count()
        by_status = {s.value: Report.query.filter_by(status=s.value).count() for s in Report.Status}
        recent = Report.query.order_by(Report.created_at.desc()).limit(8).all()
        prefix = current_app.config["API_V1_PREFIX"]
        return {
            "total": total,
            "by_status": by_status,
            "queue": {
                "queued": by_status.get(Report.Status.QUEUED.value, 0),
                "processing": by_status.get(Report.Status.PROCESSING.value, 0),
                "cancel_requested": by_status.get(Report.Status.CANCEL_REQUESTED.value, 0),
            },
            "finished": {
                "completed": by_status.get(Report.Status.COMPLETED.value, 0),
                "failed": by_status.get(Report.Status.FAILED.value, 0),
                "canceled": by_status.get(Report.Status.CANCELED.value, 0),
            },
            "recent": [r.to_dict_v1(prefix) for r in recent],
        }
