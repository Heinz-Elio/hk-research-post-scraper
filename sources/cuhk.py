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

KEY = "CUHK"
NAME = "Chinese University of Hong Kong"


def scrape() -> List[dict]:
    url = (
        "https://cuhk.taleo.net/careersection/cu_career_non_teach/"
        "jobsearch.ftl?lang=en&portal=8115020119"
    )
    posts: List[dict] = []
    soup = fetch(url, wait_for="tr.even, tr.odd")
    if not soup:
        return posts

    rows = soup.select("tr.even, tr.odd")
    if not rows:
        print("  [CUHK] Taleo listing has no job rows in the static HTML")
        return posts

    for row in rows:
        job_num = safe_text(row.select_one("th span"))
        tds = row.find_all("td")
        if len(tds) < 3:
            continue
        a = tds[1].select_one("a")
        if not a or not a.get("href"):
            continue
        href = a["href"]
        title = safe_text(a)
        dept = safe_text(tds[2].select_one("span"))

        if not is_research_related(title, department=dept):
            continue

        detail_url = urljoin(url, href)
        close_date = None

        time.sleep(REQUEST_DELAY)
        detail = fetch(detail_url)
        content = job_content(detail)
        if detail:
            close_date = parse_date(
                safe_text(detail.select_one(".reqUnpostingDate span, span.reqUnpostingDate"))
            )

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
