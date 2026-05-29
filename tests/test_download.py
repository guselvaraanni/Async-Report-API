"""Download endpoint and filesystem resolution tests."""
import os

from app.extensions import db
from app.models.report import Report


def test_download_completed_report_csv(client, app, tmp_path):
    os.environ["REPORTS_FOLDER"] = str(tmp_path)
    report_id = "dl-test-001"
    csv_path = tmp_path / f"report_{report_id}.csv"
    csv_path.write_text("id,user_id\n1,1\n", encoding="utf-8")

    with app.app_context():
        r = Report(
            user_id=1,
            task_id=report_id,
            status=Report.Status.COMPLETED.value,
            requested_rows=1,
            rows_processed=1,
            file_path=str(csv_path),
        )
        db.session.add(r)
        db.session.commit()

    res = client.get(f"/api/v1/reports/{report_id}/download")
    assert res.status_code == 200
    assert res.headers["Content-Type"].startswith("text/csv")
    assert b"id,user_id" in res.data


def test_download_legacy_url_path_resolves_canonical_file(client, app, tmp_path):
    os.environ["REPORTS_FOLDER"] = str(tmp_path)
    report_id = "dl-legacy-002"
    csv_path = tmp_path / f"report_{report_id}.csv"
    csv_path.write_text("ok\n", encoding="utf-8")

    with app.app_context():
        r = Report(
            user_id=1,
            task_id=report_id,
            status=Report.Status.COMPLETED.value,
            requested_rows=1,
            file_path=f"/reports/download/{report_id}",
        )
        db.session.add(r)
        db.session.commit()

    res = client.get(f"/api/v1/reports/{report_id}/download")
    assert res.status_code == 200
    assert res.data.strip() == b"ok"


def test_download_missing_file_returns_json_error(client, app):
    report_id = "dl-missing-003"
    with app.app_context():
        r = Report(
            user_id=1,
            task_id=report_id,
            status=Report.Status.COMPLETED.value,
            requested_rows=10,
            file_path="/reports/download/" + report_id,
        )
        db.session.add(r)
        db.session.commit()

    res = client.get(f"/api/v1/reports/{report_id}/download")
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"]["code"] == "FILE_NOT_FOUND"
