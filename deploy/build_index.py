"""Build the PN tree search index baked into the Docker image.

Run automatically by Dockerfile:  RUN python deploy/build_index.py
Run manually:                      python deploy/build_index.py
"""

from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentence_transformers import SentenceTransformer
import numpy as np

from src.recall import EMBED_MODEL_NAME
from src.recall_common import build_bm25


# ── Shared model (loaded once, reused for both index builds) ─────────────────

def _load_model() -> SentenceTransformer:
    print(f"Loading embedding model: {EMBED_MODEL_NAME}...")
    return SentenceTransformer(EMBED_MODEL_NAME)


def _build_and_save(corpus_texts: list[str], index_dir: Path, model: SentenceTransformer, batch_size: int = 8) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)

    (index_dir / "corpus.json").write_text(
        json.dumps(corpus_texts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    bm25 = build_bm25(corpus_texts)
    (index_dir / "bm25.pkl").write_bytes(pickle.dumps(bm25))

    t0 = time.time()
    embeddings = model.encode(
        corpus_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=batch_size,
    )
    np.save(str(index_dir / "embeddings.npy"), embeddings)
    print(f"    embeddings.npy shape={embeddings.shape}, {time.time()-t0:.1f}s")


# ── Part 1: Pre-DER index (PN tree nodes) ────────────────────────────────────

def build_pre_der_index(model: SentenceTransformer) -> None:
    from src.load_pn_tree import load_pn_nodes, pn_node_embed_text

    index_dir = ROOT / "data" / "index"
    print(f"\n[Pre-DER] Building PN tree index → {index_dir}")

    nodes = load_pn_nodes()
    print(f"  {len(nodes)} PN tree nodes")

    corpus_texts = [pn_node_embed_text(n) for n in nodes]
    _build_and_save(corpus_texts, index_dir, model)
    print(f"  Saved {len(corpus_texts)} texts to {index_dir}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t_total = time.time()
    model = _load_model()
    build_pre_der_index(model)
    print(f"\nIndex built in {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
