"""Tests for src/recall_common.py — tokenize, BM25, and embedding text."""
from __future__ import annotations

import pytest
from rank_bm25 import BM25Okapi

from src.load_data import OHProduct
from src.recall_common import (
    bm25_topk,
    build_bm25,
    derive_query_text,
    oh_embed_text,
    tokenize,
)


# ── tokenize ────────────────────────────────────────────────────────────────


class TestTokenize:
    def test_lowercases_input(self):
        assert tokenize("Hello WORLD") == ["hello", "world"]

    def test_extracts_alphanumeric_only(self):
        assert tokenize("foo-bar baz.qux 123") == ["foo", "bar", "baz", "qux", "123"]

    def test_drops_punctuation(self):
        assert tokenize("hello, world!") == ["hello", "world"]

    def test_handles_empty_string(self):
        assert tokenize("") == []

    def test_handles_none(self):
        assert tokenize(None) == []  # type: ignore[arg-type]

    def test_handles_whitespace_only(self):
        assert tokenize("   \t\n  ") == []


# ── build_bm25 ──────────────────────────────────────────────────────────────


class TestBuildBm25:
    def test_builds_index_from_texts(self):
        corpus = ["hello world", "goodbye world", "foo bar"]
        bm25 = build_bm25(corpus)
        assert isinstance(bm25, BM25Okapi)

    def test_empty_corpus_raises_zero_division(self):
        """rank_bm25 divides by corpus size, so an empty corpus raises
        ZeroDivisionError at build time. This documents that behavior so
        callers know to handle it."""
        with pytest.raises(ZeroDivisionError):
            build_bm25([])


# ── bm25_topk ───────────────────────────────────────────────────────────────


class TestBm25Topk:
    def test_returns_top_k_indices(self):
        corpus = ["apple banana", "cherry date", "elderberry fig grape"]
        bm25 = build_bm25(corpus)
        result = bm25_topk("apple", bm25, k=2)
        assert len(result) == 2
        assert all(isinstance(i, int) for i in result)

    def test_relevant_doc_ranked_first(self):
        corpus = ["unrelated text", "apple pie", "another unrelated"]
        bm25 = build_bm25(corpus)
        result = bm25_topk("apple", bm25, k=3)
        assert result[0] == 1  # the "apple pie" doc

    def test_k_larger_than_corpus_returns_all(self):
        corpus = ["a", "b", "c"]
        bm25 = build_bm25(corpus)
        result = bm25_topk("a", bm25, k=10)
        assert len(result) == 3

    def test_empty_query_returns_indices_in_corpus_order(self):
        corpus = ["a b c", "d e f"]
        bm25 = build_bm25(corpus)
        result = bm25_topk("", bm25, k=2)
        assert len(result) == 2


# ── oh_embed_text ────────────────────────────────────────────────────────────


def _oh(
    product_name: str = "Test Product",
    parent_product: str | None = None,
    solution_category: str | None = None,
    solution_sub_category: str | None = None,
    iso: str | None = None,
) -> OHProduct:
    return OHProduct(
        product_guid="g",
        product_name=product_name,
        product_id="pid",
        status="Active",
        business_group="IDG",
        parent_product=parent_product,
        solution_category=solution_category,
        solution_sub_category=solution_sub_category,
        iso=iso,
    )


class TestOhEmbedText:
    def test_includes_product_name(self):
        result = oh_embed_text(_oh(product_name="My Product"))
        assert "My Product" in result

    def test_omits_missing_fields(self):
        result = oh_embed_text(_oh(product_name="X"))
        assert "parent:" not in result
        assert "category:" not in result

    def test_includes_all_present_fields(self):
        result = oh_embed_text(_oh(
            product_name="X",
            parent_product="Y",
            solution_category="C",
            solution_sub_category="S",
            iso="I",
        ))
        assert "X" in result
        assert "parent: Y" in result
        assert "category: C" in result
        assert "sub-category: S" in result
        assert "ISO: I" in result

    def test_uses_pipe_separator(self):
        result = oh_embed_text(_oh(product_name="A", parent_product="B"))
        assert " | " in result


# ── derive_query_text ───────────────────────────────────────────────────────


class TestDeriveQueryText:
    def test_returns_input_when_short(self):
        assert derive_query_text("short text") == "short text"

    def test_truncates_to_max_chars(self):
        long_text = "a" * 3000
        result = derive_query_text(long_text, max_chars=2000)
        assert len(result) == 2000

    def test_empty_string_returns_empty(self):
        assert derive_query_text("") == ""

    def test_none_returns_empty(self):
        assert derive_query_text(None) == ""  # type: ignore[arg-type]

    def test_exact_max_chars_not_truncated(self):
        text = "a" * 2000
        assert derive_query_text(text, max_chars=2000) == text
