"""Jinja dashboard page routes."""
from flask import Blueprint, render_template

web_bp = Blueprint(
    "web",
    __name__,
    template_folder="../templates",
    static_folder="../static",
)


@web_bp.route("/")
def dashboard():
    """Overview dashboard home page."""
    return render_template("dashboard/index.html", active_page="dashboard", page_title="Overview")


@web_bp.route("/reports/new")
def create_report():
    """Enqueue new export job page."""
    return render_template("reports/create.html", active_page="create", page_title="Enqueue")


@web_bp.route("/reports")
def report_history():
    """Paginated jobs history page."""
    return render_template("reports/history.html", active_page="history", page_title="Jobs")


@web_bp.route("/reports/<report_id>")
def report_detail(report_id: str):
    """Single job detail and actions page."""
    return render_template(
        "reports/detail.html",
        active_page="history",
        page_title="Report Detail",
        report_id=report_id,
    )


@web_bp.route("/downloads")
def download_center():
    """Completed exports download center."""
    return render_template("downloads/index.html", active_page="downloads", page_title="Files")


@web_bp.route("/ops")
def ops_dashboard():
    """Workers, queues, and failed jobs page."""
    return render_template("ops/index.html", active_page="ops", page_title="Infrastructure")
