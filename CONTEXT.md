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

### Offering Hierarchy (OH)
Lenovo's master data structure for classifying all "sellable things" from a sales/solution perspective. It is a layered taxonomy that re-organizes every product, service, and solution into a unified hierarchy, used across sales, quoting, reporting, and performance evaluation.

An **OH node** (colloquially "OH product" in the codebase) is one entry in this hierarchy. Nodes carry metadata: `Product Name`, `Product ID`, `Parent Product` (the node above it), `Solution Category`, `Solution Sub-Category`, and `ISO`.

The auto-selection system matches a DER's problem description against active OH nodes to surface the most relevant offerings.

**Source file**: `data/raw/OH product in D365.xlsx` (sheet: "Product Advanced Find View")  
**Active nodes**: those where `Status ≠ "Retired"` (~2,049 of 2,223 total)

### Business Group (BG)
An organizational unit within Lenovo that owns a distinct product and go-to-market domain. Two BGs are relevant to this system:

| Canonical name | Alias | Domain |
|---|---|---|
| **IDG** — Intelligent Devices Group | — | PCs, tablets, commercial endpoint devices |
| **ISG** — Infrastructure Solutions Group | **DCG** (Data Center Group) | Servers, storage, networking, infrastructure |
| **SSG** — Solutions & Services Group | — | Managed services, professional services, consulting, renewals |

> **BG ↔ BU label mapping across datasets**:  
> DER Refinement Agent source files (`Approved DER in 2026.xlsx`, `OH product in D365.xlsx`) use `IDG` and `DCG`.  
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

**[DER Refinement Agent]** The BG is a **hard filter**: a DER from one BG is only matched against OH products belonging to the same BG. Cross-BG matching is not meaningful because the two domains sell entirely different products.

**[Pre-DER Agent]** The Pre-DER Agent matches against the PN hierarchy tree rather than the flat OH product list. The PN tree is not partitioned by BG (some branches span both IDG and DCG), so the hard filter was removed. BG is passed as a soft signal in the rerank prompt only. See the BU mapping table above and `docs/design_v2.md` §3.5.

### Auto-Selection Output & Consumption Model
The system outputs a markdown table of top-3 OH node recommendations per DER opportunity (with score and confidence level). This output is **human-reviewed**: a sales or solution team member reads the recommendations and manually enters the chosen OH product(s) back into D365.

This means:
- The system is a **decision-support tool**, not an automation that writes back to D365 directly.
- A "no match" result (zero candidates above threshold) is a valid, handleable outcome — the human simply proceeds without a system recommendation.
- Confidence level precision matters for **trust calibration**, not for automated routing.

---

## Agent Naming (Historical Anchor)

> **Why this section exists**: Through 2026-06-25 the two pipelines were informally referred to as "V1.0" and "V2.0". On 2026-06-27 these were renamed to align with the deal-desk workflow language used by the governance team. Archived code, log files, and meeting notes may still contain the old V-labels — this table is the canonical decode key.

| New name | Former label | Role | Runs on | Reads | Writes |
|---|---|---|---|---|---|
| **DER Refinement Agent** | V1.0 / v1.0 | Refines offering-hierarchy items against a finalized DER form; outputs the qualified DER package. In POC the output is the offering-hierarchy list. | Structured DER Excel rows (`Approved DER in 2026.xlsx`) | Flat OH product list (`OH product in D365.xlsx`) | `output/der_refinement_agent/` |
| **Pre-DER Agent** | V2.0 / v2.0 | Recommends offering-hierarchy L2/L3/L4 items BEFORE the DER form is finalized, from free-form sales voice input. | Markdown voice inputs (`data/converted/sales-voice-inputs.md`) | PN hierarchy tree (`output/advanced_pn_tree.json`) | `output/pre_der_agent/` |

**Workflow position**:
1. Pre-DER Agent runs first (sales voice input → preliminary L2/L3/L4 recommendations).
2. The seller enters / finalizes the DER form using those recommendations.
3. DER Refinement Agent runs on the finalized DER form → qualified DER package (in POC: offering-hierarchy list).

**Pipeline ordering caveat (current POC)**: today's DER Refinement Agent implementation does **not** yet consume the Pre-DER Agent output as input; it independently matches against the flat OH product list. Wiring Pre-DER output into the DER Refinement Agent's recall pool is an open next-step item (see `docs/review-2026-06-25.md` §6.1 and the new name's intent in `docs/design.md`).

**Decode rules for old references**:
- `V1.0`, `v1.0`, `output/v1.0/`, `run.py` (the original single pipeline), `rerank.txt` prompt → **DER Refinement Agent**
- `V2.0`, `v2.0`, `output/v2.0/`, `run_v2.py`, `rerank_v2.txt` prompt (the file name retains the `_v2` suffix as an internal label; content is Pre-DER Agent's prompt) → **Pre-DER Agent**
- `[V1.0]` / `[V2.0 changed this]` qualifiers in older prose → `[DER Refinement Agent]` / `[Pre-DER Agent]`

---
