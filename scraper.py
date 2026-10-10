#!/usr/bin/env python3
"""
Research Post Scraper – Main Orchestrator

- Calls site scrapers from scrapers.py
- Maintains research_posts.json (active) and outdated_posts.json
- Optional local embeddings for semantic search
- Clean separation of concerns
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

from scrapers import SCRAPERS  # all site-specific functions

# ------------------------------------------------------------------
# Optional embeddings
# ------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer
    EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    HAS_EMBED = True
except ImportError:
    HAS_EMBED = False
    print("[Info] sentence-transformers not installed → embeddings disabled")

# ------------------------------------------------------------------
# Paths & config
# ------------------------------------------------------------------
DATA_DIR = Path(__file__).parent
ACTIVE_FILE = DATA_DIR / "research_posts.json"
OUTDATED_FILE = DATA_DIR / "outdated_posts.json"


# ------------------------------------------------------------------
# JSON helpers
# ------------------------------------------------------------------
def load_json(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {item["id"]: item for item in data}
    return data


def save_json(path: Path, data: Dict[str, dict]):
    # Save as sorted list for human readability
    items = sorted(
        data.values(),
        key=lambda x: (x.get("close_date") or "9999-12-31", x.get("title") or ""),
        reverse=True,
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def get_embedding(text: str) -> Optional[List[float]]:
    if not HAS_EMBED or not text:
        return None
    # Keep it small
    text = text[:3500]
    emb = EMBED_MODEL.encode(text, show_progress_bar=False)
    return emb.tolist()


# ------------------------------------------------------------------
# Main logic
# ------------------------------------------------------------------
def run(
    sources: Optional[List[str]] = None,
    generate_embeddings: bool = True,
    verbose: bool = True,
):
    """
    sources: list of keys from SCRAPERS, or None = all
    """
    if sources is None:
        sources = list(SCRAPERS.keys())

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting scrape")
    print(f"  Sources : {sources}")
    print(f"  Embeddings: {'ON' if generate_embeddings and HAS_EMBED else 'OFF'}")

    active = load_json(ACTIVE_FILE)
    outdated = load_json(OUTDATED_FILE)
    today = date.today().isoformat()

    new_count = 0
    updated_count = 0
    moved_count = 0

    # ---------- 1. Scrape ----------
    for name in sources:
        if name not in SCRAPERS:
            print(f"  [Skip] Unknown source: {name}")
            continue

        print(f"\n→ Scraping {name} ...")
        try:
            posts = SCRAPERS[name]()
            print(f"  Found {len(posts)} research-related posts")

            for p in posts:
                pid = p["id"]
                p["scraped_at"] = datetime.now().isoformat(timespec="seconds")

                # Embedding only when content is new or changed
                if generate_embeddings and HAS_EMBED:
                    old = active.get(pid) or outdated.get(pid)
                    need_embed = (
                        not old
                        or old.get("content") != p.get("content")
                        or "embedding" not in old
                    )
                    if need_embed:
                        p["embedding"] = get_embedding(
                            p.get("title", "") + "\n" + (p.get("content") or "")[:2000]
                        )
                    else:
                        p["embedding"] = old.get("embedding")

                if pid in active:
                    updated_count += 1
                else:
                    new_count += 1

                active[pid] = p

        except Exception as e:
            print(f"  [Error] {name}: {e}")

    # ---------- 2. Move outdated ----------
    to_move = []
    for pid, post in list(active.items()):
        close = post.get("close_date")
        if close and close < today:
            outdated[pid] = post
            to_move.append(pid)
            moved_count += 1

    for pid in to_move:
        del active[pid]

    # ---------- 3. Persist ----------
    save_json(ACTIVE_FILE, active)
    save_json(OUTDATED_FILE, outdated)

    print("\n" + "=" * 50)
    print(f"[{datetime.now():%H:%M:%S}] Finished")
    print(f"  Active posts     : {len(active)}")
    print(f"  Outdated posts   : {len(outdated)}")
    print(f"  New this run     : {new_count}")
    print(f"  Updated this run : {updated_count}")
    print(f"  Moved to outdated: {moved_count}")
    print("=" * 50)


# ------------------------------------------------------------------
# Optional: simple semantic search helper
# ------------------------------------------------------------------
def semantic_search(query: str, top_k: int = 8) -> List[dict]:
    """Return top_k most similar active posts (requires embeddings)."""
    if not HAS_EMBED:
        print("Embeddings not available")
        return []

    active = load_json(ACTIVE_FILE)
    if not active:
        return []

    q_emb = EMBED_MODEL.encode(query, show_progress_bar=False)

    scored = []
    for post in active.values():
        emb = post.get("embedding")
        if not emb:
            continue
        # cosine similarity
        import numpy as np
        a = np.array(q_emb)
        b = np.array(emb)
        sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        scored.append((sim, post))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "score": round(s, 4),
            "id": p["id"],
            "title": p["title"],
            "close_date": p.get("close_date"),
            "url": p["url"],
            "source": p["source"],
        }
        for s, p in scored[:top_k]
    ]


# ------------------------------------------------------------------
if __name__ == "__main__":
    # Example 1: scrape everything
    run()

    # Example 2: only a few reliable sources
    # run(sources=["HKU", "PolyU", "CityU", "CUHK"])

    # Example 3: after scraping, do a semantic search
    # results = semantic_search("computer vision deep learning research assistant")
    # for r in results:
    #     print(r)
