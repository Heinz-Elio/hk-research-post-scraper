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
from sources import SCRAPERS, SOURCE_NAMES
from sources.base import (
    ListingUnchanged,
    commit_listing_hashes,
    configure_run,
    is_research_related,
    listing_counts,
    set_listing_hash_path,
)
from summary import fact_summary, salvage_summary, summarize as build_summary, summary_needs_repair
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
USE_LOCAL_SUMMARIZER = False
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


def summarize(
    text: str,
    title: str = "",
    university: str = "",
    department: str = "",
    project: str = "",
    close_date: str = "",
    url: str = "",
    date_type: str = "",
) -> str:
    """Deterministic extractive summary. The local model is optional and off by default."""

    def model(prompt: str) -> str:
        result = summarizer_pipeline(
            prompt,
            max_new_tokens=220,
            do_sample=False,
            temperature=0.1,
            pad_token_id=summarizer_pipeline.tokenizer.eos_token_id,
        )
        generated = result[0]["generated_text"]
        if "List:" in generated:
            return generated.split("List:")[-1].strip()
        if generated.startswith(prompt):
            return generated[len(prompt):].strip()
        return generated.strip()

    return build_summary(
        text,
        title=title,
        university=university,
        department=department,
        project=project,
        close_date=close_date,
        url=url,
        date_type=date_type,
        model=model if HAS_SUMMARIZER and summarizer_pipeline is not None else None,
    )


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
        # PolyU's listing column is a review-start date, including rows saved
        # before date_type existed. A passed review date must not retire them.
        if post.get("source") == "PolyU" and not post.get("date_type"):
            post["date_type"] = "review_start" if post.get("close_date") else "open_until_filled"
        summary = post.get("summary") or ""
        if post.get("content"):
            post["summary"] = summarize(
                post.get("content") or "",
                title=post.get("title") or "",
                university=SOURCE_NAMES.get(post.get("source") or "", ""),
                department=post.get("department") or "",
                project=post.get("project") or "",
                close_date=post.get("close_date") or "",
                url=post.get("url") or "",
                date_type=post.get("date_type") or "",
            )
        elif summary_needs_repair(summary):
            repaired = salvage_summary(summary)
            post["summary"] = repaired or fact_summary(
                "",
                title=post.get("title") or "",
                department=post.get("department") or "",
                project=post.get("project") or "",
                close_date=post.get("close_date") or "",
                date_type=post.get("date_type") or "",
            )
        enrich_classification(post)


# ==================================================================
# Main logic
# ==================================================================
def bind_data_dir(path: Path) -> None:
    """Write JSON and the listing hash under ``path`` instead of the repo."""
    global ACTIVE_FILE, OUTDATED_FILE, PUBLIC_FILE, EMBED_FILE
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / "docs").mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE = path / "research_posts.json"
    OUTDATED_FILE = path / "outdated_posts.json"
    PUBLIC_FILE = path / "docs" / "research_posts.json"
    EMBED_FILE = path / "docs" / "embeddings.json"
    set_listing_hash_path(path / "listing_hashes.json")


def _remember_summary(post: dict, full_text: str, old: Optional[dict], university: str) -> None:
    old_summary = (old or {}).get("summary") or ""
    if (
        not full_text.strip()
        and old_summary
        and not summary_needs_repair(old_summary)
    ):
        post["summary"] = old_summary
        return
    if (
        old
        and old.get("content") == full_text
        and old_summary.startswith("- Dept:")
        and not summary_needs_repair(old_summary)
    ):
        post["summary"] = old_summary
        return
    post["summary"] = summarize(
        full_text,
        title=post.get("title", ""),
        university=university,
        department=post.get("department") or "",
        project=post.get("project") or "",
        close_date=post.get("close_date") or "",
        url=post.get("url") or "",
        date_type=post.get("date_type") or "",
    )


