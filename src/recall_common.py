import re
from typing import Iterable

from rank_bm25 import BM25Okapi

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def build_bm25(corpus_texts: list[str]) -> BM25Okapi:
    tokenized = [tokenize(t) for t in corpus_texts]
    return BM25Okapi(tokenized)


def bm25_topk(query: str, bm25: BM25Okapi, k: int) -> list[int]:
    toks = tokenize(query)
    scores = bm25.get_scores(toks)
    if k >= len(scores):
        return sorted(range(len(scores)), key=lambda i: -scores[i])
    idx_sorted = sorted(range(len(scores)), key=lambda i: -scores[i])
    return idx_sorted[:k]


def oh_embed_text(p) -> str:
    parts = [p.product_name]
    if p.parent_product:
        parts.append(f"parent: {p.parent_product}")
    if p.solution_category:
        parts.append(f"category: {p.solution_category}")
    if p.solution_sub_category:
        parts.append(f"sub-category: {p.solution_sub_category}")
    if p.iso:
        parts.append(f"ISO: {p.iso}")
    return " | ".join(parts)


def derive_query_text(description: str, max_chars: int = 2000) -> str:
    if not description:
        return ""
    return description[:max_chars]
