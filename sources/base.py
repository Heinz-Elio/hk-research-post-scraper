"""
Shared helpers and Source protocol for school/org career-page scrapers.

Each source module should expose:
    KEY: str
    NAME: str
    scrape() -> list[dict]

Returned dicts must include: id, title, url, source, content
Optional listing hints: close_date, department, project
"""

from __future__ import annotations

import atexit
import re
import ssl
import time
from typing import List, Optional, Protocol
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    sync_playwright = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_DELAY = 1.3
PLAYWRIGHT_TIMEOUT = 60000

RESEARCH_KEYWORDS = [
    "research",
    "technical",
    "post-doc",
    "postdoc",
    "postdoctoral",
]

CONTENT_SELECTORS = [
    "div.ITS_Content_RichTextEditor",
    "div#job-content",
    "#requisitionDescriptionInterface .editablesection",
    "div.editablesection",
    "div.job-description",
    "article .job-content",
    "#cityu-content",
    "div#content",
]

STEM_KEYWORDS = [
    "engineering",
    "science",
    "computer",
    "computing",
    "software",
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "data science",
    "data analytic",
    "information system",
    "robotic",
    "automation",
    "electronic",
    "mechanical",
    "civil",
    "biomedical engineering",
    "industrial engineering",
    "systems engineering",
    "aerospace",
    "aviation",
    "environmental science",
    "earth science",
    "geology",
    "mathematics",
    "statistic",
    "bioinformatics",
    "computational",
    "sensor",
    "signal processing",
    "control system",
]


class Source(Protocol):
    KEY: str
    NAME: str

    def scrape(self) -> List[dict]:
        ...


