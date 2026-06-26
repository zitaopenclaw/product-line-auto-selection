"""Tests for src/load_pn_tree.py — PN hierarchy tree JSON loader."""
from __future__ import annotations

from pathlib import Path

from src.load_pn_tree import PNNode, load_pn_nodes, pn_node_embed_text


class TestLoadPnNodes:
    def test_loads_expected_count_from_fixture(self, sample_pn_tree_path: Path):
        # Fixture has: 3 L2 + 4 L3 = 7 named nodes at depth >= 2
        nodes = load_pn_nodes(sample_pn_tree_path, random_seed=42)
        assert len(nodes) == 7

    def test_returns_pn_node_instances(self, sample_pn_tree_path: Path):
        nodes = load_pn_nodes(sample_pn_tree_path)
        assert all(isinstance(n, PNNode) for n in nodes)

    def test_only_named_nodes_at_depth_2_or_3(self, sample_pn_tree_path: Path):
        nodes = load_pn_nodes(sample_pn_tree_path)
        for n in nodes:
            assert n.level in (2, 3)
            assert n.name  # all have non-empty names

    def test_path_includes_ancestor_chain(self, sample_pn_tree_path: Path):
        nodes = load_pn_nodes(sample_pn_tree_path)
        # A node at depth 3 has a path of length 3 (L1 + L2 + L3)
        depth3 = [n for n in nodes if n.level == 3]
        for n in depth3:
            assert len(n.path) == 3
            assert n.path[0]  # L1 name
            assert n.path[1]  # L2 name
            assert n.path[2] == n.name  # last segment is this node's own name

    def test_sampled_pn_descs_populated(self, sample_pn_tree_path: Path):
        nodes = load_pn_nodes(sample_pn_tree_path)
        with_pns = [n for n in nodes if n.sampled_pn_descs]
        assert len(with_pns) > 0
        for n in with_pns:
            assert all(isinstance(d, str) for d in n.sampled_pn_descs)

    def test_node_key_format(self):
        node = PNNode(name="X", level=3, path=["L1", "L2", "X"], pn_count=0)
        assert node.node_key == "L3|L1|L2|X"

    def test_seed_determinism(self, sample_pn_tree_path: Path):
        n1 = load_pn_nodes(sample_pn_tree_path, random_seed=42)
        n2 = load_pn_nodes(sample_pn_tree_path, random_seed=42)
        for a, b in zip(n1, n2):
            assert a.sampled_pn_descs == b.sampled_pn_descs

    def test_empty_name_nodes_excluded(self, tmp_path: Path):
        # Build a tree with an empty-named L2 node — should be skipped
        import json
        tree = {
            "tree": [
                {
                    "name": "Root",
                    "level": 1,
                    "children": [
                        {"name": "", "level": 2, "children": []},  # empty name
                        {"name": "Valid", "level": 2, "children": []},
                    ],
                }
            ]
        }
        path = tmp_path / "empty.json"
        path.write_text(json.dumps(tree), encoding="utf-8")
        nodes = load_pn_nodes(path)
        names = {n.name for n in nodes}
        assert "" not in names
        assert "Valid" in names


class TestPnNodeEmbedText:
    def test_includes_name_and_path(self):
        node = PNNode(
            name="Hardware Deployment",
            level=3,
            path=["Services", "Deployment", "Hardware Deployment"],
            pn_count=5,
            sampled_pn_descs=[],
        )
        result = pn_node_embed_text(node)
        assert "Hardware Deployment" in result
        assert "path: Services > Deployment > Hardware Deployment" in result

    def test_includes_sampled_pns(self):
        node = PNNode(
            name="X",
            level=3,
            path=["A", "B", "X"],
            pn_count=10,
            sampled_pn_descs=["desc one", "desc two"],
        )
        result = pn_node_embed_text(node)
        assert "pns:" in result
        assert "desc one" in result
        assert "desc two" in result

    def test_no_pns_section_when_empty(self):
        node = PNNode(name="X", level=3, path=["A", "B", "X"], pn_count=0, sampled_pn_descs=[])
        result = pn_node_embed_text(node)
        assert "pns:" not in result
