import hashlib
from typing import List
from urllib.parse import urljoin

from sources.base import (
    ListingUnchanged,
    fetch,
    finish_listing,
    is_research_related,
    make_post,
    note_counts,
    parse_date,
    prepare_posts,
    same_listing,
)

KEY = "EdUHK"
NAME = "Education University of Hong Kong"


def _dd(item, label: str) -> str:
    for dl in item.select("dl.job__dl"):
        dt = dl.select_one("dt")
        if dt and label in dt.get_text(" ", strip=True).lower():
            dd = dl.select_one("dd")
            return dd.get_text(" ", strip=True) if dd else ""
    return ""


def scrape() -> List[dict]:
    url = "https://www.eduhk.hk/en/current-openings?category=research-support-posts&department=&q="
    posts: List[dict] = []
    soup = fetch(url)
    if not soup:
        note_counts(KEY, 0, 0)
        return posts

    items = soup.select("div.job__item")
    if not items:
        print("  [EdUHK] no div.job__item on the listing page")
        note_counts(KEY, 0, 0)
        return posts

    seen = set()
    chosen = []
    for item in items:
        link = item.select_one("a.job__title-name")
        if not link or not link.get("href"):
            continue
        title = link.get_text(" ", strip=True)
        dept_el = item.select_one("p.job__title-from")
        dept = dept_el.get_text(" ", strip=True) if dept_el else ""
        if not is_research_related(title, department=dept):
            continue

        detail_url = urljoin(url, link["href"])
        if detail_url in seen:
            continue
        seen.add(detail_url)

        ref = _dd(item, "ref") or hashlib.md5(detail_url.encode()).hexdigest()[:10]
        close_date = parse_date(_dd(item, "close date"))
        content = item.get_text("\n", strip=True)
        chosen.append((ref, title, dept, close_date, detail_url, content))

    print(f"  [EdUHK] {len(items)} listing rows, {len(chosen)} match the research filter")
    note_counts(KEY, len(items), len(chosen))
    listing_rows = [
        f"{ref}|{title}|{dept}|{close}|{detail}"
        for ref, title, dept, close, detail, _content in chosen
    ]
    if same_listing(KEY, listing_rows):
        return ListingUnchanged()

    for ref, title, dept, close_date, detail_url, content in chosen:
        posts.append(
            make_post(
                source=KEY,
                ref=ref,
                title=title,
                url=detail_url,
                content=content,
                close_date=close_date,
                department=dept or None,
            )
        )
    prepare_posts(posts)
    finish_listing(KEY, posts)
    return posts
