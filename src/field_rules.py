"""
Helen's structured field cascade for DER → OH product matching.

The DER form contains several structured Yes/No and categorical fields that give
high-certainty signals about what products a deal involves — sometimes with 100%
certainty (e.g. ARS flag = Yes → Asset Recovery Services MUST be recommended).

This module reads those fields and returns:
  - guaranteed_ids : set[str] — OH product_ids that must appear in the top candidates
                                regardless of recall ranking (100%-certain products)
  - boosted_ids    : set[str] — OH product_ids to move to the front of the recall pool
                                (strongly implied by structured fields)

Integration point: call `apply_field_rules()` after recall, before the LLM rerank.
The runner injects guaranteed products at the head of the candidate list so the LLM
always scores them.

Field priority (from Helen & Ziff sync-up, 2026-06-25):
  1. BG (col 4)        — hard partition (handled in runner, not here)
  2. Service Model (col 22) — main product category hint
  3. Existing expansion (col 16) — if Yes, narrows to DaaS / managed services
  4. Emerging Tech / AI (col 10) — if Yes, inject AI products
  5. ARS (col 12)      — if Yes, ARS products are 100% guaranteed
  6. Scope (col 23)    — final confirmation of product type

See docs/field-logic.md for the full design and rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.load_data import DERRow, OHProduct

# ── Keyword patterns for OH product name matching ────────────────────────────

_ARS_KW = ["asset recovery"]
_DAAS_KW = ["daas", "device as a service"]
_AI_KW = ["ai ", "agentic ai", "ai discover", "ai adoption", "ai managed", "ai professional", "ai data"]
_TRUSCALE_KW = ["truscale", "true scale"]
_IAAS_KW = ["iaas", "infrastructure as a service"]
_MANAGED_KW = ["managed service", "managed endpoint", "managed workplace"]
_PROF_SVC_KW = ["professional service", "consulting", "advisory"]


def _matches_any(name: str, keywords: list[str]) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in keywords)


def _find_products(
    products: list[OHProduct],
    keywords: list[str],
    bg: str | None = None,
) -> list[str]:
    """Return product_ids whose name matches any keyword (optionally filtered by BG)."""
    return [
        p.product_id
        for p in products
        if (bg is None or p.business_group == bg) and _matches_any(p.product_name, keywords)
    ]


# ── Service-model → keyword mapping ─────────────────────────────────────────

_SERVICE_MODEL_KW: dict[str, list[str]] = {
    "DAAS":              _DAAS_KW + _TRUSCALE_KW,
    "IAAS":              _IAAS_KW + _TRUSCALE_KW,
    "PROF & MGD SERVICES": _MANAGED_KW + _PROF_SVC_KW,
    "ISG LEASE":         _TRUSCALE_KW + _IAAS_KW,
    "SI/VERTICAL":       _AI_KW + ["vertical"],
}

# Scope column values → keyword lists
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


def apply_field_rules(
    row: DERRow,
    oh_pool: list[OHProduct],
) -> FieldRuleResult:
    """
    Return guaranteed and boosted OH product_ids for *row* given *oh_pool*
    (already filtered to row.business_group by the caller).

    Guaranteed: ARS=Yes OR Scope=ARS_standalone → ARS products certain
                ServiceModel=DAAS → DaaS products certain
    Boosted:    AI flag=Yes → AI products move up
                ServiceModel/Scope hint → matching products move up
                Existing expansion=Yes → DaaS/managed services move up
    """
    result = FieldRuleResult()
    bg = row.business_group

    # ── 1. ARS: 100% certain when either flag triggers ────────────────────────
    ars_certain = (row.is_ars is True) or _scope_matches(row.scope, "STANDALONE ASSET RECOVERY SERVICES SCOPE")
    if ars_certain:
        result.guaranteed_ids.update(_find_products(oh_pool, _ARS_KW, bg))

    # ── 2. Service Model: DaaS is certain; others are boosted ────────────────
    if row.service_model:
        sm = row.service_model.strip().upper()
        if sm == "DAAS":
            result.guaranteed_ids.update(_find_products(oh_pool, _DAAS_KW, bg))
        else:
            kw = _SERVICE_MODEL_KW.get(sm)
            if kw:
                result.boosted_ids.update(_find_products(oh_pool, kw, bg))

    # ── 3. Existing contract expansion → boost managed/DaaS ──────────────────
    if row.is_existing_expansion:
        result.boosted_ids.update(_find_products(oh_pool, _MANAGED_KW + _DAAS_KW + _TRUSCALE_KW, bg))

    # ── 4. Emerging Tech / AI flag → boost AI products ───────────────────────
    if row.is_emerging_tech:
        result.boosted_ids.update(_find_products(oh_pool, _AI_KW, bg))

    # ── 5. Scope column (additional confirmation) → boost ────────────────────
    for scope_key, kw in _SCOPE_KW.items():
        if _scope_matches(row.scope, scope_key) and not ars_certain:
            result.boosted_ids.update(_find_products(oh_pool, kw, bg))

    # Guaranteed always supersedes boosted (avoid double-listing)
    result.boosted_ids -= result.guaranteed_ids
    return result


def _scope_matches(scope: str | None, key: str) -> bool:
    if not scope:
        return False
    return key in scope.upper()


def inject_field_candidates(
    recall_indices: list[int],
    products: list[OHProduct],
    rules: FieldRuleResult,
    max_candidates: int = 30,
    max_per_parent: int = 2,
) -> list[int]:
    """
    Merge recall indices with field-rule results.

    Order:
      1. Guaranteed product indices (from field rules)
      2. Boosted product indices (from field rules, not already in guaranteed)
      3. Remaining recall indices (not already included above)

    Result is trimmed to max_candidates.

    max_per_parent caps how many guaranteed/boosted products sharing the same
    parent_product are placed at the head of the list. This leaves room for
    a diverse recall candidate when a single product category dominates the
    field-rule signals (e.g. three ARS variants all under "Circular Economy").
    Recall candidates are not subject to this cap.
    """
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
