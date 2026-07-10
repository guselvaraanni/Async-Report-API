"""Request body and query param validation."""
from __future__ import annotations

from typing import Any, Optional, Tuple

from app.utils.responses import json_error


def validate_create_report_payload(data: dict, max_rows: int) -> Tuple[Optional[int], Optional[int], Optional[tuple]]:
    """Validate user_id and rows for new export."""
    user_id = data.get("user_id", 1)
    requested_rows = data.get("rows", 50000)

    try:
        requested_rows = int(requested_rows)
    except (TypeError, ValueError):
        return None, None, json_error("VALIDATION_ERROR", "`rows` must be an integer", 400)

    if requested_rows <= 0:
        return None, None, json_error("VALIDATION_ERROR", "`rows` must be > 0", 400)

    if requested_rows > max_rows:
        return None, None, json_error("VALIDATION_ERROR", f"`rows` must be <= {max_rows}", 400)

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None, None, json_error("VALIDATION_ERROR", "`user_id` must be an integer", 400)

    return user_id, requested_rows, None


def parse_pagination(
    page_raw,
    page_size_raw,
    *,
    default_page: int = 1,
    default_page_size: int = 20,
    max_page_size: int = 100,
) -> Tuple[int, int, Optional[tuple]]:
    """Validate page and page_size query params."""
    try:
        page = int(page_raw if page_raw is not None else default_page)
    except (TypeError, ValueError):
        return default_page, default_page_size, json_error(
            "VALIDATION_ERROR", "`page` must be a positive integer", 400
        )

    try:
        page_size = int(page_size_raw if page_size_raw is not None else default_page_size)
    except (TypeError, ValueError):
        return default_page, default_page_size, json_error(
            "VALIDATION_ERROR", "`page_size` must be a positive integer", 400
        )

    if page < 1:
        return page, page_size, json_error("VALIDATION_ERROR", "`page` must be >= 1", 400)

    if page_size < 1:
        return page, page_size, json_error("VALIDATION_ERROR", "`page_size` must be >= 1", 400)

    return page, min(page_size, max_page_size), None
