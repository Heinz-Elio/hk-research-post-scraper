import hashlib
import re
import time
from typing import List

from sources.base import (
    HAS_PLAYWRIGHT,
    PLAYWRIGHT_TIMEOUT,
    is_research_related,
    make_post,
    sync_playwright,
)

KEY = "HKBU"
NAME = "Hong Kong Baptist University"


def scrape() -> List[dict]:
    if not HAS_PLAYWRIGHT:
        print(
            "  [HKBU] Playwright not installed → skip "
            "(pip install playwright && playwright install chromium)"
        )
        return []

    url = (
        "https://fa-ewqq-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/"
        "CandidateExperience/en/sites/hkbu/jobs?keyword=research&mode=job-location"
    )
    posts: List[dict] = []

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
                }""",
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

        posts.append(
            make_post(
                source=KEY,
                ref=ref,
                title=title,
                url=href,
                content=f"Department: {dept}\n\n{card_text}",
                department=dept or None,
            )
        )

    return posts
