# Domain Context

This file is the canonical glossary for the product-line-auto-selection system.
It records domain terms as they are resolved — not implementation details.

---

## Glossary

### Deal Engagement Review (DER) / Deal Qualification Review (DQR)

> **Terminology note**: DER and DQR are near-equivalent terms used interchangeably across different Lenovo geos and teams. Similarly, "Pre-DER" and "Pre-DQR" refer to the same pre-submission workflow stage. The naming difference is purely a regional/team convention — there is no structural distinction between the two.

A mandatory step in Lenovo's sales opportunity lifecycle for **Advanced Services & Solutions deals**. When a seller registers an opportunity and the deal is classified as advanced, the seller must submit a DER/DQR form by a specified due date to trigger the **deal governance process**.

The form captures deal context that the governance team uses to qualify and tier the deal:
- **Customer** — who the deal is with
- **Offering** — what is being sold
- **Total Contract Value (TCV)** — estimated deal value
- **Due date** — governance submission deadline

Based on this information, the deal is rated as simple, moderately complex, or highly complex, which determines the level of internal scrutiny and approvals required. This qualification step is sometimes called the **Deal Qualification Review (DQR)** precisely because it answers the question: *does this deal qualify to enter the formal deal governance process, and at what complexity tier?*

**Pre-DER / Pre-DQR** refers to the actions taken before the form is submitted: creating the opportunity in CRM, completing customer master data, entering product information, and ensuring all required fields are populated.

The auto-selection system reads DER records and uses the problem description field to recommend matching OH products.

**Source file**: `data/raw/Approved DER in 2026.xlsx`  
**Key fields**: Opportunity ID, Business Group, "Describe the business problem or challenge"

### PN Hierarchy Tree (PN Tree)

Lenovo's product catalog organized as a named hierarchy built from the **Advanced PN List** — a catalog of individual Part Numbers (PNs, i.e. orderable SKUs). The tree groups PNs into named categories at up to 4 levels (L1–L4). The auto-selection system uses nodes at **L2, L3, and L4** (337 total named nodes).

A **PN tree node** carries: `name`, `level` (2/3/4), `path` (ancestor names from L1 down), `pn_count` (leaf PNs underneath), and a random sample of leaf PN descriptions used for recall.

**Source file**: `data/raw/Advanced PN List.xlsx` → pre-built into `output/advanced_pn_tree.json`  
**Owner**: Helen (Product Management). Update cadence: ~monthly.

**Current system scope**: both the Pre-DER Agent and the DER Input AI Agent output PN tree nodes (L2/L3/L4). This is the **primary output taxonomy** for all active development.

> **⚠ Known operational risk — PN tree staleness**: the tree is baked into the Docker image at build time (`RUN python deploy/build_index.py`). When Helen updates `Advanced PN List.xlsx`, the running service does not know — recommendations silently drift until the image is rebuilt and redeployed. A silent stale index is worse than a visible error.
>
> **Deferred fix**: before production rollout, add an explicit staleness signal — e.g. a build timestamp in `advanced_pn_tree.json` exposed via `/health`, or a CI check that alerts when the source Excel changes. Owner of this task: TBD. Trigger: before first production seller cohort.

### Offering Hierarchy (OH)

Lenovo's master data structure for classifying all "sellable things" from a sales/solution perspective — a separate taxonomy from the PN tree. OH nodes live in D365 and are the items sellers ultimately enter into deals and DER forms.

An **OH node** carries: `Product Name`, `Product ID`, `Parent Product`, `Solution Category`, `Solution Sub-Category`, `ISO`, `Status`.

**Source file**: `data/raw/OH product in D365.xlsx` (sheet: "Product Advanced Find View")  
**Active nodes**: those where `Status ≠ "Retired"` (~2,049 of 2,223 total)

> **Known gap — PN tree ↔ OH taxonomy misalignment**: PN tree nodes and OH nodes are not yet aligned. A seller receiving a PN tree node recommendation cannot reliably look up the corresponding OH entry in D365 by name. Resolving this mapping is deferred. Until resolved, the system functions as a **zone indicator** (pointing the seller to a category in the right area of the catalog) rather than a precise OH line-item lookup.
>
> **Current policy**: active development touches the PN tree only. Code paths that use the D365 OH product catalog (`OH product in D365.xlsx`) are **legacy/flat-mode only** and are not the focus of current work.

### Business Group (BG)
An organizational unit within Lenovo that owns a distinct product and go-to-market domain. Two BGs are relevant to this system:

| Canonical name | Alias | Domain |
|---|---|---|
| **IDG** — Intelligent Devices Group | — | PCs, tablets, commercial endpoint devices |
| **ISG** — Infrastructure Solutions Group | **DCG** (Data Center Group) | Servers, storage, networking, infrastructure |
| **SSG** — Solutions & Services Group | — | Managed services, professional services, consulting, renewals |

> **BG ↔ BU label mapping across datasets**:  
> DER Input AI Agent source files (`Approved DER in 2026.xlsx`, `OH product in D365.xlsx`) use `IDG` and `DCG`.  
> The Advanced PN List (`data/raw/Advanced PN List.xlsx`) used by the Pre-DER Agent uses a different `Business Unit` column with values `PCSD`, `MBG`, `ISG`, `ISU`:
>
> | Sales BG label | PN List BU label(s) |
> |---|---|
> | IDG | PCSD + MBG |
> | DCG / ISG | ISG |
> | SSG | ISG (shares BU label with DCG in the PN list) |
>
> SSG and DCG share the `ISG` BU label in the Advanced PN List — they are organizationally distinct in the sales org but not differentiated in that data source.  
> Pre-DER Agent uses BG as a **soft signal** in the rerank prompt only; no hard filter is applied to the PN tree.

