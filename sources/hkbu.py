"""HKBU jobs via Oracle Recruiting Cloud REST.

GET .../recruitingCEJobRequisitions?finder=findReqs;siteNumber=CX_1
Detail .../recruitingCEJobRequisitionDetails?finder=ById
The list has no closing date. An explicit date in the description is
kept; "until the position is filled" stays empty.
"""

import re
import time
from typing import List, Optional
from urllib.parse import quote

from sources.base import (
    REQUEST_DELAY,
    ListingUnchanged,
    api_request,
    finish_listing,
    html_to_text,
    is_research_related,
    make_post,
    note_counts,
    parse_date,
    prepare_posts,
    same_listing,
)

KEY = "HKBU"
NAME = "Hong Kong Baptist University"

_HOST = "https://fa-ewqq-saasfaprod1.fa.ocs.oraclecloud.com"
_SITE = "CX_1"
_PAGE = (
    f"{_HOST}/hcmUI/CandidateExperience/en/sites/hkbu/job/{{job_id}}"
)
_LIST = f"{_HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
_DETAIL = f"{_HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"

_SITS_UNDER = re.compile(r"sits under the ([^.\n]+)", re.I)
_CLOSE_PHRASE = re.compile(
    r"(?:closing date|application deadline|deadline for applications?|"
    r"applications? (?:will )?close|apply on or before|"
    r"on or before the closing date of)"
    r"\s*[:\-]?\s*([^\n.]{6,80})",
    re.I,
)
_FILLED = re.compile(r"until filled|position is filled|to be filled", re.I)


def _list_url(offset: int, limit: int = 200) -> str:
    finder = (
        f"findReqs;siteNumber={_SITE},limit={limit},offset={offset},"
        "sortBy=POSTING_DATES_DESC"
    )
    return (
        f"{_LIST}?onlyData=true&expand=requisitionList.secondaryLocations"
        f"&finder={quote(finder, safe=';=,')}"
    )


def _detail_url(job_id: str) -> str:
    finder = f'ById;Id="{job_id}",siteNumber={_SITE}'
    return f"{_DETAIL}?expand=all&onlyData=true&finder={quote(finder, safe=';=,\"')}"


_DEPT_TAIL = re.compile(
    r"\s+(?:at our|located at|located in|which|who|and will|and is)\b",
    re.I,
)


def _trim_department(name: str) -> str:
    name = _DEPT_TAIL.split(name or "", maxsplit=1)[0]
    return name.strip(" .,-")


def _department(title: str, short: str) -> str:
    if "," in title:
        candidate = _trim_department(title.split(",")[-1])
        if candidate:
            return candidate
    match = _SITS_UNDER.search(short or "")
    return _trim_department(match.group(1)) if match else ""


def _closing_date(api_value: Optional[str], description: str) -> Optional[str]:
    if api_value:
        cleaned = re.sub(r"(\d{2}:\d{2}:\d{2})\.\d+", r"\1", str(api_value))
        parsed = parse_date(cleaned)
        if parsed:
            return parsed
    match = _CLOSE_PHRASE.search(description or "")
    if not match or _FILLED.search(match.group(1)):
        return None
    return parse_date(match.group(1))


def _load_requisitions() -> Optional[List[dict]]:
    collected: List[dict] = []
    offset = 0
    total = None
    while offset < 5000:
        data = api_request("GET", _list_url(offset))
        items = (data or {}).get("items") if isinstance(data, dict) else None
        if not items:
            return None if offset == 0 else collected
        block = items[0] if isinstance(items[0], dict) else {}
        rows = block.get("requisitionList") or []
        if not isinstance(rows, list):
            return None if offset == 0 else collected
        try:
            total = int(block.get("TotalJobsCount") or 0)
        except (TypeError, ValueError):
            total = 0
        collected.extend(row for row in rows if isinstance(row, dict))
        if not rows or len(collected) >= total:
            break
        offset += len(rows)
        time.sleep(REQUEST_DELAY)
    return collected


def scrape() -> List[dict]:
    posts: List[dict] = []
    rows = _load_requisitions()
    if rows is None:
        print("  [HKBU] Oracle job search returned no data")
        note_counts(KEY, 0, 0)
        return posts

    chosen = []
    for row in rows:
        title = str(row.get("Title") or "").replace("\xa0", " ").strip()
        job_id = str(row.get("Id") or "").strip()
        short = str(row.get("ShortDescriptionStr") or "").strip()
        if not title or not job_id or len(title) < 8:
            continue
        dept = _department(title, short)
        if not is_research_related(title, department=dept, description=short):
            continue
        chosen.append((job_id, title, dept, short))

    print(f"  [HKBU] {len(rows)} listings, {len(chosen)} match the research filter")
    note_counts(KEY, len(rows), len(chosen))
    listing_rows = [f"{job_id}|{title}|{dept}" for job_id, title, dept, _short in chosen]
    if same_listing(KEY, listing_rows):
        return ListingUnchanged()

    for job_id, title, dept, short in chosen:
        time.sleep(REQUEST_DELAY)
        data = api_request("GET", _detail_url(job_id))
        item = {}
        items = (data or {}).get("items") if isinstance(data, dict) else None
        if items and isinstance(items[0], dict):
            item = items[0]
        html = item.get("ExternalDescriptionStr") or ""
        body = html_to_text(html) or short
        if not dept:
            dept = _department(item.get("Title") or title, item.get("ShortDescriptionStr") or short)
        content = f"Department: {dept}\n\n{body}".strip() if dept else body
        close_date = _closing_date(item.get("ExternalPostedEndDate"), body)
        posts.append(
            make_post(
                source=KEY,
                ref=job_id,
                title=str(item.get("Title") or title).strip(),
                url=_PAGE.format(job_id=job_id),
                content=content,
                close_date=close_date,
                department=dept or None,
            )
        )
    prepare_posts(posts)
    finish_listing(KEY, posts)
    return posts