def run(
    sources: Optional[List[str]] = None,
    generate_embeddings: bool = True,
    use_summarizer: bool = True,
    scrape: bool = True,
    force: bool = False,
    data_dir: Optional[Path] = None,
):
    if data_dir is not None:
        bind_data_dir(data_dir)
    if sources is None:
        sources = list(SCRAPERS.keys())

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting {'scrape' if scrape else 'migrate'}")
    if scrape:
        print(f"  Sources     : {sources}")
    if force:
        print("  Hashes      : ignored (--force)")
    print(
        f"  Summarizer  : {'ON (local model)' if use_summarizer and HAS_SUMMARIZER else 'extractive' if use_summarizer else 'OFF'}"
    )
    print(f"  Embeddings  : {'ON' if generate_embeddings and HAS_EMBED else 'OFF'}")

    active = load_json(ACTIVE_FILE)
    outdated = load_json(OUTDATED_FILE)
    embed_store = load_embeddings(EMBED_FILE)
    harvest_embeddings(active, embed_store)
    harvest_embeddings(outdated, embed_store)
    today = date.today().isoformat()

    stored_active = {}
    for post in active.values():
        key = post.get("source") or ""
        stored_active[key] = stored_active.get(key, 0) + 1
    empty_sources = [name for name in sources if stored_active.get(name, 0) == 0]
    configure_run(force=force, sources_with_no_posts=empty_sources)

    new_count = 0
    updated_count = 0
    moved_count = 0
    fresh_ids: Dict[str, set] = {}
    run_stats: Dict[str, dict] = {}

    if scrape:
        for name in sources:
            if name not in SCRAPERS:
                print(f"  [Skip] Unknown source: {name}")
                continue

            print(f"\n→ Scraping {name} ...")
            try:
                posts = SCRAPERS[name]()
                if isinstance(posts, ListingUnchanged):
                    print("  Listing unchanged; kept the stored posts")
                    run_stats[name] = {"unchanged": True}
                    continue
                print(f"  Found {len(posts)} research-related posts")
                if not posts:
                    run_stats[name] = {"returned": 0}
                    continue

                fresh_ids[name] = set()
                for p in posts:
                    pid = p["id"]
                    p["scraped_at"] = datetime.now().isoformat(timespec="seconds")
                    full_text = p.get("content") or ""
                    university = SOURCE_NAMES.get(p.get("source") or name, name)
                    old = active.get(pid) or outdated.get(pid)
                    if use_summarizer:
                        _remember_summary(p, full_text, old, university)
                    elif old and old.get("summary"):
                        p["summary"] = old.get("summary")

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
                    # Back on the live board: it is active again.
                    outdated.pop(pid, None)
                    active[pid] = p
                    fresh_ids[name].add(pid)

                returned = [active[pid] for pid in fresh_ids[name]]
                run_stats[name] = {
                    "returned": len(returned),
                    "empty_close": sum(1 for post in returned if not post.get("close_date")),
                    "stale": sum(1 for post in returned if post.get("possibly_stale")),
                    "review": sum(1 for post in returned if post.get("date_type") == "review_start"),
                }
            except Exception as e:
                print(f"  [Error] {name}: {e}")
                run_stats[name] = {"error": str(e)}

    backfill_posts(active)
    backfill_posts(outdated)

    if generate_embeddings and HAS_EMBED:
        for pid, post in active.items():
            if pid in embed_store.get("items", {}):
                continue
            vec = get_embedding(text_for_embed(post))
            if vec:
                upsert_vector(embed_store, pid, vec)

    # A stored project-assistant ad can be clerical even when the listing
    # hash has not changed, because the grade is only in the description.
    for pid, post in list(active.items()):
        blob = "\n".join(
            part for part in (post.get("content"), post.get("summary"), post.get("project")) if part
        )
        if not is_research_related(
            post.get("title") or "",
            department=post.get("department") or "",
            project=post.get("project") or "",
            description=blob,
        ):
            outdated[pid] = post
            del active[pid]
            moved_count += 1

    # A fresh listing replaces that source's active set. Posts no longer
    # listed move to outdated. An empty or failed scrape does not.
    for pid, post in list(active.items()):
        src = post.get("source")
        if src in fresh_ids and pid not in fresh_ids[src]:
            outdated[pid] = post
            del active[pid]
            moved_count += 1

    for pid, post in list(active.items()):
        if post.get("source") in fresh_ids:
            continue
        kind = post.get("date_type")
        if kind in ("review_start", "open_until_filled"):
            continue
        close = post.get("close_date")
        # Stored rows with no date_type still use close_date as a hard deadline.
        if close and close < today and kind in (None, "", "deadline"):
            outdated[pid] = post
            del active[pid]
            moved_count += 1

    embed_store["items"] = {
        pid: item
        for pid, item in embed_store.get("items", {}).items()
        if pid in active
    }

    save_json(ACTIVE_FILE, active)
    save_json(OUTDATED_FILE, outdated)
    save_public_json(active)
    save_embeddings(EMBED_FILE, embed_store)
    if scrape:
        commit_listing_hashes()

    print("\n" + "=" * 50)
    print(f"[{datetime.now():%H:%M:%S}] Finished")
    print(f"  Active posts     : {len(active)}")
    print(f"  Outdated posts   : {len(outdated)}")
    print(f"  New this run     : {new_count}")
    print(f"  Updated this run : {updated_count}")
    print(f"  Moved to outdated: {moved_count}")
    print(f"  Embeddings       : {len(embed_store.get('items', {}))}")
    _print_source_report(active, outdated, run_stats)
    print("=" * 50)


