import hashlib
import time
from typing import List
from urllib.parse import urljoin

from sources.base import (
    REQUEST_DELAY,
    ListingUnchanged,
    fetch,
    finish_listing,
    is_research_related,
    job_content,
    make_post,
    note_counts,
    parse_date,
    prepare_posts,
    safe_text,
    same_listing,
)

KEY = "CityU"
NAME = "City University of Hong Kong"


def scrape() -> List[dict]:
    """https://jobs1.cityu.edu.hk/apply/Default.aspx?jobtype=RS"""
    url = "https://jobs1.cityu.edu.hk/apply/Default.aspx?jobtype=RS"
    posts: List[dict] = []
    soup = fetch(url)
    if not soup:
        note_counts(KEY, 0, 0)
        return posts

    table = soup.find("table", id="MainContent_gvJobResearch")
    if not table:
        note_counts(KEY, 0, 0)
        return posts

    data_rows = table.find_all("tr")[1:]
    jobs = []
    for row in data_rows:
        tds = row.find_all("td")
        if len(tds) < 2:
            continue

        title = safe_text(tds[0])
        dept = safe_text(tds[1]) if len(tds) > 1 else ""
        if not is_research_related(title, department=dept):
            continue

        close_raw = safe_text(tds[2]) if len(tds) > 2 else ""
        a = tds[0].find("a", href=True)
        if not a or not a.get("href") or a["href"].startswith("javascript:"):
            continue
        detail_url = urljoin(url, a["href"])
        ref = a["href"].split("=")[-1] or hashlib.md5(title.encode()).hexdigest()[:8]
        jobs.append((ref, title, dept, close_raw, detail_url))

    print(f"  [CityU] {len(data_rows)} listing rows, {len(jobs)} match the research filter")
    note_counts(KEY, len(data_rows), len(jobs))
    rows = [f"{ref}|{title}|{dept}|{close}|{detail}" for ref, title, dept, close, detail in jobs]
    if same_listing(KEY, rows):
        return ListingUnchanged()

    warned_blocked = False
    for ref, title, dept, close_raw, detail_url in jobs:
        close_date = parse_date(close_raw)
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
    prepare_posts(posts)
    finish_listing(KEY, posts)
    return posts
