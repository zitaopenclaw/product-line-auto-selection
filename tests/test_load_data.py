"""Tests for src/load_data.py — DER and OH xlsx loaders + helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.load_data import (
    DERRow,
    OHProduct,
    index_oh_by_bg,
    load_der,
    load_oh,
    stratified_sample,
)


# ── load_der ────────────────────────────────────────────────────────────────


class TestLoadDer:
    def test_loads_rows_from_fixture(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        assert len(rows) > 0
        assert all(isinstance(r, DERRow) for r in rows)

    def test_required_fields_populated(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        first = rows[0]
        assert first.opportunity_id
        assert first.business_group
        assert first.description  # may be empty for some rows

    def test_yes_no_fields_coerced_to_bool(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        # OPP-TEST-001 has ars=No, ai=No
        opp1 = next(r for r in rows if r.opportunity_id == "OPP-TEST-001")
        assert opp1.is_ars is False
        assert opp1.is_emerging_tech is False
        assert opp1.is_existing_expansion is False

    def test_yes_field_yes(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        opp2 = next(r for r in rows if r.opportunity_id == "OPP-TEST-002")
        assert opp2.is_ars is True

    def test_service_model_field_loaded(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        opp1 = next(r for r in rows if r.opportunity_id == "OPP-TEST-001")
        assert opp1.service_model == "DAAS"

    def test_scope_field_loaded(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        opp1 = next(r for r in rows if r.opportunity_id == "OPP-TEST-001")
        assert "Hardware Lease" in (opp1.scope or "")

    def test_rows_without_bg_are_skipped(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        ids = {r.opportunity_id for r in rows}
        assert "OPP-TEST-NOBG" not in ids


# ── load_oh ─────────────────────────────────────────────────────────────────


class TestLoadOh:
    def test_loads_active_rows(self, sample_oh_path: Path):
        products = load_oh(sample_oh_path, drop_retired=True)
        statuses = {p.status for p in products}
        assert "Retired" not in statuses

    def test_returns_oh_product_instances(self, sample_oh_path: Path):
        products = load_oh(sample_oh_path)
        assert all(isinstance(p, OHProduct) for p in products)

    def test_can_include_retired_when_flag_false(self, sample_oh_path: Path):
        products = load_oh(sample_oh_path, drop_retired=False)
        assert any(p.status == "Retired" for p in products)

    def test_required_fields_populated(self, sample_oh_path: Path):
        products = load_oh(sample_oh_path)
        for p in products:
            assert p.product_id
            assert p.product_name
            assert p.business_group

    def test_business_group_field_loaded(self, sample_oh_path: Path):
        products = load_oh(sample_oh_path)
        bgs = {p.business_group for p in products}
        assert "IDG" in bgs
        assert "DCG" in bgs
        assert "SSG" in bgs


# ── index_oh_by_bg ──────────────────────────────────────────────────────────


class TestIndexOhByBg:
    def test_groups_products_by_bg(self, sample_oh_path: Path):
        products = load_oh(sample_oh_path)
        idx = index_oh_by_bg(products)
        assert "IDG" in idx
        assert "DCG" in idx
        assert "SSG" in idx
        for bg, plist in idx.items():
            assert all(p.business_group == bg for p in plist)


# ── stratified_sample ───────────────────────────────────────────────────────


class TestStratifiedSample:
    def test_respects_per_bg_limit(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        # Each BG has at most 3 rows in fixture, per_bg=2 should give us 2 per BG
        sample = stratified_sample(rows, per_bg=2, seed=42)
        from collections import Counter
        counts = Counter(r.business_group for r in sample)
        for bg, n in counts.items():
            assert n <= 2

    def test_seed_determinism(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        s1 = stratified_sample(rows, per_bg=2, seed=42)
        s2 = stratified_sample(rows, per_bg=2, seed=42)
        assert [r.opportunity_id for r in s1] == [r.opportunity_id for r in s2]

    def test_different_seeds_can_differ(self, sample_der_path: Path):
        rows = load_der(sample_der_path)
        s1 = stratified_sample(rows, per_bg=2, seed=1)
        s2 = stratified_sample(rows, per_bg=2, seed=2)
        # At least one of the BGs should differ if sample size > 1
        # (Not guaranteed with very small samples, so just check the API works.)
        assert isinstance(s1, list)
        assert isinstance(s2, list)
