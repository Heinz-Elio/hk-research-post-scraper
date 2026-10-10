"""
Site-specific scrapers for Hong Kong university research posts.
Each function returns a list of dicts with at least:
    id, title, close_date, content, url, source
"""

import time
import hashlib
import re
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_DELAY = 1.3  # seconds between detail page requests

RESEARCH_KEYWORDS = [
    "research assistant", "research associate", "research fellow",
    "post-doctoral", "postdoctoral", "project assistant",
    "senior research", "junior research", "research officer",
    "research support", "technical officer",  # sometimes research-related
]


def fetch(url: str, timeout: int = 25) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        print(f"  [fetch error] {url[:80]}... → {e}")
        return None


def parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    if text in ("", "-", "N/A", "Until filled", "Open until filled", "—"):
        return None
    try:
        # Prefer day-first for many HK sites, but dateutil is smart
        dt = date_parser.parse(text, fuzzy=True, dayfirst=False)
        return dt.date().isoformat()
    except Exception:
        return None


def is_research_related(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in RESEARCH_KEYWORDS)


def make_id(source: str, ref: str) -> str:
    clean = re.sub(r"[^\w\-]", "_", str(ref).strip())
    return f"{source}_{clean}"


def safe_text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


# ------------------------------------------------------------------
# 1. HKU
# ------------------------------------------------------------------
def scrape_hku() -> List[dict]:
    """https://jobs.hku.hk/en/listing/"""
    base = "https://jobs.hku.hk"
    # Request more items per page
    listing_url = f"{base}/en/listing/?page-items=100"
    posts = []
    soup = fetch(listing_url)
    if not soup:
        return posts

    for a in soup.select("a.job-link"):
        title = a.get_text(strip=True)
        if not is_research_related(title):
            continue

        href = a.get("href") or ""
        detail_url = urljoin(base, href)

        # Ref is usually the numeric part after /job/
        m = re.search(r"/job/(\d+)", href)
        ref = m.group(1) if m else hashlib.md5(href.encode()).hexdigest()[:10]

        # Closing date lives in the same <tr>
        close_date = None
        row = a.find_parent("tr")
        if row:
            tds = row.find_all("td")
            if len(tds) >= 4:
                close_date = parse_date(tds[-1].get_text(strip=True))

        # Detail page for full content
        time.sleep(REQUEST_DELAY)
        detail = fetch(detail_url)
        content = ""
        if detail:
            # Prefer the main job description block
            main = (
                detail.select_one(".job-description")
                or detail.select_one("#content")
                or detail.select_one("article")
                or detail.select_one("main")
                or detail
            )
            content = main.get_text("\n", strip=True)

        posts.append({
            "id": make_id("HKU", ref),
            "title": title,
            "close_date": close_date,
            "content": content,
            "url": detail_url,
            "source": "HKU",
        })
    return posts


# ------------------------------------------------------------------
# 2. PolyU (Research / Project Posts)
# ------------------------------------------------------------------
def scrape_polyu() -> List[dict]:
    """https://jobs.polyu.edu.hk/research.php"""
    url = "https://jobs.polyu.edu.hk/research.php"
    posts = []
    soup = fetch(url)
    if not soup:
        return posts

    table = soup.find("table")
    if not table:
        return posts

    for row in table.find_all("tr")[1:]:
        tds = row.find_all("td")
        if len(tds) < 5:
            continue

        dept = safe_text(tds[0])
        title_cell = tds[1]
        title = safe_text(title_cell)
        project = safe_text(tds[2])
        close_raw = safe_text(tds[3])
        ref = safe_text(tds[4])

        if not is_research_related(title):
            continue

        a = title_cell.find("a")
        detail_url = urljoin(url, a["href"]) if a and a.get("href") else url
        close_date = parse_date(close_raw)

        time.sleep(REQUEST_DELAY)
        content = f"Department: {dept}\nProject Title: {project}\n\n"
        detail = fetch(detail_url)
        if detail:
            # Many PolyU posts are short HTML or link to PDF
            content += detail.get_text("\n", strip=True)[:8000]

        posts.append({
            "id": make_id("PolyU", ref),
            "title": title,
            "close_date": close_date,
            "content": content,
            "url": detail_url,
            "source": "PolyU",
        })
    return posts


