# Helen's Structured Field Cascade — Design Doc

> **Source**: Helen & Ziff Sync-up transcripts (June 25, 2026)  
> **Status**: Implemented in `src/field_rules.py`. The functions described below as
> `apply_field_rules()` / `inject_field_candidates()` (flat mode) have been superseded by
> `apply_field_rules_tree()` / `inject_field_candidates_tree()` (tree mode), which is what the
> live `POST /recommend_der` endpoint (`app.py`) and `scripts/run_der_refinement_agent.py`
> (default tree mode) actually call today. The flat-mode functions this doc originally
> described no longer exist in `src/field_rules.py`.  
> **Motivation**: The DER form contains several structured Yes/No and categorical fields
> that give high-certainty signals about product type — sometimes 100% certain — that the
> pure free-text recall pipeline was not exploiting.

---

## 1. Background

The DER Refinement Agent (formerly V1.0) of the matching pipeline uses only the "Describe the business problem" field (col 5)
for recall. Helen identified that several other DER fields provide deterministic or near-
deterministic product signals:

> "百分之百确定它就是在这个产品目录下面会有"  
> (100% certain it will be under this product category)

The cascade exploits these signals **before** the LLM rerank to inject high-confidence
candidates that the semantic search might otherwise miss.

---

## 2. DER Fields Used

| Column | Field Name | Values | Signal |
|---|---|---|---|
| 4 | Business Group | IDG / DCG | Hard partition (handled by runner, not this module) |
| 10 | Involve The Use of Emerging Technology | Yes / No | AI products likely |
| 12 | Is there an opportunity for Lenovo Asset Recovery | Yes / No | ARS **certain** |
| 16 | Is this Opportunity an expansion of an existing (TruScale/managed) | Yes / No | DaaS/managed services likely |
| 22 | Service Model | DAAS / PROF & MGD SERVICES / IAAS / ISG Lease / SI/Vertical / SAAS | Primary product category |
| 23 | The Scope of This Opportunity | See values below | Confirms/refines service model |

**Scope (col 23) distinct values** (2026 data):
- `Standalone Professional Services` — professional services only
- `Managed Services or TruScale "as a Service"` — managed / DaaS products
- `Standalone Asset Recovery Services Scope` — ARS **certain**
- `Hardware Lease with Standard Services` — DaaS hardware products

---

## 3. Decision Cascade

```
DER Row
    │
    ▼
Step 1: BG filter (hard)
    IDG → search IDG OH pool
    DCG → search DCG OH pool
    (done by runner before this module is called)
    │
    ▼
Step 2: ARS check (100% certain)
    IF col_12 = Yes  OR  scope = "Standalone Asset Recovery Services Scope"
    → GUARANTEE: Asset Recovery Services OH products for this BG
    │
    ▼
Step 3: Service Model (strong signal)
    IF col_22 = "DAAS"
    → GUARANTEE: DaaS / Device as a Service OH products for this BG
    IF col_22 = "PROF & MGD SERVICES"
    → BOOST: Managed Service / Professional Services OH products
    IF col_22 = "IAAS"
    → BOOST: TruScale / IaaS OH products
    IF col_22 = "ISG Lease"
    → BOOST: TruScale / IaaS OH products
    IF col_22 = "SI/Vertical"
    → BOOST: AI / Vertical OH products
    │
    ▼
Step 4: Existing contract expansion (moderate signal)
    IF col_16 = Yes
    → BOOST: Managed Service / DaaS / TruScale OH products
    │
    ▼
Step 5: Emerging Technology / AI flag (moderate signal)
    IF col_10 = Yes
    → BOOST: AI-related OH products for this BG
    │
    ▼
Step 6: Scope column (confirmation)
    "Managed Services or TruScale" → BOOST: Managed/DaaS products
    "Hardware Lease with Standard Services" → BOOST: DaaS HW products
    "Standalone Professional Services" → BOOST: Professional services
    │
    ▼
Step 7: Free-text recall (col 5) — always runs
    BM25 + dense embedding recall on business problem description
    │
    ▼
Merge: Guaranteed → Boosted → Recall remainder
    (trimmed to RERANK_TOPN=30 candidates for LLM)
    │
    ▼
LLM Rerank + Confidence scoring
```

