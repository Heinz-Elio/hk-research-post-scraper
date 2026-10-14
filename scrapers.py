"""Backward-compatible re-export. New sources live under sources/."""

from sources import SCRAPERS, SOURCE_NAMES
from sources.base import (
    HAS_PLAYWRIGHT,
    HEADERS,
    PLAYWRIGHT_TIMEOUT,
    REQUEST_DELAY,
    fetch,
    is_research_related,
    make_id,
    parse_date,
    safe_text,
)

__all__ = [
    "SCRAPERS",
    "SOURCE_NAMES",
    "HAS_PLAYWRIGHT",
    "HEADERS",
    "PLAYWRIGHT_TIMEOUT",
    "REQUEST_DELAY",
    "fetch",
    "is_research_related",
    "make_id",
    "parse_date",
    "safe_text",
]
