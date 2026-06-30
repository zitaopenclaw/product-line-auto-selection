# Data Exploration: IDG & ISG Catalog Files

**Date:** 2026-06-30 (updated 2026-06-30 after ISG file replacement)  
**Purpose:** Evaluate `IDG_Product Category_HW Related.xlsx` and `DCG_Product_Catagory_20260624110842.xlsx` (ISG) for integration into the recall index alongside the existing `Advanced PN List.xlsx`.

> **Terminology note:** DCG and ISG are used interchangeably at Lenovo. This document uses **ISG** as the canonical term throughout. The file `DCG_Product_Catagory_20260624110842.xlsx` is the authoritative ISG product catalog. The earlier file `ISG_SALES_CATEGORY.xlsx` contained test data only and has been discarded.

---

## 1. Files Overview

| Attribute | Advanced PN List | IDG Product Category | ISG Product Category |
|-----------|-----------------|---------------------|----------------------|
| **Filename** | `Advanced PN List.xlsx` | `IDG_Product Category_HW Related.xlsx` | `DCG_Product_Catagory_20260624110842.xlsx` |
| **Sheet** | Sheet1 | sheet1 | category |
| **Rows** | 68,918 | 7,071 | 1,674 |
| **Columns** | 26 | 11 | 6 |
| **Hierarchy depth** | OH L1–L6 | Level 1–5 | Level 1–3 |
| **Column naming** | OH L1 … OH L6 + PN + PN Description | Level N Name + Level N Code + IsDefault | Level N Category ID + Level N Description |
| **Primary key / leaf ID** | PN (Part Number) | Level code (7-char, L5: 4-char) | Category ID (7-char, `LN…`) |
| **Domain** | Service offerings | Hardware device taxonomy | Infrastructure product taxonomy |
| **BG label** | ISG, PCSD, MBG, ISU (explicit col) | None (implicit: IDG) | None (implicit: ISG) |
| **Unique leaf nodes** | ~7,800 L6 nodes | 6,828 unique L4 / 4,475 L5 | **553 unique L3** |
| **Fill rate** | L1–L4 ~100%, L5 55.8%, L6 50.9% | L1–L4 ~97–100%, L5 63.3% | **100% all levels** |

---

## 2. Hierarchy Structure Detail

### 2.1 Advanced PN List (SSG — current)

| Level | Column | Example values | Fill rate |
|-------|--------|---------------|-----------|
| L1 | OH L1 | AI Solutions, Digital Workplace Solutions, Global Product Services, Hybrid Cloud Services, Intelligent Infrastructure, Smart Portfolio Services | ~100% |
| L2–L4 | OH L2–L4 | Service sub-categories | ~100% |
| L5–L6 | OH L5–L6 | Fine-grained service types | 55–51% |

- **Leaf nodes (L6)** store arrays of `{pn, description}` pairs.
- **BU split:** ISG = 34,318 rows, PCSD = 33,032, ISU = 1,132, MBG = 436.
- Pipeline currently indexes L2/L3/L4 nodes (337 total) with sampled PN descriptions as embedding text.

### 2.2 IDG Product Category

| Level | Column | Example values | Fill rate | Unique values |
|-------|--------|---------------|-----------|---------------|
| L1 | Level 1 Name | Laptops, Desktops & AIOs, Tablets, Workstations, Smart Collaboration, Edge Devices | ~100% | 6 |
| L2 | Level 2 Name | ThinkPad, IdeaPad, Yoga, Legion, ThinkCentre, ThinkStation, ThinkBook, ThinkEdge, LOQ… | ~100% | ~26 |
| L3 | Level 3 Name | E Series AIO, M Series, L Series, X1 Series… | 99.5% | ~211 |
| L4 | Level 4 Name | Specific model names | 96.6% | 6,828 |
| L5 | Level 5 Name | Variants: colors, storage, SKU suffixes | 63.3% | 4,475 |

- Each level has a paired **Level N Code** column (7-char for L1–L4; 4-char for L5, e.g., `ZA0H`).
- **`IsDefault` column:** boolean flag for preferred/canonical variant (95.96% True).
- L5 codes are actual product SKUs (short 4-char format); not Lenovo PNs.
- No PN column. Hierarchy codes ≠ Lenovo part numbers.

### 2.3 ISG Product Category (DCG file — authoritative)

| Level | Column | Example values | Fill rate | Unique values |
|-------|--------|---------------|-----------|---------------|
| L1 | Level 1 Category ID / Description | L110001 → Servers, L110002 → Storage, L110003 → Networking, L110004 → ON DEMAND Solutions, L110056 → Software Defined Infrastructure, L110058 → Racks and Power Systems | **100%** | **6** |
| L2 | Level 2 Category ID / Description | L210060 → Rack and Tower Servers, Mission-Critical, Blades, Edge Servers… | **100%** | **42** |
| L3 | Level 3 Category ID / Description | L310398 → ThinkSystem SR250, ThinkSystem SR530, ThinkSystem SR550… | **100%** | **553** |

- Code format: exactly **7 characters**, prefix encodes level (`L1xxxxx`, `L2xxxxx`, `L3xxxxx`).
- **No L4/L5** — this is a 3-level taxonomy.
- No PN column. Category IDs are taxonomy codes, not part numbers.
- **Zero nulls across all 1,674 rows** — cleanest of the three files.
- 1,121 duplicate rows are valid (same L1/L2 repeated for each L3 child; this is a flat "exploded" representation).

**Example path:**
```
L1: L110001 → Servers
L2: L210060 → Rack and Tower Servers
L3: L310398 → ThinkSystem SR250
```

