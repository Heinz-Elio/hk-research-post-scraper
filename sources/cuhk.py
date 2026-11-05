"""CUHK non-teaching jobs via the Taleo REST board.

POST https://cuhk.taleo.net/careersection/rest/jobboard/searchjobs
portal 8115020119. Columns are contest number, title, department.
"""

import time
from typing import List

from sources.base import (
    REQUEST_DELAY,
    ListingUnchanged,
    finish_listing,
    is_research_related,
    make_post,
    parse_date,
    same_listing,
)
from sources.taleo import detail_url, fetch_detail, search_jobs

KEY = "CUHK"
NAME = "Chinese University of Hong Kong"

_HOST = "https://cuhk.taleo.net"
_PORTAL = "8115020119"
_SECTION = "cu_career_non_teach"


def scrape() -> List[dict]:
    posts: List[dict] = []
    rows = search_jobs(_HOST, _PORTAL)
    if rows is None:
        print("  [CUHK] Taleo job search returned no data")
        return posts

    jobs = []
    for row in rows:
        columns = row.get("column") or []
        if len(columns) < 3:
            continue
        ref = str(row.get("contestNo") or columns[0] or "").strip()
        title = str(columns[1] or "").replace("\xa0", " ").strip()
        dept = str(columns[2] or "").replace("\xa0", " ").strip()
        if not ref or not title:
            continue
        if not is_research_related(title, department=dept):
            continue
        jobs.append((ref, title, dept, detail_url(_HOST, _SECTION, ref)))

    print(f"  [CUHK] {len(rows)} listings, {len(jobs)} match the research filter")
    listing_rows = [f"{ref}|{title}|{dept}|{url}" for ref, title, dept, url in jobs]
    if same_listing(KEY, listing_rows):
        return ListingUnchanged()

    for ref, title, dept, url in jobs:
        time.sleep(REQUEST_DELAY)
        detail = fetch_detail(url) or {}
        close_date = parse_date(detail.get("unposting_date") or "")
        content = detail.get("description") or ""
        if not dept:
            dept = detail.get("organization") or ""
        posts.append(
            make_post(
                source=KEY,
                ref=ref,
                title=detail.get("title") or title,
                url=url,
                content=content,
                close_date=close_date,
                department=dept or None,
            )
        )
    finish_listing(KEY, posts)
    return posts
