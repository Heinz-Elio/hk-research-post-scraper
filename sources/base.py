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
import hashlib
import json
import re
import ssl
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
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

_LISTING_HASH_PATH = Path(__file__).resolve().parent.parent / "listing_hashes.json"
_PENDING_LISTING: dict = {}
_READY_LISTING: dict = {}
_LISTING_COUNTS: dict = {}
_FORCE_RESCRAPE = False
_EMPTY_STORED: set = set()
# SHA-256 of "". A run that parsed no kept rows used to store this and then
# skip the source forever. It is never a successful listing fingerprint.
EMPTY_LISTING_HASH = hashlib.sha256(b"").hexdigest()
_MIN_SAVED_CONTENT = 80


class ListingUnchanged:
    """The job list hash matches the last successful scrape, so detail pages were skipped."""


def set_listing_hash_path(path: Path) -> None:
    """Point the hash file somewhere other than the repo (dry-run / tests)."""
    global _LISTING_HASH_PATH
    _LISTING_HASH_PATH = Path(path)


def configure_run(*, force: bool = False, sources_with_no_posts=None) -> None:
    """Reset per-run listing-hash state.

    ``force`` is the --force / --ignore-hashes switch. Sources with no active
    posts are re-scraped even when the stored hash matches, so a hash written
    before the JSON was saved cannot stick at zero posts.
    """
    global _FORCE_RESCRAPE
    _FORCE_RESCRAPE = bool(force)
    _EMPTY_STORED.clear()
    _EMPTY_STORED.update(sources_with_no_posts or ())
    _PENDING_LISTING.clear()
    _READY_LISTING.clear()
    _LISTING_COUNTS.clear()


def note_counts(source: str, listed: int, kept: int) -> None:
    """How many listing rows were seen, and how many passed the research filter."""
    _LISTING_COUNTS[source] = {"listed": int(listed), "kept": int(kept)}


def listing_counts() -> dict:
    return dict(_LISTING_COUNTS)


