from __future__ import annotations

import asyncio
import hmac
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.load_pn_tree import PNNode

INDEX_DIR = ROOT / "data" / "index"
DER_INDEX_ROOT = ROOT / "data" / "index" / "der"
PROMPT_PATH = ROOT / "prompts" / "rerank_v2.txt"
DER_PROMPT_PATH = ROOT / "prompts" / "rerank.txt"

# ── Global state ──────────────────────────────────────────────────────────────

_index = None
_client = None
_der_client = None
_nodes: list[PNNode] | None = None
_model = None                          # shared SentenceTransformer instance
_der_indices: dict = {}                # BG -> RecallIndex
_der_products: dict = {}               # BG -> list[OHProduct]


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client, _der_client, _nodes

    from src.rerank import RerankClient
    from src.load_pn_tree import load_pn_nodes

    _nodes = load_pn_nodes()
    _client = RerankClient(prompt_path=PROMPT_PATH, format_fn=_format_candidates_block_v2)
    _der_client = RerankClient(prompt_path=DER_PROMPT_PATH)
    yield


# ── Shared embedding model ────────────────────────────────────────────────────

def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        from src.recall import EMBED_MODEL_NAME
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


# ── Pre-DER index (lazy) ──────────────────────────────────────────────────────

def _ensure_index():
    global _index
    if _index is not None:
        return
    import json
    import pickle

    import numpy as np
    from src.recall import RecallIndex
    from src.recall_common import build_bm25
    from src.load_pn_tree import pn_node_embed_text

    model = _get_model()

    if not (INDEX_DIR / "embeddings.npy").exists():
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        corpus_texts = [pn_node_embed_text(n) for n in _nodes]
        (INDEX_DIR / "corpus.json").write_text(json.dumps(corpus_texts), encoding="utf-8")
        bm25 = build_bm25(corpus_texts)
        (INDEX_DIR / "bm25.pkl").write_bytes(pickle.dumps(bm25))
        embeddings = model.encode(corpus_texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False, batch_size=8)
        np.save(str(INDEX_DIR / "embeddings.npy"), embeddings)

    _index = RecallIndex.from_pretrained(INDEX_DIR, model)


# ── DER index (lazy, per BG) ──────────────────────────────────────────────────

def _ensure_der_index(bg: str) -> None:
    if bg in _der_indices:
        return

    import json
    from src.load_data import OHProduct
    from src.recall import RecallIndex
    from src.recall_common import build_bm25, oh_embed_text
    import numpy as np, pickle

    products_path = ROOT / "output" / f"oh_products_{bg}.json"
    if not products_path.exists():
        raise HTTPException(status_code=503, detail=f"OH product data not available for BG: {bg}")

    raw = json.loads(products_path.read_text(encoding="utf-8"))
    products = [OHProduct(**d) for d in raw]

    model = _get_model()
    index_dir = DER_INDEX_ROOT / bg

    if not (index_dir / "embeddings.npy").exists():
        # Fallback: build on the fly (first request after deployment without pre-built index)
        index_dir.mkdir(parents=True, exist_ok=True)
        corpus_texts = [oh_embed_text(p) for p in products]
        (index_dir / "corpus.json").write_text(json.dumps(corpus_texts), encoding="utf-8")
        bm25 = build_bm25(corpus_texts)
        (index_dir / "bm25.pkl").write_bytes(pickle.dumps(bm25))
        embeddings = model.encode(corpus_texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False, batch_size=32)
        np.save(str(index_dir / "embeddings.npy"), embeddings)

    _der_indices[bg] = RecallIndex.from_pretrained(index_dir, model)
    _der_products[bg] = products


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    lifespan=lifespan,
    title="Pre-DER Recommendation API",
    swagger_ui_parameters={"persistAuthorization": True},
)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── Candidate formatters ──────────────────────────────────────────────────────

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


# ── Auth ──────────────────────────────────────────────────────────────────────

async def _verify_key(x_api_key: str | None = Security(_api_key_header)):
    expected = os.environ.get("APP_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Server auth not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API Key")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Pre-DER: free-text → PN tree nodes ───────────────────────────────────────

