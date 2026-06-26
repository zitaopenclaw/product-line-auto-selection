"""Tests for src/parse_voice_input.py — markdown parser and LLM extract.

LLM calls are mocked via `requests.post`.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.parse_voice_input import (
    VoiceInput,
    _llm_extract,
    parse_voice_inputs_md,
)


# ── parse_voice_inputs_md ──────────────────────────────────────────────────


class TestParseVoiceInputsMd:
    def test_parses_single_entry(self, tmp_path: Path):
        md = tmp_path / "input.md"
        md.write_text(
            "1. First opportunity\n"
            "\n"
            "BG: IDG\n"
            "\n"
            "Sales voice input\n"
            "Customer wants 100 laptops.\n"
            "⸻⸻⸻\n",
            encoding="utf-8",
        )
        result = parse_voice_inputs_md(md)
        assert len(result) == 1
        assert result[0].id == 1
        assert result[0].title == "First opportunity"
        assert result[0].bg == "IDG"
        assert "100 laptops" in result[0].raw_text

    def test_parses_multiple_entries_with_delimiter(self, sample_voice_input_path: Path):
        result = parse_voice_inputs_md(sample_voice_input_path)
        assert len(result) == 3
        assert [r.id for r in result] == [1, 2, 3]
        assert [r.bg for r in result] == ["IDG", "IDG", "SSG"]

    def test_bg_field_is_case_insensitive(self, tmp_path: Path):
        md = tmp_path / "input.md"
        md.write_text("1. Test\n\nbg: dcg\n\nSales voice input\nText.\n", encoding="utf-8")
        result = parse_voice_inputs_md(md)
        assert result[0].bg == "dcg"

    def test_empty_text_under_header_excluded(self, tmp_path: Path):
        md = tmp_path / "input.md"
        md.write_text(
            "1. Empty\n\nBG: IDG\n\nSales voice input\n\n⸻⸻⸻\n"
            "2. With text\n\nBG: IDG\n\nSales voice input\n\nSome text.\n",
            encoding="utf-8",
        )
        result = parse_voice_inputs_md(md)
        # First entry has no body text, should be excluded
        assert [r.id for r in result] == [2]

    def test_returns_voice_input_instances(self, sample_voice_input_path: Path):
        result = parse_voice_inputs_md(sample_voice_input_path)
        assert all(isinstance(r, VoiceInput) for r in result)


# ── _llm_extract (mocked) ──────────────────────────────────────────────────


def _mock_llm_response(text: str) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "choices": [{"message": {"content": text}}]
    }
    return mock


class TestLlmExtract:
    def test_returns_extracted_text(self):
        with patch("src.parse_voice_input.requests.post") as mock_post:
            mock_post.return_value = _mock_llm_response("Customer needs laptops.")
            result = _llm_extract(
                raw_text="Customer wants 100 ThinkPads",
                api_key="key",
                base_url="https://example.com/v1",
                model="m",
            )
            assert result == "Customer needs laptops."

    def test_retries_on_failure(self):
        with patch("src.parse_voice_input.requests.post") as mock_post, \
             patch("src.parse_voice_input.time.sleep"):
            fail = MagicMock()
            fail.raise_for_status.side_effect = Exception("boom")
            ok = _mock_llm_response("extracted")
            mock_post.side_effect = [fail, fail, ok]
            result = _llm_extract(
                raw_text="text",
                api_key="key",
                base_url="https://example.com/v1",
                model="m",
                retries=3,
            )
            assert result == "extracted"
            assert mock_post.call_count == 3

    def test_raises_after_all_retries_exhausted(self):
        with patch("src.parse_voice_input.requests.post") as mock_post, \
             patch("src.parse_voice_input.time.sleep"):
            mock_post.side_effect = Exception("boom")
            with pytest.raises(RuntimeError, match="LLM extraction failed"):
                _llm_extract(
                    raw_text="text",
                    api_key="key",
                    base_url="https://example.com/v1",
                    model="m",
                    retries=2,
                )
