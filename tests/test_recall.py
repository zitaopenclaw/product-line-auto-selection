"""Tests for src/recall.py — RecallIndex (BM25 + dense embedding recall).

These tests use a mock SentenceTransformer so they do NOT download the
~30MB bge-small-en-v1.5 model. They are marked @slow because the
production code path involves real model loading.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.recall import RecallIndex


pytestmark = pytest.mark.slow


def _mock_model() -> MagicMock:
    """A mock SentenceTransformer that returns fixed embeddings."""
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


class TestRecallIndex:
    def test_recall_returns_relevant_results_first(self):
        corpus = ["ThinkPad X1 Carbon laptop", "ThinkSystem Server", "Managed Service"]
        idx = RecallIndex(corpus_texts=corpus, model=_mock_model())
        results = idx.recall("laptop deployment", topk=3)
        assert results[0] == 0

    def test_recall_respects_topk(self):
        corpus = [f"Product {i}" for i in range(10)]
        idx = RecallIndex(corpus_texts=corpus, model=_mock_model())
        results = idx.recall("Product", topk=3)
        assert len(results) == 3

    def test_recall_handles_empty_description(self):
        corpus = ["A", "B"]
        idx = RecallIndex(corpus_texts=corpus, model=_mock_model())
        results = idx.recall("", topk=2)
        assert len(results) <= 2

    def test_recall_unions_bm25_and_dense(self):
        corpus = ["ThinkPad laptop", "Server rack", "Generic Laptop Accessory"]
        idx = RecallIndex(corpus_texts=corpus, model=_mock_model())
        results = idx.recall("laptop", topk=3)
        assert len(results) == 3
        assert 0 in results  # ThinkPad laptop

    def test_recall_returns_valid_indices(self):
        corpus = ["X", "Y", "Z"]
        idx = RecallIndex(corpus_texts=corpus, model=_mock_model())
        results = idx.recall("X", topk=3)
        for r in results:
            assert 0 <= r < len(corpus)


class TestRecallIndexFromPretrained:
    def test_from_pretrained_loads_and_recalls_correctly(self, tmp_path):
        corpus = ["ThinkPad X1 Carbon laptop", "ThinkSystem Server", "Managed Service"]
        model = _mock_model()
        idx = RecallIndex(corpus_texts=corpus, model=model)

        (tmp_path / "corpus.json").write_text(json.dumps(idx.corpus_texts), encoding="utf-8")
        (tmp_path / "bm25.pkl").write_bytes(pickle.dumps(idx.bm25))
        np.save(str(tmp_path / "embeddings.npy"), idx.embeddings)

        loaded = RecallIndex.from_pretrained(tmp_path, model)
        assert loaded.corpus_texts == idx.corpus_texts
        assert loaded.embeddings.shape == idx.embeddings.shape

        original_results = idx.recall("laptop deployment", topk=3)
        loaded_results = loaded.recall("laptop deployment", topk=3)
        assert original_results == loaded_results

    def test_from_pretrained_missing_file_raises(self, tmp_path):
        model = _mock_model()
        with pytest.raises(Exception):
            RecallIndex.from_pretrained(tmp_path, model)
