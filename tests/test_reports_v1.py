import os
import time

from app.extensions import db
from app.models.report import Report


def test_create_report_job_202(client):
    res = client.post("/api/v1/reports/", json={"user_id": 1, "rows": 50})
    assert res.status_code == 202
    data = res.get_json()
    assert data["task_id"]
    assert data["report_id"] == data["task_id"]


def test_report_lifecycle_completes_and_downloads(client, app, tmp_path):
    # Use temp report folder for this test run
    os.environ["REPORTS_FOLDER"] = str(tmp_path)

    res = client.post("/api/v1/reports/", json={"user_id": 1, "rows": 20})
    report_id = res.get_json()["report_id"]

    # Celery runs eager in testing config; task should complete quickly.
    status_res = client.get(f"/api/v1/reports/{report_id}/status")
    assert status_res.status_code == 200
    status = status_res.get_json()
    assert status["status"] in (
        Report.Status.COMPLETED.value,
        Report.Status.FAILED.value,
    )

    if status["status"] == Report.Status.FAILED.value:
        raise AssertionError(f"task failed: {status.get('error_message')}")

    dl = client.get(f"/api/v1/reports/{report_id}/download")
    assert dl.status_code == 200
    assert dl.headers["Content-Type"].startswith("text/csv")
    assert b"id,user_id,amount,currency,status,created_at" in dl.data.splitlines()[0]


def test_cancel_before_processing_marks_canceled(client, app):
    # Create a report row manually in QUEUED then cancel it
    with app.app_context():
        report = Report(user_id=1, task_id="r-cancel-1", status=Report.Status.QUEUED.value, requested_rows=10)
        db.session.add(report)
        db.session.commit()

    cancel_res = client.post("/api/v1/reports/r-cancel-1/cancel")
    assert cancel_res.status_code == 200

    status_res = client.get("/api/v1/reports/r-cancel-1/status")
    status = status_res.get_json()
    assert status["status"] in (Report.Status.CANCEL_REQUESTED.value, Report.Status.CANCELED.value)


def test_retry_only_failed(client, app):
    with app.app_context():
        report = Report(user_id=1, task_id="r-fail-1", status=Report.Status.FAILED.value, requested_rows=10)
        report.error_message = "boom"
        db.session.add(report)
        db.session.commit()

    res = client.post("/api/v1/reports/r-fail-1/retry")
    assert res.status_code in (202, 200)


def test_list_pagination(client):
    # create a few reports
    for _ in range(5):
        client.post("/api/v1/reports/", json={"user_id": 1, "rows": 5})

    res = client.get("/api/v1/reports/?page=1&page_size=2&user_id=1")
    assert res.status_code == 200
    data = res.get_json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2


def test_validation_rows_must_be_int(client):
    res = client.post("/api/v1/reports/", json={"user_id": 1, "rows": "abc"})
    assert res.status_code == 400
    data = res.get_json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_report_not_found(client):
    res = client.get("/api/v1/reports/does-not-exist/status")
    assert res.status_code == 404

