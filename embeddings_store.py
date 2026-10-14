"""Quantized embeddings for listing JSON (pipeline) and GitHub Pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
EMBED_DIM = 384


def quantize(vector: List[float]) -> dict:
    if not vector:
        return {"scale": 0.0, "q": []}
    peak = max(abs(x) for x in vector) or 1.0
    scale = peak / 127.0
    q = [int(round(x / scale)) for x in vector]
    q = [max(-127, min(127, v)) for v in q]
    return {"scale": scale, "q": q}


def dequantize(item: dict) -> Optional[List[float]]:
    if not item:
        return None
    scale = float(item.get("scale") or 0)
    q = item.get("q") or []
    if not q:
        return None
    return [v * scale for v in q]


def load_embeddings(path: Path) -> dict:
    if not path.exists():
        return {"model": EMBED_MODEL_NAME, "dim": EMBED_DIM, "items": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "items" not in data:
        data = {"model": EMBED_MODEL_NAME, "dim": EMBED_DIM, "items": data}
    return data


def save_embeddings(path: Path, store: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": store.get("model") or EMBED_MODEL_NAME,
        "dim": store.get("dim") or EMBED_DIM,
        "items": store.get("items") or {},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def upsert_vector(store: dict, post_id: str, vector: List[float]) -> None:
    store.setdefault("items", {})
    store["items"][post_id] = quantize(vector)


def take_post_embedding(post: dict) -> Optional[List[float]]:
    emb = post.pop("embedding", None)
    if isinstance(emb, list) and emb:
        return emb
    return None


def cosine(a: List[float], b: List[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = (na ** 0.5) * (nb ** 0.5) + 1e-9
    return float(dot / denom)


def text_for_embed(post: dict) -> str:
    domains = post.get("domains") or []
    domain_text = " ".join(str(d) for d in domains)
    parts = [
        post.get("title") or "",
        domain_text,
        post.get("department") or "",
        post.get("project") or "",
        post.get("summary") or "",
    ]
    return "\n".join(p for p in parts if p)
