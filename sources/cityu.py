import hashlib
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

KEY = "CityU"
NAME = "City University of Hong Kong"


def scrape() -> List[dict]:
    """https://jobs1.cityu.edu.hk/apply/Default.aspx?jobtype=RS"""
    url = "https://jobs1.cityu.edu.hk/apply/Default.aspx?jobtype=RS"
    posts: List[dict] = []
    soup = fetch(url)
    if not soup:
        return posts

    table = soup.find("table", id="MainContent_gvJobResearch")
    if not table:
        return posts

    warned_blocked = False
    for row in table.find_all("tr")[1:]:
        tds = row.find_all("td")
        if len(tds) < 2:
            continue

        title = safe_text(tds[0])
        dept = safe_text(tds[1]) if len(tds) > 1 else ""
        if not is_research_related(title, department=dept):
            continue

        close_raw = safe_text(tds[2]) if len(tds) > 2 else ""
        close_date = parse_date(close_raw)

        a = tds[0].find("a", href=True)
        if not a or not a.get("href") or a["href"].startswith("javascript:"):
            continue
        detail_url = urljoin(url, a["href"])
        ref = a["href"].split("=")[-1] or hashlib.md5(title.encode()).hexdigest()[:8]

        time.sleep(REQUEST_DELAY)
        detail = fetch(detail_url)
        body = job_content(detail)
        if not body and not warned_blocked:
            print("  [CityU] job description page was blocked; keeping listing fields only")
            warned_blocked = True
        content = f"Department: {dept}\n{body}".strip()

        posts.append(
            make_post(
                source=KEY,
                ref=ref,
                title=title,
                url=detail_url,
                content=content,
                close_date=close_date,
                department=dept,
            )
        )
    return posts
