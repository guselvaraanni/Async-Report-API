"""Operational monitoring: workers, queues, metrics, cleanup."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from flask import current_app

from app import celery
from app.extensions import db
from app.models.report import Report
from app.utils.responses import json_error


class OpsService:
    """Celery inspect and report maintenance logic."""

    @staticmethod
    def safe_inspect():
        """Return Celery inspect handle or None."""
        try:
            return celery.control.inspect(timeout=1.0)
        except Exception:
            return None

    @staticmethod
    def health() -> dict:
        """Lightweight ops health check."""
        insp = OpsService.safe_inspect()
        if not insp:
            return {"status": "degraded", "celery": {"inspect": "unavailable"}}
        try:
            ping = insp.ping() or {}
        except Exception:
            ping = {}
        return {"status": "ok", "celery": {"ping": ping}}

    @staticmethod
    def workers() -> tuple[Optional[dict], Optional[tuple]]:
        """Live worker stats from Celery inspect."""
        insp = OpsService.safe_inspect()
        if not insp:
            return None, json_error("CELERY_UNAVAILABLE", "Celery inspect unavailable", 503)
        try:
            stats = insp.stats() or {}
            active = insp.active() or {}
            reserved = insp.reserved() or {}
            scheduled = insp.scheduled() or {}
        except Exception:
            return None, json_error("CELERY_INSPECT_FAILED", "Could not inspect Celery workers", 503)

        return {
            "workers": sorted(list(stats.keys())),
            "stats": stats,
            "active": active,
            "reserved": reserved,
            "scheduled": scheduled,
        }, None

    @staticmethod
    def queues() -> tuple[Optional[dict], Optional[tuple]]:
        """Active queue topology from Celery inspect."""
        insp = OpsService.safe_inspect()
        if not insp:
            return None, json_error("CELERY_UNAVAILABLE", "Celery inspect unavailable", 503)
        try:
            active_queues = insp.active_queues() or {}
        except Exception:
            return None, json_error("CELERY_INSPECT_FAILED", "Could not inspect Celery queues", 503)
        return {"active_queues": active_queues}, None

    @staticmethod
    def metrics() -> dict:
        """Combined Celery live stats and DB report counts."""
        insp = OpsService.safe_inspect()
        worker_count = 0
        active_tasks = 0
        reserved_tasks = 0
        celery_status = "degraded"
        workers_list: list[str] = []

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
        by_status = {s.value: Report.query.filter_by(status=s.value).count() for s in Report.Status}

        return {
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
            "reports": {"total": total, "by_status": by_status},
        }

    @staticmethod
    def failed_jobs(page: int, page_size: int) -> dict:
        """Paginated FAILED reports for ops UI."""
        q = (
            Report.query.filter_by(status=Report.Status.FAILED.value)
            .order_by(Report.completed_at.desc())
        )
        total = q.count()
        items = q.offset((page - 1) * page_size).limit(page_size).all()
        prefix = current_app.config["API_V1_PREFIX"]
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [r.to_dict_v1(prefix) for r in items],
        }

    @staticmethod
    def cleanup(days: int, dry_run: bool) -> dict:
        """Delete old terminal reports and CSV files."""
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
            for report in candidates:
                report.delete_files_best_effort()
                db.session.delete(report)
                deleted += 1
            db.session.commit()

        return {
            "dry_run": dry_run,
            "cutoff": cutoff.isoformat(),
            "candidates": len(candidates),
            "deleted": deleted,
        }