# ------------------------------------------------------------------
# 3. CityU
# ------------------------------------------------------------------
def scrape_cityu() -> List[dict]:
    """https://jobs1.cityu.edu.hk/apply/Default.aspx?jobtype=RS"""
    url = "https://jobs1.cityu.edu.hk/apply/Default.aspx?jobtype=RS"
    posts = []
    soup = fetch(url)
    if not soup:
        return posts

    # The page has a table of research positions
    table = soup.find("table")
    if not table:
        # fallback: look for any links that look like jobs
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if is_research_related(title):
                posts.append({
                    "id": make_id("CityU", hashlib.md5(a["href"].encode()).hexdigest()[:10]),
                    "title": title,
                    "close_date": None,
                    "content": title,
                    "url": urljoin(url, a["href"]),
                    "source": "CityU",
                })
        return posts

    for row in table.find_all("tr")[1:]:
        tds = row.find_all("td")
        if len(tds) < 2:
            continue

        title = safe_text(tds[0])
        if not is_research_related(title):
            continue

        dept = safe_text(tds[1]) if len(tds) > 1 else ""
        close_raw = safe_text(tds[2]) if len(tds) > 2 else ""
        close_date = parse_date(close_raw)

        a = tds[0].find("a")
        detail_url = urljoin(url, a["href"]) if a and a.get("href") else url
        ref = a["href"].split("=")[-1] if a and a.get("href") else hashlib.md5(title.encode()).hexdigest()[:8]

        time.sleep(REQUEST_DELAY)
        content = f"Department: {dept}\n"
        detail = fetch(detail_url)
        if detail:
            content += detail.get_text("\n", strip=True)[:8000]

        posts.append({
            "id": make_id("CityU", ref),
            "title": title,
            "close_date": close_date,
            "content": content,
            "url": detail_url,
            "source": "CityU",
        })
    return posts


# ------------------------------------------------------------------
# 4. CUHK (Taleo)
# ------------------------------------------------------------------
def scrape_cuhk() -> List[dict]:
    """
    CUHK Taleo non-teaching careers.
    Note: Taleo is JS-heavy; this scraper gets the initial listing.
    For very complete results a browser (Playwright) would be better.
    """
    url = (
        "https://cuhk.taleo.net/careersection/cu_career_non_teach/"
        "jobsearch.ftl?lang=en&portal=8115020119"
    )
    posts = []
    soup = fetch(url)
    if not soup:
        return posts

    # Taleo renders rows with class even/odd
    for row in soup.select("tr.even, tr.odd"):
        title_a = row.select_one("a[href*='jobdetail']")
        if not title_a:
            continue
        title = title_a.get_text(strip=True)
        if not is_research_related(title):
            continue

        detail_url = urljoin(url, title_a["href"])
        # Extract job number if possible
        job_num = ""
        tds = row.find_all("td")
        if tds:
            job_num = safe_text(tds[0])

        ref = job_num or hashlib.md5(detail_url.encode()).hexdigest()[:10]

        # Closing date is often not in the list view
        close_date = None

        time.sleep(REQUEST_DELAY)
        content = ""
        detail = fetch(detail_url)
        if detail:
            content = detail.get_text("\n", strip=True)[:10000]

        posts.append({
            "id": make_id("CUHK", ref),
            "title": title,
            "close_date": close_date,
            "content": content,
            "url": detail_url,
            "source": "CUHK",
        })
    return posts


# ------------------------------------------------------------------
# 5. HKUST (Clear Water Bay)
# ------------------------------------------------------------------
def scrape_hkust() -> List[dict]:
    """
    Official portal: https://hkustcareers.hkust.edu.hk
    Current openings often redirect into categories.
    We try the research-support path and the general current-opening page.
    """
    posts = []
    candidates = [
        "https://hkustcareers.hkust.edu.hk/join-us/current-opening",
        "https://hkustcareers.hkust.edu.hk/join-us/current-opening/teaching-support",
    ]

    for list_url in candidates:
        soup = fetch(list_url)
        if not soup:
            continue

        # Look for job cards or links containing research keywords
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if not title or not is_research_related(title):
                continue
            if len(title) < 8:  # skip menu items
                continue

            detail_url = urljoin(list_url, a["href"])
            ref = hashlib.md5(detail_url.encode()).hexdigest()[:10]

            # Avoid duplicates
            if any(p["url"] == detail_url for p in posts):
                continue

            time.sleep(REQUEST_DELAY)
            content = ""
            detail = fetch(detail_url)
            if detail:
                content = detail.get_text("\n", strip=True)[:8000]

            posts.append({
                "id": make_id("HKUST", ref),
                "title": title,
                "close_date": None,  # often not shown on list
                "content": content,
                "url": detail_url,
                "source": "HKUST",
            })
    return posts


# ------------------------------------------------------------------
# 6. HKUST Guangzhou
# ------------------------------------------------------------------
def scrape_hkust_gz() -> List[dict]:
    url = "https://jobs.hkust-gz.edu.cn/"
    # alternative: https://career.hkust-gz.edu.cn/en/career
    posts = []
    soup = fetch(url)
    if not soup:
        # try English career portal
        soup = fetch("https://career.hkust-gz.edu.cn/en/career")
        if not soup:
            return posts

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not is_research_related(title):
            continue
        detail_url = urljoin(url, a["href"])
        ref = hashlib.md5(detail_url.encode()).hexdigest()[:10]

        time.sleep(REQUEST_DELAY)
        content = ""
        detail = fetch(detail_url)
        if detail:
            content = detail.get_text("\n", strip=True)[:8000]

        posts.append({
            "id": make_id("HKUST-GZ", ref),
            "title": title,
            "close_date": None,
            "content": content,
            "url": detail_url,
            "source": "HKUST-GZ",
        })
    return posts


