"""Tests for src/confidence.py — score → level mapping and top-k selection.

Confidence levels:
    High   >= 0.85
    Medium >= 0.60
    Low    >= 0.40
    drop   <  0.40
"""
from __future__ import annotations

import pytest

from src.confidence import (
    HIGH_THRESHOLD,
    LOW_THRESHOLD,
    MEDIUM_THRESHOLD,
    keep_topk,
    keep_topk_diverse,
    keep_topk_diverse_tree,
    score_to_level,
)


# ── score_to_level ──────────────────────────────────────────────────────────


class TestScoreToLevel:
    """Boundary tests for the score → confidence-level mapping."""

    def test_above_high_threshold_returns_high(self):
        assert score_to_level(0.90) == "High"
        assert score_to_level(1.0) == "High"

    def test_exactly_high_threshold_returns_high(self):
        assert score_to_level(HIGH_THRESHOLD) == "High"

    def test_below_high_above_medium_returns_medium(self):
        assert score_to_level(0.84) == "Medium"
        assert score_to_level(0.70) == "Medium"

    def test_exactly_medium_threshold_returns_medium(self):
        assert score_to_level(MEDIUM_THRESHOLD) == "Medium"

    def test_below_medium_above_low_returns_low(self):
        assert score_to_level(0.59) == "Low"
        assert score_to_level(0.50) == "Low"

    def test_exactly_low_threshold_returns_low(self):
        assert score_to_level(LOW_THRESHOLD) == "Low"

    def test_below_low_threshold_returns_none_label(self):
        assert score_to_level(0.39) == "None"
        assert score_to_level(0.0) == "None"

    def test_none_input_returns_none_label(self):
        assert score_to_level(None) == "None"


# ── keep_topk ───────────────────────────────────────────────────────────────


class TestKeepTopk:
    """Tests for the simple top-k selection (no diversity)."""

    def test_returns_top_k_sorted_descending(self):
        scored = [
            {"product_id": "p1", "score": 0.5, "parent_product": "A"},
            {"product_id": "p2", "score": 0.9, "parent_product": "B"},
            {"product_id": "p3", "score": 0.7, "parent_product": "C"},
        ]
        result = keep_topk(scored, k=2)
        assert [c["product_id"] for c in result] == ["p2", "p3"]

    def test_drops_sub_threshold_candidates(self):
        scored = [
            {"product_id": "p1", "score": 0.9, "parent_product": "A"},
            {"product_id": "p2", "score": 0.3, "parent_product": "B"},  # below threshold
            {"product_id": "p3", "score": 0.5, "parent_product": "C"},
        ]
        result = keep_topk(scored, k=3)
        assert len(result) == 2
        assert all(c["score"] >= LOW_THRESHOLD for c in result)

    def test_empty_input_returns_empty(self):
        assert keep_topk([], k=3) == []

    def test_handles_missing_score(self):
        scored = [
            {"product_id": "p1", "score": None, "parent_product": "A"},
            {"product_id": "p2", "score": 0.8, "parent_product": "B"},
        ]
        result = keep_topk(scored, k=3)
        assert [c["product_id"] for c in result] == ["p2"]


# ── keep_topk_diverse ────────────────────────────────────────────────────────