def _read_listing_hashes() -> dict:
    if not _LISTING_HASH_PATH.exists():
        return {}
    try:
        data = json.loads(_LISTING_HASH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def same_listing(source: str, rows: List[str]) -> bool:
    """True when this listing's jobs match the last run. Detail pages can be skipped.

    An empty row list, the empty-string fingerprint, and a source with no
    stored posts are never treated as unchanged.
    """
    fingerprint = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
    _PENDING_LISTING[source] = fingerprint
    if _FORCE_RESCRAPE or source in _EMPTY_STORED:
        return False
    if not rows or fingerprint == EMPTY_LISTING_HASH:
        return False
    stored = _read_listing_hashes().get(source)
    if not stored or stored == EMPTY_LISTING_HASH:
        return False
    if stored == fingerprint:
        print(f"  [{source}] listing unchanged")
        return True
    return False


def finish_listing(source: str, posts: List[dict]) -> None:
    """Remember a fingerprint to write only after the JSON save succeeds.

    Does not touch ``listing_hashes.json``. Empty results, the empty-string
    fingerprint, and scrapes whose detail text never arrived are dropped.
    """
    fingerprint = _PENDING_LISTING.get(source)
    if not fingerprint or fingerprint == EMPTY_LISTING_HASH:
        return
    if not posts:
        return
    if all(len((post.get("content") or "").strip()) < _MIN_SAVED_CONTENT for post in posts):
        return
    _READY_LISTING[source] = fingerprint


def commit_listing_hashes() -> None:
    """Write hashes for listings whose posts were just saved."""
    if not _READY_LISTING:
        return
    data = _read_listing_hashes()
    data.update(_READY_LISTING)
    _LISTING_HASH_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LISTING_HASH_PATH.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _READY_LISTING.clear()


def prepare_posts(posts: List[dict]) -> List[dict]:
    """Drop clerk grades found in the ad, then fill date fields.

    The listing filter already sees clerk wording in the title. Some ads only
    name the clerk grade in the body ("at the rank of Clerk", "Clerk grade").
    """
    from sources.dates import refine_dates

    kept: List[dict] = []
    for post in posts or []:
        if not isinstance(post, dict):
            continue
        if not is_research_related(
            post.get("title") or "",
            department=post.get("department") or "",
            project=post.get("project") or "",
            description=post.get("content") or "",
        ):
            continue
        refine_dates(post)
        kept.append(post)
    if isinstance(posts, list):
        posts[:] = kept
    return posts

# A research appointment in the title. Discipline is not required: a research
# assistant in history is still a research post. HKU appends a pay grade,
# "(at the rank of ...)", which is not the job.
_RANK = re.compile(
    r"\((?:at the rank of|holding the functional title of)\s*[^)]*\)",
    re.I,
)
_RESEARCH_ROLE = re.compile(
    r"research\s+assistants?"
    r"|research\s+associates?"
    r"|research\s+officers?"
    r"|research\s+fellows?"
    r"|research\s+engineers?"
    r"|research\s+scientists?"
    r"|research\s+professors?"
    r"|research\s+nurses?"
    r"|clinical\s+research"
    r"|post[-\s]?doctoral"
    r"|post[-\s]?docs?\b"
    r"|\bresearchers?\b"
    r"|project\s+fellows?"
    r"|data\s+analysts?"
    r"|data\s+scientists?"
    r"|research\s+analysts?"
    r"|研究助理|博士后|博士後|博后|研究员|研究員|副研究员",
    re.I,
)
# Project assistant/associate is a research grade in academic departments.
# The same words are also used for admissions and college admin posts.
_PROJECT_SUPPORT = re.compile(
    r"project\s+(?:assistants?|associates?)",
    re.I,
)
_ADMIN_OFFICE = re.compile(
    r"office of|admissions|institutional advancement|financial aid|"
    r"undergraduate studies|\bcollege\b|human resources|finance office|registry",
    re.I,
)
# Grants managers, clerks, and admissions staff are not research posts,
# even when the office name contains "research".
_ADMIN_ROLE = re.compile(
    r"executive\s+(?:assistant|officer)s?"
    r"|administrative\s+(?:officer|assistant|manager)s?"
    r"|\bclerks?\b"
    r"|clerical"
    r"|admissions"
    r"|human\s+resources"
    r"|finance\s+(?:officer|manager)s?"
    r"|financial\s+(?:officer|manager)s?"
    r"|\baccountants?\b"
    r"|receptionist"
    r"|secretar(?:y|ial)"
    r"|librarians?|library\s+assistants?"
    r"|programme\s+officers?"
    r"|program\s+officers?"
    r"|public\s+(?:affairs|engagement)"
    r"|student\s+services"
    r"|teaching\s+assistants?"
    r"|\b(?:senior\s+|assistant\s+|deputy\s+)?(?:general\s+)?managers?\b"
    r"|\bheads?\b"
    r"|行政(?:专员|主任|助理)|人事|财务|会计|文员|秘书",
    re.I,
)
_TECHNICAL_ROLE = re.compile(
    r"technical\s+(?:officer|assistant|manager)s?"
    r"|\btechnicians?\b"
    r"|\bscientists?\b"
    r"|scientific\s+officers?"
    r"|技术助理|技術助理|技术专员|技術專員|工程师|工程師",
    re.I,
)
_PROJECT_LEAD = re.compile(
    r"project\s+(?:officer|coordinator|co-ordinator)s?",
    re.I,
)
_FACILITIES_ENGINEER = re.compile(r"设施|维护|维修|物业|保洁|清洁")
_LAB_UNIT = re.compile(r"\blaborator(?:y|ies)\b|\blabs?\b|实验室", re.I)
# Used only for technical / scientist / engineer titles, not as a gate on
# research assistants. Bare "science" is omitted so "science park" and
# "social sciences" do not qualify a technician.
_DISCIPLINE = re.compile(
    r"artificial intelligence|\bmachine learning\b|\bdeep learning\b|\bai\b"
    r"|data science|analytics|statistic|bioinformatic"
    r"|computer|computing|software|informatic|algorithm"
    r"|engineering|robotic|electronic|mechanical|biomedical"
    r"|physics|chemistr|biolog|bioscience|life science|neuro"
    r"|mathematic|geograph|geospatial|\bgis\b|transport|urban"
    r"|environment|climate|energy|optical|photonic|quantum"
    r"|medicin|clinical|nurs|health|veterinary|pharmac|computational|material|\bbrain\b"
    r"|生物|物理|化学|医学|计算机|數據|数据|人工智能|算法|机械|電子|电子|光电|嵌入式|电路",
    re.I,
)
_RESEARCH_WORD = re.compile(r"research|研究", re.I)
# A clerk grade excludes the post even when the functional title is a research
# or project grade. The pay-grade parenthesis is stripped for other checks,
# so clerk wording has to be read from the raw title.
_CLERK_WORD = re.compile(
    r"\bclerks?\b|\bclerical\b|文員|文员|文書|文书",
    re.I,
)
_CLERK_RANK = re.compile(
    r"at the rank of\s+(?:[^.\n]{0,50})?(?:\bclerks?\b|\bclerical\b)"
    r"|holding the functional title of\s+(?:[^.\n]{0,50})?(?:\bclerks?\b|\bclerical\b)"
    r"|\bclerks?(?:\s+(?:[ivx]+|\d+))?\s+grades?\b"
    r"|\bclerical\s+grades?\b"
    r"|(?:文員|文员|文書|文书)\s*職[級级衔銜]"
    r"|職[級级衔銜]\s*(?:為|为|是)?\s*(?:文員|文员|文書|文书)",
    re.I,
)

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
            html = _decode_html(r)
            if html:
                soup = BeautifulSoup(html, "lxml")
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
            # HKU keeps a second copy of the job table in the DOM but hides it.
            # "visible" would wait until timeout even though the rows are there.
            page.wait_for_selector(wait_for, timeout=30000, state="attached")
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


def _decode_html(response) -> str:
    """Career pages are UTF-8. A missing charset must not be read as Latin-1."""
    raw = response.content or b""
    if not raw:
        return ""
    ctype = (response.headers.get("content-type") or "").lower()
    if "utf-8" in ctype or "utf8" in ctype:
        return raw.decode("utf-8", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        encoding = response.encoding or "utf-8"
        return raw.decode(encoding, errors="replace")


_MOJIBAKE_RUN = re.compile(r"(?:[\u00c0-\u00ff][\u0080-\u00bf]{1,3})+")


def repair_mojibake(text: str) -> str:
    """UTF-8 bytes that were decoded as Latin-1, e.g. 「正好生活計劃」."""
    if not text or not _MOJIBAKE_RUN.search(text):
        return text

    def fix(match) -> str:
        chunk = match.group(0)
        try:
            return chunk.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return chunk

    return _MOJIBAKE_RUN.sub(fix, text)


def html_to_text(html: str) -> str:
    """Visible text of an HTML fragment from a JSON job description."""
    if not html or not str(html).strip():
        return ""
    soup = BeautifulSoup(str(html), "lxml")
    for junk in soup.select("script, style"):
        junk.decompose()
    return repair_mojibake(soup.get_text("\n", strip=True)).replace("\xa0", " ")


def api_request(
    method: str,
    url: str,
    *,
    json_body=None,
    extra_headers: Optional[dict] = None,
    timeout: int = 30,
    expect: str = "json",
    pause: float = 1,
):
    """One JSON or text call on the shared session.

    Career JSON APIs do not need a browser. Returns None when the response
    is an error page or cannot be decoded.
    """
    headers = dict(HEADERS)
    if expect == "json":
        headers["Accept"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    last_error = None
    for attempt in range(2):
        try:
            response = _SESSION.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=timeout,
            )
            if response.status_code in (429, 503) and attempt == 0:
                time.sleep(max(REQUEST_DELAY * 2, pause))
                continue
            if response.status_code >= 400:
                print(f"  [http] {response.status_code} {url[:90]}")
                return None
            if expect == "text":
                return _decode_html(response)
            ctype = (response.headers.get("content-type") or "").lower()
            body = response.text.lstrip()
            if "json" not in ctype and not body.startswith(("{", "[")):
                print(f"  [http] not json {url[:90]}")
                return None
            return response.json()
        except Exception as e:
            last_error = e
            print(f"  [http] {url[:80]} → {e}")
            time.sleep(pause)
    if last_error:
        print(f"  [http] give up {url[:80]}")
    return None


def job_content(soup: Optional[BeautifulSoup]) -> str:
    """Text of the job description element, not the site chrome."""
    if not soup or is_challenge_page(soup):
        return ""
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node:
            text = node.get_text("\n", strip=True)
            if len(text) > 40:
                return repair_mojibake(text)
    root = soup.select_one("main") or soup.body
    if not root:
        return ""
    for junk in root.select("header, footer, nav, script, style, noscript"):
        junk.decompose()
    return repair_mojibake(root.get_text("\n", strip=True))


_HKT = timezone(timedelta(hours=8))
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_ISO_STAMP = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(Z|[+-]\d{2}:?\d{2})?\b"
)
_OPEN_ENDED = re.compile(
    r"until filled|open until|is/are filled|to be filled|until the position",
    re.I,
)


def parse_date(text: str) -> Optional[str]:
    """Calendar date as YYYY-MM-DD.

    Hong Kong career pages write day/month/year (20/11/2026) or a month name
    (26 November 2026, Nov 13, 2026). A timestamp such as 2026-11-13T15:55:00Z
    is the same closing instant in Hong Kong time.
    """
    if not text:
        return None
    text = repair_mojibake(text).strip()
    if text in ("", "-", "N/A", "—"):
        return None

    slashes = list(_SLASH_DATE.finditer(text))
    if slashes:
        # Two dates in one cell: the later one is the closing date.
        day, month, year = (int(part) for part in slashes[-1].groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None

    stamp = _ISO_STAMP.search(text)
    if stamp:
        raw = f"{stamp.group(1)}T{stamp.group(2)}"
        if len(stamp.group(2)) == 5:
            raw += ":00"
        tz = stamp.group(3) or ""
        if tz == "Z":
            raw += "+00:00"
        elif tz:
            raw += tz
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return stamp.group(1)
        if dt.tzinfo:
            dt = dt.astimezone(_HKT)
        return dt.date().isoformat()

    if _OPEN_ENDED.search(text):
        return None

    # "Open Date: 30+ days ago" is a relative age. Fuzzy parsing would read
    # the 30 as the 30th of the current month.
    if re.search(r"\bago\b|\byesterday\b|\btoday\b", text, re.I) and not re.search(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", text, re.I
    ):
        return None
    if re.fullmatch(r"\d{1,2}\s*\+?", text.strip()):
        return None

    try:
        # Month names stay unambiguous. Numeric leftovers are day-first.
        dt = date_parser.parse(text, fuzzy=True, dayfirst=True)
        return dt.date().isoformat()
    except Exception:
        return None


def _primarily_clerical(*blobs: str) -> bool:
    """True when the opening duties are clerical or administrative support.

    Research work mentioned before that support keeps the post.
    """
    text = " ".join(part for part in blobs if part)
    if not text:
        return False
    head = text[:900]
    clerical = re.search(
        r"clerical(?:\s+and\s+administrative)?(?:\s+support)?"
        r"|administrative support"
        r"|clerical support"
        r"|clerical duties",
        head,
        re.I,
    )
    if not clerical:
        return False
    research = re.search(
        r"\bresearch\b|experiment|laboratory|literature review|data analysis|fieldwork",
        head,
        re.I,
    )
    if research and research.start() < clerical.start():
        return False
    return True


def _role_title(title: str) -> str:
    text = _RANK.sub(" ", title or "")
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def is_research_related(
    title: str,
    department: str = "",
    project: str = "",
    description: str = "",
) -> bool:
    """True for research appointments, including outside STEM.

    Research assistant, research associate/officer/fellow, postdoc, research
    engineer/scientist/analyst, project fellow, and data analyst pass on the title.
    Project assistant/associate pass unless the post sits in an admin office.
    Technical and engineer titles still need a discipline, a lab, or a
    research word. Clerks, executive officers, admissions, HR, and finance do not.
    A clerk or clerical grade anywhere in the title, including inside
    "(at the rank of Clerk)", excludes the post. The same grade named in the
    advertisement ("Clerk grade", "文員職級") does too.
    """
    raw_title = title or ""
    if _CLERK_WORD.search(raw_title) or _CLERK_RANK.search(raw_title):
        return False
    rank_blob = "\n".join(part for part in (description, project) if part)
    if rank_blob and _CLERK_RANK.search(rank_blob):
        return False
    role = _role_title(raw_title)
    if not role:
        return False
    # A combined title can offer either a research grade or an admin grade
    # ("Research Assistant / Research Administrative Assistant"). The research
    # grade is enough. Admin words only reject a title that has no research grade.
    if _RESEARCH_ROLE.search(role):
        return True
    if _ADMIN_ROLE.search(role) or re.search(r"\badministration\b", role, re.I):
        return False
    place = f"{role} {department or ''}"
    # "Project Assistant II" whose duties are clerical support is not a research post.
    # A research title is already accepted above, so a mention of admin tasks there stays.
    if _PROJECT_SUPPORT.search(role) and _primarily_clerical(description, project):
        return False
    if _PROJECT_SUPPORT.search(role) and not _ADMIN_OFFICE.search(place):
        return True
    if _PROJECT_LEAD.search(role) and _RESEARCH_WORD.search(role):
        return True
    if _TECHNICAL_ROLE.search(role) and not _FACILITIES_ENGINEER.search(role):
        if _DISCIPLINE.search(role) or _RESEARCH_WORD.search(role):
            return True
        # "Technical Officer（测试工程师）" is lab engineering support.
        if re.search(r"technical\s+(?:officer|assistant)|技术专员|技術專員|技术助理|技術助理", role, re.I) and re.search(
            r"工程师|工程師", role
        ):
            return True
        context = " ".join(part for part in (department, project, description) if part)
        if _DISCIPLINE.search(context) or _LAB_UNIT.search(context):
            return True
    return False


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
    date_type: Optional[str] = None,
    open_date: Optional[str] = None,
    open_date_approximate: bool = False,
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
    if date_type:
        post["date_type"] = date_type
    if open_date:
        post["open_date"] = open_date
    if open_date_approximate:
        post["open_date_approximate"] = True
    return post
