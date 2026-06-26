"""
LEGACY — Helen's 6-field structured cascade for OH-product matching.

Replaced by tree-based `src/field_rules.py` on 2026-06-27 (data source switch).
Kept for rollback / reference only. Not imported by the current pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_ARS_KW = ["asset recovery"]
_DAAS_KW = ["daas", "device as a service"]
_AI_KW = ["ai ", "agentic ai", "ai discover", "ai adoption", "ai managed", "ai professional", "ai data"]
_TRUSCALE_KW = ["truscale", "true scale"]
_IAAS_KW = ["iaas", "infrastructure as a service"]
_MANAGED_KW = ["managed service", "managed endpoint", "managed workplace"]
_PROF_SVC_KW = ["professional service", "consulting", "advisory"]

_SERVICE_MODEL_KW: dict[str, list[str]] = {
    "DAAS":              _DAAS_KW + _TRUSCALE_KW,
    "IAAS":              _IAAS_KW + _TRUSCALE_KW,
    "PROF & MGD SERVICES": _MANAGED_KW + _PROF_SVC_KW,
    "ISG LEASE":         _TRUSCALE_KW + _IAAS_KW,
    "SI/VERTICAL":       _AI_KW + ["vertical"],
}

_SCOPE_KW: dict[str, list[str]] = {
    "STANDALONE ASSET RECOVERY SERVICES SCOPE": _ARS_KW,
    "MANAGED SERVICES OR TRUSCALE":             _MANAGED_KW + _TRUSCALE_KW + _DAAS_KW,
    "HARDWARE LEASE WITH STANDARD SERVICES":    _DAAS_KW,
    "STANDALONE PROFESSIONAL SERVICES":         _PROF_SVC_KW,
}


@dataclass
class FieldRuleResult:
    guaranteed_ids: set[str] = field(default_factory=set)
    boosted_ids: set[str] = field(default_factory=set)


def _matches_any(name: str, keywords: list[str]) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in keywords)


def _find_products(
    products: list,
    keywords: list[str],
    bg: str | None = None,
) -> list[str]:
    return [
        p.product_id
        for p in products
        if (bg is None or p.business_group == bg) and _matches_any(p.product_name, keywords)
    ]


def apply_field_rules(row, oh_pool) -> FieldRuleResult:
    result = FieldRuleResult()
    bg = row.business_group

    ars_certain = (row.is_ars is True) or _scope_matches(row.scope, "STANDALONE ASSET RECOVERY SERVICES SCOPE")
    if ars_certain:
        result.guaranteed_ids.update(_find_products(oh_pool, _ARS_KW, bg))

    if row.service_model:
        sm = row.service_model.strip().upper()
        if sm == "DAAS":
            result.guaranteed_ids.update(_find_products(oh_pool, _DAAS_KW, bg))
        else:
            kw = _SERVICE_MODEL_KW.get(sm)
            if kw:
                result.boosted_ids.update(_find_products(oh_pool, kw, bg))

    if row.is_existing_expansion:
        result.boosted_ids.update(_find_products(oh_pool, _MANAGED_KW + _DAAS_KW + _TRUSCALE_KW, bg))

    if row.is_emerging_tech:
        result.boosted_ids.update(_find_products(oh_pool, _AI_KW, bg))

    for scope_key, kw in _SCOPE_KW.items():
        if _scope_matches(row.scope, scope_key) and not ars_certain:
            result.boosted_ids.update(_find_products(oh_pool, kw, bg))

    result.boosted_ids -= result.guaranteed_ids
    return result


def _scope_matches(scope: str | None, key: str) -> bool:
    if not scope:
        return False
    return key in scope.upper()


def inject_field_candidates(
    recall_indices: list[int],
    products: list,
    rules: FieldRuleResult,
    max_candidates: int = 30,
    max_per_parent: int = 2,
) -> list[int]:
    pid_to_idx = {p.product_id: i for i, p in enumerate(products)}
    parent_counts: dict[str, int] = {}

    def _pick_with_cap(pids: set[str]) -> list[int]:
        picked = []
        for pid in pids:
            if pid not in pid_to_idx:
                continue
            idx = pid_to_idx[pid]
            parent = (products[idx].parent_product or "").strip() or "(none)"
            if parent_counts.get(parent, 0) < max_per_parent:
                picked.append(idx)
                parent_counts[parent] = parent_counts.get(parent, 0) + 1
        return picked

    guaranteed = _pick_with_cap(rules.guaranteed_ids)
    boosted = _pick_with_cap(rules.boosted_ids)

    seen: set[int] = set()
    merged: list[int] = []
    for idx in guaranteed + boosted + recall_indices:
        if idx not in seen:
            seen.add(idx)
            merged.append(idx)
        if len(merged) >= max_candidates:
            break
    return merged