**[DER Input AI Agent]** BG is passed as a **soft signal** to the rerank prompt (same as Pre-DER Agent). The PN tree is not partitioned by BG. The `/recommend_der` API validates that `business_group` is one of IDG/DCG/SSG to catch caller errors, but does not hard-filter the recall pool.

**[Pre-DER Agent]** The Pre-DER Agent matches against the PN hierarchy tree rather than the flat OH product list. The PN tree is not partitioned by BG (some branches span both IDG and DCG), so the hard filter was removed. BG is passed as a soft signal in the rerank prompt only. See the BU mapping table above and `docs/design_v2.md` §3.5.

### HW Product Catalog

Hardware product taxonomy files used as the source for `hw_recommendations`. Separate from the PN Tree (which covers service offerings only).

| BG | Source file | Levels indexed | Unique nodes |
|----|------------|---------------|-------------|
| **IDG** | `data/raw/IDG_Product Category_HW Related.xlsx` | L2/L3/L4 (deepest available; fallback up if empty) | ~26 L2 / ~211 L3 / ~2k L4 |
| **ISG** | `data/raw/DCG_Product_Catagory_20260624110842.xlsx` | L2/L3 (file only has 3 levels) | 42 L2 / 553 L3 |

> **Terminology note:** The ISG file is named `DCG_…` because DCG (Data Center Group) and ISG (Infrastructure Solutions Group) are used interchangeably at Lenovo. **ISG is the canonical term** used throughout this system.

Pre-built tree artifacts: `output/idg_pn_tree.json`, `output/isg_pn_tree.json`  
Build scripts: `scripts/build_idg_tree.py`, `scripts/build_isg_tree.py`

HW catalog nodes carry: `name`, `level`, `path`, `source_bg` (IDG or ISG). They do **not** have PN descriptions (no PN column in source files) — embedding text is built from the hierarchy path + node name only.

SSG has no HW catalog. SSG queries return service offerings only.

---

### Auto-Selection Output & Consumption Model

The system has two distinct consumption modes. For BG=IDG and BG=ISG, each mode now produces **dual recommendations**; for BG=SSG, service recommendations only.

#### Dual-output response schema (IDG/ISG)
```json
{
  "service_recommendations": [ {"node": "...", "score": 0.9, "level": "L3", "path": [...]} ],
  "hw_recommendations":      [ {"node": "...", "score": 0.85, "level": "L3", "path": [...]} ]
}
```
SSG returns `service_recommendations` only (`hw_recommendations` absent or empty).

HW pipeline (IDG/ISG): separate `RecallIndex` per BG (hard filter) → no field cascade → `rerank_hw.txt` prompt → `keep_topk_diverse_tree(k=3)`.  
Service pipeline (all BGs): unchanged — shared PN Tree, soft BG signal, field cascade, existing prompts.

#### Mode 1 — Batch Report (internal/ops)
Output: markdown table (`matches_<tag>.md`) produced by running the agent pipeline offline over a full DER dataset.
- **Consumer**: solution architects, ops team, or deal desk reviewing aggregate results across many DER opportunities
- **Use**: validation, model quality assessment, spotting patterns across a DER cohort
- **Flow**: run script → review markdown → manually enter chosen OH nodes into D365 if applicable

#### Mode 2 — Live Copilot Topic (seller-facing)
Output: real-time JSON response from the FastAPI service, rendered as an Adaptive Card in Microsoft Teams via Copilot Studio.
- **Consumer**: sales reps using the Copilot Studio agent during an active sales conversation
- **Two topics**:
  - **Pre-DER topic** — before the DER form is finalized; seller describes customer need in free-form voice input; Copilot calls `/recommend`
  - **DER Input topic** — during/after DER form completion; seller re-enters key DER fields via an **Adaptive Card form** presented in the Copilot conversation (not read from D365 directly); Copilot calls `/recommend_der` with those field values
- **DER Input Adaptive Card fields**: the card collects the structured inputs that drive the field cascade — `service_model`, `ars_flag`, `ai_flag`, `scope`, `existing_expansion` — plus a free-text `query` describing the business problem
- **Flow (Pre-DER)**: seller types/speaks → Copilot calls `/recommend` → top-3 service cards (+ top-3 HW cards for IDG/ISG) in Teams
- **Flow (DER Input)**: seller fills Adaptive Card → Copilot calls `/recommend_der` → same dual/single output logic
- **Note**: Copilot Studio Adaptive Card UI update for dual-output display is **deferred**

#### Shared invariants (both modes)
- The system is a **decision-support tool**, not an automation that writes back to D365 directly.
- A "no match" result (zero candidates above threshold) is a valid, handleable outcome.
- Confidence level precision matters for **trust calibration**, not automated routing.

---

## Agent Naming

The two agents were formerly referred to as "V1.0" (now **DER Input AI Agent**) and "V2.0" (now **Pre-DER Agent**); old labels may appear in archived output files, log directories, and meeting notes — see [ADR-0004](docs/adr/0004-agent-rename-v1-v2-to-named-agents.md) for the full decode key.

**Workflow position**:
1. Pre-DER Agent runs first — sales voice input → preliminary L2/L3/L4 PN tree node recommendations.
2. Seller uses those recommendations to complete the DER form.
3. DER Input AI Agent runs on the finalized DER form → top-3 PN tree L2/L3/L4 node recommendations (same format).

**Pipeline relationship (current POC — Option C)**: both agents run independently on disjoint datasets. "Comparison at report level" means independent quality checks, not a cross-agent delta on the same deal. See `docs/design_v2.md` §9.2.

---
