"""Tests for src/field_rules.py — Helen's 6-field structured cascade.

Field priority (from Helen & Ziff sync-up, 2026-06-25):
  1. BG (hard filter, handled in runner)
  2. Service Model
  3. Existing expansion
  4. Emerging Tech / AI
  5. ARS
  6. Scope
"""
from __future__ import annotations

from src.field_rules import apply_field_rules, inject_field_candidates
from src.load_data import DERRow, OHProduct


def _oh(
    product_id: str,
    name: str,
    bg: str = "IDG",
    parent: str | None = None,
) -> OHProduct:
    """Shorthand OH product factory for tests."""
    return OHProduct(
        product_guid=f"guid-{product_id}",
        product_name=name,
        product_id=product_id,
        status="Active",
        business_group=bg,
        parent_product=parent,
        solution_category=None,
        solution_sub_category=None,
        iso=None,
    )


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


# ── apply_field_rules ───────────────────────────────────────────────────────


class TestApplyFieldRules:
    """Tests for the 6-field cascade in field_rules.py."""

    def test_ars_yes_makes_ars_products_guaranteed(self):
        products = [
            _oh("p1", "Lenovo Asset Recovery Services"),
            _oh("p2", "Some Other Service"),
        ]
        row = _der(is_ars=True)
        result = apply_field_rules(row, products)
        assert "p1" in result.guaranteed_ids
        assert result.boosted_ids == set() or "p1" not in result.boosted_ids

    def test_standalone_ars_scope_also_guarantees_ars(self):
        products = [_oh("p1", "Lenovo Asset Recovery Services")]
        row = _der(scope="Standalone Asset Recovery Services Scope")
        result = apply_field_rules(row, products)
        assert "p1" in result.guaranteed_ids

    def test_daas_service_model_guarantees_daas(self):
        products = [
            _oh("p1", "ThinkPad DaaS Subscription"),
            _oh("p2", "Other Product"),
        ]
        row = _der(service_model="DAAS")
        result = apply_field_rules(row, products)
        assert "p1" in result.guaranteed_ids

    def test_ai_flag_boosts_ai_products(self):
        products = [
            _oh("p1", "AI Professional Services"),
            _oh("p2", "Other Product"),
        ]
        row = _der(is_emerging_tech=True)
        result = apply_field_rules(row, products)
        assert "p1" in result.boosted_ids
        assert "p1" not in result.guaranteed_ids

    def test_existing_expansion_boosts_managed(self):
        products = [
            _oh("p1", "Managed Endpoint Service"),
            _oh("p2", "Other Product"),
        ]
        row = _der(is_existing_expansion=True)
        result = apply_field_rules(row, products)
        assert "p1" in result.boosted_ids

    def test_business_group_filter_applied_to_lookups(self):
        # Same product name in two BGs; only matching BG is returned
        products = [
            _oh("p_idg", "Lenovo Asset Recovery", bg="IDG"),
            _oh("p_dcg", "Lenovo Asset Recovery", bg="DCG"),
        ]
        row = _der(bg="IDG", is_ars=True)
        result = apply_field_rules(row, products)
        assert "p_idg" in result.guaranteed_ids
        assert "p_dcg" not in result.guaranteed_ids

    def test_no_fields_set_returns_empty(self):
        products = [_oh("p1", "Any Product")]
        row = _der()
        result = apply_field_rules(row, products)
        assert result.guaranteed_ids == set()
        assert result.boosted_ids == set()

    def test_guaranteed_supersedes_boosted(self):
        # ARS product should not appear in both guaranteed and boosted.
        products = [_oh("p1", "Lenovo Asset Recovery")]
        row = _der(is_ars=True, is_emerging_tech=True)
        result = apply_field_rules(row, products)
        assert "p1" in result.guaranteed_ids
        assert "p1" not in result.boosted_ids


# ── inject_field_candidates ─────────────────────────────────────────────────


class TestInjectFieldCandidates:
    """Tests for the candidate-merging step that places field-rule products
    ahead of the recall pool."""

    def _products(self) -> list[OHProduct]:
        return [
            _oh("guaranteed1", "Lenovo Asset Recovery", parent="Circular Economy"),
            _oh("guaranteed2", "ARS Premium", parent="Circular Economy"),  # same parent
            _oh("guaranteed3", "ARS Standard", parent="Other"),  # different parent
            _oh("boosted1", "AI Professional Services", parent="AI Services"),
            _oh("recall1", "ThinkPad X1", parent="PCs"),
            _oh("recall2", "ThinkSystem Server", parent="Servers"),
        ]

    def test_guaranteed_come_first(self):
        products = self._products()
        rules = type("R", (), {"guaranteed_ids": {"guaranteed1"}, "boosted_ids": set()})()
        result = inject_field_candidates([4, 5], products, rules, max_candidates=10)
        assert products[result[0]].product_id == "guaranteed1"

    def test_boosted_come_after_guaranteed(self):
        products = self._products()
        rules = type("R", (), {"guaranteed_ids": {"guaranteed1"}, "boosted_ids": {"boosted1"}})()
        result = inject_field_candidates([4, 5], products, rules, max_candidates=10)
        ids = [products[i].product_id for i in result]
        assert ids.index("guaranteed1") < ids.index("boosted1")

    def test_max_per_parent_caps_field_injections(self):
        products = self._products()
        # Two guaranteed products share the same parent "Circular Economy".
        rules = type("R", (), {
            "guaranteed_ids": {"guaranteed1", "guaranteed2", "guaranteed3"},
            "boosted_ids": set(),
        })()
        result = inject_field_candidates([], products, rules, max_candidates=10, max_per_parent=2)
        # Only 2 of the 3 Circular Economy children fit; "guaranteed3" has parent="Other" so OK.
        ids = [products[i].product_id for i in result]
        # We expect guaranteed1 and guaranteed2 (same parent) to be capped.
        # guaranteed3 has a different parent so should be included.
        circular_count = sum(1 for i in result if products[i].parent_product == "Circular Economy")
        assert circular_count <= 2

    def test_recall_indices_preserved(self):
        products = self._products()
        rules = type("R", (), {"guaranteed_ids": set(), "boosted_ids": set()})()
        result = inject_field_candidates([4, 5], products, rules, max_candidates=10)
        # Recall indices map to products at positions 4 and 5.
        assert set(result) == {4, 5}

    def test_respects_max_candidates(self):
        products = self._products()
        rules = type("R", (), {"guaranteed_ids": set(), "boosted_ids": set()})()
        result = inject_field_candidates([4, 5], products, rules, max_candidates=2)
        assert len(result) == 2
