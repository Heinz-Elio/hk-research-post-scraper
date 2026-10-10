#!/usr/bin/env python3
"""
Research Post Scraper – Main Orchestrator

- Calls site scrapers from scrapers.py
- Maintains research_posts.json (active) and outdated_posts.json
- Optional local model summarization (small instruct model)
- Optional local embeddings for semantic search
- Classification: work_type, degree_level, department
- Clean separation of concerns
"""

import json
import re
import logging
import os
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

from scrapers import SCRAPERS  # all site-specific functions

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
USE_LOCAL_SUMMARIZER = True          # ← set False to disable model summarization
USE_EMBEDDINGS = True                # ← set False to disable embeddings

# Prefer a small instruct model. Change if you have a better one locally.
SUMMARIZER_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"   # good balance
# Alternatives:
# SUMMARIZER_MODEL = "meta-llama/Llama-3.2-1B-Instruct"
# SUMMARIZER_MODEL = "microsoft/Phi-3.5-mini-instruct"

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


def rule_based_summary(text: str, max_chars: int = 520) -> str:
    """Fast fallback: clean + truncate."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_period = max(cut.rfind(". "), cut.rfind("。"), cut.rfind("! "))
    if last_period > max_chars * 0.6:
        return cut[: last_period + 1].strip()
    return cut.strip() + "..."


def summarize(text: str, title: str = "") -> str:
    """Produce a short summary of a research job post."""
    if not text:
        return ""
    text = text[:3500].strip()

    if not HAS_SUMMARIZER or summarizer_pipeline is None:
        return rule_based_summary(text)

    prompt = f"""You are a helpful assistant that writes concise summaries of academic research job postings.

Summarize the following research position in 2-4 short sentences.
Focus on: main role/duties, key requirements (degree, skills, experience), and any important conditions (duration, part-time/full-time).
Do not invent information. Be factual and neutral.

Title: {title}

Job text:
{text}

