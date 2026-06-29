"""Shared helpers for Pre-DER Agent and DER Input AI Agent (tree mode).

Both agents search against PN tree nodes. These functions convert nodes to
Candidate objects and format them for the rerank prompt.
"""
from __future__ import annotations

from typing import Iterable

from src.load_pn_tree import PNNode
from src.rerank import Candidate


def format_candidates_block_v2(cands: Iterable[Candidate]) -> str:
    lines = []
    for i, c in enumerate(cands, 1):
        parts = []
        if c.solution_category:
            parts.append(f"level={c.solution_category}")
        parts.append(f"name={c.product_name}")
        if c.parent_product:
            parts.append(f"path={c.parent_product}")
        if c.solution_sub_category:
            parts.append(f"sample_pns={c.solution_sub_category}")
        lines.append(f"{i}. " + " | ".join(parts))
    return "\n".join(lines)


def node_to_candidate(node: PNNode, idx: int) -> Candidate:
    sample_pns = "; ".join(node.sampled_pn_descs[:6])
    return Candidate(
        product_id=str(idx),
        product_name=node.name,
        parent_product=" > ".join(node.path),
        solution_category=f"L{node.level}",
        solution_sub_category=sample_pns or None,
        iso=None,
    )
