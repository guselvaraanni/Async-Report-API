"""
Operational monitoring API — worker health, queue depth, failed jobs.

These endpoints power the "Queue & Workers" dashboard page.
They read from two sources:
  1. Celery inspect API (live worker/queue state via Redis/Memurai)
  2. MySQL reports table (historical job counts and failed job list)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request

from app import celery
from app.extensions import db
from app.models.report import Report
from app.api.v1.helpers import json_error, log_endpoint_error, parse_pagination


ops_v1_bp = Blueprint("ops_v1", __name__)


def _safe_inspect():
    """
    Ask Celery which workers are alive. Returns None if Redis/worker is unreachable.
    Uses a short timeout so dashboard requests do not hang.
    """
    try:
        return celery.control.inspect(timeout=1.0)
    except Exception:
        return None


@ops_v1_bp.get("/health")
def ops_health():
    """Lightweight ops health: can we talk to Celery workers?"""
    insp = _safe_inspect()
    if not insp:
        return jsonify({"status": "degraded", "celery": {"inspect": "unavailable"}}), 200

    try:
        ping = insp.ping() or {}
    except Exception:
        ping = {}

    return jsonify({"status": "ok", "celery": {"ping": ping}}), 200


@ops_v1_bp.get("/workers")
def workers():
    insp = _safe_inspect()
    if not insp:
        return json_error("CELERY_UNAVAILABLE", "Celery inspect unavailable", 503)

    try:
        stats = insp.stats() or {}
        active = insp.active() or {}
        reserved = insp.reserved() or {}
        scheduled = insp.scheduled() or {}
    except Exception as exc:
        log_endpoint_error("GET /ops/workers", exc)
        return json_error(
            "CELERY_INSPECT_FAILED",
            "Could not inspect Celery workers",
            503,
        )

    return jsonify(
        {
            "workers": sorted(list(stats.keys())),
            "stats": stats,
            "active": active,
            "reserved": reserved,
            "scheduled": scheduled,
        }
    ), 200


@ops_v1_bp.get("/queues")
def queues():
    insp = _safe_inspect()
    if not insp:
        return json_error("CELERY_UNAVAILABLE", "Celery inspect unavailable", 503)

    try:
        active_queues = insp.active_queues() or {}
    except Exception as exc:
        log_endpoint_error("GET /ops/queues", exc)
        return json_error(
            "CELERY_INSPECT_FAILED",
            "Could not inspect Celery queues",
            503,
        )

    return jsonify({"active_queues": active_queues}), 200


@ops_v1_bp.get("/metrics")
def ops_metrics():
    """
    Combined dashboard metrics: live Celery stats + report counts from DB.

    Response shape:
      celery.workers_online  — how many Celery worker processes responded
      celery.active_tasks    — jobs currently executing on workers
      celery.reserved_tasks  — jobs prefetched by workers but not started yet
      celery.queue_depth_estimate — rough backlog (active + reserved + QUEUED in DB)
      reports.by_status      — count of reports in each lifecycle state
    """
    try:
        insp = _safe_inspect()
        worker_count = 0
        active_tasks = 0
        reserved_tasks = 0
        celery_status = "degraded"
        workers_list = []

        if insp:
            try:
                ping = insp.ping() or {}
                stats = insp.stats() or {}
                active = insp.active() or {}
                reserved = insp.reserved() or {}
                workers_list = sorted(list(stats.keys()))
                worker_count = len(workers_list)
                active_tasks = sum(len(v or []) for v in active.values())
                reserved_tasks = sum(len(v or []) for v in reserved.values())
                celery_status = "ok" if ping else "degraded"
            except Exception:
                celery_status = "degraded"

        total = Report.query.count()
        by_status = {
            s.value: Report.query.filter_by(status=s.value).count()
            for s in Report.Status
        }

        return jsonify(
            {
                "celery": {
                    "status": celery_status,
                    "workers_online": worker_count,
                    "workers": workers_list,
                    "active_tasks": active_tasks,
                    "reserved_tasks": reserved_tasks,
                    "queue_depth_estimate": active_tasks
                    + reserved_tasks
                    + by_status.get(Report.Status.QUEUED.value, 0),
                },
                "reports": {
                    "total": total,
                    "by_status": by_status,
                },
            }
        ), 200
    except Exception as exc:
        log_endpoint_error("GET /ops/metrics", exc)
        return json_error(
            "METRICS_UNAVAILABLE",
            "Could not load operational metrics",
            500,
        )


@ops_v1_bp.get("/failed")
def failed_jobs():
    """
    Paginated list of reports with status=FAILED for the ops UI.

    Query params: page (default 1), page_size (default 20, max 100)
    """
    page, page_size, err = parse_pagination(
        request.args.get("page"),
        request.args.get("page_size"),
    )
    if err:
        return err

    try:
        q = (
            Report.query.filter_by(status=Report.Status.FAILED.value)
            .order_by(Report.completed_at.desc())
        )
        total = q.count()
        items = q.offset((page - 1) * page_size).limit(page_size).all()
        prefix = current_app.config["API_V1_PREFIX"]

        return jsonify(
            {
                "page": page,
                "page_size": page_size,
                "total": total,
                "items": [r.to_dict_v1(prefix) for r in items],
            }
        ), 200
    except Exception as exc:
        log_endpoint_error("GET /ops/failed", exc)
        return json_error(
            "FAILED_JOBS_UNAVAILABLE",
            "Could not load failed jobs list",
            500,
        )


@ops_v1_bp.post("/cleanup")
def cleanup_reports():
    """
    Cleanup old report artifacts (best-effort).
    Query params:
      - days: int (default 7)  delete COMPLETED/FAILED/CANCELED older than N days
      - dry_run: bool (default true)  when true, no deletion performed
    """
    try:
        days = int((request.args.get("days") or 7))
    except Exception:
        days = 7
    dry_run = (request.args.get("dry_run") or "true").lower() == "true"

    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = Report.query.filter(
            Report.completed_at.isnot(None),
            Report.completed_at < cutoff,
            Report.status.in_(
                [
                    Report.Status.COMPLETED.value,
                    Report.Status.FAILED.value,
                    Report.Status.CANCELED.value,
                ]
            ),
        )

        candidates = q.all()
        deleted = 0

        if not dry_run:
            for r in candidates:
                r.delete_files_best_effort()
                db.session.delete(r)
                deleted += 1
            db.session.commit()

        return (
            jsonify(
                {
                    "dry_run": dry_run,
                    "cutoff": cutoff.isoformat(),
                    "candidates": len(candidates),
                    "deleted": deleted,
                }
            ),
            200,
        )
    except Exception as exc:
        log_endpoint_error("POST /ops/cleanup", exc)
        return json_error(
            "CLEANUP_FAILED",
            "Report cleanup could not be completed",
            500,
        )
