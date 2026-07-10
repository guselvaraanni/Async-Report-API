"""HTTP controllers for report export API."""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, request, send_file

from app.extensions import limiter
from app.services.report_service import ReportService
from app.utils.validation import parse_pagination, validate_create_report_payload

reports_v1_bp = Blueprint("reports_v1", __name__)
logger = logging.getLogger(__name__)


@reports_v1_bp.get("/health")
def health():
    """Liveness probe for report API."""
    return jsonify({"status": "healthy"}), 200


@reports_v1_bp.post("/")
@limiter.limit(lambda: current_app.config.get("RATELIMIT_DEFAULT") or None)
def create_report_job():
    """Enqueue async CSV export; returns 202."""
    data = request.get_json(silent=True) or {}
    max_rows = int(current_app.config.get("MAX_ROWS_PER_REPORT", 1_000_000))
    user_id, requested_rows, err = validate_create_report_payload(data, max_rows)
    if err:
        return err

    payload, svc_err, status = ReportService.create_job(user_id, requested_rows)
    if svc_err:
        return svc_err
    return jsonify(payload), status


@reports_v1_bp.get("/stats")
def report_stats():
    """Dashboard aggregate counts."""
    return jsonify(ReportService.stats()), 200


@reports_v1_bp.get("/<report_id>")
def get_report(report_id: str):
    """Fetch one report by public id."""
    payload, err = ReportService.get_report(report_id)
    if err:
        return err
    return jsonify(payload), 200


@reports_v1_bp.get("/<report_id>/status")
def get_report_status(report_id: str):
    """Poll job status and Celery state."""
    payload, err = ReportService.get_status(report_id)
    if err:
        return err
    return jsonify(payload), 200


@reports_v1_bp.get("/<report_id>/download")
def download_report(report_id: str):
    """Stream completed CSV attachment."""
    csv_path, err = ReportService.resolve_download(report_id)
    if err:
        return err
    return send_file(
        csv_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"report_{report_id}.csv",
        conditional=True,
    )


@reports_v1_bp.post("/<report_id>/cancel")
def cancel_report(report_id: str):
    """Request cooperative cancel."""
    payload, err = ReportService.cancel(report_id)
    if err:
        return err
    return jsonify(payload), 200


@reports_v1_bp.post("/<report_id>/retry")
def retry_report(report_id: str):
    """Re-queue a failed export job."""
    payload, status, err = ReportService.retry(report_id)
    if err:
        return err
    return jsonify(payload), status


@reports_v1_bp.delete("/<report_id>")
def delete_report(report_id: str):
    """Delete report row and CSV file."""
    payload, err = ReportService.delete(report_id)
    if err:
        return err
    return jsonify(payload), 200


@reports_v1_bp.get("/")
def list_reports():
    """Paginated report list with filters."""
    page, page_size, err = parse_pagination(
        request.args.get("page"),
        request.args.get("page_size"),
    )
    if err:
        return err

    payload = ReportService.list_reports(
        {
            "user_id": request.args.get("user_id", type=int),
            "status": request.args.get("status", type=str),
            "q": request.args.get("q", type=str),
            "page": page,
            "page_size": page_size,
            "sort": request.args.get("sort", default="created_at", type=str),
            "order": request.args.get("order", default="desc", type=str),
        }
    )
    return jsonify(payload), 200
