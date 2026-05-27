"""Shared helpers for v1 API blueprints (errors, pagination, logging)."""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from flask import jsonify

logger = logging.getLogger(__name__)


def json_error(
    code: str,
    message: str,
    status: int,
    *,
    details: Any = None,
):
    """Return a consistent JSON error body understood by the frontend."""
    payload = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status


def parse_pagination(
    page_raw,
    page_size_raw,
    *,
    default_page: int = 1,
    default_page_size: int = 20,
    max_page_size: int = 100,
) -> Tuple[int, int, Optional[tuple]]:
    """
    Validate page + page_size query params.

    Returns (page, page_size, error_response).
    error_response is None when validation succeeds.
    """
    try:
        page = int(page_raw if page_raw is not None else default_page)
    except (TypeError, ValueError):
        return (
            default_page,
            default_page_size,
            json_error("VALIDATION_ERROR", "`page` must be a positive integer", 400),
        )

    try:
        page_size = int(page_size_raw if page_size_raw is not None else default_page_size)
    except (TypeError, ValueError):
        return (
            default_page,
            default_page_size,
            json_error("VALIDATION_ERROR", "`page_size` must be a positive integer", 400),
        )

    if page < 1:
        return (
            page,
            page_size,
            json_error("VALIDATION_ERROR", "`page` must be >= 1", 400),
        )

    if page_size < 1:
        return (
            page,
            page_size,
            json_error("VALIDATION_ERROR", "`page_size` must be >= 1", 400),
        )

    page_size = min(page_size, max_page_size)
    return page, page_size, None


def log_endpoint_error(endpoint: str, exc: Exception) -> None:
    """Structured log line for ops/debugging without leaking internals to clients."""
    logger.exception("API endpoint failed: %s", endpoint, exc_info=exc)
