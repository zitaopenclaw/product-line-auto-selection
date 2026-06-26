from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.load_pn_tree import PNNode

INDEX_DIR = ROOT / "data" / "index"
PROMPT_PATH = ROOT / "prompts" / "rerank_v2.txt"

_index = None
_client = None
_nodes: list[PNNode] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _index, _client, _nodes

    import json
    import pickle

    import numpy as np
    from sentence_transformers import SentenceTransformer
    from src.recall import EMBED_MODEL_NAME, RecallIndex
    from src.recall_common import build_bm25
    from src.rerank import RerankClient
    from src.load_pn_tree import load_pn_nodes, pn_node_embed_text

    _nodes = load_pn_nodes()
    if not (INDEX_DIR / "embeddings.npy").exists():
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        corpus_texts = [pn_node_embed_text(n) for n in _nodes]
        (INDEX_DIR / "corpus.json").write_text(json.dumps(corpus_texts), encoding="utf-8")
        bm25 = build_bm25(corpus_texts)
        (INDEX_DIR / "bm25.pkl").write_bytes(pickle.dumps(bm25))
        model = SentenceTransformer(EMBED_MODEL_NAME)
        embeddings = model.encode(corpus_texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False, batch_size=8)
        np.save(str(INDEX_DIR / "embeddings.npy"), embeddings)
    else:
        model = SentenceTransformer(EMBED_MODEL_NAME)
    _index = RecallIndex.from_pretrained(INDEX_DIR, model)
    _client = RerankClient(prompt_path=PROMPT_PATH, format_fn=_format_candidates_block_v2)
    yield


app = FastAPI(lifespan=lifespan, title="Pre-DER Recommendation API")


def _format_candidates_block_v2(cands: Iterable) -> str:
    lines = []
    for i, c in enumerate(cands, 1):
        parts = []
        if c.solution_category:
            parts.append(f"level={c.solution_category}")
        parts.append(f"name={c.product_name}")
        if c.parent_product:
            parts.append(f"path={c.parent_product}")
        if c.solution_sub_category:
            parts.append(f"sample_pns={c.solution_sub_category}")
        lines.append(f"{i}. " + " | ".join(parts))
    return "\n".join(lines)


def _node_to_candidate(node: PNNode, idx: int):
    from src.rerank import Candidate
    sample_pns = "; ".join(node.sampled_pn_descs[:6])
    return Candidate(
        product_id=str(idx),
        product_name=node.name,
        parent_product=" > ".join(node.path),
        solution_category=f"L{node.level}",
        solution_sub_category=sample_pns or None,
        iso=None,
    )


# ── Auth ──


async def _verify_key(x_api_key: str | None = Header(None)):
    expected = os.environ.get("APP_API_KEY", "")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API Key")


# ── Endpoints ──


@app.get("/health")
async def health():
    return {"status": "ok"}


class RecommendRequest(BaseModel):
    query: str


@app.post("/recommend", dependencies=[Depends(_verify_key)])
async def recommend(req: RecommendRequest):
    global _index, _client, _nodes
    if _index is None or _client is None or _nodes is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    cand_indices = _index.recall(req.query, topk=60)[:30]
    if not cand_indices:
        return {"topk": []}

    cand_nodes = [_nodes[j] for j in cand_indices]
    cand_objs = [_node_to_candidate(n, j) for j, n in zip(cand_indices, cand_nodes)]

    from src.confidence import keep_topk_diverse_tree, score_to_level

    scored_raw = _client.rerank(req.query, "", cand_objs)

    by_idx = {str(j): n for j, n in zip(cand_indices, cand_nodes)}
    merged = []
    for s in scored_raw:
        n = by_idx.get(s["product_id"])
        if not n:
            continue
        merged.append({
            "node_key": n.node_key,
            "name": n.name,
            "level": f"L{n.level}",
            "path": n.path,
            "path_str": " > ".join(n.path),
            "pn_count": n.pn_count,
            "score": s["score"],
            "level_label": score_to_level(s["score"]) or "None",
        })

    topk = keep_topk_diverse_tree(merged, k=3)
    return {"topk": topk}