class RecommendRequest(BaseModel):
    query: str
    business_group: str = ""


@app.post("/recommend", dependencies=[Depends(_verify_key)])
async def recommend(req: RecommendRequest):
    global _index, _client, _nodes
    if _client is None or _nodes is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    _ensure_index()
    if _index is None:
        raise HTTPException(status_code=503, detail="Index not available")

    cand_indices = _index.recall(req.query, topk=60)[:30]
    if not cand_indices:
        return {"topk": []}

    cand_nodes = [_nodes[j] for j in cand_indices]
    cand_objs = [_node_to_candidate(n, j) for j, n in zip(cand_indices, cand_nodes)]

    from src.confidence import keep_topk_diverse_tree, score_to_level

    loop = asyncio.get_event_loop()
    scored_raw = await loop.run_in_executor(None, _client.rerank, req.query, req.business_group, cand_objs)

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


# ── DER: structured form → flat OH products ───────────────────────────────────

class RecommendDerRequest(BaseModel):
    query: str
    business_group: str              # IDG / DCG / SSG (hard filter, required)
    service_model: str = ""          # DAAS / IAAS / ISG Lease / PROF & MGD SERVICES / SAAS / SI or Vertical
    ars_flag: str = "No"             # Yes / No
    ai_flag: str = "No"              # Yes / No
    scope: str = ""                  # New / Expansion / Renewal


@app.post("/recommend_der", dependencies=[Depends(_verify_key)])
async def recommend_der(req: RecommendDerRequest):
    global _der_client

    bg = req.business_group.strip().upper()
    # Normalize common variations
    if bg not in ("IDG", "DCG", "SSG"):
        raise HTTPException(status_code=400, detail="business_group must be IDG, DCG, or SSG")

    if _der_client is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    _ensure_der_index(bg)

    products = _der_products[bg]
    der_index = _der_indices[bg]

    from src.load_data import DERRow
    from src.field_rules import apply_field_rules, inject_field_candidates
    from src.rerank import Candidate
    from src.confidence import keep_topk_diverse, score_to_level

    # Build a synthetic DERRow from API request fields
    synthetic_row = DERRow(
        opportunity_id="api-request",
        business_group=bg,
        description=req.query,
        service_model=req.service_model or None,
        is_ars=(req.ars_flag.strip().lower() == "yes") if req.ars_flag else None,
        is_emerging_tech=(req.ai_flag.strip().lower() == "yes") if req.ai_flag else None,
        scope=req.scope or None,
        is_existing_expansion=None,
    )

    # BM25 + dense recall
    recall_indices = der_index.recall(req.query, topk=60)

    # Helen's field cascade: inject guaranteed/boosted OH products
    rules = apply_field_rules(synthetic_row, products)
    merged_indices = inject_field_candidates(recall_indices, products, rules, max_candidates=30)

    if not merged_indices:
        return {"topk": []}

    cand_objs = [
        Candidate(
            product_id=products[i].product_id,
            product_name=products[i].product_name,
            parent_product=products[i].parent_product,
            solution_category=products[i].solution_category,
            solution_sub_category=products[i].solution_sub_category,
            iso=products[i].iso,
        )
        for i in merged_indices
    ]

    loop = asyncio.get_event_loop()
    scored_raw = await loop.run_in_executor(None, _der_client.rerank, req.query, bg, cand_objs)

    pid_to_product = {products[i].product_id: products[i] for i in merged_indices}
    merged = []
    for s in scored_raw:
        p = pid_to_product.get(s["product_id"])
        if not p:
            continue
        parent = p.parent_product or ""
        merged.append({
            "name": p.product_name,
            "path_str": f"{parent} > {p.product_name}" if parent else p.product_name,
            "category": p.solution_category or "",
            "score": s["score"],
            "level_label": score_to_level(s["score"]) or "None",
            "parent_product": parent,  # used by keep_topk_diverse for diversity; not in API spec
        })

    topk = keep_topk_diverse(merged, k=3)
    # Strip internal diversity key before returning
    for item in topk:
        item.pop("parent_product", None)
    return {"topk": topk}