---

## 4. Guarantee vs. Boost

| Certainty | Mechanism | Product in top-3? |
|---|---|---|
| **Guaranteed** | Injected at head of candidate list | Yes — LLM always scores it; if ≥ threshold it appears |
| **Boosted** | Moved ahead of pure-recall candidates | Likely — LLM sees it before recall-only items |
| **Recalled** | Normal BM25 + dense position | Depends on recall rank and LLM score |

"Guaranteed" does not mean the product always appears in the final top-3 output —
it means the LLM is always shown the product to score. If the LLM gives it a low score
(< LOW_THRESHOLD = 0.40), it is still dropped. This preserves accuracy: the guarantee
is about visibility, not forced inclusion.

**Per-parent injection cap**: `inject_field_candidates` limits guaranteed and boosted
injections to at most `max_per_parent=2` products sharing the same `parent_product`.
This prevents a single category (e.g. three ARS variants all under "Circular Economy")
from occupying all 3 recommendation slots. The third slot is left for a diverse recall
candidate that the LLM can score competitively.

---

## 5. OH Product Keyword Mapping

The module matches OH product names using the following keyword lists (runtime, not hardcoded IDs):

| Signal | Keywords matched in OH product name |
|---|---|
| ARS | "asset recovery" |
| DaaS | "daas", "device as a service" |
| AI | "ai ", "agentic ai", "ai discover", "ai adoption", "ai managed", "ai professional", "ai data" |
| TruScale / IaaS | "truscale", "true scale", "iaas", "infrastructure as a service" |
| Managed services | "managed service", "managed endpoint", "managed workplace" |
| Professional services | "professional service", "consulting", "advisory" |

Keyword matching is case-insensitive. Keywords are scoped to the BG-partitioned OH pool
so IDG rules only match IDG products and DCG rules only match DCG products.

---

## 6. Coverage in 2026 DER Data (first 498 rows sampled)

| Field | Yes count | No count | Coverage |
|---|---|---|---|
| Col 10 — Emerging Technology | 33 | 465 | 6.6% |
| Col 12 — ARS | 55 | 443 | 11.0% |
| Col 16 — Existing expansion | 21 | 477 | 4.2% |
| Col 22 — Service Model (any value) | 498 | 0 | ~100% |
| Col 23 — Scope (any value) | 498 | 0 | ~100% |

Service Model and Scope are present on virtually all rows, making them the most broadly
applicable signals. ARS and Emerging Technology affect roughly 1 in 10 and 1 in 15 rows.

---

## 7. Known Limitations and Next Steps

1. **Hardware PNs not covered**: The OH product pool is services-oriented. Hardware PNs (LPC
   product line) are not yet in the matching corpus, so hardware-heavy deals (IDG with pure
   "DaaS HW" signals) may match services when hardware products should be primary. Requires
   LPC product data from IT team.

2. **SAAS service model**: Only 1 occurrence in sampled data; no clear OH product mapping.
   Currently produces no guaranteed/boosted candidates — falls back to pure text recall.

3. **Scope truncation**: The Scope field value in D365 appears to be truncated in some records.
   Helen noted the field "截断了" (was cut off) in the sync-up. Keyword matching is robust to
   partial strings.

4. **Col 23 → Product type**: Helen's cascade described col 23 as the "final confirmation"
   that directly determines whether DAS or ISS is the right product. This mapping is partially
   implemented (scope → keyword boost) but could be made more precise with explicit enum mapping.

5. **Feedback loop**: Recommended products should be tracked against what the seller actually
   selected in D365 to validate and improve the keyword mappings over time.

---

## 8. Files

| File | Role |
|---|---|
| `src/field_rules.py` | Implementation — `apply_field_rules()`, `inject_field_candidates()` |
| `scripts/run_der_refinement_agent.py` | Integration point — called in `process_one()` after recall |
| `src/load_data.py` | Loads structured fields into `DERRow` dataclass |
| `docs/field-logic.md` | This document |
