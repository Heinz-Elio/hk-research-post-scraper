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
from sources import SCRAPERS, SOURCE_NAMES
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


_SECTION_HEADS = [
    ("Project", re.compile(r"^(?:project(?:\s+title)?|research\s+project)\b\s*:?\s*(.*)$", re.I)),
    ("Duties", re.compile(r"^(?:duties|responsibilities|job\s+duties)\b\s*:?\s*(.*)$", re.I)),
    ("Requirements", re.compile(r"^(?:requirements?|qualifications?|entry\s+requirements)\b\s*:?\s*(.*)$", re.I)),
    ("Contact", re.compile(r"^(?:contacts?|enquir(?:y|ies)|how\s+to\s+apply)\b\s*:?\s*(.*)$", re.I)),
    ("Salary", re.compile(r"^(?:salary|remuneration)\b\s*:?\s*(.*)$", re.I)),
    ("Appointment", re.compile(r"^(?:appointment(?:\s+period)?|duration)\b\s*:?\s*(.*)$", re.I)),
    ("Conditions", re.compile(r"^(?:conditions(?:\s+of\s+service)?|what\s+we\s+offer|benefits)\b\s*:?\s*(.*)$", re.I)),
]
# "Duties and Responsibilities" is one heading. The words after Duties are not the duty text.
_COMPOUND_HEAD = re.compile(
    r"^(?:and|&|/)\s+(?:duties|responsibilities|requirements?|qualifications?)\s*$",
    re.I,
)
_CONTACT_LINE = re.compile(r"\b(invited to contact|please contact|for enquir)", re.I)
_CLOSE_LINE = re.compile(r"^the closing date\b", re.I)
_END_LINE = re.compile(
    r"^(?:advertised\b|applications close\b|back to search results\b|whatsapp\b|facebook\b|linkedin\b)",
    re.I,
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?852[\s\-]?)?\d{4}[\s\-]\d{4}")
_SKIP_LINE = re.compile(
    r"^(apply now|printable version|skip to|posting date|share\b|menu\b|return to previous page)\b",
    re.I,
)
_META_LINE = re.compile(
    r"^(?:ref\.?|work type|department|categories|job title|job id|job description|job posting details|hong kong)\b",
    re.I,
)


