import time
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

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

KEY = "HKU"
NAME = "University of Hong Kong"

# The listing repeats the same rows in tbody#recent-jobs-content. Only the
# search-results table is read. Page size 500 returns the full board in one
# response (about 400 rows); a "More Jobs" link is followed if the site caps it.
_PAGE = "https://jobs.hku.hk/en/listing/?page={page}&page-items=500"


def _jobs_from_table(soup: BeautifulSoup, base: str) -> Optional[List[tuple]]:
    """Rows from the search-results table, or None when that table is missing."""
    table = soup.select_one("tbody#search-results-content")
    if table is None:
        return None
    jobs = []
    seen = set()
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 4:
            continue
        link = tds[1].select_one("a.job-link")
        if not link or not link.get("href"):
            continue
        job_num = safe_text(tds[0].select_one("span.job-externalJobNo"))
        title = safe_text(link)
        detail_url = urljoin(base, link.get("href") or "")
        key = job_num or detail_url
        if key in seen:
            continue
        seen.add(key)
        dept = safe_text(tds[2])
        close_el = tds[3].select_one("time")
        close_raw = ""
        if close_el:
            close_raw = close_el.get("datetime") or safe_text(close_el)
        jobs.append((job_num, title, dept, close_raw, detail_url))
    return jobs


def scrape() -> List[dict]:
    """https://jobs.hku.hk/en/listing/"""
    base = "https://jobs.hku.hk"
    posts: List[dict] = []
    collected = []
    seen_refs = set()
    listed = 0
    page = 1
    while page <= 8:
        soup = fetch(_PAGE.format(page=page), wait_for="tbody#search-results-content")
        if not soup:
            if page == 1:
                print("  [HKU] listing page was not readable")
                note_counts(KEY, 0, 0)
                return posts
            break
        jobs = _jobs_from_table(soup, base)
        if jobs is None:
            if page == 1:
                print("  [HKU] job table not in the listing HTML")
                note_counts(KEY, 0, 0)
                return posts
            break
        listed += len(jobs)
        fresh = []
        for job in jobs:
            ref = job[0] or job[4]
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            fresh.append(job)
        collected.extend(fresh)
        more = soup.select_one("a.more-link[data-page]")
        next_page = int(more.get("data-page") or 0) if more else 0
        if not fresh or next_page <= page:
            break
        page = next_page
        time.sleep(REQUEST_DELAY)

    chosen = []
    for job_num, title, dept, close_raw, detail_url in collected:
        if not is_research_related(title, department=dept):
            continue
        chosen.append((job_num, title, dept, close_raw, detail_url))

    print(f"  [HKU] {listed} listing rows, {len(chosen)} match the research filter")
    note_counts(KEY, listed, len(chosen))
    listing_rows = [
        f"{ref}|{title}|{dept}|{close}|{detail}"
        for ref, title, dept, close, detail in chosen
    ]
    if same_listing(KEY, listing_rows):
        return ListingUnchanged()

    for job_num, title, dept, close_raw, detail_url in chosen:
        close_date = parse_date(close_raw)
        time.sleep(REQUEST_DELAY)
        detail = fetch(detail_url)
        content = job_content(detail)
        posts.append(
            make_post(
                source=KEY,
                ref=job_num or detail_url.rsplit("/", 2)[-2],
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
