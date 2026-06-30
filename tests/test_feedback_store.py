from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.feedback_store import FeedbackStore, JsonlFeedbackStore, FeedbackRecord


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _sample_record(**overrides) -> dict:
    base = {
        "feedback_id": "test-uuid-001",
        "timestamp": "2026-07-01T10:00:00Z",
        "opportunity_id": "OPP-0001234567",
        "bg": "IDG",
        "der_description": "Deploy laptops for enterprise users",
        "scope": "Standalone Professional Services",
        "service_model": "DAAS",
        "ars_flag": False,
        "ai_flag": False,
        "candidates_shown": [
            {"rank": 1, "node_key": "L4|GPS|Config|Integration|FIS", "score": 0.85, "confidence": "High"},
            {"rank": 2, "node_key": "L4|GPS|Field|OnSite|OnSite", "score": 0.72, "confidence": "Medium"},
            {"rank": 3, "node_key": "L4|GPS|Field|Remote|Remote", "score": 0.61, "confidence": "Medium"},
        ],
        "user_selected_rank": 1,
        "is_negative": False,
        "negative_hint": None,
        "ab_group": "B",
    }
    base.update(overrides)
    return base


# ── FeedbackRecord validation ──────────────────────────────────────────────────

class TestFeedbackRecord:
    def test_positive_feedback_valid(self):
        rec = FeedbackRecord(**_sample_record())
        assert rec.is_negative is False
        assert rec.user_selected_rank == 1
        assert rec.ab_group == "B"

    def test_negative_feedback_with_hint(self):
        rec = FeedbackRecord(**_sample_record(
            user_selected_rank=None,
            is_negative=True,
            negative_hint="Should be hardware lease service",
        ))
        assert rec.is_negative is True
        assert rec.user_selected_rank is None
        assert rec.negative_hint == "Should be hardware lease service"

    def test_negative_feedback_skip_hint(self):
        rec = FeedbackRecord(**_sample_record(
            user_selected_rank=None,
            is_negative=True,
            negative_hint=None,
        ))
        assert rec.negative_hint is None

    def test_ab_group_a(self):
        rec = FeedbackRecord(**_sample_record(ab_group="A"))
        assert rec.ab_group == "A"

    def test_candidates_shown_preserved(self):
        rec = FeedbackRecord(**_sample_record())
        assert len(rec.candidates_shown) == 3
        assert rec.candidates_shown[0]["rank"] == 1


# ── JsonlFeedbackStore ─────────────────────────────────────────────────────────

class TestJsonlFeedbackStore:
    def test_write_creates_file(self, tmp_path):
        store = JsonlFeedbackStore(tmp_path / "feedback.jsonl")
        rec = FeedbackRecord(**_sample_record())
        store.write(rec)
        assert (tmp_path / "feedback.jsonl").exists()

    def test_write_appends_valid_json_line(self, tmp_path):
        store = JsonlFeedbackStore(tmp_path / "feedback.jsonl")
        rec = FeedbackRecord(**_sample_record())
        store.write(rec)
        lines = (tmp_path / "feedback.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["opportunity_id"] == "OPP-0001234567"
        assert data["bg"] == "IDG"
        assert data["ab_group"] == "B"

    def test_write_multiple_records_appends(self, tmp_path):
        store = JsonlFeedbackStore(tmp_path / "feedback.jsonl")
        store.write(FeedbackRecord(**_sample_record(feedback_id="id-1")))
        store.write(FeedbackRecord(**_sample_record(feedback_id="id-2")))
        lines = (tmp_path / "feedback.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2

    def test_write_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "feedback.jsonl"
        store = JsonlFeedbackStore(nested)
        store.write(FeedbackRecord(**_sample_record()))
        assert nested.exists()

    def test_read_all_returns_all_records(self, tmp_path):
        store = JsonlFeedbackStore(tmp_path / "feedback.jsonl")
        store.write(FeedbackRecord(**_sample_record(feedback_id="id-1")))
        store.write(FeedbackRecord(**_sample_record(feedback_id="id-2")))
        records = store.read_all()
        assert len(records) == 2
        assert records[0]["feedback_id"] == "id-1"
        assert records[1]["feedback_id"] == "id-2"

    def test_read_all_empty_file_returns_empty_list(self, tmp_path):
        store = JsonlFeedbackStore(tmp_path / "feedback.jsonl")
        assert store.read_all() == []

    def test_read_all_nonexistent_file_returns_empty_list(self, tmp_path):
        store = JsonlFeedbackStore(tmp_path / "nonexistent.jsonl")
        assert store.read_all() == []

    def test_implements_feedback_store_interface(self, tmp_path):
        store = JsonlFeedbackStore(tmp_path / "feedback.jsonl")
        assert isinstance(store, FeedbackStore)
