#!/usr/bin/env python3
"""
Research Post Scraper – Main Orchestrator

- Calls plugin scrapers from sources/
- research_posts.json (active) + outdated_posts.json
- Optional local model summarization
- Quantized embeddings in docs/embeddings.json for semantic search
- Classification: work_type, min_degree, domains, department
"""

import argparse
import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from embeddings_store import (
    cosine,
    dequantize,
    load_embeddings,
    save_embeddings,
    take_post_embedding,
    text_for_embed,
    upsert_vector,
)
from sources import SCRAPERS
from taxonomy import enrich_classification

# ==================================================================
# Quiet transformers / huggingface / torch logs
# ==================================================================
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("torch").setLevel(logging.ERROR)

# ==================================================================
# Config switches
# ==================================================================
USE_LOCAL_SUMMARIZER = True
USE_EMBEDDINGS = True

SUMMARIZER_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

# ==================================================================
# Optional local summarizer
# ==================================================================
HAS_SUMMARIZER = False
summarizer_pipeline = None

if USE_LOCAL_SUMMARIZER:
    try:
        from transformers import pipeline
        import torch

        device = 0 if torch.cuda.is_available() else -1
        print(f"[Info] Loading summarizer: {SUMMARIZER_MODEL} (device={'cuda' if device == 0 else 'cpu'})")
        summarizer_pipeline = pipeline(
            "text-generation",
            model=SUMMARIZER_MODEL,
            device=device,
            torch_dtype=torch.float16 if device == 0 else torch.float32,
            max_new_tokens=180,
        )
        HAS_SUMMARIZER = True
        print("[Info] Local summarizer ready")
    except Exception as e:
        print(f"[Info] Local summarizer not available → {e}")
        print("       Falling back to rule-based summary")
        HAS_SUMMARIZER = False


def rule_based_summary(text: str) -> str:
    """Full job text, cleaned. Never stop in the middle of a sentence."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _complete_sentences(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\.{3,}$|…$", "", text).strip()
    if not text or text[-1] in ".!?。":
        return text
    cut = max(text.rfind(". "), text.rfind("。"), text.rfind("! "), text.rfind("? "))
    if cut > 40:
        return text[: cut + 1].strip()
    return text


def summarize(text: str, title: str = "") -> str:
    if not text:
        return ""
    text = rule_based_summary(text)

    if not HAS_SUMMARIZER or summarizer_pipeline is None:
        return rule_based_summary(text)

    prompt = f"""You are a helpful assistant that writes concise summaries of academic research job postings.

Write a complete summary of the research position.
Cover the duties, the requirements, and the project domain.
Finish the last sentence. Do not stop mid-sentence and do not invent information.

Title: {title}

Job text:
{text}

