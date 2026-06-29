from __future__ import annotations

import asyncio
import hmac
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Security, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, field_validator

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.load_pn_tree import PNNode
from src.pre_der_shared import format_candidates_block_v2, node_to_candidate

INDEX_DIR = ROOT / "data" / "index"
PROMPT_PATH = ROOT / "prompts" / "rerank_v2.txt"
DER_PROMPT_PATH = ROOT / "prompts" / "rerank_der_tree.txt"

# ── Global state ──────────────────────────────────────────────────────────────

_index = None
_client = None       # Pre-DER rerank client (rerank_v2.txt)
_der_client = None   # DER Input rerank client (rerank_der_tree.txt)
_nodes: list[PNNode] | None = None
_model = None        # shared SentenceTransformer instance

_index_lock = threading.Lock()

ENDPOINT_TIMEOUT = 50.0   # seconds; stay under Copilot Studio's 60s limit


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client, _der_client, _nodes

    from src.rerank import RerankClient
    from src.load_pn_tree import load_pn_nodes

    _nodes = load_pn_nodes()
    _client = RerankClient(prompt_path=PROMPT_PATH, format_fn=format_candidates_block_v2)
    _der_client = RerankClient(prompt_path=DER_PROMPT_PATH, format_fn=format_candidates_block_v2)
    yield


# ── Shared embedding model ────────────────────────────────────────────────────

def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        from src.recall import EMBED_MODEL_NAME
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


# ── PN tree index (lazy, shared by both endpoints) ────────────────────────────

def _ensure_index():
    global _index
    if _index is not None:
        return
    with _index_lock:
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
            embeddings = model.encode(
                corpus_texts, convert_to_numpy=True,
                normalize_embeddings=True, show_progress_bar=False, batch_size=8,
            )
            np.save(str(INDEX_DIR / "embeddings.npy"), embeddings)

        _index = RecallIndex.from_pretrained(INDEX_DIR, model)


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    lifespan=lifespan,
    title="Product Line Auto-Selection API",
    swagger_ui_parameters={"persistAuthorization": True},
)


@app.middleware("http")
async def _log_request_body(request: Request, call_next):
    if request.url.path == "/recommend_der":
        body = await request.body()
        logging.warning("MIDDLEWARE RAW BODY: %s", body.decode("utf-8", errors="replace"))
    return await call_next(request)


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


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


# ── Pre-DER: free-text voice input → PN tree nodes ───────────────────────────

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
    cand_objs = [node_to_candidate(n, j) for j, n in zip(cand_indices, cand_nodes)]

    from src.confidence import keep_topk_diverse_tree, score_to_level

    loop = asyncio.get_event_loop()
    try:
        scored_raw = await asyncio.wait_for(
            loop.run_in_executor(None, _client.rerank, req.query, req.business_group, cand_objs),
            timeout=ENDPOINT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Recommendation timed out, please retry.")

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
            "level_label": score_to_level(s["score"]),
        })

    topk = keep_topk_diverse_tree(merged, k=3)
    return {"topk": topk}


# ── DER Input: structured DER fields → PN tree nodes ─────────────────────────

class RecommendDerRequest(BaseModel):
    query: str
    business_group: str              # IDG / DCG / SSG — passed as soft signal to rerank prompt
    service_model: str = ""          # DAAS / IAAS / ISG Lease / PROF & MGD SERVICES / SAAS / SI or Vertical
    ars_flag: str = "No"             # Yes / No (also accepts JSON boolean true/false)
    ai_flag: str = "No"              # Yes / No (also accepts JSON boolean true/false)
    scope: str = ""                  # Full D365 scope string — substring-matched against cascade keys.
    # Triggering values (pass the full string): "Standalone Asset Recovery Services Scope",
    # "Managed Services or TruScale \"as a Service\"", "Hardware Lease with Standard Services",
    # "Standalone Professional Services". Empty or non-matching values produce no cascade effect.
    existing_expansion: Optional[bool] = None  # True if expansion of existing TruScale/managed contract

    @field_validator("ars_flag", "ai_flag", mode="before")
    @classmethod
    def _coerce_bool_flag(cls, v):
        if isinstance(v, bool):
            return "Yes" if v else "No"
        return v


@app.post("/recommend_der", dependencies=[Depends(_verify_key)])
async def recommend_der(req: RecommendDerRequest, request: Request):
    body_bytes = await request.body()
    logging.warning("RAW /recommend_der BODY: %s", body_bytes.decode("utf-8", errors="replace"))
    global _index, _der_client, _nodes
    if _der_client is None or _nodes is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    _ensure_index()
    if _index is None:
        raise HTTPException(status_code=503, detail="Index not available")

    bg = req.business_group.strip().upper()
    if bg not in ("IDG", "DCG", "SSG"):
        raise HTTPException(status_code=400, detail="business_group must be IDG, DCG, or SSG")

    from src.load_data import DERRow
    from src.field_rules import apply_field_rules_tree, inject_field_candidates_tree
    from src.confidence import keep_topk_diverse_tree, score_to_level

    synthetic_row = DERRow(
        opportunity_id="api-request",
        business_group=bg,
        description=req.query,
        service_model=req.service_model or None,
        is_ars=(req.ars_flag.strip().lower() == "yes") if req.ars_flag else None,
        is_emerging_tech=(req.ai_flag.strip().lower() == "yes") if req.ai_flag else None,
        scope=req.scope or None,
        is_existing_expansion=req.existing_expansion,
    )

    # BM25 + dense recall against shared PN tree index
    recall_indices = _index.recall(req.query, topk=60)

    # Field cascade: boost/inject PN tree nodes matching structured DER fields
    rules = apply_field_rules_tree(synthetic_row, _nodes)
    merged_indices = inject_field_candidates_tree(recall_indices, _nodes, rules, max_candidates=30)

    if not merged_indices:
        return {"topk": []}

    cand_nodes = [_nodes[j] for j in merged_indices]
    cand_objs = [node_to_candidate(n, j) for j, n in zip(merged_indices, cand_nodes)]

    loop = asyncio.get_event_loop()
    try:
        scored_raw = await asyncio.wait_for(
            loop.run_in_executor(None, _der_client.rerank, req.query, bg, cand_objs),
            timeout=ENDPOINT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Recommendation timed out, please retry.")

    by_idx = {str(j): n for j, n in zip(merged_indices, cand_nodes)}
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
            "level_label": score_to_level(s["score"]),
        })

    topk = keep_topk_diverse_tree(merged, k=3)
    return {"topk": topk}
