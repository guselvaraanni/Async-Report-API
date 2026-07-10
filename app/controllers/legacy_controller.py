"""Legacy /reports/* routes forwarding to v1 controllers."""
from __future__ import annotations

import json

from flask import Blueprint, current_app, request

from app.controllers.reports_controller import (
    cancel_report as v1_cancel,
    create_report_job as v1_create,
    delete_report as v1_delete,
    download_report as v1_download,
    get_report_status as v1_status,
    health as v1_health,
    list_reports as v1_list,
)

legacy_reports_bp = Blueprint("legacy_reports", __name__, url_prefix="/reports")


@legacy_reports_bp.get("/health")
def health():
    """Legacy health shim."""
    return v1_health()


@legacy_reports_bp.post("/generate")
def generate():
    """Legacy create export shim."""
    return v1_create()


@legacy_reports_bp.get("/status/<task_id>")
def status(task_id: str):
    """Legacy status poll shim."""
    return v1_status(task_id)


@legacy_reports_bp.get("/download/<task_id>")
def download(task_id: str):
    """Legacy download shim."""
    return v1_download(task_id)


@legacy_reports_bp.get("/list")
def list_legacy():
    """Legacy list with optional user_id wrapper."""
    user_id = request.args.get("user_id", type=int)
    resp, status = v1_list()
    if status != 200:
        return resp, status

    data = resp.get_json() or {}
    items = data.get("items", [])
    if user_id is None:
        return resp, status

    return (
        current_app.response_class(
            response=json.dumps({"user_id": user_id, "count": len(items), "reports": items}),
            status=200,
            mimetype="application/json",
        ),
        200,
    )


@legacy_reports_bp.delete("/delete/<task_id>")
def delete(task_id: str):
    """Legacy delete shim."""
    return v1_delete(task_id)


@legacy_reports_bp.post("/cancel/<task_id>")
def cancel(task_id: str):
    """Legacy cancel shim."""
    return v1_cancel(task_id)