Summary:"""

    try:
        result = summarizer_pipeline(
            prompt,
            max_new_tokens=420,
            do_sample=False,
            temperature=0.1,
            pad_token_id=summarizer_pipeline.tokenizer.eos_token_id,
        )
        generated = result[0]["generated_text"]
        if "Summary:" in generated:
            summary = generated.split("Summary:")[-1].strip()
        else:
            summary = generated[len(prompt) :].strip()
        summary = re.sub(r"\n+", " ", summary).strip()
        summary = _complete_sentences(summary)
        return summary if summary else rule_based_summary(text)
    except Exception as e:
        print(f"  [summarize error] {e}")
        return rule_based_summary(text)


# ==================================================================
# Optional embeddings
# ==================================================================
HAS_EMBED = False
EMBED_MODEL = None

if USE_EMBEDDINGS:
    try:
        from sentence_transformers import SentenceTransformer

        EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        HAS_EMBED = True
        print("[Info] Embedding model ready (all-MiniLM-L6-v2)")
    except ImportError:
        print("[Info] sentence-transformers not installed → embeddings disabled")


def get_embedding(text: str) -> Optional[List[float]]:
    if not HAS_EMBED or not text:
        return None
    text = text[:3000]
    emb = EMBED_MODEL.encode(text, show_progress_bar=False)
    return emb.tolist()


# ==================================================================
# Paths & JSON helpers
# ==================================================================
DATA_DIR = Path(__file__).parent
ACTIVE_FILE = DATA_DIR / "research_posts.json"
OUTDATED_FILE = DATA_DIR / "outdated_posts.json"
PUBLIC_FILE = DATA_DIR / "docs" / "research_posts.json"
EMBED_FILE = DATA_DIR / "docs" / "embeddings.json"

DROP_FROM_STORE = {"embedding", "content"}


def load_json(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {item["id"]: item for item in data if item.get("id")}
    return data


def _clean_post(post: dict) -> dict:
    return {k: v for k, v in post.items() if k not in DROP_FROM_STORE}


def save_json(path: Path, data: Dict[str, dict]):
    items = sorted(
        (_clean_post(x) for x in data.values()),
        key=lambda x: (x.get("close_date") or "9999-12-31", x.get("title") or ""),
        reverse=True,
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def save_public_json(data: Dict[str, dict]):
    PUBLIC_FILE.parent.mkdir(parents=True, exist_ok=True)
    public_posts = [_clean_post(post) for post in data.values()]
    with open(PUBLIC_FILE, "w", encoding="utf-8") as f:
        json.dump(public_posts, f, ensure_ascii=False)


def harvest_embeddings(posts: Dict[str, dict], store: dict) -> None:
    for pid, post in posts.items():
        vec = take_post_embedding(post)
        if vec:
            upsert_vector(store, pid, vec)


def backfill_posts(posts: Dict[str, dict]) -> None:
    for post in posts.values():
        enrich_classification(post)


# ==================================================================
# Main logic
# ==================================================================
def run(
    sources: Optional[List[str]] = None,
    generate_embeddings: bool = True,
    use_summarizer: bool = True,
    scrape: bool = True,
):
    if sources is None:
        sources = list(SCRAPERS.keys())

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting {'scrape' if scrape else 'migrate'}")
    if scrape:
        print(f"  Sources     : {sources}")
    print(
        f"  Summarizer  : {'ON (local model)' if use_summarizer and HAS_SUMMARIZER else 'ON (rule-based)' if use_summarizer else 'OFF'}"
    )
    print(f"  Embeddings  : {'ON' if generate_embeddings and HAS_EMBED else 'OFF'}")

    active = load_json(ACTIVE_FILE)
    outdated = load_json(OUTDATED_FILE)
    embed_store = load_embeddings(EMBED_FILE)
    harvest_embeddings(active, embed_store)
    harvest_embeddings(outdated, embed_store)
    today = date.today().isoformat()

    new_count = 0
    updated_count = 0
    moved_count = 0

    if scrape:
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

                    full_text = p.get("content") or ""
                    if use_summarizer:
                        old = active.get(pid) or outdated.get(pid)
                        if not old or old.get("content") != full_text or not old.get("summary"):
                            p["summary"] = summarize(full_text, title=p.get("title", ""))
                        else:
                            p["summary"] = old.get("summary")
                    else:
                        p["summary"] = rule_based_summary(full_text)

                    p = enrich_classification(p)
                    p.pop("content", None)

                    if generate_embeddings and HAS_EMBED:
                        old = active.get(pid) or outdated.get(pid)
                        text_emb = text_for_embed(p)
                        need_embed = (
                            not old
                            or old.get("summary") != p.get("summary")
                            or pid not in embed_store.get("items", {})
                        )
                        if need_embed:
                            vec = get_embedding(text_emb)
                            if vec:
                                upsert_vector(embed_store, pid, vec)

                    if pid in active:
                        updated_count += 1
                    else:
                        new_count += 1

                    active[pid] = p

            except Exception as e:
                print(f"  [Error] {name}: {e}")

    backfill_posts(active)
    backfill_posts(outdated)

    if generate_embeddings and HAS_EMBED:
        for pid, post in active.items():
            if pid in embed_store.get("items", {}):
                continue
            vec = get_embedding(text_for_embed(post))
            if vec:
                upsert_vector(embed_store, pid, vec)

    to_move = []
    for pid, post in list(active.items()):
        close = post.get("close_date")
        if close and close < today:
            outdated[pid] = post
            to_move.append(pid)
            moved_count += 1

    for pid in to_move:
        del active[pid]

    # Drop embeddings for posts that are no longer active from the public file
    embed_store["items"] = {
        pid: item
        for pid, item in embed_store.get("items", {}).items()
        if pid in active
    }

    save_json(ACTIVE_FILE, active)
    save_json(OUTDATED_FILE, outdated)
    save_public_json(active)
    save_embeddings(EMBED_FILE, embed_store)

    print("\n" + "=" * 50)
    print(f"[{datetime.now():%H:%M:%S}] Finished")
    print(f"  Active posts     : {len(active)}")
    print(f"  Outdated posts   : {len(outdated)}")
    print(f"  New this run     : {new_count}")
    print(f"  Updated this run : {updated_count}")
    print(f"  Moved to outdated: {moved_count}")
    print(f"  Embeddings       : {len(embed_store.get('items', {}))}")
    print("=" * 50)


def semantic_search(query: str, top_k: int = 8) -> List[dict]:
    store = load_embeddings(EMBED_FILE)
    items = store.get("items") or {}
    if not items:
        print("Embeddings not available (run with USE_EMBEDDINGS or migrate existing vectors)")
        return []

    q_emb: Optional[List[float]] = None
    if HAS_EMBED and EMBED_MODEL is not None:
        q_emb = EMBED_MODEL.encode(query, show_progress_bar=False).tolist()
    else:
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer("all-MiniLM-L6-v2")
            q_emb = model.encode(query, show_progress_bar=False).tolist()
        except Exception as e:
            print(f"Need sentence-transformers to encode the query → {e}")
            return []

    active = load_json(ACTIVE_FILE)
    scored = []
    for pid, packed in items.items():
        vec = dequantize(packed)
        post = active.get(pid)
        if not vec or not post:
            continue
        scored.append((cosine(q_emb, vec), post))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "score": round(s, 4),
            "id": p["id"],
            "title": p["title"],
            "close_date": p.get("close_date"),
            "summary": (p.get("summary") or "")[:200],
            "url": p["url"],
            "source": p["source"],
            "domains": p.get("domains") or [],
            "min_degree": p.get("min_degree"),
        }
        for s, p in scored[:top_k]
    ]


def parse_args():
    parser = argparse.ArgumentParser(description="HK research post collector")
    parser.add_argument(
        "--sources",
        help="Comma-separated source keys (default: all registered)",
    )
    parser.add_argument(
        "--migrate-only",
        action="store_true",
        help="Re-enrich stored posts and split embeddings; do not scrape",
    )
    parser.add_argument("--search", help="Semantic search query (CLI)")
    parser.add_argument("--top-k", type=int, default=8)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.search:
        for row in semantic_search(args.search, top_k=args.top_k):
            print(f"{row['score']:.3f}  {row['source']:8}  {row['title']}")
            print(f"       {row.get('url')}")
    else:
        source_list = None
        if args.sources:
            source_list = [s.strip() for s in args.sources.split(",") if s.strip()]
        run(sources=source_list, scrape=not args.migrate_only)
