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
)

KEY = "HKUST"
NAME = "HKUST Clear Water Bay"


def _card_fields(card) -> dict:
    title_el = card.select_one("h3 a") or card.select_one("h3")
    title = title_el.get_text(" ", strip=True) if title_el else ""
    href = title_el.get("href") if title_el and title_el.has_attr("href") else ""

    job_id = ""
    dept = ""
    close_date = None
    for p in card.select("p"):
        text = p.get_text(" ", strip=True)
        low = text.lower()
        if low.startswith("job id"):
            job_id = text.split(":")[-1].strip()
        elif "apply by" in low:
            close_date = parse_date(text.split(":")[-1].strip())
        elif "open date" in low:
            continue
        elif not dept and text and "date" not in low:
            dept = text
    return {
        "title": title,
        "href": href,
        "job_id": job_id,
        "dept": dept,
        "close_date": close_date,
    }


def scrape() -> List[dict]:
    list_url = "https://hkustcareers.hkust.edu.hk/join-us/current-opening/teaching-support"
    posts: List[dict] = []
    soup = fetch(list_url)
    if not soup:
        return posts

    cards = soup.select("div.job-card")
    if not cards:
        print("  [HKUST] no div.job-card on the listing page")
        return posts

    seen = set()
    for card in cards:
        fields = _card_fields(card)
        title = fields["title"]
        href = fields["href"]
        if not title or len(title) < 8 or not href:
            continue
        if not is_research_related(title, department=fields["dept"]):
            continue

        detail_url = urljoin(list_url, href)
        if detail_url in seen:
            continue
        seen.add(detail_url)

        ref = fields["job_id"] or hashlib.md5(detail_url.encode()).hexdigest()[:10]
        card_text = card.get_text("\n", strip=True)

        time.sleep(REQUEST_DELAY)
        detail = fetch(detail_url)
        body = job_content(detail)
        content = body or card_text

        posts.append(
            make_post(
                source=KEY,
                ref=ref,
                title=title,
                url=detail_url,
                content=content,
                close_date=fields["close_date"],
                department=fields["dept"] or None,
            )
        )
    return posts
