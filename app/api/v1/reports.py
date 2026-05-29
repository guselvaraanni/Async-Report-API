from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from celery.result import AsyncResult
from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy import asc, desc

from app import celery
from app.extensions import db, limiter
from app.models.report import Report
from app.models.user import User
from app.tasks.export_tasks import export_transactions_task


reports_v1_bp = Blueprint("reports_v1", __name__)
logger = logging.getLogger(__name__)


def _json_error(code: str, message: str, status: int, *, details=None):
    payload = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    logger.info(
        "api_error code=%s status=%s detail=%s",
        code,
        status,
        message,
    )
    return jsonify(payload), status


@reports_v1_bp.get("/health")
def health():
    return jsonify({"status": "healthy"}), 200


@reports_v1_bp.post("/")
@limiter.limit(lambda: current_app.config.get("RATELIMIT_DEFAULT") or None)
def create_report_job():
    """
    Create (enqueue) an async report export job.

    This handler only *schedules* work — it does not export rows itself.
    The heavy work runs in export_transactions_task() on a Celery worker.
    """
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", 1)
    requested_rows = data.get("rows", 50000)

    try:
        requested_rows = int(requested_rows)
    except Exception:
        return _json_error("VALIDATION_ERROR", "`rows` must be an integer", 400)

    if requested_rows <= 0:
        return _json_error("VALIDATION_ERROR", "`rows` must be > 0", 400)

    max_rows = int(current_app.config.get("MAX_ROWS_PER_REPORT", 1_000_000))
    if requested_rows > max_rows:
        return _json_error("VALIDATION_ERROR", f"`rows` must be <= {max_rows}", 400)

    user = db.session.get(User, user_id)
    if not user:
        return _json_error("USER_NOT_FOUND", f"User {user_id} not found", 404)

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

    # Enqueue the task using the report.task_id as the Celery task_id for 1:1 mapping
    try:
        async_result = export_transactions_task.apply_async(
            args=[task_id, user_id, requested_rows],
            task_id=task_id,
            queue="reports",
        )
        logger.info(
            "report_enqueued report_id=%s celery_id=%s queue=reports",
            task_id,
            async_result.id,
        )
    except Exception as exc:
        logger.exception("report_enqueue_failed report_id=%s", task_id)
        report.status = Report.Status.FAILED.value
        report.error_message = f"Failed to enqueue Celery task: {exc}"
        report.completed_at = datetime.utcnow()
        db.session.commit()
        return _json_error(
            "QUEUE_UNAVAILABLE",
            "Could not enqueue job — is Memurai running? Start the Celery worker with pool=solo on Windows.",
            503,
            details={"report_id": task_id},
        )

    return jsonify(
        {
            "report_id": task_id,
            "task_id": task_id,  # backward-friendly alias
            "status": report.status,
            "created_at": report.created_at.isoformat(),
        }
    ), 202


@reports_v1_bp.get("/stats")
def report_stats():
    """Aggregate report counts for dashboards."""
    total = Report.query.count()
    by_status = {
        s.value: Report.query.filter_by(status=s.value).count()
        for s in Report.Status
    }
    recent = (
        Report.query.order_by(Report.created_at.desc()).limit(8).all()
    )
    prefix = current_app.config["API_V1_PREFIX"]
    return jsonify(
        {
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
    ), 200


@reports_v1_bp.get("/<report_id>")
def get_report(report_id: str):
    report = Report.query.filter_by(task_id=report_id).first()
    if not report:
        return _json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)
    return jsonify(report.to_dict_v1(current_app.config["API_V1_PREFIX"])), 200


def _sync_report_from_celery_state(report: Report, ar: AsyncResult) -> None:
    """
    If Celery says FAILURE/REVOKED but DB still shows QUEUED/PROCESSING,
    update MySQL so the UI matches reality (worker crash, Windows pool bug, etc.).
    """
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
            logger.warning(
                "report_status_synced_from_celery report_id=%s celery=FAILURE",
                report.task_id,
            )
    elif celery_state == "REVOKED" and report.status in (
        Report.Status.QUEUED.value,
        Report.Status.PROCESSING.value,
        Report.Status.CANCEL_REQUESTED.value,
    ):
        report.status = Report.Status.CANCELED.value
        report.completed_at = datetime.utcnow()
        db.session.commit()