class TestKeepTopkDiverse:
    """Tests for the diverse top-k selection (different parent_product)."""

    def test_avoids_same_parent(self):
        scored = [
            {"product_id": "p1", "score": 0.9, "parent_product": "A"},
            {"product_id": "p2", "score": 0.8, "parent_product": "A"},  # same parent
            {"product_id": "p3", "score": 0.7, "parent_product": "B"},
        ]
        result = keep_topk_diverse(scored, k=2)
        assert [c["product_id"] for c in result] == ["p1", "p3"]

    def test_fills_deferred_when_needed(self):
        scored = [
            {"product_id": "p1", "score": 0.9, "parent_product": "A"},
            {"product_id": "p2", "score": 0.8, "parent_product": "A"},
            {"product_id": "p3", "score": 0.7, "parent_product": "A"},
        ]
        result = keep_topk_diverse(scored, k=3)
        # When all share parent, deferred fill kicks in.
        assert len(result) == 3

    def test_treats_none_parent_as_unique(self):
        scored = [
            {"product_id": "p1", "score": 0.9, "parent_product": None},
            {"product_id": "p2", "score": 0.8, "parent_product": None},
        ]
        result = keep_topk_diverse(scored, k=2)
        # None → "(none)" bucket, both kept because of fallback fill
        assert len(result) == 2

    def test_drops_sub_threshold_candidates(self):
        scored = [
            {"product_id": "p1", "score": 0.9, "parent_product": "A"},
            {"product_id": "p2", "score": 0.3, "parent_product": "B"},
        ]
        result = keep_topk_diverse(scored, k=3)
        assert [c["product_id"] for c in result] == ["p1"]


# ── keep_topk_diverse_tree ───────────────────────────────────────────────────


class TestKeepTopkDiverseTree:
    """Tests for tree-aware diverse selection (no ancestor-descendant pairs)."""

    def test_avoids_ancestor_descendant_pair(self):
        scored = [
            {"path": ["L1", "L2"], "score": 0.9, "name": "ancestor"},
            {"path": ["L1", "L2", "L3"], "score": 0.85, "name": "descendant"},
            {"path": ["L1", "OTHER"], "score": 0.8, "name": "sibling"},
        ]
        result = keep_topk_diverse_tree(scored, k=2)
        names = [c["name"] for c in result]
        assert "ancestor" in names
        assert "descendant" not in names

    def test_keeps_siblings_at_same_level(self):
        scored = [
            {"path": ["L1", "A", "B"], "score": 0.9, "name": "x"},
            {"path": ["L1", "A", "C"], "score": 0.8, "name": "y"},
            {"path": ["L1", "A", "D"], "score": 0.7, "name": "z"},
        ]
        result = keep_topk_diverse_tree(scored, k=3)
        assert len(result) == 3

    def test_empty_path_falls_back(self):
        scored = [
            {"path": [], "score": 0.9, "name": "a"},
            {"path": ["L1"], "score": 0.8, "name": "b"},
        ]
        result = keep_topk_diverse_tree(scored, k=2)
        assert len(result) == 2

    def test_drops_sub_threshold_candidates(self):
        scored = [
            {"path": ["L1", "L2"], "score": 0.9, "name": "a"},
            {"path": ["L1", "L3"], "score": 0.2, "name": "b"},  # below threshold
        ]
        result = keep_topk_diverse_tree(scored, k=3)
        assert [c["name"] for c in result] == ["a"]

    def test_fills_deferred_when_all_ancestor_descendant(self):
        # All three form a strict ancestor chain → deferred fill must supply slots 2 & 3
        scored = [
            {"path": ["A", "B"], "score": 0.9, "name": "root"},
            {"path": ["A", "B", "C"], "score": 0.8, "name": "child"},
            {"path": ["A", "B", "C", "D"], "score": 0.7, "name": "grandchild"},
        ]
        result = keep_topk_diverse_tree(scored, k=3)
        assert len(result) == 3
        assert result[0]["name"] == "root"
        # child and grandchild filled from deferred in score order
        assert result[1]["name"] == "child"
        assert result[2]["name"] == "grandchild"

    def test_deferred_fill_partial_conflict(self):
        # First two slots filled diversely; third must come from deferred
        scored = [
            {"path": ["A", "B"], "score": 0.9, "name": "p1"},
            {"path": ["X", "Y"], "score": 0.85, "name": "p2"},
            {"path": ["A", "B", "C"], "score": 0.8, "name": "p3"},  # descendant of p1 → deferred
        ]
        result = keep_topk_diverse_tree(scored, k=3)
        assert len(result) == 3
        names = [c["name"] for c in result]
        assert "p1" in names
        assert "p2" in names
        assert "p3" in names  # filled from deferred
