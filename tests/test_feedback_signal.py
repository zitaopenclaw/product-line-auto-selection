from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.feedback_signal import load_feedback_index, apply_feedback_signal


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _write_index(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "feedback_index.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _candidates(node_keys: list[str], bg: str = "IDG") -> list[dict]:
    return [
        {"node_key": nk, "score": 0.80, "confidence": "High", "bg": bg}
        for nk in node_keys
    ]


NODE_A = "L4|GPS|Config|Integration|FIS"
NODE_B = "L4|GPS|Field|OnSite|OS"
KEY_A = f"IDG|{NODE_A}"
KEY_B = f"IDG|{NODE_B}"


class TestLoadFeedbackIndex:
    def test_loads_valid_index(self, tmp_path):
        _write_index(tmp_path, {KEY_A: {"pos": 10, "neg": 0, "signal": 0.15}})
        index = load_feedback_index(tmp_path / "feedback_index.json")
        assert KEY_A in index
        assert index[KEY_A]["signal"] == 0.15

    def test_missing_file_returns_empty(self, tmp_path):
        index = load_feedback_index(tmp_path / "nonexistent.json")
        assert index == {}

    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "feedback_index.json"
        p.write_text("{}")
        index = load_feedback_index(p)
        assert index == {}


class TestApplyFeedbackSignal:
    def test_b_group_positive_signal_boosts_score(self, tmp_path):
        index = {KEY_A: {"pos": 10, "neg": 0, "signal": 0.15}}
        candidates = _candidates([NODE_A])
        result = apply_feedback_signal(candidates, index, bg="IDG", ab_group="B")
        assert result[0]["score"] > 0.80

    def test_b_group_negative_signal_reduces_score(self, tmp_path):
        index = {KEY_A: {"pos": 0, "neg": 10, "signal": -0.15}}
        candidates = _candidates([NODE_A])
        result = apply_feedback_signal(candidates, index, bg="IDG", ab_group="B")
        assert result[0]["score"] < 0.80

    def test_a_group_signal_not_applied(self):
        index = {KEY_A: {"pos": 10, "neg": 0, "signal": 0.15}}
        candidates = _candidates([NODE_A])
        result = apply_feedback_signal(candidates, index, bg="IDG", ab_group="A")
        assert result[0]["score"] == pytest.approx(0.80)

    def test_node_not_in_index_score_unchanged(self):
        index = {}
        candidates = _candidates([NODE_A])
        result = apply_feedback_signal(candidates, index, bg="IDG", ab_group="B")
        assert result[0]["score"] == pytest.approx(0.80)

    def test_score_capped_at_1_0(self):
        index = {KEY_A: {"pos": 100, "neg": 0, "signal": 0.15}}
        candidates = [{"node_key": NODE_A, "score": 0.99, "confidence": "High", "bg": "IDG"}]
        result = apply_feedback_signal(candidates, index, bg="IDG", ab_group="B")
        assert result[0]["score"] <= 1.0

    def test_score_floored_at_0_0(self):
        index = {KEY_A: {"pos": 0, "neg": 100, "signal": -0.15}}
        candidates = [{"node_key": NODE_A, "score": 0.05, "confidence": "High", "bg": "IDG"}]
        result = apply_feedback_signal(candidates, index, bg="IDG", ab_group="B")
        assert result[0]["score"] >= 0.0

    def test_multiple_candidates_each_adjusted_independently(self):
        index = {
            KEY_A: {"pos": 10, "neg": 0, "signal": 0.15},
            KEY_B: {"pos": 0, "neg": 10, "signal": -0.15},
        }
        candidates = _candidates([NODE_A, NODE_B])
        result = apply_feedback_signal(candidates, index, bg="IDG", ab_group="B")
        assert result[0]["score"] > 0.80
        assert result[1]["score"] < 0.80

    def test_original_candidates_not_mutated(self):
        index = {KEY_A: {"pos": 10, "neg": 0, "signal": 0.15}}
        candidates = _candidates([NODE_A])
        original_score = candidates[0]["score"]
        apply_feedback_signal(candidates, index, bg="IDG", ab_group="B")
        assert candidates[0]["score"] == original_score
