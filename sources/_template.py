"""
Template for a new school or organisation career page.

Copy this file to sources/<short_key>.py (do not keep the leading underscore).
Set KEY / NAME, implement scrape(), and the module is auto-registered.

Returned posts must include: id, title, url, source, content
Optional: close_date, department, project
"""

from typing import List
from urllib.parse import urljoin

from sources.base import (
    REQUEST_DELAY,
    fetch,
    is_research_related,
    make_post,
    parse_date,
    safe_text,
)

# KEY = "OrgKey"          # used in post ids and the source filter
# NAME = "Organisation"   # human-readable; not required at runtime

# def scrape() -> List[dict]:
#     listing_url = "https://example.edu/careers/"
#     posts: List[dict] = []
#     soup = fetch(listing_url)
#     if not soup:
#         return posts
#
#     for row in soup.select("tr.job-row"):  # site-specific
#         title = safe_text(row.select_one("a"))
#         href = (row.select_one("a") or {}).get("href") if row.select_one("a") else None
#         dept = safe_text(row.select_one(".dept"))
#         if not title or not href:
#             continue
#         if not is_research_related(title, department=dept):
#             continue
#
#         detail_url = urljoin(listing_url, href)
#         # time.sleep(REQUEST_DELAY)
#         detail = fetch(detail_url)
#         content = detail.get_text("\n", strip=True)[:8000] if detail else ""
#         close_date = parse_date(safe_text(row.select_one(".close")))
#
#         posts.append(
#             make_post(
#                 source=KEY,
#                 ref=href,
#                 title=title,
#                 url=detail_url,
#                 content=content,
#                 close_date=close_date,
#                 department=dept,
#             )
#         )
#     return posts