---

## 3. Schema Comparison

| Attribute | Advanced PN List | IDG | ISG |
|-----------|-----------------|-----|-----|
| Has PN / part number leaf | ✅ PN column | ❌ | ❌ |
| Code system | Offering Hierarchy codes | 7-char (L1–L4), 4-char (L5) | 7-char `LN…` format |
| Cross-file ID overlap | — | None with PN List | None with PN List or IDG |
| Hierarchy depth (usable) | L1–L4 (L5/L6 sparse) | L1–L4 (L5 partial) | L1–L3 (all clean) |
| Description text for embedding | ✅ PN Descriptions (rich, per leaf) | Hierarchy names only | Hierarchy names only |
| Business domain | Services & solutions | Hardware products | Infrastructure hardware |
| Data quality | Good | Good | **Excellent** |

---

## 4. Does IDG/ISG Link to "Advanced Number" (PN)?

**No direct linkage between any of the three files.**

- Advanced PN List PNs (`SUB7B74180`, `7Q13104999`) are **service/solution SKUs** — not hardware part numbers.
- IDG Level Codes (`SVXUTDW`, `ZA0H`) are **category hierarchy IDs** and **SKU codes**, not Lenovo PNs.
- ISG Category IDs (`L110001`, `L310398`) are **taxonomy codes** from the ISG product catalog system, not PNs.
- An existing `output/oh_products_IDG.json` from D365 uses yet another format (`H00000000KT7`) — also not shared.

**Integration must be at the semantic level** (hierarchy names + product descriptions), not by ID cross-reference.

---

## 5. Data Quality Summary

| File | Issue | Severity | Recommendation |
|------|-------|----------|----------------|
| Advanced PN List | L5/L6 sparse (44–49% empty) | Medium | Handled by existing pipeline |
| IDG | L5 variants 36.7% empty | Low | Index at L3/L4; skip L5 |
| IDG | 6 rows missing L2 | Low | Drop incomplete rows |
| **ISG** | None — 100% fill, clean hierarchy | ✅ | Ready to use as-is |
| ISG | 1,121 apparent duplicate rows | Cosmetic | Deduplicate into tree structure at build time |
| ~~ISG_SALES_CATEGORY~~ | ~~Test data~~ | **Discarded** | Do not use |

---

## 6. Proposed Node Count for Recall Index

| Source | Indexable nodes | Level(s) | Rationale |
|--------|----------------|----------|-----------|
| Advanced PN List (SSG) | 337 | L2/L3/L4 | Current baseline |
| IDG | ~211 | L3 (product line) | L4 too granular (6,828 models); L3 = ThinkPad E Series etc. |
| ISG | **553** | **L3** | Only 3 levels; L3 = specific product models (ThinkSystem SR250) — natural recall target |
| **Total (merged)** | **~1,101** | — | ~3× current index size; manageable |

---

## 7. Architecture Impact Assessment

### What needs to change

| Component | Current state | Change needed |
|-----------|--------------|---------------|
| `scripts/build_pre_der_pn_tree.py` | Reads Advanced PN List only | Add `scripts/build_isg_tree.py` for ISG |
| `scripts/build_idg_tree.py` | Does not exist | Create; reads IDG file, indexes L3 nodes |
| `output/advanced_pn_tree.json` | SSG-only | Produce `output/idg_pn_tree.json` + `output/isg_pn_tree.json` |
| `src/load_pn_tree.py` | Loads single JSON | Load + merge multiple JSONs; tag `PNNode` with `source_bg` |
| `src/recall.py` → `RecallIndex` | Single corpus | No change — pass longer merged node list |
| `prompts/rerank_v2.txt` | BG as soft signal | No change needed |
| `src/field_rules.py` | SSG service fields only | IDG/ISG nodes have no matching fields; cascade auto-skips them (correct behavior) |
| `app.py` | BG validated as {IDG, DCG, SSG} | Update validation to accept both "ISG" and "DCG" (since they're synonymous); or normalize to ISG |

### What does NOT need to change
- BM25 + embedding recall logic
- LLM rerank prompt (BG already soft signal)
- Confidence scoring and diversity filter
- API contract

---

## 8. Open Design Questions

| # | Question | Status |
|---|----------|--------|
| **Q1** | Should IDG queries return hardware taxonomy nodes, SSG service nodes, or both? | **Open — most critical** |
| Q2 | Is ISG catalog the right source? | ✅ **Resolved:** DCG file is authoritative |
| Q3 | Which hierarchy level is the target for IDG/ISG? | Proposed: L3 for both (see §6) |
| Q4 | Hard filter or soft signal for BG? | Proposed: keep soft signal (minimal change) |
| Q5 | Relationship between Advanced PN List ISG rows and ISG catalog? | Complementary: PN List = service offerings; ISG catalog = hardware products |
| Q6 | Should Helen's field cascade apply to IDG/ISG nodes? | Proposed: skip (auto-skipped anyway since no matching fields) |

---

## 9. Next Steps

1. Answer **Q1** (what IDG queries should return) — determines whether IDG catalog supplements or replaces current index for IDG BG
2. Build `scripts/build_isg_tree.py` — reads DCG file, deduplicates, produces `output/isg_pn_tree.json` (553 L3 nodes)
3. Build `scripts/build_idg_tree.py` — reads IDG file, produces `output/idg_pn_tree.json` (~211 L3 nodes)
4. Extend `src/load_pn_tree.py` to merge all three trees
5. Update `app.py` to normalize DCG → ISG in BG validation
6. TDD: add tests for multi-tree load and ISG/IDG node retrieval
