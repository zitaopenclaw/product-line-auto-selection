from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.feedback_aggregator import FeedbackAggregator, MIN_SAMPLES, DELTA_CAP


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rec(node_key: str, rank: int, is_negative: bool = False, bg: str = "IDG") -> dict:
    selected = None if is_negative else rank
    return {
        "feedback_id": "x",
        "timestamp": "2026-07-01T10:00:00Z",
        "opportunity_id": "OPP-001",
        "bg": bg,
        "der_description": "test",
        "scope": "",
        "service_model": "",
        "ars_flag": False,
        "ai_flag": False,
        "candidates_shown": [{"rank": 1, "node_key": node_key, "score": 0.85, "confidence": "High"}],
        "user_selected_rank": selected,
        "is_negative": is_negative,
        "negative_hint": None,
        "ab_group": "B",
    }


NODE = "L4|GPS|Config|Integration|FIS"
KEY = f"IDG|{NODE}"


class TestConstants:
    def test_min_samples_is_5(self):
        assert MIN_SAMPLES == 5

    def test_delta_cap_is_0_15(self):
        assert DELTA_CAP == 0.15


class TestFeedbackAggregator:
    def test_below_min_samples_signal_is_zero(self):
        records = [_rec(NODE, rank=1) for _ in range(4)]  # 4 < 5
        agg = FeedbackAggregator(records)
        index = agg.build()
        assert KEY not in index or index[KEY]["signal"] == 0.0

    def test_exactly_min_samples_signal_nonzero(self):
        records = [_rec(NODE, rank=1) for _ in range(5)]  # all positive
        agg = FeedbackAggregator(records)
        index = agg.build()
        assert KEY in index
        assert index[KEY]["signal"] > 0.0

    def test_all_positive_signal_equals_delta_cap(self):
        records = [_rec(NODE, rank=1) for _ in range(10)]
        agg = FeedbackAggregator(records)
        index = agg.build()
        assert abs(index[KEY]["signal"] - DELTA_CAP) < 1e-9

    def test_all_negative_signal_equals_neg_delta_cap(self):
        records = [_rec(NODE, rank=None, is_negative=True) for _ in range(10)]
        agg = FeedbackAggregator(records)
        index = agg.build()
        assert abs(index[KEY]["signal"] - (-DELTA_CAP)) < 1e-9

    def test_mixed_signal_formula(self):
        # 8 pos, 2 neg → (8-2)/10 × 0.15 = 0.09
        records = (
            [_rec(NODE, rank=1) for _ in range(8)] +
            [_rec(NODE, rank=None, is_negative=True) for _ in range(2)]
        )
        agg = FeedbackAggregator(records)
        index = agg.build()
        expected = (8 - 2) / 10 * DELTA_CAP
        assert abs(index[KEY]["signal"] - expected) < 1e-9

    def test_pos_neg_counts_stored(self):
        records = (
            [_rec(NODE, rank=1) for _ in range(7)] +
            [_rec(NODE, rank=None, is_negative=True) for _ in range(3)]
        )
        agg = FeedbackAggregator(records)
        index = agg.build()
        assert index[KEY]["pos"] == 7
        assert index[KEY]["neg"] == 3

    def test_selected_rank_2_counts_as_positive(self):
        # User selected rank 2 — still a positive signal for that node_key
        rec = _rec(NODE, rank=2)
        # rank 2 means candidates_shown[0] was NOT selected, so node at rank=1 is not positive
        # We need to set up candidates_shown properly
        rec["candidates_shown"] = [
            {"rank": 1, "node_key": "L4|OTHER", "score": 0.85, "confidence": "High"},
            {"rank": 2, "node_key": NODE, "score": 0.72, "confidence": "Medium"},
        ]
        rec["user_selected_rank"] = 2
        records = [rec] * 5
        agg = FeedbackAggregator(records)
        index = agg.build()
        assert index[KEY]["pos"] == 5

    def test_multiple_nodes_aggregated_independently(self):
        node_a = "L4|GPS|Config|A"
        node_b = "L4|GPS|Field|B"
        key_a = f"IDG|{node_a}"
        key_b = f"IDG|{node_b}"

        def _multi_rec(selected_node: str, selected_rank: int) -> dict:
            r = _rec(node_a, rank=1)
            r["candidates_shown"] = [
                {"rank": 1, "node_key": node_a, "score": 0.85, "confidence": "High"},
                {"rank": 2, "node_key": node_b, "score": 0.72, "confidence": "Medium"},
            ]
            r["user_selected_rank"] = selected_rank
            return r

        records = [_multi_rec(node_a, 1) for _ in range(6)] + \
                  [_multi_rec(node_b, 2) for _ in range(5)]
        agg = FeedbackAggregator(records)
        index = agg.build()
        assert index[key_a]["pos"] == 6
        assert index[key_b]["pos"] == 5

    def test_only_b_group_records_counted(self):
        pos_b = [_rec(NODE, rank=1, bg="IDG") for _ in range(5)]
        neg_a = [dict(_rec(NODE, rank=None, is_negative=True), ab_group="A") for _ in range(10)]
        agg = FeedbackAggregator(pos_b + neg_a)
        index = agg.build()
        assert index[KEY]["pos"] == 5
        assert index[KEY]["neg"] == 0
        assert index[KEY]["signal"] == DELTA_CAP

    def test_save_and_load_json(self, tmp_path):
        records = [_rec(NODE, rank=1) for _ in range(5)]
        agg = FeedbackAggregator(records)
        index = agg.build()
        out = tmp_path / "feedback_index.json"
        agg.save(out, index)
        loaded = json.loads(out.read_text())
        assert KEY in loaded
        assert loaded[KEY]["signal"] == DELTA_CAP
