import hashlib
import time
from typing import List
from urllib.parse import urljoin

from sources.base import REQUEST_DELAY, fetch, is_research_related, job_content, make_post

KEY = "HKMU"
NAME = "Hong Kong Metropolitan University"


def scrape() -> List[dict]:
    url = "https://hkmu.taleo.net/careersection/ex_full_time/jobsearch.ftl?lang=en"
    posts: List[dict] = []
    soup = fetch(url, wait_for="a[href*='jobdetail']")
    if not soup:
        return posts

    for row in soup.select("tr.even, tr.odd, tr"):
        title_a = row.select_one("a[href*='jobdetail']")
        if not title_a:
            continue
        title = title_a.get_text(strip=True)
        if not is_research_related(title):
            continue

        detail_url = urljoin(url, title_a["href"])
        ref = hashlib.md5(detail_url.encode()).hexdigest()[:10]

        time.sleep(REQUEST_DELAY)
        content = job_content(fetch(detail_url))

        posts.append(
            make_post(
                source=KEY,
                ref=ref,
                title=title,
                url=detail_url,
                content=content,
            )
        )
    return posts