def _print_source_report(active: Dict[str, dict], outdated: Dict[str, dict], run_stats: Dict[str, dict]) -> None:
    counts = listing_counts()
    names = sorted(set(counts) | set(run_stats) | {p.get("source") for p in active.values()} | {p.get("source") for p in outdated.values()})
    names = [name for name in names if name]
    if not names:
        return
    print(f"  {'Source':<10} {'Listed':>7} {'Kept':>6} {'Active':>7} {'Outdated':>9} {'No close':>9} {'Stale':>6} {'Review':>7}")
    active_by = {}
    outdated_by = {}
    for post in active.values():
        active_by[post.get("source")] = active_by.get(post.get("source"), 0) + 1
    for post in outdated.values():
        outdated_by[post.get("source")] = outdated_by.get(post.get("source"), 0) + 1
    for name in names:
        listed = counts.get(name, {}).get("listed", "")
        kept = counts.get(name, {}).get("kept", "")
        stat = run_stats.get(name) or {}
        if stat.get("unchanged"):
            kept = kept if kept != "" else "skip"
        no_close = stat.get("empty_close", "")
        stale = stat.get("stale", "")
        review = stat.get("review", "")
        if stat.get("error"):
            kept = "ERR"
        print(
            f"  {name:<10} {str(listed):>7} {str(kept):>6} {active_by.get(name, 0):>7} "
            f"{outdated_by.get(name, 0):>9} {str(no_close):>9} {str(stale):>6} {str(review):>7}"
        )


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
    parser.add_argument(
        "--force",
        "--ignore-hashes",
        action="store_true",
        dest="force",
        help="Re-fetch detail pages even when the listing hash is unchanged",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape into a temporary directory and do not update repo JSON or listing hashes",
    )
    parser.add_argument(
        "--data-dir",
        help="Write JSON and listing hashes under this directory instead of the repo",
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
        data_dir = None
        if args.dry_run:
            import tempfile

            data_dir = Path(tempfile.mkdtemp(prefix="hkrps-dry-"))
            print(f"[dry-run] writing under {data_dir} (repo JSON and listing hashes are left untouched)")
        elif args.data_dir:
            data_dir = Path(args.data_dir)
        run(
            sources=source_list,
            scrape=not args.migrate_only,
            force=args.force,
            data_dir=data_dir,
        )
