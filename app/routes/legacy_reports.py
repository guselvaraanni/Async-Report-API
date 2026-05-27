from __future__ import annotations

import json

from flask import Blueprint, current_app, request

from app.api.v1.reports import (
    health as v1_health,
    create_report_job as v1_create,
    get_report_status as v1_status,
    download_report as v1_download,
    list_reports as v1_list,
    delete_report as v1_delete,
    cancel_report as v1_cancel,
)


legacy_reports_bp = Blueprint("legacy_reports", __name__, url_prefix="/reports")


@legacy_reports_bp.get("/health")
def health():
    return v1_health()


@legacy_reports_bp.post("/generate")
def generate():
    # Legacy payload stays the same; v1 handler also accepts defaults.
    return v1_create()


@legacy_reports_bp.get("/status/<task_id>")
def status(task_id: str):
    return v1_status(task_id)


@legacy_reports_bp.get("/download/<task_id>")
def download(task_id: str):
    return v1_download(task_id)


@legacy_reports_bp.get("/list")
def list_legacy():
    # Legacy response shape differs; keep it for compatibility.
    # Convert v1 list into legacy {user_id, count, reports:[...]} when user_id is provided,
    # otherwise return a v1-compatible list.
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
    return v1_delete(task_id)


@legacy_reports_bp.post("/cancel/<task_id>")
def cancel(task_id: str):
    return v1_cancel(task_id)

