import hashlib
from typing import List
from urllib.parse import urljoin

from sources.base import fetch, is_research_related, make_post, parse_date

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
        return posts

    items = soup.select("div.job__item")
    if not items:
        print("  [EdUHK] no div.job__item on the listing page")
        return posts

    seen = set()
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
    return posts
