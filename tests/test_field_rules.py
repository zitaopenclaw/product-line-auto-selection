"""Tests for src/field_rules.py — Helen's 6-field structured cascade (PN tree mode)."""
from __future__ import annotations

from src.field_rules import apply_field_rules_tree, inject_field_candidates_tree
from src.load_data import DERRow


def _node(name: str, path: list[str] | None = None):
    """Minimal PNNode-like object for testing."""
    class FakeNode:
        def __init__(self, n, p):
            self.name = n
            self.path = p or ["L1Root", n]
            self.level = len(self.path) - 1
    return FakeNode(name, path)


def _der(
    *,
    bg: str = "IDG",
    service_model: str | None = None,
    is_existing_expansion: bool | None = None,
    is_emerging_tech: bool | None = None,
    is_ars: bool | None = None,
    scope: str | None = None,
) -> DERRow:
    return DERRow(
        opportunity_id="OPP-TEST",
        business_group=bg,
        description="test",
        service_model=service_model,
        is_existing_expansion=is_existing_expansion,
        is_emerging_tech=is_emerging_tech,
        is_ars=is_ars,
        scope=scope,
    )


# ── apply_field_rules_tree ──────────────────────────────────────────────────


class TestApplyFieldRulesTree:

    def test_ars_yes_guarantees_ars_nodes(self):
        nodes = [_node("Lenovo Asset Recovery Services"), _node("Other Service")]
        result = apply_field_rules_tree(_der(is_ars=True), nodes)
        assert "0" in result.guaranteed_ids
        assert "1" not in result.guaranteed_ids

    def test_standalone_ars_scope_also_guarantees(self):
        nodes = [_node("Lenovo Asset Recovery Services")]
        result = apply_field_rules_tree(_der(scope="Standalone Asset Recovery Services Scope"), nodes)
        assert "0" in result.guaranteed_ids

    def test_daas_service_model_guarantees_daas_nodes(self):
        nodes = [_node("ThinkPad DaaS Subscription"), _node("Other Product")]
        result = apply_field_rules_tree(_der(service_model="DAAS"), nodes)
        assert "0" in result.guaranteed_ids

    def test_ai_flag_boosts_ai_nodes(self):
        nodes = [_node("AI Professional Services"), _node("Other Product")]
        result = apply_field_rules_tree(_der(is_emerging_tech=True), nodes)
        assert "0" in result.boosted_ids
        assert "0" not in result.guaranteed_ids

    def test_existing_expansion_boosts_managed_nodes(self):
        nodes = [_node("Managed Endpoint Service"), _node("Other Product")]
        result = apply_field_rules_tree(_der(is_existing_expansion=True), nodes)
        assert "0" in result.boosted_ids

    def test_no_fields_returns_empty(self):
        nodes = [_node("Any Node")]
        result = apply_field_rules_tree(_der(), nodes)
        assert result.guaranteed_ids == set()
        assert result.boosted_ids == set()

    def test_guaranteed_supersedes_boosted(self):
        nodes = [_node("Lenovo Asset Recovery")]
        result = apply_field_rules_tree(_der(is_ars=True, is_emerging_tech=True), nodes)
        assert "0" in result.guaranteed_ids
        assert "0" not in result.boosted_ids

    def test_no_bg_filter_applied(self):
        # Tree mode has no BG hard filter — same node matches regardless of BG in row
        nodes = [_node("Lenovo Asset Recovery")]
        result_idg = apply_field_rules_tree(_der(bg="IDG", is_ars=True), nodes)
        result_dcg = apply_field_rules_tree(_der(bg="DCG", is_ars=True), nodes)
        assert result_idg.guaranteed_ids == result_dcg.guaranteed_ids


# ── inject_field_candidates_tree ─────────────────────────────────────────────


class TestInjectFieldCandidatesTree:

    def _nodes(self):
        return [
            _node("Asset Recovery", path=["Root", "Circular Economy", "Asset Recovery"]),
            _node("ARS Premium", path=["Root", "Circular Economy", "ARS Premium"]),
            _node("ARS Standard", path=["Root", "Other", "ARS Standard"]),
            _node("AI Services", path=["Root", "AI", "AI Services"]),
            _node("ThinkPad", path=["Root", "Devices", "ThinkPad"]),
            _node("ThinkSystem", path=["Root", "Servers", "ThinkSystem"]),
        ]

    def test_guaranteed_come_first(self):
        nodes = self._nodes()
        rules = type("R", (), {"guaranteed_ids": {"0"}, "boosted_ids": set()})()
        result = inject_field_candidates_tree([4, 5], nodes, rules, max_candidates=10)
        assert result[0] == 0

    def test_boosted_come_after_guaranteed(self):
        nodes = self._nodes()
        rules = type("R", (), {"guaranteed_ids": {"0"}, "boosted_ids": {"3"}})()
        result = inject_field_candidates_tree([4, 5], nodes, rules, max_candidates=10)
        assert result.index(0) < result.index(3)

    def test_max_per_parent_caps_same_parent_guaranteed(self):
        nodes = self._nodes()
        # nodes 0 and 1 both have parent "Circular Economy", node 2 has "Other"
        rules = type("R", (), {"guaranteed_ids": {"0", "1", "2"}, "boosted_ids": set()})()
        result = inject_field_candidates_tree([], nodes, rules, max_candidates=10, max_per_parent=1)
        circular = sum(1 for i in result if nodes[i].path[-2] == "Circular Economy")
        assert circular <= 1
        other = sum(1 for i in result if nodes[i].path[-2] == "Other")
        assert other == 1

    def test_recall_indices_preserved_when_no_rules(self):
        nodes = self._nodes()
        rules = type("R", (), {"guaranteed_ids": set(), "boosted_ids": set()})()
        result = inject_field_candidates_tree([4, 5], nodes, rules, max_candidates=10)
        assert set(result) == {4, 5}

    def test_respects_max_candidates(self):
        nodes = self._nodes()
        rules = type("R", (), {"guaranteed_ids": set(), "boosted_ids": set()})()
        result = inject_field_candidates_tree([0, 1, 2, 3, 4, 5], nodes, rules, max_candidates=3)
        assert len(result) == 3

    def test_invalid_str_indices_skipped(self):
        nodes = self._nodes()
        rules = type("R", (), {"guaranteed_ids": {"999", "bad"}, "boosted_ids": set()})()
        result = inject_field_candidates_tree([0], nodes, rules, max_candidates=10)
        assert result == [0]
