"""Tests for src/pre_der_shared.py — shared helpers for tree-mode agents."""
from __future__ import annotations

import pytest

from src.load_pn_tree import PNNode
from src.pre_der_shared import format_candidates_block_v2, node_to_candidate
from src.rerank import Candidate


def _cand(
    name: str = "TestNode",
    level: str | None = "L3",
    path: str | None = "Root > Branch > TestNode",
    sample_pns: str | None = "PN1; PN2",
) -> Candidate:
    return Candidate(
        product_id="0",
        product_name=name,
        parent_product=path,
        solution_category=level,
        solution_sub_category=sample_pns,
        iso=None,
    )


def _node(
    name: str = "AI Managed Service",
    level: int = 3,
    path: list[str] | None = None,
    pn_count: int = 5,
    descs: list[str] | None = None,
) -> PNNode:
    return PNNode(
        name=name,
        level=level,
        path=path or ["Global", "AI Services", "AI Managed Service"],
        pn_count=pn_count,
        sampled_pn_descs=descs if descs is not None else ["desc1", "desc2", "desc3"],
    )


class TestFormatCandidatesBlockV2:
    def test_single_candidate_all_fields(self):
        cands = [_cand()]
        out = format_candidates_block_v2(cands)
        assert "1." in out
        assert "level=L3" in out
        assert "name=TestNode" in out
        assert "path=Root > Branch > TestNode" in out
        assert "sample_pns=PN1; PN2" in out

    def test_numbering_increments(self):
        cands = [_cand("A"), _cand("B"), _cand("C")]
        lines = format_candidates_block_v2(cands).splitlines()
        assert lines[0].startswith("1.")
        assert lines[1].startswith("2.")
        assert lines[2].startswith("3.")

    def test_missing_level_omits_level_field(self):
        cands = [_cand(level=None)]
        out = format_candidates_block_v2(cands)
        assert "level=" not in out
        assert "name=TestNode" in out

    def test_missing_path_omits_path_field(self):
        cands = [_cand(path=None)]
        out = format_candidates_block_v2(cands)
        assert "path=" not in out

    def test_missing_sample_pns_omits_sample_pns_field(self):
        cands = [_cand(sample_pns=None)]
        out = format_candidates_block_v2(cands)
        assert "sample_pns=" not in out

    def test_empty_input_returns_empty_string(self):
        assert format_candidates_block_v2([]) == ""

    def test_multiple_candidates_one_line_each(self):
        cands = [_cand("A"), _cand("B")]
        lines = format_candidates_block_v2(cands).splitlines()
        assert len(lines) == 2

    def test_fields_joined_with_pipe(self):
        cands = [_cand()]
        out = format_candidates_block_v2(cands)
        assert " | " in out


class TestNodeToCandidate:
    def test_basic_conversion(self):
        node = _node()
        cand = node_to_candidate(node, idx=0)
        assert cand.product_id == "0"
        assert cand.product_name == "AI Managed Service"
        assert cand.solution_category == "L3"
        assert cand.iso is None

    def test_level_formatted_as_lN(self):
        node = _node(level=2)
        cand = node_to_candidate(node, idx=1)
        assert cand.solution_category == "L2"

    def test_path_joined_with_arrow(self):
        node = _node(path=["Root", "Branch", "Leaf"])
        cand = node_to_candidate(node, idx=0)
        assert cand.parent_product == "Root > Branch > Leaf"

    def test_sample_pns_capped_at_six(self):
        descs = ["d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8"]
        node = _node(descs=descs)
        cand = node_to_candidate(node, idx=0)
        parts = cand.solution_sub_category.split("; ")
        assert len(parts) == 6

    def test_empty_descs_gives_none_sub_category(self):
        node = _node(descs=[])
        cand = node_to_candidate(node, idx=0)
        assert cand.solution_sub_category is None

    def test_idx_becomes_string_product_id(self):
        node = _node()
        cand = node_to_candidate(node, idx=42)
        assert cand.product_id == "42"
