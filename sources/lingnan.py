"""Lingnan research-support jobs via the Cornerstone (CSOD) search API.

The careers HTML embeds a bearer token (``csod.context.token``).
robots.txt asks for a 10-second crawl delay, so this module requests
that page once and then calls uk.api.csod.com.

Dropdown 151 / option 103 is the site's "Research Support and Project
posts" category. Closing dates are not published (the API sends "-").
"""

import re
import time
from typing import List, Optional

from sources.base import (
    REQUEST_DELAY,
    ListingUnchanged,
    api_request,
    finish_listing,
    is_research_related,
    make_post,
    note_counts,
    parse_date,
    prepare_posts,
    same_listing,
)

KEY = "Lingnan"
NAME = "Lingnan University"

_PAGE = "https://lingnan.csod.com/ux/ats/careersite/4/home?c=lingnan"
_JOB_URL = (
    "https://lingnan.csod.com/ux/ats/careersite/4/home/requisition/{job_id}?c=lingnan"
)
_DEFAULT_API = "https://uk.api.csod.com/"
# Careers-site custom field "Research Support and Project posts".
_RESEARCH_DROPDOWN = {"id": 151, "options": [103]}
_CRAWL_DELAY = 10

_TOKEN = re.compile(r'"token"\s*:\s*"([^"]+)"')
_CLOUD = re.compile(r'"cloud"\s*:\s*"(https:[^"]+)"')


def _token_and_cloud() -> Optional[tuple]:
    # robots.txt on lingnan.csod.com is "Crawl-delay: 10". This is the only
    # request to that host; a retry waits out the delay. Job search itself
    # goes to the CSOD API host.
    html = api_request("GET", _PAGE, expect="text", pause=_CRAWL_DELAY)
    if not html:
        return None
    token = _TOKEN.search(html)
    if not token:
        print("  [Lingnan] careers page had no CSOD token")
        return None
    cloud = _CLOUD.search(html)
    base = cloud.group(1) if cloud else _DEFAULT_API
    return token.group(1), base if base.endswith("/") else base + "/"


def _search(token: str, cloud: str) -> Optional[List[dict]]:
    url = cloud + "rec-job-search/external/jobs"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    collected: List[dict] = []
    page = 1
    total = None
    while page <= 20:
        body = {
            "careerSiteId": 4,
            "careerSitePageId": 4,
            "pageNumber": page,
            "pageSize": 50,
            "cultureId": 1,
            "searchText": "",
            "cultureName": "en-US",
            "states": [],
            "countryCodes": [],
            "cities": [],
            "placeID": "",
            "radius": None,
            "postingsWithinDays": None,
            "customFieldCheckboxKeys": [],
            "customFieldDropdowns": [_RESEARCH_DROPDOWN],
            "customFieldRadios": [],
        }
        data = api_request("POST", url, json_body=body, extra_headers=headers)
        block = (data or {}).get("data") if isinstance(data, dict) else None
        if not isinstance(block, dict):
            return None if page == 1 else collected
        rows = block.get("requisitions") or []
        if not isinstance(rows, list):
            return None if page == 1 else collected
        try:
            total = int(block.get("totalCount") or 0)
        except (TypeError, ValueError):
            total = 0
        collected.extend(row for row in rows if isinstance(row, dict))
        if not rows or len(collected) >= total:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return collected


def _department(title: str) -> str:
    if "," not in title:
        return ""
    return title.split(",")[-1].strip()


def scrape() -> List[dict]:
    posts: List[dict] = []
    opened = _token_and_cloud()
    if not opened:
        print("  [Lingnan] CSOD careers page returned no data")
        note_counts(KEY, 0, 0)
        return posts
    token, cloud = opened
    # The token page is the only hit on lingnan.csod.com. Further calls
    # go to the API host. A later HTML fetch must wait out Crawl-delay: 10.
    rows = _search(token, cloud)
    if rows is None:
        print("  [Lingnan] CSOD job search returned no data")
        note_counts(KEY, 0, 0)
        return posts

    jobs = []
    seen = set()
    for row in rows:
        title = str(row.get("displayJobTitle") or "").replace("\xa0", " ").strip()
        job_id = str(row.get("requisitionId") or "").strip()
        description = str(row.get("externalDescription") or "").strip()
        if not title or not job_id or job_id in seen or len(title) < 8:
            continue
        dept = _department(title)
        if not is_research_related(title, department=dept, project=description):
            continue
        seen.add(job_id)
        close_raw = str(row.get("postingExpirationDate") or "").strip()
        jobs.append((job_id, title, dept, close_raw, description))

    print(f"  [Lingnan] {len(rows)} research-category listings, {len(jobs)} match the research filter")
    note_counts(KEY, len(rows), len(jobs))
    listing_rows = [
        f"{job_id}|{title}|{dept}|{close}" for job_id, title, dept, close, _desc in jobs
    ]
    if same_listing(KEY, listing_rows):
        return ListingUnchanged()

    for job_id, title, dept, close_raw, description in jobs:
        posts.append(
            make_post(
                source=KEY,
                ref=job_id,
                title=title,
                url=_JOB_URL.format(job_id=job_id),
                content=description,
                close_date=parse_date(close_raw),
                department=dept or None,
            )
        )
    prepare_posts(posts)
    finish_listing(KEY, posts)
    return posts
