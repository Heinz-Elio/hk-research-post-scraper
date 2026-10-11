"""
Site-specific scrapers for Hong Kong university research posts.
Each function returns a list of dicts with at least:
    id, title, close_date, content, url, source

Focus: Engineering and Science related research positions only.
Playwright is used for JS-heavy sites (HKBU, Lingnan).
"""

import time
import hashlib
import re
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Optional Playwright (for JS-heavy sites: HKBU, Lingnan)
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    sync_playwright = None

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
PLAYWRIGHT_TIMEOUT = 60000  # ms

# Must look like a research-type post
RESEARCH_KEYWORDS = [
    "research", "technical",
]

# Focus on Engineering & Science related posts
STEM_KEYWORDS = [
    # Broad
    "engineering", "science",
    # Computer / AI / Data
    "computer", "computing", "software", "artificial intelligence", "machine learning",
    "deep learning", "data science", "data analytic", "information system", "robotic",
    "automation",
    # Engineering disciplines
    "electronic", "mechanical", "civil",
    "biomedical engineering", "industrial engineering", "systems engineering",
    "aerospace", "aviation",
    # Natural sciences
    "environmental science", "earth science", "geology", "mathematics", "statistic"
    # Applied / interdisciplinary
    "bioinformatics", "computational", "sensor", "signal processing",
    "control system"
]


def fetch(url: str, timeout: int=25, retry=5) -> Optional[BeautifulSoup]:
    for rt in range(retry):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)

            if r.status_code == 202:
                print('HTTP response:', r.status_code)
                time.sleep(1)
                continue

            r.raise_for_status()
            print('HTTP response:', r.status_code)
            if r.text:
                return BeautifulSoup(r.text, "lxml")
            else:
                continue

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
        dt = date_parser.parse(text, fuzzy=True, dayfirst=False)
        return dt.date().isoformat()
    except Exception:
        return None


def is_research_related(title: str, department: str = "", project: str = "") -> bool:
    """
    Keep only research-type posts related to Engineering or Science.
    Uses title + department + project title together (more reliable than title alone).
    """
    title_l = (title or "").lower()
    dept_l = (department or "").lower()
    project_l = (project or "").lower()
    combined = f"{title_l} {dept_l} {project_l}"

    # 1. Must look like a research post
    is_research = any(kw in title_l for kw in RESEARCH_KEYWORDS)
    if not is_research:
        return False

    # 2. Must match Engineering / Science (checked across title + dept + project)
    is_stem = any(kw in combined for kw in STEM_KEYWORDS)
    return is_stem


def make_id(source: str, ref: str) -> str:
    clean = re.sub(r"[^\w\-]", "_", str(ref).strip())
    return f"{source}_{clean}"


def safe_text(el) -> str:
    return el.get_text(strip=True) if el else ""


