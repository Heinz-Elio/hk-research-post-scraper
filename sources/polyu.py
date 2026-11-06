import re
import time
from typing import List

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

KEY = "PolyU"
NAME = "Hong Kong Polytechnic University"


def scrape() -> List[dict]:
    """https://jobs.polyu.edu.hk/research.php"""
    url = "https://jobs.polyu.edu.hk/research.php"
    posts: List[dict] = []
    soup = fetch(url)
    if not soup:
        note_counts(KEY, 0, 0)
        return posts

    rows_on_page = soup.select("tr.ITS_clickableTableRow")
    jobs = []
    for row in rows_on_page:
        tds = row.select("td")
        if len(tds) < 5:
            continue

        url_part = row.get("data-href")
        if not url_part:
            continue
        dept = safe_text(tds[0])
        title = safe_text(tds[1])
        project = safe_text(tds[2])
        close_raw = safe_text(tds[3])
        ref = safe_text(tds[4])

        if not is_research_related(title, department=dept, project=project):
            continue

        detail_url = url.replace("research.php", url_part)
        jobs.append((ref, title, dept, project, close_raw, detail_url))

    # The "Closing / Initial Screening Date" column is when consideration
    # starts, not a hard deadline. Posts stay active while they remain listed.
    print(f"  [PolyU] {len(rows_on_page)} listing rows, {len(jobs)} match the research filter")
    note_counts(KEY, len(rows_on_page), len(jobs))
    rows = [
        f"{ref}|{title}|{dept}|{project}|{close}|{detail}"
        for ref, title, dept, project, close, detail in jobs
    ]
    if same_listing(KEY, rows):
        return ListingUnchanged()

    for ref, title, dept, project, close_raw, detail_url in jobs:
        close_date = parse_date(close_raw)
        time.sleep(REQUEST_DELAY)
        detail = fetch(detail_url)
        body = job_content(detail)
        body = re.sub(r"\nApply Now\s*Posting date:.*\Z", "", body, flags=re.S).strip()
        content = f"Department: {dept}\nProject Title: {project}\n\n{body}".strip()

        posts.append(
            make_post(
                source=KEY,
                ref=ref,
                title=title,
                url=detail_url,
                content=content,
                close_date=close_date,
                department=dept,
                project=project,
                date_type="review_start" if close_date else "open_until_filled",
            )
        )
    prepare_posts(posts)
    finish_listing(KEY, posts)
    return posts
