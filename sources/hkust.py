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
    same_listing,
)
from sources.dates import interpret_open_date

KEY = "HKUST"
NAME = "HKUST Clear Water Bay"


def _card_fields(card) -> dict:
    title_el = card.select_one("h3 a") or card.select_one("h3")
    title = title_el.get_text(" ", strip=True) if title_el else ""
    href = title_el.get("href") if title_el and title_el.has_attr("href") else ""

    job_id = ""
    dept = ""
    close_date = None
    open_date = None
    open_approx = False
    for p in card.select("p"):
        text = p.get_text(" ", strip=True)
        low = text.lower()
        if low.startswith("job id"):
            job_id = text.split(":")[-1].strip()
        elif "apply by" in low:
            close_date = parse_date(text.split(":")[-1].strip())
        elif "open date" in low:
            open_date, open_approx = interpret_open_date(text.split(":")[-1].strip())
        elif not dept and text and "date" not in low:
            dept = text
    return {
        "title": title,
        "href": href,
        "job_id": job_id,
        "dept": dept,
        "close_date": close_date,
        "open_date": open_date,
        "open_date_approximate": open_approx,
    }


def scrape() -> List[dict]:
    list_url = "https://hkustcareers.hkust.edu.hk/join-us/current-opening/teaching-support"
    posts: List[dict] = []
    soup = fetch(list_url)
    if not soup:
        note_counts(KEY, 0, 0)
        return posts

    cards = soup.select("div.job-card")
    if not cards:
        print("  [HKUST] no div.job-card on the listing page")
        note_counts(KEY, 0, 0)
        return posts

    seen = set()
    jobs = []
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
        jobs.append(
            (
                ref,
                title,
                fields["dept"],
                fields["close_date"],
                fields["open_date"],
                fields["open_date_approximate"],
                detail_url,
                card_text,
            )
        )

    print(f"  [HKUST] {len(cards)} cards, {len(jobs)} match the research filter")
    note_counts(KEY, len(cards), len(jobs))
    listing_rows = [
        f"{ref}|{title}|{dept}|{close}|{detail}"
        for ref, title, dept, close, _opened, _approx, detail, _card in jobs
    ]
    if same_listing(KEY, listing_rows):
        return ListingUnchanged()

    for ref, title, dept, close_date, open_date, open_approx, detail_url, card_text in jobs:
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
                close_date=close_date,
                department=dept or None,
                open_date=open_date,
                open_date_approximate=open_approx,
            )
        )
    prepare_posts(posts)
    finish_listing(KEY, posts)
    return posts
