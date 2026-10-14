import re
import time
from typing import List

from sources.base import (
    REQUEST_DELAY,
    fetch,
    is_research_related,
    job_content,
    make_post,
    parse_date,
    safe_text,
)

KEY = "PolyU"
NAME = "Hong Kong Polytechnic University"


def scrape() -> List[dict]:
    """https://jobs.polyu.edu.hk/research.php"""
    url = "https://jobs.polyu.edu.hk/research.php"
    posts: List[dict] = []
    soup = fetch(url)
    if not soup:
        return posts

    for row in soup.select("tr.ITS_clickableTableRow"):
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
            )
        )
    return posts