# ------------------------------------------------------------------
# 7. HKBU
# ------------------------------------------------------------------
def scrape_hkbu() -> List[dict]:
    url = "https://hr.hkbu.edu.hk/careers/"
    posts = []
    soup = fetch(url)
    if not soup:
        return posts

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not is_research_related(title):
            continue
        detail_url = urljoin(url, a["href"])
        ref = hashlib.md5(detail_url.encode()).hexdigest()[:10]

        time.sleep(REQUEST_DELAY)
        content = ""
        detail = fetch(detail_url)
        if detail:
            content = detail.get_text("\n", strip=True)[:8000]

        posts.append({
            "id": make_id("HKBU", ref),
            "title": title,
            "close_date": None,
            "content": content,
            "url": detail_url,
            "source": "HKBU",
        })
    return posts


# ------------------------------------------------------------------
# 8. Lingnan University
# ------------------------------------------------------------------
def scrape_lingnan() -> List[dict]:
    url = "https://www.ln.edu.hk/careers"
    posts = []
    soup = fetch(url)
    if not soup:
        return posts

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not is_research_related(title):
            continue
        detail_url = urljoin(url, a["href"])
        ref = hashlib.md5(detail_url.encode()).hexdigest()[:10]

        time.sleep(REQUEST_DELAY)
        content = ""
        detail = fetch(detail_url)
        if detail:
            content = detail.get_text("\n", strip=True)[:8000]

        posts.append({
            "id": make_id("Lingnan", ref),
            "title": title,
            "close_date": None,
            "content": content,
            "url": detail_url,
            "source": "Lingnan",
        })
    return posts


# ------------------------------------------------------------------
# 9. EdUHK
# ------------------------------------------------------------------
def scrape_eduhk() -> List[dict]:
    url = "https://www.eduhk.hk/careers/"
    # Chinese version sometimes richer: https://www.eduhk.hk/zht/current-openings
    posts = []
    for u in [url, "https://www.eduhk.hk/zht/current-openings"]:
        soup = fetch(u)
        if not soup:
            continue
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if not is_research_related(title):
                continue
            detail_url = urljoin(u, a["href"])
            ref = hashlib.md5(detail_url.encode()).hexdigest()[:10]

            if any(p["url"] == detail_url for p in posts):
                continue

            time.sleep(REQUEST_DELAY)
            content = ""
            detail = fetch(detail_url)
            if detail:
                content = detail.get_text("\n", strip=True)[:8000]

            posts.append({
                "id": make_id("EdUHK", ref),
                "title": title,
                "close_date": None,
                "content": content,
                "url": detail_url,
                "source": "EdUHK",
            })
    return posts


# ------------------------------------------------------------------
# 10. HKMU (Taleo)
# ------------------------------------------------------------------
def scrape_hkmu() -> List[dict]:
    url = "https://hkmu.taleo.net/careersection/ex_full_time/jobsearch.ftl?lang=en"
    posts = []
    soup = fetch(url)
    if not soup:
        return posts

    for row in soup.select("tr.even, tr.odd, tr"):
        title_a = row.select_one("a[href*='jobdetail']")
        if not title_a:
            continue
        title = title_a.get_text(strip=True)
        if not is_research_related(title):
            continue

        detail_url = urljoin(url, title_a["href"])
        ref = hashlib.md5(detail_url.encode()).hexdigest()[:10]

        time.sleep(REQUEST_DELAY)
        content = ""
        detail = fetch(detail_url)
        if detail:
            content = detail.get_text("\n", strip=True)[:10000]

        posts.append({
            "id": make_id("HKMU", ref),
            "title": title,
            "close_date": None,
            "content": content,
            "url": detail_url,
            "source": "HKMU",
        })
    return posts


# ------------------------------------------------------------------
# Registry – used by main script
# ------------------------------------------------------------------
SCRAPERS = {
    "HKU": scrape_hku,
    "PolyU": scrape_polyu,
    "CityU": scrape_cityu,
    "CUHK": scrape_cuhk,
    "HKUST": scrape_hkust,
    "HKUST-GZ": scrape_hkust_gz,
    "HKBU": scrape_hkbu,
    "Lingnan": scrape_lingnan,
    "EdUHK": scrape_eduhk,
    "HKMU": scrape_hkmu,
}
