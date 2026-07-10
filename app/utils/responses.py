"""JSON error helpers for API controllers."""
from __future__ import annotations

import logging
from typing import Any

from flask import jsonify

logger = logging.getLogger(__name__)


def json_error(code: str, message: str, status: int, *, details: Any = None):
    """Return consistent JSON error payload."""
    payload = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status


def log_endpoint_error(endpoint: str, exc: Exception) -> None:
    """Log endpoint failure without leaking internals."""
    logger.exception("API endpoint failed: %s", endpoint, exc_info=exc)