Summary:"""

    try:
        result = summarizer_pipeline(
            prompt,
            max_new_tokens=160,
            do_sample=False,
            temperature=0.1,
            pad_token_id=summarizer_pipeline.tokenizer.eos_token_id,
        )
        generated = result[0]["generated_text"]
        if "Summary:" in generated:
            summary = generated.split("Summary:")[-1].strip()
        else:
            summary = generated[len(prompt):].strip()
        summary = re.sub(r"\n+", " ", summary).strip()
        if len(summary) > 700:
            summary = summary[:700].rsplit(" ", 1)[0] + "..."
        return summary if summary else rule_based_summary(text)
    except Exception as e:
        print(f"  [summarize error] {e}")
        return rule_based_summary(text)


# ==================================================================
# Classification extraction
# ==================================================================
def extract_work_type(title: str, text: str = "") -> Optional[str]:
    combined = f"{title} {text}".lower()
    has_full = bool(re.search(r"\bfull[-\s]?time\b", combined))
    has_part = bool(re.search(r"\bpart[-\s]?time\b", combined))
    has_fractional = bool(re.search(r"\bfractional\b", combined))
    has_hourly = bool(re.search(r"\bhourly[-\s]?paid\b", combined))
    if has_full and has_part:
        return "Full-time/Part-time"
    if has_full:
        return "Full-time"
    if has_part or has_fractional or has_hourly:
        return "Part-time"
    return None


def extract_degree_level(title: str, text: str = "") -> Optional[str]:
    combined = f"{title} {text}".lower()
    if re.search(r"\b(ph\.?d|doctor(ate)?|doctoral|dphil)\b", combined):
        return "Doctor"
    if re.search(r"\b(master'?s?|mphil|m\.phil|msc|m\.sc|ma\b|m\.a\.)\b", combined):
        return "Master"
    if re.search(r"\b(bachelor'?s?|bsc|b\.sc|ba\b|b\.a\.|undergraduate)\b", combined):
        return "Bachelor"
    if re.search(r"\b(degree|graduate)\b", combined):
        return "Any"
    return None


def extract_department(title: str, text: str = "", source: str = "") -> Optional[str]:
    combined = f"{title}\n{text}"
    patterns = [
        r"(?:Department|School|Faculty|Division|Centre|Center|Institute) of ([A-Z][^,\n\.]{5,60})",
        r"(?:in the |at the )?(Department|School|Faculty|Division) of ([A-Z][^,\n\.]{5,60})",
        r"([A-Z][A-Za-z& \-]{5,50} Department)",
        r"([A-Z][A-Za-z& \-]{5,50} School)",
    ]
    for pat in patterns:
        m = re.search(pat, combined)
        if m:
            name = m.group(1) if len(m.groups()) == 1 else (m.group(2) if m.lastindex >= 2 else m.group(0))
            name = name.strip(" .,-")
            if 5 < len(name) < 70:
                return name
    return None


def enrich_classification(post: dict) -> dict:
    title = post.get("title") or ""
    text = post.get("summary") or post.get("content") or ""
    post["work_type"] = extract_work_type(title, text)
    post["degree_level"] = extract_degree_level(title, text)
    post["department"] = extract_department(title, text, post.get("source", ""))
    return post


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


def load_json(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {item["id"]: item for item in data}
    return data


def save_json(path: Path, data: Dict[str, dict]):
    items = sorted(
        data.values(),
        key=lambda x: (x.get("close_date") or "9999-12-31", x.get("title") or ""),
        reverse=True,
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


# ==================================================================
# Main logic
# ==================================================================
def run(
    sources: Optional[List[str]] = None,
    generate_embeddings: bool = True,
    use_summarizer: bool = True,
):
    if sources is None:
        sources = list(SCRAPERS.keys())

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting scrape")
    print(f"  Sources     : {sources}")
    print(f"  Summarizer  : {'ON (local model)' if use_summarizer and HAS_SUMMARIZER else 'ON (rule-based)' if use_summarizer else 'OFF'}")
    print(f"  Embeddings  : {'ON' if generate_embeddings and HAS_EMBED else 'OFF'}")

    active = load_json(ACTIVE_FILE)
    outdated = load_json(OUTDATED_FILE)
    today = date.today().isoformat()

    new_count = 0
    updated_count = 0
    moved_count = 0

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
                    if (
                        not old
                        or old.get("content") != full_text
                        or not old.get("summary")
                    ):
                        p["summary"] = summarize(full_text, title=p.get("title", ""))
                    else:
                        p["summary"] = old.get("summary")
                else:
                    p["summary"] = rule_based_summary(full_text)

                p.pop("content", None)

                # Classification fields
                p = enrich_classification(p)

                if generate_embeddings and HAS_EMBED:
                    old = active.get(pid) or outdated.get(pid)
                    text_for_embed = p.get("title", "") + "\n" + (p.get("summary") or "")
                    need_embed = (
                        not old
                        or old.get("summary") != p.get("summary")
                        or "embedding" not in old
                    )
                    if need_embed:
                        p["embedding"] = get_embedding(text_for_embed)
                    else:
                        p["embedding"] = old.get("embedding")

                if pid in active:
                    updated_count += 1
                else:
                    new_count += 1

                active[pid] = p

        except Exception as e:
            print(f"  [Error] {name}: {e}")

    to_move = []
    for pid, post in list(active.items()):
        close = post.get("close_date")
        if close and close < today:
            outdated[pid] = post
            to_move.append(pid)
            moved_count += 1

    for pid in to_move:
        del active[pid]

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


def semantic_search(query: str, top_k: int = 8) -> List[dict]:
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
            "summary": p.get("summary", "")[:200],
            "url": p["url"],
            "source": p["source"],
        }
        for s, p in scored[:top_k]
    ]


if __name__ == "__main__":
    run()
