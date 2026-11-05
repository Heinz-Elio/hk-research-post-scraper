"""HKMU full-time jobs via the Taleo REST board.

POST https://hkmu.taleo.net/careersection/rest/jobboard/searchjobs
portal 101430233. Columns are title, department, closing date.
Titles such as "Research Assistant I/II (N&HS)" only pass the STEM
check when the department is included.
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

KEY = "HKMU"
NAME = "Hong Kong Metropolitan University"

_HOST = "https://hkmu.taleo.net"
_PORTAL = "101430233"
_SECTION = "ex_full_time"


def scrape() -> List[dict]:
    posts: List[dict] = []
    rows = search_jobs(_HOST, _PORTAL)
    if rows is None:
        print("  [HKMU] Taleo job search returned no data")
        return posts

    jobs = []
    for row in rows:
        columns = row.get("column") or []
        if len(columns) < 2:
            continue
        ref = str(row.get("contestNo") or "").strip()
        title = str(columns[0] or "").replace("\xa0", " ").strip()
        dept = str(columns[1] or "").replace("\xa0", " ").strip()
        close_raw = str(columns[2] or "").strip() if len(columns) > 2 else ""
        if not ref or not title:
            continue
        if not is_research_related(title, department=dept):
            continue
        jobs.append((ref, title, dept, close_raw, detail_url(_HOST, _SECTION, ref)))

    print(f"  [HKMU] {len(rows)} listings, {len(jobs)} match the research filter")
    listing_rows = [
        f"{ref}|{title}|{dept}|{close}|{url}" for ref, title, dept, close, url in jobs
    ]
    if same_listing(KEY, listing_rows):
        return ListingUnchanged()

    for ref, title, dept, close_raw, url in jobs:
        time.sleep(REQUEST_DELAY)
        detail = fetch_detail(url) or {}
        if detail:
            close_date = parse_date(detail.get("unposting_date") or "")
            content = detail.get("description") or ""
            title = detail.get("title") or title
            dept = dept or detail.get("organization") or ""
        else:
            close_date = parse_date(close_raw)
            content = ""
        posts.append(
            make_post(
                source=KEY,
                ref=ref,
                title=title,
                url=url,
                content=content,
                close_date=close_date,
                department=dept or None,
            )
        )
    finish_listing(KEY, posts)
    return posts
