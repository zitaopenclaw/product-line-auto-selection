# DER Refinement Agent — Design Doc (formerly V1.0)

> **Term definitions**: all domain terms (DER, DQR, OH, etc.) are defined in [CONTEXT.md](../CONTEXT.md). This document uses DER as the dataset/field identifier, which is interchangeable with DQR in business context.
>
> **Rename history**: previously referred to as "V1.0" / "v1.0". The agent was renamed on 2026-06-27 to **DER Refinement Agent** to align with the deal-desk workflow language. See [CONTEXT.md §"Agent Naming"](../CONTEXT.md#agent-naming-historical-anchor) for the decode key.

## 1. Goal

Given a finalized DER form (from `Approved DER in 2026`) with structured fields and a free-text "Describe the business problem or challenge" field, the **DER Refinement Agent** recommends **top-3 Lenovo OH products** with a confidence score. In the current POC, the output is the offering-hierarchy list that populates the qualified DER package.

The matching must respect the **Business Group filter**: a `DER` row with `Business Group = IDG` may only match OH products whose `Business Group = IDG` (and similarly for `DCG`). This is a hard gate, not a soft prior.

## 2. Input / Output

### Inputs
- `Approved DER in 2026.xlsx` — 2,353 rows. Columns used: `Opportunity ID`, `Business Group`, `Describe the business problem or challenge`.
- `OH product in D365.xlsx` — 2,223 rows. After filtering `Status = Retired` (174 rows), 2,049 active products remain. Columns used: `Product` (GUID), `Product Name`, `Product ID`, `Status`, `Business Group`, plus auxiliary context (`Parent Product`, `Solution Category`, `Solution Sub-Category`, `ISO`) for the rerank prompt.

### Output
A markdown table, one row per DER opportunity, with the top-3 candidate products laid out horizontally.

```
| Opportunity ID | BG | #1 Product ID | #1 Product Name | #1 Parent | #1 Score | #1 Level | #2 Product ID | #2 Product Name | #2 Parent | #2 Score | #2 Level | #3 Product ID | #3 Product Name | #3 Parent | #3 Score | #3 Level |
```

Missing slots (when fewer than 3 candidates pass the threshold) are filled with `—`.

## 3. Data Observations

From the exploration:

| Metric | DER | OH (Active) |
|---|---|---|
| Rows | 2,353 | 2,049 |
| Business Group | IDG 1,357 / DCG 996 | IDG 612 / DCG 1,611 |
| Text length | min 1 / max 2,000 / avg 182.6 chars | name avg 43.8 chars |
| Empty description | 0 | n/a |

Notable: `BU` column in OH mostly maps to Business Group (`ISG ↔ DCG`, `IDG/SSG ↔ IDG`), but the user explicitly requested matching on `Business Group` (col 16), so we ignore `BU`.

## 4. Pipeline

```
DER row ─┐
         ▼
   ┌─────────────────────────────────────┐
   │ 1. Load + Filter                    │
   │    - Drop Retired from OH           │
   │    - Partition OH by BG (IDG / DCG) │
   └─────────────────────────────────────┘
         │
         ▼
   ┌─────────────────────────────────────┐
   │ 2. Recall (top-60 per DER)          │
   │    a) BM25 over OH Product Name     │
   │    b) Dense Embedding (bge-small)   │
   │       cosine over (name + parent +  │
   │       category + ISO) embedding     │
   │    Union → candidate pool (≤60)     │
   └─────────────────────────────────────┘
         │
         ▼
   ┌─────────────────────────────────────┐
   │ 3. Field Cascade (Helen's 6 fields) │
   │    - Guaranteed injects (ARS, DaaS) │
   │    - Boosted injects (AI, scope…)  │
   │    - Per-parent cap = 2             │
   │    - Trim merged pool to top-30     │
   └─────────────────────────────────────┘
         │
         ▼
   ┌─────────────────────────────────────┐
   │ 4. LLM Rerank (top-30 → top-3)      │
   │    Prompt: DER desc + 30 candidates │
   │    Output: per-cand score           │
   └─────────────────────────────────────┘
         │
         ▼
   ┌─────────────────────────────────────┐
   │ 5. Score → Level + top-3 + markdown │
   │    High   ≥ 0.85                     │
   │    Medium 0.60–0.85                  │
   │    Low    0.40–0.60  (raised from    │
   │           0.30 by ADR-0002)          │
   │    drop   < 0.40                     │
   └─────────────────────────────────────┘
```

### Stage 1 — Load & Filter
- Read both workbooks via `openpyxl`.
- OH: drop `Status == "Retired"`. Build two indexes keyed by `Business Group` (`{"IDG": [...], "DCG": [...]}`).
- DER: take every row. Group by BG for sampling later.

### Stage 2 — Recall
Two retrieval channels, then union by `Product ID`.

**(a) BM25** over OH `Product Name` field. Built with `rank_bm25.BM25Okapi`. Tokenized lowercase, alphanumeric only. For each DER description, take top-60 by BM25 score.

**(b) Dense embedding** using `BAAI/bge-small-en-v1.5` (sentence-transformers). 
- Embedding input for OH: `"<Product Name> | parent: <Parent> | category: <Solution Category> / <Solution Sub-Category> | ISO: <ISO>"`. Empty fields are dropped.
- Embedding input for DER: the raw description, truncated to 2000 chars.
- Cosine similarity, top-60.

The two top-60 lists are unioned and de-duplicated. Result: up to 60 candidates per DER, typically 30–45. The full recall pool then enters the field cascade (Stage 3), which trims it to 30 for the LLM.

### Stage 3 — Field Cascade
Documented in detail in [docs/field-logic.md](field-logic.md). Briefly: Helen's 6 DER fields (Service Model, ARS flag, AI flag, existing-expansion flag, Scope, BG) are evaluated and used to **inject** guaranteed / boosted OH products at the head of the candidate list before the LLM rerank. This closes the largest precision gap that pure-text recall leaves open. The merged pool is then trimmed to 30 candidates for Stage 4.

### Stage 4 — LLM Rerank
The DeepSeek API (primary) is called once per DER with a batched prompt listing the top-30 candidates from the cascade. If the primary call fails, MiniMax is used as fallback. The LLM returns a JSON object with one entry per candidate: `{product_id: "...", score: 0.0–1.0}`.

The prompt template lives in `prompts/rerank.txt` and is rendered with `str.format`.

### Stage 5 — Score → Level & Output
- Sort candidates by score descending.
- Apply thresholds:

| Score | Level |
|---|---|
| ≥ 0.85 | **High** |
| 0.60 ≤ s < 0.85 | **Medium** |
| 0.40 ≤ s < 0.60 | **Low** — _threshold raised from 0.30 by ADR-0002_ |
| < 0.40 | drop |

- Select up to top-3 that survive the threshold. In the 1000-row run, parent diversity is applied (`keep_topk_diverse`) to reduce repeated parent products.
- Write the markdown table.

## 5. POC Plan

- **Sample size**: 50 DER rows, stratified: 25 IDG + 25 DCG.
- **Goal**: validate the end-to-end pipeline and tune the prompt / thresholds.
- **Deliverables**:
  - `output/der_refinement_agent/matches_poc.md` — 50 rows with top-3 matches
  - `output/der_refinement_agent/poc_summary.md` — score distribution, Level distribution, average candidates per row
- **Gate to full run**: human spot-checks POC output. If precision on top-1 ≥ ~70%, proceed to full 2,353.

## 6. File Layout

```
product-line-auto-selection/
├── docs/
│   ├── design.md            # this file (DER Refinement Agent)
│   ├── design_v2.md         # Pre-DER Agent design
│   └── field-logic.md       # Stage 3 (field cascade) design
├── src/
│   ├── load_data.py         # load + filter, returns DER & OH
│   ├── load_pn_tree.py      # Pre-DER Agent only: load PN tree
│   ├── parse_voice_input.py # Pre-DER Agent only: voice input parsing + extraction
│   ├── recall.py            # BM25 + embedding recall (shared)
│   ├── rerank.py            # LLM rerank client (shared)
│   ├── confidence.py        # score → Level + diversity (shared)
│   └── field_rules.py       # Stage 3: apply_field_rules(), inject_field_candidates()
├── prompts/
│   ├── rerank.txt           # DER Refinement Agent prompt
│   └── rerank_v2.txt        # Pre-DER Agent prompt (BG soft signal, tree path)
├── output/
│   ├── der_refinement_agent/  # DER Refinement Agent run outputs
│   └── pre_der_agent/         # Pre-DER Agent run outputs
├── .env                     # DEEPSEEK_* (required), MINIMAX_* (optional fallback)
├── requirements.txt
└── scripts/
    ├── run_der_refinement_agent.py
    └── run_pre_der_agent.py
```

## 7. Open Questions / Risks

1. **Embedding model availability**: `bge-small-en-v1.5` is ~130 MB and runs on CPU fine, but `sentence-transformers` + `torch` pull in ~1 GB of deps. Acceptable for POC.
2. **LLM endpoint resilience**: DeepSeek is primary and MiniMax is fallback. Keep both base URL/model/auth settings aligned in `.env`.
3. **Prompt cost / latency**: 50 rows × 1 call each ≈ trivial. Full run = 2,353 calls; if that's too slow, we can batch multiple DERs per call (multiple JSON blocks) — design allows it but POC keeps it simple.
4. **Score calibration**: thresholds (0.85 / 0.60 / 0.30) are heuristics. POC will surface actual score distribution; adjust if needed.
5. **Cross-BG matches**: the BG filter is strict. If a DER's `Business Group` is miscoded in CRM, we'll miss the right product. Out of scope for POC.

## 8. Success Criteria (POC)

- Pipeline runs end-to-end on 50 rows without error.
- ≥ 80% of rows have at least one candidate at Level ≥ Medium.
- Top-1 Level = High on at least 30% of rows (sanity check, not a hard bar).
- Score distribution shows reasonable spread (not all 0.5s or all 0.99s).
