"""
Helen's structured field cascade for DER → PN tree node matching.

The DER form contains several structured Yes/No and categorical fields that give
high-certainty signals about what products a deal involves — sometimes with 100%
certainty (e.g. ARS flag = Yes → Asset Recovery Services MUST be recommended).

This module reads those fields and returns:
  - guaranteed_ids : set[str] — str(idx) into nodes list for nodes that must appear
                                regardless of recall ranking (100%-certain nodes)
  - boosted_ids    : set[str] — str(idx) into nodes list to move to the front
                                (strongly implied by structured fields)

Integration point: call `apply_field_rules_tree()` after recall, before the LLM rerank.
The runner injects guaranteed nodes at the head of the candidate list so the LLM
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

import logging
from dataclasses import dataclass, field

from src.load_data import DERRow

_logger = logging.getLogger(__name__)

# ── Keyword patterns for PN tree node name matching ─────────────────────────

_ARS_KW = ["asset recovery"]
_DAAS_KW = ["daas", "device as a service"]
_AI_KW = ["ai ", " ai", "agentic ai", "ai discover", "ai adoption", "ai managed", "ai professional", "ai data"]
_TRUSCALE_KW = ["truscale", "true scale"]
_IAAS_KW = ["iaas", "infrastructure as a service"]
_MANAGED_KW = ["managed service", "managed endpoint", "managed workplace"]
_PROF_SVC_KW = ["professional service", "consulting", "advisory"]
_SAAS_KW = ["saas", "software as a service"]


def _matches_any(name: str, keywords: list[str]) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in keywords)




# ── Service-model → keyword mapping ─────────────────────────────────────────

_SERVICE_MODEL_KW: dict[str, list[str]] = {
    "DAAS":              _DAAS_KW + _TRUSCALE_KW,
    "IAAS":              _IAAS_KW + _TRUSCALE_KW,
    "PROF & MGD SERVICES": _MANAGED_KW + _PROF_SVC_KW,
    "ISG LEASE":         _TRUSCALE_KW + _IAAS_KW,
    "SAAS":              _SAAS_KW,
    "SI OR VERTICAL":    _AI_KW + ["vertical"],
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


def _scope_matches(scope: str | None, key: str) -> bool:
    if not scope:
        return False
    return key in scope.upper()


# ── Tree-mode variants (PN tree nodes instead of OH products) ─────────────────

def _find_nodes(nodes: list, keywords: list[str]) -> list[str]:
    """Return str(idx) for PN tree nodes whose name matches any keyword."""
    return [str(i) for i, n in enumerate(nodes) if _matches_any(n.name, keywords)]


def apply_field_rules_tree(row: DERRow, nodes: list) -> FieldRuleResult:
    """Same field cascade as apply_field_rules but matched against PN tree node names.

    No BG hard filter — BG is a soft signal for tree mode.
    guaranteed_ids / boosted_ids contain str(index) into the nodes list.
    """
    result = FieldRuleResult()

    ars_certain = (row.is_ars is True) or _scope_matches(row.scope, "STANDALONE ASSET RECOVERY SERVICES SCOPE")
    if ars_certain:
        result.guaranteed_ids.update(_find_nodes(nodes, _ARS_KW))

    if row.service_model:
        sm = row.service_model.strip().upper()
        if sm == "DAAS":
            result.guaranteed_ids.update(_find_nodes(nodes, _DAAS_KW))
        else:
            kw = _SERVICE_MODEL_KW.get(sm)
            if kw:
                result.boosted_ids.update(_find_nodes(nodes, kw))
            else:
                _logger.warning("Unknown service_model %r — no keyword mapping; boost skipped", sm)

    if row.is_existing_expansion:
        result.boosted_ids.update(_find_nodes(nodes, _MANAGED_KW + _DAAS_KW + _TRUSCALE_KW))

    if row.is_emerging_tech:
        result.boosted_ids.update(_find_nodes(nodes, _AI_KW))

    for scope_key, kw in _SCOPE_KW.items():
        if _scope_matches(row.scope, scope_key) and not ars_certain:
            result.boosted_ids.update(_find_nodes(nodes, kw))

    result.boosted_ids -= result.guaranteed_ids
    return result


def inject_field_candidates_tree(
    recall_indices: list[int],
    nodes: list,
    rules: FieldRuleResult,
    max_candidates: int = 30,
    max_per_parent: int = 2,
) -> list[int]:
    """Like inject_field_candidates but for PN tree nodes.

    Parent cap uses the second-to-last path element (immediate parent node name).
    guaranteed_ids / boosted_ids in rules are str(index) into nodes.
    """
    parent_counts: dict[str, int] = {}

    def _pick_with_cap(str_indices: set[str]) -> list[int]:
        picked = []
        for s in str_indices:
            try:
                idx = int(s)
            except ValueError:
                continue
            if idx < 0 or idx >= len(nodes):
                continue
            path = nodes[idx].path
            parent = path[-2] if len(path) >= 2 else (path[0] if path else "(none)")
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

