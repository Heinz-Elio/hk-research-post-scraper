"""HKUST(GZ) jobs via the careers JSON API.

GET https://career.hkust-gz.edu.cn/api/itdcms-rpc/career/list
GET https://career.hkust-gz.edu.cn/api/itdcms-rpc/career/detail/<id>

``id`` is the detail key. ``jobid`` is the public job number; requesting
detail by ``jobid`` returns 502. An offline date of 3000-01-02 means
the posting has no closing date. Many titles are Chinese only.
"""

import time
from typing import List, Optional

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

KEY = "HKUST-GZ"
NAME = "HKUST Guangzhou"

_LIST = "https://career.hkust-gz.edu.cn/api/itdcms-rpc/career/list"
_DETAIL = "https://career.hkust-gz.edu.cn/api/itdcms-rpc/career/detail/{record_id}"
_PAGE = "https://career.hkust-gz.edu.cn/en/job-detail?jobId={record_id}"

_SECTIONS = (
    ("jobPostingDetail", "Job posting"),
    ("interdisciplinaryApproach", "Interdisciplinary approach"),
    ("qualificationCandidates", "Qualifications"),
    ("remunerationConditionsService", "Remuneration"),
    ("applicationProcedure", "Application"),
    ("remark", "Remark"),
)


def _clean(value) -> str:
    return str(value or "").replace("\xa0", " ").strip()


def _close_date(offline: str) -> Optional[str]:
    text = _clean(offline)
    # 3000-01-02 is the site's open-ended sentinel, not a real deadline.
    if not text or text.startswith("3000-"):
        return None
    return parse_date(text)


def _description(detail: dict) -> str:
    parts = []
    for key, label in _SECTIONS:
        raw = ((detail.get(key) or {}) if isinstance(detail.get(key), dict) else {})
        text = html_to_text(raw.get("content") or "")
        if text:
            parts.append(f"{label}\n{text}")
    return "\n\n".join(parts)


def _load_list() -> Optional[List[dict]]:
    data = api_request("GET", _LIST)
    if not isinstance(data, dict) or data.get("code") not in (0, "0"):
        return None
    rows = data.get("data")
    if not isinstance(rows, list):
        return None
    return [row for row in rows if isinstance(row, dict)]


def scrape() -> List[dict]:
    posts: List[dict] = []
    rows = _load_list()
    if rows is None:
        print("  [HKUST-GZ] career list returned no data")
        note_counts(KEY, 0, 0)
        return posts

    jobs = []
    for row in rows:
        record_id = _clean(row.get("id"))
        job_id = _clean(row.get("jobid")) or record_id
        title = _clean(row.get("postNameCh"))
        dept = _clean(row.get("enPostDept"))
        hub = _clean(row.get("hubName"))
        if not record_id or not title:
            continue
        if not is_research_related(title, department=f"{dept} {hub}".strip()):
            continue
        jobs.append((record_id, job_id, title, dept, _clean(row.get("offlineDate"))))

    print(f"  [HKUST-GZ] {len(rows)} listings, {len(jobs)} match the research filter")
    note_counts(KEY, len(rows), len(jobs))
    listing_rows = [
        f"{job_id}|{title}|{dept}|{offline}"
        for _record, job_id, title, dept, offline in jobs
    ]
    if same_listing(KEY, listing_rows):
        return ListingUnchanged()

    for record_id, job_id, title, dept, offline in jobs:
        time.sleep(REQUEST_DELAY)
        data = api_request("GET", _DETAIL.format(record_id=record_id))
        detail = data.get("data") if isinstance(data, dict) else None
        if not isinstance(detail, dict):
            detail = {}
        body = _description(detail)
        # Some Technical Officer ads publish a title and department only.
        content = body or f"Department: {dept}\nJob ID: {job_id}".strip()
        posted = parse_date(_clean(detail.get("onlineDate") or detail.get("publicDate")))
        posts.append(
            make_post(
                source=KEY,
                ref=job_id,
                title=_clean(detail.get("postNameCh")) or title,
                url=_PAGE.format(record_id=record_id),
                content=content,
                close_date=_close_date(detail.get("offlineDate") or offline),
                department=_clean(detail.get("enPostDept")) or dept or None,
                open_date=posted,
            )
        )
    prepare_posts(posts)
    finish_listing(KEY, posts)
    return posts
