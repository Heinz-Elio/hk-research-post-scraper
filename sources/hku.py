import time
from typing import List
from urllib.parse import urljoin

from sources.base import (
    REQUEST_DELAY,
    fetch,
    is_research_related,
    job_content,
    make_post,
    parse_date,
    safe_text,
)

KEY = "HKU"
NAME = "University of Hong Kong"


def scrape() -> List[dict]:
    """https://jobs.hku.hk/en/listing/"""
    base = "https://jobs.hku.hk"
    listing_url = f"{base}/en/listing/"
    posts: List[dict] = []
    soup = fetch(listing_url)
    if not soup:
        return posts

    rows = []
    for body_id in ("search-results-content", "recent-jobs-content"):
        table = soup.select_one(f"tbody#{body_id}")
        if table:
            rows.extend(table.select("tr"))
    if not rows:
        print("  [HKU] job table not in the listing HTML")
        return posts

    seen = set()
    for tr in rows:
        tds = tr.select("td")
        if len(tds) < 4:
            continue
        link = tds[1].select_one("a.job-link")
        if not link or not link.get("href"):
            continue

        job_num = safe_text(tds[0].select_one("span.job-externalJobNo"))
        title = safe_text(link)
        detail_url = urljoin(base, link.get("href") or "")
        if detail_url in seen:
            continue
        seen.add(detail_url)
        dept = safe_text(tds[2])
        close_el = tds[3].select_one("time")
        close_raw = ""
        if close_el:
            close_raw = close_el.get("datetime") or safe_text(close_el)
        close_date = parse_date(close_raw)

        if not is_research_related(title, department=dept):
            continue

        time.sleep(REQUEST_DELAY)
        detail = fetch(detail_url)
        content = job_content(detail)

        posts.append(
            make_post(
                source=KEY,
                ref=job_num,
                title=title,
                url=detail_url,
                content=content,
                close_date=close_date,
                department=dept,
            )
        )
    return posts
