"""Tests for src/rerank.py — LLM client, prompt rendering, JSON extraction.

All tests mock `requests.post` so no real API calls are made.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.rerank import (
    Candidate,
    _extract_json,
    format_candidates_block,
    render_prompt,
)
from src.rerank import RerankClient


# ── format_candidates_block ────────────────────────────────────────────────


class TestFormatCandidatesBlock:
    def test_includes_product_name(self):
        cands = [Candidate(product_id="p1", product_name="My Product")]
        result = format_candidates_block(cands)
        assert "My Product" in result
        assert "1." in result

    def test_omits_empty_metadata(self):
        cands = [Candidate(product_id="p1", product_name="X", parent_product=None)]
        result = format_candidates_block(cands)
        assert "parent=" not in result
        assert "category=" not in result

    def test_includes_all_metadata_fields(self):
        cands = [Candidate(
            product_id="p1",
            product_name="X",
            parent_product="Parent",
            solution_category="Cat",
            solution_sub_category="SubCat",
            iso="ISO-1",
        )]
        result = format_candidates_block(cands)
        assert "parent=Parent" in result
        assert "category=Cat" in result
        assert "subcat=SubCat" in result
        assert "ISO=ISO-1" in result

    def test_numbered_sequentially(self):
        cands = [
            Candidate(product_id="p1", product_name="A"),
            Candidate(product_id="p2", product_name="B"),
            Candidate(product_id="p3", product_name="C"),
        ]
        result = format_candidates_block(cands)
        for n in (1, 2, 3):
            assert f"{n}." in result


# ── _extract_json ──────────────────────────────────────────────────────────


class TestExtractJson:
    def test_plain_json(self):
        text = '{"candidates": [{"candidate_no": 1, "score": 0.9}]}'
        result = _extract_json(text)
        assert result["candidates"][0]["score"] == 0.9

    def test_code_fenced_json(self):
        text = '```json\n{"candidates": []}\n```'
        result = _extract_json(text)
        assert result == {"candidates": []}

    def test_code_fenced_without_language(self):
        text = '```\n{"a": 1}\n```'
        result = _extract_json(text)
        assert result == {"a": 1}

    def test_embedded_json_in_text(self):
        text = 'Here is the result: {"x": 42} and some trailing text'
        result = _extract_json(text)
        assert result == {"x": 42}

    def test_malformed_raises(self):
        with pytest.raises(Exception):
            _extract_json("not json at all")


# ── render_prompt ──────────────────────────────────────────────────────────


class TestRenderPrompt:
    def test_substitutes_placeholders(self, tmp_path):
        template_path = tmp_path / "tmpl.txt"
        template_path.write_text(
            "BG={business_group}\nDESC={description}\nN={n_candidates}\n---\n{candidates_block}",
            encoding="utf-8",
        )
        cands = [Candidate(product_id="p1", product_name="X")]
        result = render_prompt("my desc", "IDG", cands, prompt_path=template_path)
        assert "BG=IDG" in result
        assert "DESC=my desc" in result
        assert "N=1" in result

    def test_truncates_long_description(self, tmp_path):
        template_path = tmp_path / "tmpl.txt"
        template_path.write_text("D={description}", encoding="utf-8")
        long = "a" * 5000
        result = render_prompt(long, "IDG", [], prompt_path=template_path)
        # Description is truncated to 2000 chars
        assert "{description}" not in result
        assert "a" * 2000 in result


# ── RerankClient.rerank (mocked API) ───────────────────────────────────────


def _mock_response(candidates: list[dict]) -> MagicMock:
    """Build a mock requests.Response with a given JSON body."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"candidates": candidates})}}]
    }
    return mock


class TestRerankClientRerank:
    def _cands(self) -> list[Candidate]:
        return [
            Candidate(product_id="p1", product_name="A"),
            Candidate(product_id="p2", product_name="B"),
            Candidate(product_id="p3", product_name="C"),
        ]

    def test_returns_scored_candidates_from_primary(self):
        with patch("src.rerank.requests.post") as mock_post:
            mock_post.return_value = _mock_response([
                {"candidate_no": 1, "score": 0.9},
                {"candidate_no": 3, "score": 0.7},
            ])
            client = RerankClient()
            result = client.rerank("desc", "IDG", self._cands())
            assert len(result) == 2
            assert result[0]["product_id"] == "p1"
            assert result[0]["score"] == 0.9

    def test_clamps_score_to_zero_one(self):
        with patch("src.rerank.requests.post") as mock_post:
            mock_post.return_value = _mock_response([
                {"candidate_no": 1, "score": 1.5},   # above 1
                {"candidate_no": 2, "score": -0.3},  # below 0
            ])
            client = RerankClient()
            result = client.rerank("desc", "IDG", self._cands())
            assert result[0]["score"] == 1.0
            assert result[1]["score"] == 0.0

    def test_drops_invalid_candidate_nos(self):
        with patch("src.rerank.requests.post") as mock_post:
            mock_post.return_value = _mock_response([
                {"candidate_no": 99, "score": 0.9},  # out of range
                {"candidate_no": 1, "score": 0.7},
            ])
            client = RerankClient()
            result = client.rerank("desc", "IDG", self._cands())
            assert len(result) == 1
            assert result[0]["product_id"] == "p1"

    def test_drops_duplicate_candidate_nos(self):
        with patch("src.rerank.requests.post") as mock_post:
            mock_post.return_value = _mock_response([
                {"candidate_no": 1, "score": 0.9},
                {"candidate_no": 1, "score": 0.8},  # duplicate
            ])
            client = RerankClient()
            result = client.rerank("desc", "IDG", self._cands())
            assert len(result) == 1

    def test_falls_back_when_primary_fails(self):
        with patch("src.rerank.requests.post") as mock_post, \
             patch("src.rerank.time.sleep"):  # speed up retries
            # Primary retries 3 times (all fail), then fallback succeeds.
            primary_response = MagicMock()
            primary_response.raise_for_status.side_effect = Exception("primary down")
            fallback_response = _mock_response([{"candidate_no": 1, "score": 0.85}])
            mock_post.side_effect = [primary_response] * 3 + [fallback_response]

            client = RerankClient()
            stats_before = client.get_stats()
            result = client.rerank("desc", "IDG", self._cands())
            stats_after = client.get_stats()
            assert len(result) == 1
            assert result[0]["score"] == 0.85
            assert stats_after["fallback_ok"] == stats_before["fallback_ok"] + 1
            assert stats_after["deepseek_fail"] == stats_before["deepseek_fail"] + 1

    def test_empty_candidates_returns_empty(self):
        client = RerankClient()
        result = client.rerank("desc", "IDG", [])
        assert result == []

    def test_provider_stats_tracking(self):
        with patch("src.rerank.requests.post") as mock_post:
            mock_post.return_value = _mock_response([{"candidate_no": 1, "score": 0.5}])
            client = RerankClient()
            client.rerank("desc", "IDG", self._cands())
            client.rerank("desc", "IDG", self._cands())
            stats = client.get_stats()
            assert stats["deepseek_ok"] == 2
            assert stats["deepseek_fail"] == 0
