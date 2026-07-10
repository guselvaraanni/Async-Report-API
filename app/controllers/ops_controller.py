"""HTTP controllers for ops and infrastructure API."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.ops_service import OpsService
from app.utils.responses import json_error, log_endpoint_error
from app.utils.validation import parse_pagination

ops_v1_bp = Blueprint("ops_v1", __name__)


@ops_v1_bp.get("/health")
def ops_health():
    """Check Celery worker connectivity."""
    return jsonify(OpsService.health()), 200


@ops_v1_bp.get("/workers")
def workers():
    """List live Celery workers."""
    payload, err = OpsService.workers()
    if err:
        return err
    return jsonify(payload), 200


@ops_v1_bp.get("/queues")
def queues():
    """Show active Celery queue topology."""
    payload, err = OpsService.queues()
    if err:
        return err
    return jsonify(payload), 200


@ops_v1_bp.get("/metrics")
def ops_metrics():
    """Combined worker and report metrics."""
    try:
        return jsonify(OpsService.metrics()), 200
    except Exception as exc:
        log_endpoint_error("GET /ops/metrics", exc)
        return json_error("METRICS_UNAVAILABLE", "Could not load operational metrics", 500)


@ops_v1_bp.get("/failed")
def failed_jobs():
    """Paginated list of failed reports."""
    page, page_size, err = parse_pagination(
        request.args.get("page"),
        request.args.get("page_size"),
    )
    if err:
        return err
    try:
        return jsonify(OpsService.failed_jobs(page, page_size)), 200
    except Exception as exc:
        log_endpoint_error("GET /ops/failed", exc)
        return json_error("FAILED_JOBS_UNAVAILABLE", "Could not load failed jobs list", 500)


@ops_v1_bp.post("/cleanup")
def cleanup_reports():
    """Delete old terminal reports (dry-run default)."""
    try:
        days = int(request.args.get("days") or 7)
    except (TypeError, ValueError):
        days = 7
    dry_run = (request.args.get("dry_run") or "true").lower() == "true"
    try:
        return jsonify(OpsService.cleanup(days, dry_run)), 200
    except Exception as exc:
        log_endpoint_error("POST /ops/cleanup", exc)
        return json_error("CLEANUP_FAILED", "Report cleanup could not be completed", 500)
