import os
import logging
from pythonjsonlogger import jsonlogger
from flask import Flask, jsonify, render_template, request
from flasgger import Swagger

from app.celery_app import make_celery
from app.extensions import db, migrate, limiter

swagger = Swagger()

# Celery instance is created in create_app and re-exported for imports
celery = None


def _select_config_object() -> str:
    """
    Select config class by env. Defaults to DevelopmentConfig.
    """
    env = (os.environ.get("FLASK_ENV") or os.environ.get("ENV") or "development").lower()
    if env in ("prod", "production"):
        return "app.config.ProductionConfig"
    if env in ("test", "testing"):
        return "app.config.TestingConfig"
    return "app.config.DevelopmentConfig"


def create_app(config_override=None):
    """
    Application factory.

    Tests should set FLASK_ENV=testing before calling create_app() so
    TestingConfig (in-memory SQLite, Celery eager) is used — never the dev MySQL DB.
    """
    global celery

    app = Flask(__name__)
    app.config.from_object(_select_config_object())
    if config_override:
        app.config.update(config_override)

    # Logging (structured JSON by default)
    _configure_logging(app)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    swagger.init_app(app)

    # Rate limiting can be enabled via config flag
    limiter.enabled = bool(app.config.get("RATELIMIT_ENABLED", False))
    limiter.init_app(app)

    # Central error shape (JSON for API, HTML for UI)
    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "NOT_FOUND", "message": "Resource not found"}}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(405)
    def method_not_allowed(_e):
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "METHOD_NOT_ALLOWED", "message": "Method not allowed"}}), 405
        return render_template("errors/404.html"), 405

    @app.errorhandler(500)
    def internal_error(_e):
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}}), 500
        return render_template("errors/500.html"), 500

    # Celery (single source of truth)
    celery = make_celery(app)

    # Blueprints — controllers group related endpoints
    from app.controllers.reports_controller import reports_v1_bp
    from app.controllers.ops_controller import ops_v1_bp
    from app.controllers.legacy_controller import legacy_reports_bp
    from app.controllers.web_controller import web_bp

    app.register_blueprint(reports_v1_bp, url_prefix=f"{app.config['API_V1_PREFIX']}/reports")
    app.register_blueprint(ops_v1_bp, url_prefix=f"{app.config['API_V1_PREFIX']}/ops")
    app.register_blueprint(legacy_reports_bp)
    app.register_blueprint(web_bp)

    return app


def _configure_logging(app: Flask) -> None:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers in reload scenarios
    if root.handlers:
        return

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