def _clean_line(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip(" \t:-")
    return text


def _section_text(chunks: List[str]) -> str:
    parts: List[str] = []
    for part in chunks:
        part = _clean_line(part)
        if not part or _SKIP_LINE.match(part):
            continue
        # A layout break can split a word across lines ("Fello" / "w,").
        if parts and re.match(r"^[a-z]{1,2}(?:,|\.|\s)", part) and parts[-1][-1].isalpha():
            parts[-1] = parts[-1] + part
        else:
            parts.append(part)
    text = " ".join(parts)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip()


def _split_sections(text: str) -> Dict[str, str]:
    found: Dict[str, List[str]] = {}
    current = None
    last_plain = ""
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw.strip()
        if not line or _SKIP_LINE.match(line) or _CLOSE_LINE.match(line) or _END_LINE.match(line):
            if _END_LINE.match(line):
                current = None
            continue
        probe = line[1:-1].strip() if line.startswith("[") and line.endswith("]") else line
        matched = False
        for label, pattern in _SECTION_HEADS:
            hit = pattern.match(probe)
            if not hit:
                continue
            found.setdefault(label, [])
            rest = (hit.group(1) or "").strip(" :")
            if _COMPOUND_HEAD.match(rest):
                rest = ""
            if rest:
                if label == "Appointment" and last_plain:
                    found[label].append(f"{last_plain}: {rest}")
                else:
                    found[label].append(rest)
                # The heading line already holds the value. Don't swallow the next lines.
                current = None
            else:
                current = label
            matched = True
            break
        if matched:
            continue
        dept = re.match(r"^department\s*:\s*(.+)$", line, re.I)
        if dept and "Department" not in found:
            found["Department"] = [dept.group(1)]
            current = None
            continue
        if _CONTACT_LINE.search(line):
            current = "Contact"
            found.setdefault("Contact", []).append(line)
            continue
        if current:
            found.setdefault(current, []).append(line)
        else:
            last_plain = line
    sections = {}
    for label, parts in found.items():
        if label == "Appointment":
            bits = [_clean_line(part) for part in parts]
            text = "; ".join(bit for bit in bits if bit)
        else:
            text = _section_text(parts)
        if text:
            sections[label] = text
    return sections


def _contacts(text: str, section: str) -> str:
    section = _clean_line(section)
    blob = text or ""
    emails = []
    for email in _EMAIL_RE.findall(blob):
        if email.lower().endswith((".png", ".jpg", ".gif")):
            continue
        if "example.com" in email.lower() or email.startswith("["):
            continue
        if email not in emails:
            emails.append(email)
    phones = []
    if re.search(r"tel|phone|enquir|contact", blob, re.I):
        for phone in _PHONE_RE.findall(blob):
            parts = re.split(r"[\s\-]", phone.strip())
            # 2026-2027 is an academic year, not a telephone number.
            if len(parts) == 2 and all(re.fullmatch(r"(?:19|20)\d{2}", part) for part in parts):
                continue
            if phone not in phones:
                phones.append(phone)
    extra = []
    haystack = section.lower()
    for bit in emails + phones:
        if bit.lower() not in haystack:
            extra.append(bit)
    if section and extra:
        return f"{section}; " + "; ".join(extra)
    if section:
        return section
    return "; ".join(extra)


def _narrative(text: str) -> str:
    """Prose from a page that has no Duties or Requirements heading."""
    kept: List[str] = []
    skip_value = False
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw.strip()
        if not line or _SKIP_LINE.match(line) or _CLOSE_LINE.match(line) or _END_LINE.match(line):
            continue
        if _META_LINE.match(line) or _CONTACT_LINE.search(line):
            # "Department:" is on its own line and the name follows.
            skip_value = line.endswith(":") or ":" not in line
            continue
        if skip_value:
            skip_value = False
            if len(_clean_line(line)) < 90:
                continue
        probe = line[1:-1].strip() if line.startswith("[") and line.endswith("]") else line
        if any(pattern.match(probe) for _, pattern in _SECTION_HEADS):
            break
        if re.match(r"^(?:how to apply|contacts?|enquir(?:y|ies))\b", probe, re.I):
            break
        if len(_clean_line(line)) < 40:
            continue
        kept.append(line)
    return _section_text(kept)[:1000]


def fact_summary(
    text: str,
    *,
    title: str = "",
    university: str = "",
    department: str = "",
    project: str = "",
    close_date: str = "",
    url: str = "",
) -> str:
    """Bullet list of facts taken from the scrape. Does not invent a university or contact."""
    sections = _split_sections(text)
    department = _clean_line(department) or sections.get("Department", "")
    project = _clean_line(project) or sections.get("Project", "")
    contact = _contacts(text, sections.get("Contact", ""))
    items = []

    def add(label: str, value: str) -> None:
        value = _clean_line(value)
        if value:
            items.append(f"- {label}: {value}")

    add("University", university)
    add("Department", department)
    add("Project", project)
    if not sections.get("Duties") and not sections.get("Requirements"):
        add("Description", _narrative(text))
    add("Duties", sections.get("Duties", ""))
    add("Requirements", sections.get("Requirements", ""))
    add("Appointment", sections.get("Appointment", ""))
    add("Salary", sections.get("Salary", ""))
    add("Conditions", sections.get("Conditions", ""))
    add("Contact", contact)
    add("Closing date", close_date)
    if not contact and url:
        add("Apply", url)
    if not items and title:
        add("Post", title)
    return "\n".join(items)


def summarize(
    text: str,
    title: str = "",
    university: str = "",
    department: str = "",
    project: str = "",
    close_date: str = "",
    url: str = "",
) -> str:
    facts = fact_summary(
        text,
        title=title,
        university=university,
        department=department,
        project=project,
        close_date=close_date,
        url=url,
    )
    if not text or not HAS_SUMMARIZER or summarizer_pipeline is None:
        return facts

    prompt = f"""You rewrite academic job facts into a bullet list.
Use only the facts below. Keep the university name exactly as given.
Include project domain, main duties, key requirements, and contact when they are present.
Do not invent names, emails, dates, or placeholders.
One fact per line, each line starting with "- ".

{facts}

List:"""

    try:
        result = summarizer_pipeline(
            prompt,
            max_new_tokens=420,
            do_sample=False,
            temperature=0.1,
            pad_token_id=summarizer_pipeline.tokenizer.eos_token_id,
        )
        generated = result[0]["generated_text"]
        summary = generated.split("List:")[-1].strip() if "List:" in generated else generated[len(prompt):].strip()
        lines = [line.strip() for line in summary.splitlines() if line.strip().startswith("- ")]
        joined = "\n".join(lines)
        if university and university not in joined:
            return facts
        if re.search(r"\[[^\]]*(university|email|contact|deadline)", joined, re.I):
            return facts
        labels = re.findall(r"(?m)^-\s*([^:]+):", joined)
        junk = {"what we offer", "advertised", "applications close", "back to search results"}
        if any(label.strip().lower() in junk for label in labels):
            return facts
        if re.search(r"(?m)^- Duties:\s*and Responsibilities\s*$", joined):
            return facts
        def has_body(blob: str) -> bool:
            return bool(re.search(r"(?m)^- (?:Duties|Requirements|Description):", blob))
        if has_body(facts) and not has_body(joined):
            return facts
        return joined or facts
    except Exception as e:
        print(f"  [summarize error] {e}")
        return facts


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
        university = SOURCE_NAMES.get(post.get("source") or "", post.get("source") or "")
        summary = post.get("summary") or ""
        # Older model summaries invented the school and the contact. Keep only
        # text that is already a fact list, or a scrape that has real headings.
        invented = bool(re.search(r"\[University Name\]|XYZ University|\[email|\[contact|\[deadline", summary, re.I))
        has_headings = bool(re.search(r"(?m)^(Duties|Requirements|Qualifications|Project(?: Title)?|Department)\b", summary))
        if not summary.startswith("- University:"):
            post["summary"] = fact_summary(
                summary if has_headings and not invented else "",
                title=post.get("title") or "",
                university=university,
                department=post.get("department") or "",
                project=post.get("project") or "",
                close_date=post.get("close_date") or "",
                url=post.get("url") or "",
            )
        # A list that only names the school has no requirements text. Leave the
        # degree and domain fields already stored on the post.
        if post.get("content") or re.search(r"(?m)^- Requirements:", post.get("summary") or ""):
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
                    university = SOURCE_NAMES.get(p.get("source") or name, name)
                    old = active.get(pid) or outdated.get(pid)
                    if (
                        use_summarizer
                        and old
                        and old.get("content") == full_text
                        and (old.get("summary") or "").startswith("- University:")
                    ):
                        p["summary"] = old.get("summary")
                    else:
                        p["summary"] = summarize(
                            full_text,
                            title=p.get("title", ""),
                            university=university,
                            department=p.get("department") or "",
                            project=p.get("project") or "",
                            close_date=p.get("close_date") or "",
                            url=p.get("url") or "",
                        )

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
