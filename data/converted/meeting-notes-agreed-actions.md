# Meeting Notes — Agreed Decisions (Product-Line Auto-Selection)

> Extracted from `data/raw/Meeting Notes and transcripts.md`.
> Filter: only items agreed in meeting AND relevant to **product-line-auto-selection** (DER → OH matching pipeline).
> Excluded: Deal Desk AI Agent items (Rachel's separate project on qualification / pricing / risk scoring).

---

## Agreed Decisions & Items

| # | Decision / Item | Owner | Source Meeting | Status |
|---|---|---|---|---|
| 1 | Test 1 already executed — 20 samples run in pre-DQR stage (sales enters deal info before DQR is filled); used as accuracy baseline. | Ziff / Helen | VTT Helen & Ziff Sync-up (1) | Done |
| 2 | Test 2 will rerun with broader-coverage samples (since original 20 could not cover full SG product range); purpose is to verify whether richer DER-stage descriptions yield more precise candidate sets. | Ziff / Helen | VTT Helen & Ziff Sync-up (1) | Agreed |
| 3 | Core research question framed: can we obtain a more accurate candidate dataset from the sales-provided DER description? | Ziff / Helen | VTT Helen & Ziff Sync-up (1) | Open |
| 4 | Terminology aligned — DER ≈ DQR (interchangeable in this context); pre-DER / pre-DQR both refer to the same pre-submission stage (opportunity creation + master data). | Helen | VTT Helen & Ziff Sync-up | Agreed |
| 5 | Pipeline stage semantics agreed: Step 4 = pre-matching (semantic matching only); Step 5 / DER stage = information is richer → theoretically higher matching precision. | Helen | VTT Helen & Ziff Sync-up | Agreed |
| 6 | Step 3 → Step 5 field mapping must be finalized — scope: BOM, part number, product line, unit price, terms, sales source. | Unassigned (suggest Hiten + Ziff) | VTT Helen & Ziff Sync-up | Open |
| 7 | `sales source` is a critical input column — must not be dropped; ASR mis-transcribed it as "sales sore" but the canonical column name is `sales source`. | Model owner (TBD) | VTT Helen & Ziff Sync-up | Agreed |
| 8 | Hierarchical modeling decision: part number + description must hang at the leaf level (e.g. level 6); sales early stage typically only provides higher-level info (level 2/3). | Model owner (TBD) | VTT Helen & Ziff Sync-up | Agreed |
| 9 | A reviewable field writeback rule must be established between D365 and the analytics data table, so semantic matching never silently drops key columns. | Unassigned (suggest Hiten + D365 team) | VTT Helen & Ziff Sync-up | Open |
| 10 | Cost model table (Step 3 — solution development) purpose confirmed: used for IC pricing + seller-to-IC handoff; SA must populate BOM info at this stage; hardware part number must be written back to D365 product-line-related fields. | Rachel / SA lead | VTT Helen & Ziff Sync-up | Agreed |
| 11 | Price data semantics to be unified — unit price, terms, and whether the column carries a quantity / percentage must have one canonical interpretation across the pipeline. | Unassigned (suggest Finance + Ziff) | VTT Helen & Ziff Sync-up | Open |

---

## Status Legend

- **Done** — already executed; recorded as baseline.
- **Agreed** — conclusion reached in meeting; no further decision needed.
- **Open** — direction agreed, but execution / ownership still to be assigned or worked.

---

## Excluded Scope (Different Project)

The main meeting (Tuesday June 23, 2026, Deal Desk AI Grooming) covered Rachel's **Deal Desk AI Agent** MVP (qualification scoring, pricing, risk factors, win/loss analytics). These items are intentionally **not** included here because they belong to a separate project. Likewise, the 7 "Follow-up Tasks" checkboxes and the 4 VTT "C) 可执行补充动作" are scoped to that other project, except for #2, #6, and #9 which overlap with this project and are captured above.

---

## Source

- `data/raw/Meeting Notes and transcripts.md`
  - Section A) Helen & Ziff Sync-up (1) — 关键信息
  - Section B) Helen & Ziff Sync-up — 关键信息