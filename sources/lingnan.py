import hashlib
import time
from typing import List

from sources.base import (
    HAS_PLAYWRIGHT,
    PLAYWRIGHT_TIMEOUT,
    is_research_related,
    make_post,
    sync_playwright,
)

KEY = "Lingnan"
NAME = "Lingnan University"


def scrape() -> List[dict]:
    if not HAS_PLAYWRIGHT:
        print(
            "  [Lingnan] Playwright not installed → skip "
            "(pip install playwright && playwright install chromium)"
        )
        return []

    url = (
        "https://lingnan.csod.com/ux/ats/careersite/4/home"
        "?c=lingnan&cfdd[0][id]=151&cfdd[0][options][0]=103"
    )
    posts: List[dict] = []

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
                }""",
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
                    }""",
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

        posts.append(
            make_post(
                source=KEY,
                ref=ref,
                title=title,
                url=href,
                content=card_text,
            )
        )

    return posts
