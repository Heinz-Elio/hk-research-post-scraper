"""Contract length parsed from an appointment line or a job title.

``contract_months`` is the shortest stated term. ``contract_months_max`` is the
longest, and equals the minimum when the ad gives a single length. ``up to N``
sets only the maximum. Nothing is guessed from a salary line or from
``until <date>`` when no start date is given. Missing fields stay null so the
browse filters can show those posts as unknown.
"""

from __future__ import annotations

import re
from typing import List, Optional

_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "twenty-four": 24,
    "twentyfour": 24,
    "thirty-six": 36,
    "thirtysix": 36,
}
_NUM = (
    r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty(?:-four)?|thirty-six)"
)
_UNIT = r"(months?|years?)"
_SPAN = re.compile(
    rf"(?P<a>{_NUM})\s*(?:[-–]|to)\s*(?P<b>{_NUM})\s*-?\s*(?P<u>{_UNIT})",
    re.I,
)
_SPAN_MIXED = re.compile(
    rf"(?P<a>{_NUM})\s*-?\s*(?P<ua>{_UNIT})\s*(?:[-–]|to)\s*(?P<b>{_NUM})\s*-?\s*(?P<ub>{_UNIT})",
    re.I,
)
_UP_TO = re.compile(rf"\bup to\s+(?P<a>{_NUM})\s*-?\s*(?P<u>{_UNIT})", re.I)
_SINGLE = re.compile(
    rf"(?P<a>{_NUM})\s*-?\s*(?P<u>{_UNIT})",
    re.I,
)
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_ONES = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
}


def _normalize_compounds(text: str) -> str:
    """Turn 'twenty-four' and 'twenty four' into 24 before range matching.

    The hyphen in a compound is not a range. 'twelve to twenty-four' stays a
    range because 'to' is the separator and the compound is already one number.
    """

    def replace(match: re.Match) -> str:
        tens = _TENS[match.group(1).lower()]
        ones = _ONES[match.group(2).lower()] if match.group(2) else 0
        return str(tens + ones)

    return re.sub(
        r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
        r"(?:[-\s]+(one|two|three|four|five|six|seven|eight|nine))?\b",
        replace,
        text,
        flags=re.I,
    )


_RENEW = re.compile(
    r"\brenewable\b|possibility of renewal|possibility of further appointment|"
    r"with the possibility of renewal|further appointment",
    re.I,
)
def _is_experience(raw: str, match: re.Match) -> bool:
    """Skip 'two years of experience', not 'Duration: 2 years'."""
    before = raw[max(0, match.start() - 18) : match.start()]
    after = raw[match.end() : match.end() + 28]
    if re.search(r"experience\s+(?:of\s+)?$", before, re.I):
        return True
    return bool(re.search(r"\bexperience\b", after, re.I))


def _number(token: str) -> Optional[float]:
    key = token.lower().strip()
    if key in _WORDS:
        return float(_WORDS[key])
    try:
        return float(key)
    except ValueError:
        return None


def _months(token: str, unit: str) -> Optional[int]:
    value = _number(token)
    if value is None:
        return None
    if unit.lower().startswith("year"):
        return int(round(value * 12))
    return int(round(value))


def _appointment_text(title: str = "", summary: str = "", content: str = "") -> str:
    """Prefer the appointment line. Fall back to the title, not the whole advert."""
    parts: List[str] = []
    for line in (summary or "").splitlines():
        if line.strip().lower().startswith("- appointment:"):
            parts.append(line.split(":", 1)[1])
    if content and not parts:
        for line in content.splitlines():
            if re.search(r"appointment|duration|contract", line, re.I):
                parts.append(line)
    if title:
        parts.append(title)
    return " ".join(parts)


def parse_contract(text: str) -> dict:
    """Return contract_months, contract_months_max, and contract_renewable."""
    raw = _normalize_compounds(re.sub(r"\s+", " ", text or "").strip())
    renewable = bool(_RENEW.search(raw)) if raw else None
    if renewable is False:
        renewable = None
    lows: List[int] = []
    highs: List[int] = []
    if not raw:
        return {
            "contract_months": None,
            "contract_months_max": None,
            "contract_renewable": None,
        }

    consumed = []

    def mark(match) -> None:
        consumed.append((match.start(), match.end()))

    def free(match) -> bool:
        return not any(start <= match.start() < end for start, end in consumed)

    for match in _UP_TO.finditer(raw):
        if not free(match) or _is_experience(raw, match):
            continue
        months = _months(match.group("a"), match.group("u"))
        if months:
            highs.append(months)
            mark(match)
    for matcher in (_SPAN_MIXED, _SPAN):
        for match in matcher.finditer(raw):
            if not free(match) or _is_experience(raw, match):
                continue
            if matcher is _SPAN_MIXED:
                left = _months(match.group("a"), match.group("ua"))
                right = _months(match.group("b"), match.group("ub"))
            else:
                left = _months(match.group("a"), match.group("u"))
                right = _months(match.group("b"), match.group("u"))
            if left and right:
                lows.append(min(left, right))
                highs.append(max(left, right))
                mark(match)
    for match in _SINGLE.finditer(raw):
        if not free(match) or _is_experience(raw, match):
            continue
        months = _months(match.group("a"), match.group("u"))
        if months:
            lows.append(months)
            highs.append(months)
            mark(match)

    low = min(lows) if lows else None
    high = max(highs) if highs else None
    if low is None and high is None:
        renewable = True if renewable else None
    return {
        "contract_months": low,
        "contract_months_max": high,
        "contract_renewable": True if renewable else None,
    }


def parse_post_contract(post: dict) -> dict:
    text = _appointment_text(
        post.get("title") or "",
        post.get("summary") or "",
        post.get("content") or "",
    )
    return parse_contract(text)


def attach_contract(post: dict) -> dict:
    """Set the three contract fields. Null means the advert did not say."""
    parsed = parse_post_contract(post)
    for key, value in parsed.items():
        if value is None:
            post.pop(key, None)
        else:
            post[key] = value
    return post


def contract_overlaps(post: dict, bucket: str) -> bool:
    """True when a stored term overlaps a browse bucket.

    Buckets are ``le6``, ``6-12``, ``12-24``, ``gt24``, and ``unknown``.
    A range can match more than one bucket. ``up to N`` (maximum only) is
    placed in the bucket that contains N, not in every shorter bucket.
    """
    low = post.get("contract_months")
    high = post.get("contract_months_max")
    if low is None and high is None:
        return bucket == "unknown"
    if bucket == "unknown":
        return False
    # "up to N" stores only the maximum. Put it in the bucket that contains N.
    if low is None:
        low = high
    if high is None:
        high = low
    if bucket == "le6":
        return high <= 6
    if bucket == "6-12":
        return low <= 12 and high > 6
    if bucket == "12-24":
        return low <= 24 and high > 12
    if bucket == "gt24":
        return high > 24
    return False