# ------------------------------------------------------------------
# 1. HKU
# ------------------------------------------------------------------
def scrape_hku() -> List[dict]:
    """https://jobs.hku.hk/en/listing/"""
    base = "https://jobs.hku.hk"
    listing_url = f"{base}/en/listing/"
    posts = []
    soup = fetch(listing_url)
    if not soup:
        return posts

    table = soup.select_one("tbody#recent-jobs-content")
    for tr in table.select("tr"):
        tds = tr.select("td")

        job_num = safe_text(tds[0].select_one("span.job-externalJobNo"))
        title = safe_text(tds[1].select_one("a.job-link"))
        href = tds[1].select_one("a.job-link").get("href") or ""
        detail_url = urljoin(base, href)
        dept = safe_text(tds[2])
        close_date = tds[3].select_one("time").get("datetime")

        if not is_research_related(title, department=dept):
            continue

        time.sleep(REQUEST_DELAY)
        detail = fetch(detail_url)
        content = ""
        if detail:
            main = detail.select_one("div#job-content")
            content = main.get_text("\n", strip=True)

        print(job_num, title, close_date, content[:100], detail_url)
        posts.append({
            "id": make_id("HKU", job_num),
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

    for row in soup.select("tr.ITS_clickableTableRow"):
        tds = row.select("td")

        url_part = row.get("data-href")
        dept = safe_text(tds[0])
        title_cell = tds[1]
        title = safe_text(title_cell)
        project = safe_text(tds[2])
        close_raw = safe_text(tds[3])
        ref = safe_text(tds[4])

        if not is_research_related(title, department=dept, project=project):
            continue

        detail_url = url.replace("research.php", url_part)
        close_date = parse_date(close_raw)

        time.sleep(REQUEST_DELAY)
        content = f"Department: {dept}\nProject Title: {project}\n\n"
        detail = fetch(detail_url)
        if detail:
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

    table = soup.find("table",id="MainContent_gvJobResearch")
    # if not table:
    #     for a in soup.find_all("a", href=True):
    #         title = a.get_text(strip=True)
    #         if is_research_related(title):
    #             posts.append({
    #                 "id": make_id("CityU", hashlib.md5(a["href"].encode()).hexdigest()[:10]),
    #                 "title": title,
    #                 "close_date": None,
    #                 "content": title,
    #                 "url": urljoin(url, a["href"]),
    #                 "source": "CityU",
    #             })
    #     return posts

    for row in table.find_all("tr")[1:]:
        tds = row.find_all("td")
        if len(tds) < 2:
            continue

        title = safe_text(tds[0])
        dept = safe_text(tds[1]) if len(tds) > 1 else ""
        if not is_research_related(title, department=dept):
            continue

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
    url = (
        "https://cuhk.taleo.net/careersection/cu_career_non_teach/"
        "jobsearch.ftl?lang=en&portal=8115020119"
    )
    posts = []
    soup = fetch(url)
    if not soup:
        return posts

    for row in soup.select("tr.even, tr.odd"):
        job_num = safe_text(row.select("th span"))

        tds = row.find_all("td")
        a =tds[1].select("a")
        href = a["href"]
        title = safe_text(a)
        dept = safe_text(tds[2].select("span"))

        if not is_research_related(title, department=dept):
            continue

        detail_url = urljoin(url, href)
        close_date = None

        time.sleep(REQUEST_DELAY)
        detail = fetch(detail_url)
        content = ""
        if detail:
            main = detail.select("div#requisitionDescriptionInterface.ID1448.row1 p")
            content += main.get_text("\n", strip=True)[:10000]
            close_date = safe_text(detail.select("div#requisitionDescriptionInterface.reqUnpostingDate.row1 span"))

        posts.append({
            "id": make_id("CUHK", job_num),
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
    Main listing: https://hkustcareers.hkust.edu.hk/join-us/current-opening/teaching-support
    """
    list_url = "https://hkustcareers.hkust.edu.hk/join-us/current-opening/teaching-support"
    posts = []
    soup = fetch(list_url)
    if not soup:
        return posts

    for h3 in soup.select("h3"):
        a = h3.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 8:
            continue

        detail_url = urljoin(list_url, a["href"])

        dept = ""
        close_date = None
        job_id = ""
        node = h3.next_sibling
        while node and getattr(node, "name", None) != "h3":
            text = ""
            if hasattr(node, "get_text"):
                text = node.get_text(" ", strip=True)
            elif isinstance(node, str):
                text = node.strip()
            if not text:
                node = getattr(node, "next_sibling", None)
                continue
            low = text.lower()
            if low.startswith("job id"):
                job_id = text.split(":")[-1].strip()
            elif "apply by" in low:
                close_date = parse_date(text.split(":")[-1].strip())
            elif "open date" in low:
                pass
            elif not dept and len(text) > 5 and "date" not in low and "job id" not in low:
                dept = text
            node = getattr(node, "next_sibling", None)

        if not is_research_related(title, department=dept):
            continue

        ref = job_id or hashlib.md5(detail_url.encode()).hexdigest()[:10]

        if any(p["url"] == detail_url for p in posts):
            continue

        time.sleep(REQUEST_DELAY)
        content = f"Department: {dept}\n" if dept else ""
        detail = fetch(detail_url)
        if detail:
            content += detail.get_text("\n", strip=True)[:8000]

        posts.append({
            "id": make_id("HKUST", ref),
            "title": title,
            "close_date": close_date,
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
    posts = []
    soup = fetch(url)
    if not soup:
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
# 7. HKBU (Playwright – Oracle Cloud HCM)
# ------------------------------------------------------------------
def scrape_hkbu() -> List[dict]:
    """
    Official Oracle Cloud HCM portal (JS-rendered):
    https://fa-ewqq-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/hkbu/jobs?keyword=research&mode=job-location
    """
    if not HAS_PLAYWRIGHT:
        print("  [HKBU] Playwright not installed → skip (pip install playwright && playwright install chromium)")
        return []

    url = (
        "https://fa-ewqq-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/"
        "CandidateExperience/en/sites/hkbu/jobs?keyword=research&mode=job-location"
    )
    posts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT)
            page.wait_for_selector('a[href*="/job/"]', timeout=15000)
            page.mouse.wheel(0, 2500)
            time.sleep(1.2)

            cards = page.eval_on_selector_all(
                'a[href*="/job/"]',
                """els => {
                    const seen = new Set();
                    const out = [];
                    for (const a of els) {
                        if (seen.has(a.href)) continue;
                        seen.add(a.href);
                        const card = a.closest('[class*="job"], [class*="card"], li, article, div') || a.parentElement;
                        out.push({
                            href: a.href,
                            title: (a.innerText || '').trim().split('\\n')[0].slice(0, 200),
                            cardText: (card ? card.innerText : a.innerText || '').trim().slice(0, 700)
                        });
                    }
                    return out;
                }"""
            )
        except Exception as e:
            print(f"  [HKBU] Playwright error: {e}")
            browser.close()
            return []

        browser.close()

    for card in cards:
        title = (card.get("title") or "").strip()
        href = card.get("href") or ""
        card_text = card.get("cardText") or ""
        if not title or len(title) < 8:
            continue

        dept = ""
        if "," in title:
            dept = title.split(",")[-1].strip()
        if not dept:
            m = re.search(r"sits under the ([^.\n]+)", card_text, re.I)
            if m:
                dept = m.group(1).strip()

        if not is_research_related(title, department=dept or card_text):
            continue

        m = re.search(r"/job/(\d+)", href)
        ref = m.group(1) if m else hashlib.md5(href.encode()).hexdigest()[:10]

        posts.append({
            "id": make_id("HKBU", ref),
            "title": title,
            "close_date": None,
            "content": f"Department: {dept}\n\n{card_text}",
            "url": href,
            "source": "HKBU",
        })

    return posts


# ------------------------------------------------------------------
# 8. Lingnan University (Playwright – CSOD)
# ------------------------------------------------------------------
def scrape_lingnan() -> List[dict]:
    """
    Cornerstone OnDemand (CSOD) career site, pre-filtered (JS-rendered):
    https://lingnan.csod.com/ux/ats/careersite/4/home?c=lingnan&cfdd[0][id]=151&cfdd[0][options][0]=103
    """
    if not HAS_PLAYWRIGHT:
        print("  [Lingnan] Playwright not installed → skip (pip install playwright && playwright install chromium)")
        return []

    url = (
        "https://lingnan.csod.com/ux/ats/careersite/4/home"
        "?c=lingnan&cfdd[0][id]=151&cfdd[0][options][0]=103"
    )
    posts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT)
            page.wait_for_timeout(3000)
            page.mouse.wheel(0, 2000)
            time.sleep(1.0)

            cards = page.eval_on_selector_all(
                'a[href*="JobDetail"], a[href*="jobdetail"], a[href*="/jobs/"], a[href*="requisition"]',
                """els => {
                    const seen = new Set();
                    const out = [];
                    for (const a of els) {
                        if (seen.has(a.href)) continue;
                        seen.add(a.href);
                        const card = a.closest('[class*="job"], [class*="card"], li, article, div, tr') || a.parentElement;
                        out.push({
                            href: a.href,
                            title: (a.innerText || '').trim().split('\\n')[0].slice(0, 200),
                            cardText: (card ? card.innerText : a.innerText || '').trim().slice(0, 700)
                        });
                    }
                    return out;
                }"""
            )

            if not cards:
                cards = page.eval_on_selector_all(
                    "a[href]",
                    """els => {
                        const seen = new Set();
                        const out = [];
                        for (const a of els) {
                            const t = (a.innerText || '').trim();
                            if (t.length < 12 || t.length > 180) continue;
                            if (seen.has(a.href)) continue;
                            seen.add(a.href);
                            out.push({
                                href: a.href,
                                title: t.split('\\n')[0].slice(0, 200),
                                cardText: t.slice(0, 700)
                            });
                        }
                        return out;
                    }"""
                )
        except Exception as e:
            print(f"  [Lingnan] Playwright error: {e}")
            browser.close()
            return []

        browser.close()

    for card in cards:
        title = (card.get("title") or "").strip()
        href = card.get("href") or ""
        card_text = card.get("cardText") or ""
        if not title or len(title) < 8:
            continue
        if not is_research_related(title, department=card_text):
            continue

        ref = hashlib.md5(href.encode()).hexdigest()[:10]
        if any(p["url"] == href for p in posts):
            continue

        posts.append({
            "id": make_id("Lingnan", ref),
            "title": title,
            "close_date": None,
            "content": card_text,
            "url": href,
            "source": "Lingnan",
        })

    return posts


# ------------------------------------------------------------------
# 9. EdUHK
# ------------------------------------------------------------------
def scrape_eduhk() -> List[dict]:
    """
    Research Support Posts listing:
    https://www.eduhk.hk/en/current-openings?category=research-support-posts&department=&q=
    """
    url = "https://www.eduhk.hk/en/current-openings?category=research-support-posts&department=&q="
    posts = []
    soup = fetch(url)
    if not soup:
        return posts

    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        if "/cms/f/career/" not in href and ".pdf" not in href.lower():
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 8:
            continue

        dept = ""
        close_date = None
        ref = ""
        parent = a.parent
        if parent:
            text_block = parent.get_text("\n", strip=True)
            node = parent.next_sibling
            extra = []
            while node and len(extra) < 12:
                if hasattr(node, "get_text"):
                    t = node.get_text(" ", strip=True)
                    if t:
                        extra.append(t)
                node = getattr(node, "next_sibling", None)
            text_block = text_block + "\n" + "\n".join(extra)

            lines = [ln.strip() for ln in text_block.splitlines() if ln.strip()]
            for i, ln in enumerate(lines):
                low = ln.lower()
                if low.startswith("ref"):
                    ref = ln.split(":")[-1].strip() if ":" in ln else (lines[i + 1] if i + 1 < len(lines) else "")
                elif "close date" in low:
                    val = ln.split(":")[-1].strip() if ":" in ln else (lines[i + 1] if i + 1 < len(lines) else "")
                    close_date = parse_date(val)
                elif not dept and ln != title and "date" not in low and "ref" not in low and len(ln) > 5:
                    if not any(k in low for k in ("ad date", "close date", "ref")):
                        dept = ln

        if not is_research_related(title, department=dept):
            continue

        detail_url = urljoin(url, href)
        if not ref:
            ref = hashlib.md5(detail_url.encode()).hexdigest()[:10]

        if any(p["url"] == detail_url for p in posts):
            continue

        content = f"Department: {dept}\nTitle: {title}\n"
        posts.append({
            "id": make_id("EdUHK", ref),
            "title": title,
            "close_date": close_date,
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
# Registry
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