class _LegacySSLAdapter(HTTPAdapter):
    """EdUHK still requires legacy TLS renegotiation."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


_SESSION = requests.Session()
_SESSION.mount("https://", _LegacySSLAdapter())

_PW = None
_BROWSER = None
_CONTEXT = None
_BROWSER_WARNED = False


def is_challenge_page(soup: Optional[BeautifulSoup]) -> bool:
    if not soup:
        return True
    if soup.select_one("#challenge-container, iframe#main-iframe"):
        return True
    html = str(soup)[:4000].lower()
    return "incapsula incident" in html or "awswafintegration" in html


def _ready(soup: Optional[BeautifulSoup], wait_for: Optional[str]) -> bool:
    if not soup or is_challenge_page(soup):
        return False
    if wait_for and not soup.select(wait_for):
        return False
    # An empty shell (Interfolio, PeopleSoft) is not the job page yet.
    if len(soup.get_text(" ", strip=True)) < 80:
        return False
    return True


def _expand_frame(soup: Optional[BeautifulSoup], page_url: str, timeout: int, retry: int) -> Optional[BeautifulSoup]:
    """PeopleSoft wraps the job text in a frameset. The wrapper page itself is empty."""
    if not soup:
        return soup
    frame = soup.find("frame", attrs={"name": "TargetContent"})
    src = (frame.get("src") if frame else "") or ""
    if not src or len(soup.get_text(" ", strip=True)) > 400:
        return soup
    inner = _fetch_http(urljoin(page_url, src), timeout=timeout, retry=max(retry, 1))
    if inner and len(inner.get_text(" ", strip=True)) > 200:
        return inner
    return soup


def fetch(
    url: str,
    timeout: int = 25,
    retry: int = 3,
    wait_for: Optional[str] = None,
) -> Optional[BeautifulSoup]:
    """HTTP first. A real browser is used when the site shows a bot check or the waited-for element is missing."""
    soup = _expand_frame(_fetch_http(url, timeout=timeout, retry=retry), url, timeout, retry)
    if _ready(soup, wait_for):
        return soup

    rendered = _expand_frame(_fetch_browser(url, wait_for=wait_for), url, timeout, retry)
    if _ready(rendered, wait_for):
        _sync_cookies()
        # Later pages on this host can stay on plain HTTP, but only when that
        # response actually contains the job. A cookie wall is longer than the
        # empty shell and would otherwise replace the rendered page.
        retried = _expand_frame(_fetch_http(url, timeout=timeout, retry=1), url, timeout, retry)
        if _ready(retried, wait_for) and len(job_content(retried)) > 80:
            return retried
        return rendered
    return rendered or soup


def _fetch_http(url: str, timeout: int = 25, retry: int = 3) -> Optional[BeautifulSoup]:
    last_error = None
    for _attempt in range(retry):
        try:
            r = _SESSION.get(url, headers=HEADERS, timeout=timeout)

            if _is_hard_block(r.text) or r.status_code == 202 or _looks_like_challenge(r.text):
                print("HTTP response:", r.status_code, "(bot check)")
                return None

            r.raise_for_status()
            print("HTTP response:", r.status_code)
            if r.text:
                soup = BeautifulSoup(r.text, "lxml")
                if is_challenge_page(soup):
                    print("HTTP response:", r.status_code, "(bot check)")
                    return None
                return soup
            return None

        except Exception as e:
            last_error = e
            print(f"  [fetch error] {url[:80]}... → {e}")
            time.sleep(1)
    if last_error:
        print(f"  [fetch give up] {url[:80]}")
    return None


def _warn_browser() -> None:
    global _BROWSER_WARNED
    if _BROWSER_WARNED:
        return
    _BROWSER_WARNED = True
    print(
        "  [browser] Bot check or late-loading page needs Playwright. "
        "pip install playwright && playwright install chromium"
    )


def _browser_context():
    global _PW, _BROWSER, _CONTEXT
    if _CONTEXT is not None:
        return _CONTEXT
    if not HAS_PLAYWRIGHT:
        _warn_browser()
        return None
    try:
        _PW = sync_playwright().start()
        launch_args = ["--disable-blink-features=AutomationControlled"]
        last_error = None
        for channel in ("chrome", "msedge", None):
            try:
                kwargs = {"headless": True, "args": launch_args}
                if channel:
                    kwargs["channel"] = channel
                _BROWSER = _PW.chromium.launch(**kwargs)
                break
            except Exception as e:
                last_error = e
                _BROWSER = None
        if _BROWSER is None:
            raise last_error or RuntimeError("no browser")
        _CONTEXT = _BROWSER.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        _CONTEXT.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return _CONTEXT
    except Exception as e:
        print(f"  [browser] could not start → {e}")
        _warn_browser()
        return None


def _sync_cookies() -> None:
    if _CONTEXT is None:
        return
    for cookie in _CONTEXT.cookies():
        _SESSION.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path") or "/",
        )


def _fetch_browser(url: str, wait_for: Optional[str] = None) -> Optional[BeautifulSoup]:
    context = _browser_context()
    if context is None:
        return None
    page = context.new_page()
    try:
        print(f"  [browser] {url[:80]}")
        page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)
        if wait_for:
            page.wait_for_selector(wait_for, timeout=30000)
        else:
            page.wait_for_function(
                """() => {
                    const text = document.body ? document.body.innerText : '';
                    const blocked = document.querySelector('#challenge-container, iframe#main-iframe');
                    const cookieOnly = /cookie preference center/i.test(text) && text.length < 4000;
                    return !blocked && !cookieOnly && text.length > 400;
                }""",
                timeout=30000,
            )
        html = page.content()
        _sync_cookies()
        return BeautifulSoup(html, "lxml")
    except Exception as e:
        print(f"  [browser] {url[:70]}... → {e}")
        try:
            html = page.content()
            if html and not _looks_like_challenge(html) and not _is_hard_block(html):
                _sync_cookies()
                return BeautifulSoup(html, "lxml")
        except Exception:
            pass
        return None
    finally:
        page.close()


def _close_browser() -> None:
    global _PW, _BROWSER, _CONTEXT
    try:
        if _CONTEXT is not None:
            _CONTEXT.close()
        if _BROWSER is not None:
            _BROWSER.close()
        if _PW is not None:
            _PW.stop()
    except Exception:
        pass
    _CONTEXT = None
    _BROWSER = None
    _PW = None


atexit.register(_close_browser)


def _is_hard_block(text: str) -> bool:
    low = (text or "")[:2500].lower()
    return "_incapsula_resource" in low or "incapsula incident" in low


def _looks_like_challenge(text: str) -> bool:
    if not text:
        return False
    low = text[:2500].lower()
    return "awswafintegration" in low or "_incapsula_resource" in low or "challenge-container" in low


def job_content(soup: Optional[BeautifulSoup]) -> str:
    """Text of the job description element, not the site chrome."""
    if not soup or is_challenge_page(soup):
        return ""
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node:
            text = node.get_text("\n", strip=True)
            if len(text) > 40:
                return text
    root = soup.select_one("main") or soup.body
    if not root:
        return ""
    for junk in root.select("header, footer, nav, script, style, noscript"):
        junk.decompose()
    return root.get_text("\n", strip=True)


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
    title_l = (title or "").lower()
    dept_l = (department or "").lower()
    project_l = (project or "").lower()
    combined = f"{title_l} {dept_l} {project_l}"

    is_research = any(kw in title_l for kw in RESEARCH_KEYWORDS)
    if not is_research:
        return False

    return any(kw in combined for kw in STEM_KEYWORDS)


def make_id(source: str, ref: str) -> str:
    clean = re.sub(r"[^\w\-]", "_", str(ref).strip())
    return f"{source}_{clean}"


def safe_text(el) -> str:
    return el.get_text(strip=True) if el else ""


def make_post(
    *,
    source: str,
    ref: str,
    title: str,
    url: str,
    content: str = "",
    close_date: Optional[str] = None,
    department: Optional[str] = None,
    project: Optional[str] = None,
) -> dict:
    post = {
        "id": make_id(source, ref),
        "title": title,
        "close_date": close_date,
        "content": content,
        "url": url,
        "source": source,
    }
    if department:
        post["department"] = department
    if project:
        post["project"] = project
    return post
