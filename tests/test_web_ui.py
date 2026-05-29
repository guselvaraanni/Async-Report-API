"""Web UI route and ops API smoke tests."""
from app.models.report import Report


def test_dashboard_page_loads(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Export Queue" in res.data
    assert b"Overview" in res.data


def test_all_ui_pages_load(client):
    pages = [
        "/",
        "/reports/new",
        "/reports",
        "/downloads",
        "/ops",
    ]
    for path in pages:
        res = client.get(path)
        assert res.status_code == 200, f"{path} returned {res.status_code}"


def test_report_detail_page_loads(client):
    res = client.get("/reports/test-report-id-123")
    assert res.status_code == 200
    assert b"test-report-id-123" in res.data


def test_static_css_served(client):
    res = client.get("/static/css/app.css")
    assert res.status_code == 200
    assert b"Export Queue" in res.data or b"--accent" in res.data


def test_reports_stats_api(client):
    res = client.get("/api/v1/reports/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert "total" in data
    assert "by_status" in data
    assert "recent" in data


def test_ops_metrics_api(client):
    res = client.get("/api/v1/ops/metrics")
    assert res.status_code == 200
    data = res.get_json()
    assert "celery" in data
    assert "reports" in data


def test_ops_failed_jobs_api(client, app):
    """Regression: /ops/failed must not 500 (was missing current_app import)."""
    with app.app_context():
        from datetime import datetime
        from app.extensions import db

        r = Report(
            user_id=1,
            task_id="failed-test-1",
            status=Report.Status.FAILED.value,
            requested_rows=10,
            error_message="simulated failure",
            completed_at=datetime.utcnow(),
        )
        db.session.add(r)
        db.session.commit()

    res = client.get("/api/v1/ops/failed?page=1&page_size=20")
    assert res.status_code == 200
    data = res.get_json()
    assert "items" in data
    assert data["total"] >= 1
    assert any(i["report_id"] == "failed-test-1" for i in data["items"])


def test_ops_failed_invalid_page(client):
    res = client.get("/api/v1/ops/failed?page=0")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "VALIDATION_ERROR"
