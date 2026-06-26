import numpy as np
from sentence_transformers import SentenceTransformer

from src.load_data import OHProduct
from src.recall_common import (
    bm25_topk,
    build_bm25,
    derive_query_text,
    oh_embed_text,
    tokenize,
)

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_TOPK = 30


class RecallIndex:
    def __init__(
        self,
        products: list[OHProduct] | None = None,
        model: SentenceTransformer | None = None,
        *,
        corpus_texts: list[str] | None = None,
    ):
        self.products = products or []
        if corpus_texts is None:
            corpus_texts = [oh_embed_text(p) for p in self.products]
        self.corpus_texts = corpus_texts
        self.bm25 = build_bm25(self.corpus_texts)
        if model is None:
            model = SentenceTransformer(EMBED_MODEL_NAME)
        self.model = model
        self.embeddings = model.encode(
            self.corpus_texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )

    def recall(self, description: str, topk: int = DEFAULT_TOPK) -> list[int]:
        ids_bm25 = bm25_topk(description or "", self.bm25, topk)
        q = derive_query_text(description or "")
        cos = None
        ids_dense: set[int] = set()
        if q.strip():
            q_vec = self.model.encode([q], convert_to_numpy=True, normalize_embeddings=True)[0]
            cos = self.embeddings @ q_vec
            order = np.argsort(-cos)[:topk]
            ids_dense = set(int(i) for i in order)
        ids_bm25_set = set(ids_bm25)
        union = list(ids_bm25_set | ids_dense)
        if cos is not None:
            # Rank union by actual cosine score so dense-quality items surface first.
            # BM25-only items are included with their real (possibly lower) cosine score.
            union_sorted = sorted(union, key=lambda i: -float(cos[i]))
        else:
            # No dense index — preserve BM25 rank ordering.
            bm25_rank = {idx: rank for rank, idx in enumerate(ids_bm25)}
            union_sorted = sorted(union, key=lambda i: bm25_rank.get(i, len(union)))
        return union_sorted[:topk]