@reports_v1_bp.get("/<report_id>/status")
def get_report_status(report_id: str):
    report = Report.query.filter_by(task_id=report_id).first()
    if not report:
        return _json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

    # Enrich with Celery status if broker/backend is available
    try:
        ar = AsyncResult(report_id, app=celery)
        _sync_report_from_celery_state(report, ar)
        db.session.refresh(report)
    except Exception:
        ar = None

    payload = report.to_status_v1(current_app.config["API_V1_PREFIX"])
    if ar:
        try:
            payload["celery"] = {"state": ar.state}
            if ar.state == "FAILURE" and ar.result:
                payload["celery"]["error"] = str(ar.result)[:500]
        except Exception:
            payload["celery"] = {"state": "UNKNOWN"}
    else:
        payload["celery"] = {"state": "UNKNOWN"}

    return jsonify(payload), 200


@reports_v1_bp.get("/<report_id>/download")
def download_report(report_id: str):
    """
    Stream the generated CSV file.

    Legacy reports may have a URL stored in file_path; we resolve the real
    filesystem path via Report.resolve_csv_path().
    """
    report = Report.query.filter_by(task_id=report_id).first()
    if not report:
        return _json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

    if report.status != Report.Status.COMPLETED.value:
        return _json_error(
            "REPORT_NOT_READY",
            f"Report not ready. Current status: {report.status}",
            400,
        )

    csv_path = report.resolve_csv_path()
    if not csv_path:
        logger.warning(
            "download_missing_file",
            extra={
                "report_id": report_id,
                "stored_path": report.file_path,
                "expected": report.build_file_path(),
            },
        )
        return _json_error(
            "FILE_NOT_FOUND",
            "CSV file is not on disk. The export may have been created before file "
            "storage was enabled, or the file was removed. Create a new export to "
            "generate a fresh download.",
            404,
            details={
                "expected_path": report.build_file_path(),
                "legacy_path": report.file_path,
            },
        )

    # Backfill DB when we recovered from canonical path (fixes legacy URL rows)
    if report.file_path != csv_path:
        report.file_path = csv_path
        db.session.commit()

    return send_file(
        csv_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"report_{report_id}.csv",
        conditional=True,
    )


@reports_v1_bp.post("/<report_id>/cancel")
def cancel_report(report_id: str):
    report = Report.query.filter_by(task_id=report_id).first()
    if not report:
        return _json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

    if report.status in (
        Report.Status.COMPLETED.value,
        Report.Status.FAILED.value,
        Report.Status.CANCELED.value,
    ):
        return _json_error(
            "INVALID_STATE",
            f"Cannot cancel report in state {report.status}",
            400,
        )

    report.status = Report.Status.CANCEL_REQUESTED.value
    report.cancel_requested_at = datetime.utcnow()
    db.session.commit()

    # Best-effort revoke (cooperative cancel is enforced in the task loop)
    try:
        celery.control.revoke(report_id, terminate=False)
    except Exception:
        pass

    return jsonify({"report_id": report_id, "status": report.status}), 200


@reports_v1_bp.post("/<report_id>/retry")
def retry_report(report_id: str):
    report = Report.query.filter_by(task_id=report_id).first()
    if not report:
        return _json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

    if report.status != Report.Status.FAILED.value:
        return _json_error("INVALID_STATE", "Only FAILED reports can be retried", 400)

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

    return jsonify({"report_id": report_id, "status": report.status}), 202


@reports_v1_bp.delete("/<report_id>")
def delete_report(report_id: str):
    report = Report.query.filter_by(task_id=report_id).first()
    if not report:
        return _json_error("REPORT_NOT_FOUND", f"Report {report_id} not found", 404)

    report.delete_files_best_effort()
    db.session.delete(report)
    db.session.commit()
    return jsonify({"message": f"Report {report_id} deleted"}), 200


@reports_v1_bp.get("/")
def list_reports():
    """
    List reports with pagination + filtering.
    Query params:
      - user_id: int (optional)
      - status: string (optional)
      - q: string search on task_id (optional)
      - page: int (default 1)
      - page_size: int (default 20, max 100)
      - sort: created_at|started_at|completed_at (default created_at)
      - order: asc|desc (default desc)
    """
    user_id = request.args.get("user_id", type=int)
    status = request.args.get("status", type=str)
    q = request.args.get("q", type=str)
    page = request.args.get("page", default=1, type=int)
    page_size = min(request.args.get("page_size", default=20, type=int), 100)
    sort = request.args.get("sort", default="created_at", type=str)
    order = request.args.get("order", default="desc", type=str)

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

    return jsonify(
        {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [r.to_dict_v1(current_app.config["API_V1_PREFIX"]) for r in items],
        }
    ), 200

