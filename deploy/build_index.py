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

from src.load_pn_tree import load_pn_nodes, pn_node_embed_text
from src.recall import EMBED_MODEL_NAME
from src.recall_common import build_bm25

INDEX_DIR = ROOT / "data" / "index"


def main() -> None:
    print("Building Pre-DER index from PN tree...")
    t0 = time.time()

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/4] Loading PN tree nodes...")
    nodes = load_pn_nodes()
    print(f"  Loaded {len(nodes)} nodes")

    print("[2/4] Building corpus texts...")
    corpus_texts = [pn_node_embed_text(n) for n in nodes]
    index_dir = Path
    (INDEX_DIR / "corpus.json").write_text(
        json.dumps(corpus_texts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Saved corpus.json ({len(corpus_texts)} texts)")

    print("[3/4] Building BM25 index...")
    bm25 = build_bm25(corpus_texts)
    (INDEX_DIR / "bm25.pkl").write_bytes(pickle.dumps(bm25))
    print(f"  Saved bm25.pkl")

    print(f"[4/4] Computing dense embeddings via {EMBED_MODEL_NAME}...")
    t1 = time.time()
    model = SentenceTransformer(EMBED_MODEL_NAME)
    embeddings = model.encode(
        corpus_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=8,
    )
    import numpy as np
    np.save(str(INDEX_DIR / "embeddings.npy"), embeddings)
    print(f"  Saved embeddings.npy (shape={embeddings.shape}) in {time.time()-t1:.1f}s")

    print(f"Done. Total: {time.time()-t0:.1f}s")
    print(f"Index files in: {INDEX_DIR}")


if __name__ == "__main__":
    main()
