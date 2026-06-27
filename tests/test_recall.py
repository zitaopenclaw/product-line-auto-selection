"""Tests for src/recall.py — RecallIndex (BM25 + dense embedding recall).

These tests use a mock SentenceTransformer so they do NOT download the
~30MB bge-small-en-v1.5 model. They are marked @slow because the
production code path involves real model loading.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.load_data import OHProduct
from src.recall import RecallIndex


pytestmark = pytest.mark.slow


# ── Fixtures ───────────────────────────────────────────────────────────────


def _oh(name: str, parent: str | None = None) -> OHProduct:
    return OHProduct(
        product_guid=f"g-{name}",
        product_name=name,
        product_id=f"pid-{name}",
        status="Active",
        business_group="IDG",
        parent_product=parent,
        solution_category=None,
        solution_sub_category=None,
        iso=None,
    )


def _mock_model() -> MagicMock:
    """A mock SentenceTransformer that returns fixed embeddings.

    Each text is mapped to a one-hot-ish vector so cosine similarity
    reflects lexical overlap. Good enough to test ranking behavior.
    """
    model = MagicMock()
    vocab = {
        "thinkpad": np.array([1.0, 0.0, 0.0, 0.0]),
        "laptop":   np.array([0.0, 1.0, 0.0, 0.0]),
        "server":   np.array([0.0, 0.0, 1.0, 0.0]),
        "service":  np.array([0.0, 0.0, 0.0, 1.0]),
    }

    def encode(texts, **_kwargs):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for t in texts:
            t = t.lower()
            v = np.zeros(4)
            for w, vec in vocab.items():
                if w in t:
                    v = v + vec
            norm = np.linalg.norm(v) or 1.0
            out.append(v / norm)
        return np.array(out)

    model.encode = encode
    return model


# ── Tests ──────────────────────────────────────────────────────────────────


class TestRecallIndex:
    def test_recall_returns_relevant_results_first(self):
        products = [
            _oh("ThinkPad X1 Carbon"),
            _oh("ThinkSystem Server"),
            _oh("Managed Service"),
        ]
        idx = RecallIndex(products, model=_mock_model())
        results = idx.recall("laptop deployment", topk=3)
        # BM25 may prefer ThinkPad (exact word match) over Server/Service
        assert products[results[0]].product_name == "ThinkPad X1 Carbon"

    def test_recall_respects_topk(self):
        products = [_oh(f"Product {i}") for i in range(10)]
        idx = RecallIndex(products, model=_mock_model())
        results = idx.recall("Product", topk=3)
        assert len(results) == 3

    def test_recall_handles_empty_description(self):
        products = [_oh("A"), _oh("B")]
        idx = RecallIndex(products, model=_mock_model())
        # Should not raise; returns BM25-only results
        results = idx.recall("", topk=2)
        assert len(results) <= 2

    def test_recall_unions_bm25_and_dense(self):
        # Construct corpus where BM25 and dense would return different orderings
        products = [
            _oh("ThinkPad laptop"),         # strong in both
            _oh("Server rack"),             # strong in dense only via "laptop"→"server" vec distance
            _oh("Generic Laptop Accessory"),  # bm25-only
        ]
        idx = RecallIndex(products, model=_mock_model())
        # When query is "laptop" — both BM25 and dense will surface the laptop-related ones
        results = idx.recall("laptop", topk=3)
        # All three should be in the union
        assert len(results) == 3
        names = [products[i].product_name for i in results]
        assert "ThinkPad laptop" in names

    def test_recall_returns_indices_into_products_list(self):
        products = [_oh("X"), _oh("Y"), _oh("Z")]
        idx = RecallIndex(products, model=_mock_model())
        results = idx.recall("X", topk=3)
        for r in results:
            assert 0 <= r < len(products)


class TestRecallIndexFromPretrained:
    def test_from_pretrained_loads_and_recalls_correctly(self, tmp_path):
        """Build an index, persist to disk, reload via from_pretrained, verify recall matches."""
        products = [
            _oh("ThinkPad X1 Carbon"),
            _oh("ThinkSystem Server"),
            _oh("Managed Service"),
        ]
        model = _mock_model()
        idx = RecallIndex(products, model=model)

        # Persist index to tmp_path (mirrors what deploy/build_index.py does)
        (tmp_path / "corpus.json").write_text(
            json.dumps(idx.corpus_texts), encoding="utf-8"
        )
        (tmp_path / "bm25.pkl").write_bytes(pickle.dumps(idx.bm25))
        np.save(str(tmp_path / "embeddings.npy"), idx.embeddings)

        # Load via from_pretrained using the same mock model
        loaded = RecallIndex.from_pretrained(tmp_path, model)

        assert loaded.corpus_texts == idx.corpus_texts
        assert loaded.embeddings.shape == idx.embeddings.shape

        # Recall results must be identical
        original_results = idx.recall("laptop deployment", topk=3)
        loaded_results = loaded.recall("laptop deployment", topk=3)
        assert original_results == loaded_results

    def test_from_pretrained_missing_file_raises(self, tmp_path):
        """Missing index files should raise, not return a silently broken index."""
        model = _mock_model()
        with pytest.raises(Exception):
            RecallIndex.from_pretrained(tmp_path, model)
