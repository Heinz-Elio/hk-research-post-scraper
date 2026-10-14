import hashlib
import time
from typing import List
from urllib.parse import urljoin

from sources.base import REQUEST_DELAY, fetch, is_research_related, job_content, make_post

KEY = "HKUST-GZ"
NAME = "HKUST Guangzhou"


def scrape() -> List[dict]:
    url = "https://jobs.hkust-gz.edu.cn/"
    posts: List[dict] = []
    soup = fetch(url)
    if not soup:
        soup = fetch("https://career.hkust-gz.edu.cn/en/career")
        if not soup:
            return posts

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not is_research_related(title):
            continue
        detail_url = urljoin(url, a["href"])
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
