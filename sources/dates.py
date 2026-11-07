"""Listing and advertisement dates.

``date_type`` is one of:

- ``deadline`` — a hard closing date
- ``review_start`` — consideration or screening begins on this date and the
  post stays open (PolyU's "Closing / Initial Screening Date" column)
- ``open_until_filled`` — the advertisement says the search stays open
- ``unspecified`` — no date was published

Appointment start dates ("starting in Fall 2025") and funding windows
("2025-28 triennium") are not deadlines. A year in the advertisement that
disagrees with the listing is recorded in ``date_note``; the listing wins.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional, Tuple

from sources.base import parse_date

_MONTH = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
_DATE_TOKEN = (
    rf"(?:\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}}"
    rf"|\d{{1,2}}\s+(?:{_MONTH})\s+\d{{4}}"
    rf"|(?:{_MONTH})\s+\d{{1,2}},?\s+\d{{4}}"
    rf"|\d{{4}}-\d{{2}}-\d{{2}})"
)

_DEADLINE = re.compile(
    rf"(?:closing date(?:\s+for applications?)?"
    rf"|application deadline"
    rf"|deadline for applications?"
    rf"|applications? (?:will |shall )?close"
    rf"|apply by"
    rf"|apply on or before"
    rf"|on or before the closing date of"
    rf"|on or before)"
    rf"\s*(?:is|of|on|:|-)?\s*({_DATE_TOKEN})",
    re.I,
)
_REVIEW = re.compile(
    rf"(?:review of applications? will (?:begin|commence|start)"
    rf"|applications? will be considered (?:from|until)"
    rf"|consideration(?: of applications?)? will commence"
    rf"|initial screening(?: date)?"
    rf"|screening will commence)"
    rf"[^.\n]{{0,80}}?({_DATE_TOKEN})",
    re.I,
)
_UNTIL = re.compile(
    r"until (?:the )?(?:positions?|posts?|vacancies) (?:are|is) filled"
    r"|open until filled"
    r"|until filled",
    re.I,
)
_TERM = re.compile(
    r"\b(spring|summer|fall|autumn|winter)\s+(20\d{2})\b"
    r"|\b(20\d{2})\s*[-–/]\s*(\d{2,4})\b",
    re.I,
)
_CONTEXT_DATE = re.compile(
    rf"(?:start\w*|commenc\w*|appoint\w*|deadline|closing|apply|review|"
    rf"consider\w*|screening|from|until)"
    rf"[^.\n]{{0,50}}?({_DATE_TOKEN})",
    re.I,
)
_TRIennium_NEAR = re.compile(r"trienn|funding|grant", re.I)


_RELATIVE_DAYS = re.compile(r"(\d+)\s*(\+)?\s*days?\s+ago", re.I)


def interpret_open_date(text: str, today: Optional[date] = None) -> Tuple[Optional[str], bool]:
    """Turn a card's open-date text into YYYY-MM-DD.

    "30+ days ago" is a relative age, not the 30th of this month. The second
    value is True when the date is only approximate.
    """
    today = today or date.today()
    raw = text or ""
    match = _RELATIVE_DAYS.search(raw)
    if match:
        opened = today - timedelta(days=int(match.group(1)))
        return opened.isoformat(), True
    if re.search(r"\byesterday\b", raw, re.I):
        return (today - timedelta(days=1)).isoformat(), True
    if re.search(r"\btoday\b", raw, re.I) and not re.search(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", raw, re.I
    ):
        return today.isoformat(), True
    return parse_date(raw), False


def extract_deadline(text: str) -> Optional[str]:
    """A hard closing date stated in the advertisement. None for start dates and funding windows."""
    if not text:
        return None
    match = _DEADLINE.search(text)
    if not match:
        return None
    return parse_date(match.group(1))


def extract_review_start(text: str) -> Optional[str]:
    """Date on which review or consideration begins."""
    if not text:
        return None
    match = _REVIEW.search(text)
    if not match:
        return None
    return parse_date(match.group(1))


def mentions_open_until_filled(text: str) -> bool:
    return bool(text and _UNTIL.search(text))


def _expand_year(start: int, raw: str) -> int:
    year = int(raw)
    if year >= 100:
        return year
    year = (start // 100) * 100 + year
    if year < start:
        year += 100
    return year


def _term_end(match: re.Match, text: str) -> Optional[date]:
    if match.group(1):
        season = match.group(1).lower()
        year = int(match.group(2))
        if season == "spring":
            return date(year, 6, 30)
        if season == "summer":
            return date(year, 8, 31)
        if season in ("fall", "autumn"):
            return date(year, 12, 31)
        return date(year + 1, 3, 31)
    start = int(match.group(3))
    end = _expand_year(start, match.group(4))
    window = text[match.start() : match.end() + 30]
    if _TRIennium_NEAR.search(window):
        return date(end, 12, 31)
    return date(end, 8, 31)


def latest_referenced(text: str) -> Optional[date]:
    """Latest academic term or contextual date in the advertisement.

    Used only to flag a posting that never states a closing date. A funding
    triennium counts here so a current grant is not marked stale.
    """
    if not text:
        return None
    found = []
    for match in _TERM.finditer(text):
        end = _term_end(match, text)
        if end:
            found.append(end)
    for match in _CONTEXT_DATE.finditer(text):
        parsed = parse_date(match.group(1))
        if parsed:
            found.append(date.fromisoformat(parsed))
    if not found:
        return None
    return max(found)


def _years_differ(left: Optional[str], right: Optional[str]) -> bool:
    return bool(left and right and left[:4] != right[:4])


def _note(listing: str, other: str) -> str:
    return f"Listing date {listing} kept; advertisement text says {other}."


def _possibly_stale(post: dict, body: str, today: date) -> bool:
    """No closing date, and the ad's latest term is already over or the card is old."""
    kind = post.get("date_type")
    if post.get("close_date") and kind in ("deadline", "review_start"):
        return False
    latest = latest_referenced(body or "")
    if latest is not None and latest < today:
        return True
    if latest is not None and latest >= today:
        return False
    opened = (post.get("open_date") or "")[:10]
    if not opened:
        return False
    try:
        opened_on = date.fromisoformat(opened)
    except ValueError:
        return False
    return (today - opened_on).days >= 365


def refine_dates(post: dict, *, today: Optional[date] = None) -> dict:
    """Set close_date, date_type, date_note and possibly_stale on ``post``."""
    today = today or date.today()
    body = post.get("content") or ""
    listing = post.get("close_date") or None
    hint = (post.get("date_type") or "").strip()
    review = extract_review_start(body)
    deadline = extract_deadline(body)
    until = mentions_open_until_filled(body)
    note = None

    if hint == "review_start":
        post["date_type"] = "review_start"
        post["close_date"] = listing or review
        other = review or deadline
        if listing and other and _years_differ(listing, other):
            note = _note(listing, other)
            post["close_date"] = listing
    elif listing and hint != "open_until_filled":
        post["date_type"] = "deadline"
        post["close_date"] = listing
        other = deadline or review
        if other and _years_differ(listing, other):
            note = _note(listing, other)
    elif deadline:
        post["date_type"] = "deadline"
        post["close_date"] = deadline
    elif review:
        post["date_type"] = "review_start"
        post["close_date"] = review
    elif until or hint == "open_until_filled":
        post["date_type"] = "open_until_filled"
        post["close_date"] = None
    else:
        post["date_type"] = "unspecified"
        post["close_date"] = None

    if note:
        post["date_note"] = note
    else:
        post.pop("date_note", None)
    post["possibly_stale"] = _possibly_stale(post, body, today)
    return post
