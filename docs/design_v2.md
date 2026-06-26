# Pre-DER Agent — Design Doc (formerly V2.0)

> **Rename history**: previously referred to as "V2.0" / "v2.0". The agent was renamed on 2026-06-27 to **Pre-DER Agent** to align with the deal-desk workflow language. See [CONTEXT.md §"Agent Naming"](../CONTEXT.md#agent-naming-historical-anchor) for the decode key.
>
> **Workflow position**: Pre-DER is the stage that runs **before** the DER form is finalized. It takes a free-form sales voice input and surfaces preliminary offering-hierarchy (L2/L3/L4) recommendations that the seller can use as a starting point when completing the DER form. The downstream stage is the DER Refinement Agent, which works on the finalized structured DER form.
>
> **Status (2026-06-23)**: 20-input experiment completed. Human validation against Helen's expectations is the primary gate before broader rollout.  
> **Term definitions**: see [CONTEXT.md](../CONTEXT.md) for BG, BU, OH, PN terminology.

---

## 1. Goal

The **Pre-DER Agent** takes free-form sales voice inputs — natural-language utterances a salesperson would speak to an AI agent — and matches them against the **PN product hierarchy tree** (L2/L3/L4 nodes) to recommend preliminary offering-hierarchy items. These recommendations feed into the seller's DER-form completion workflow, after which the DER Refinement Agent takes over.

The match corpus is the same Lenovo catalog the DER Refinement Agent uses, but accessed through a different surface:
- DER Refinement Agent → flat OH product list (~2,000 products, BG-partitioned).
- Pre-DER Agent → PN hierarchy tree at L2/L3/L4 (337 named nodes, with up to 68,918 leaf PNs underneath), not partitioned by BG.

---

## 2. Input / Output

### Input
- `data/converted/sales-voice-inputs.md` — 20 voice input entries. Each entry has:
  - A numbered title (e.g. `1. New opportunity — hardware + services`)
  - An explicit `BG:` field (`IDG` / `DCG` / `SSG`)
  - A free-form "Sales voice input" text block (noisy: includes TCV, dates, CRM commands, customer names)

### Matching Corpus
- `output/advanced_pn_tree.json` — the Lenovo OH hierarchy tree. The Pre-DER Agent extracts all named nodes at **L2, L3, L4** (337 total: L2=11, L3=50, L4=276). L1 and deeper-than-L4 nodes are excluded.

### Output (per run, named by `--tag`)
```
output/pre_der_agent/
  matches_pre_der_<tag>.md      — markdown table, one row per voice input, top-3 node recommendations
  results_pre_der_<tag>.json    — full per-row JSON (raw text, extracted description, all scored nodes)
  summary_pre_der_<tag>.md      — BG coverage, confidence distribution, tree depth distribution, LLM stats
```

---

## 3. Key Design Decisions

### 3.1 BG Source: Read Directly from Markdown
The `BG:` field is explicitly embedded in `sales-voice-inputs.md` (added by the user). This is the ground truth; no LLM inference or heuristic is needed. In a real agent workflow, the BG would be a CRM session attribute.

### 3.2 Description Extraction: LLM Pre-Step
Voice inputs contain noise (TCV amounts, close dates, CRM verbs, customer names) that hurts recall precision. A pre-step calls DeepSeek to distill a clean 1–3 sentence product-need description. 

**Extraction prompt** (`src/parse_voice_input.py`):
> "Extract a concise 1–3 sentence description of what products or services the customer needs. Focus on: product type, quantity if mentioned, and service scope. Ignore: customer names, TCV, dollar values, dates, CRM actions."

**Experiment comparison** (exp1 = raw text, exp1_extracted = LLM-cleaned):

| Metric | exp1 (raw) | exp1_extracted |
|---|---|---|
| Match rate | 95% (19/20) | 95% (19/20) |
| High-confidence top-1 | 15 | 16 |
| Avg score (kept) | 0.754 | 0.771 |
| High-confidence slots | 23 | 26 |
| L2/L3/L4 distribution | 10/17/21 | 8/19/20 |

**Conclusion**: LLM extraction yields a modest but consistent improvement. Recommended as default.

### 3.3 Matching Corpus: PN Tree L2/L3/L4 Nodes
The DER Refinement Agent matches against a flat OH product list (~2,000 rows). The Pre-DER Agent matches against the PN hierarchy tree nodes — a different dimension of the same catalog. The tree has 337 named L2/L3/L4 nodes with up to 68,918 leaf PNs underneath.

Each node's **corpus text** is constructed as:
```
{node_name} | path: {L1} > {L2} > {L3} | pns: {desc1}, {desc2}, ..., {desc20}
```
The `pns:` segment uses **random 20** sampled leaf PN descriptions (seed=42). "Top 20" would be arbitrary without a relevance signal; random sampling surfaces the breadth of the node.

### 3.4 Dynamic Level Recommendation
Unlike the DER Refinement Agent which always matched against a flat product list, the Pre-DER Agent recommends at different levels depending on match specificity. A flat index is built across **all** L2/L3/L4 nodes; the LLM scores each node on its own merits.

Scoring guidance in `prompts/rerank_v2.txt`:
> "Prefer more specific (deeper) nodes when the description gives enough detail. A confident L4 match beats a vague L2 match. Accept shallower if deep nodes are too narrow."

Result: 95% of recommendations are at L3 or L4, showing the system correctly prefers specificity when warranted.

### 3.5 BG as Soft Signal (No Hard Filter)
The DER Refinement Agent applies a **hard BG filter**: IDG DER rows only searched IDG OH products. In the Pre-DER Agent, the PN tree is not partitioned by BG — some tree branches (e.g. "Global Product Services") span both IDG and DCG. A hard filter would lose valid matches.

Instead, BG is passed as soft context to the rerank prompt:
> "Business Group is a soft signal. Prefer nodes aligned with that BG but do not blindly exclude cross-BG nodes that are genuinely relevant."

This also handles **SSG** (Solutions & Services Group), a third BG present in the voice inputs but absent from the DER Refinement Agent's data. SSG maps to ISG BU in the PN list (same as DCG).

| BG (sales) | BU in PN list |
|---|---|
| IDG | PCSD + MBG |
| DCG | ISG |
| SSG | ISG (shares label with DCG) |

### 3.6 Parent-Child Diversity in Top-3
The original `keep_topk_diverse()` in `confidence.py` avoids returning products with the same parent. For the tree, the equivalent is avoiding **ancestor-descendant pairs** — e.g. do not recommend both `Deployment Services (L2)` and `Hardware Only Deployment (L3)` in the same top-3, as the L3 is a subset of the L2.

New function `keep_topk_diverse_tree(scored, k=3)` in `src/confidence.py`:
- Sort candidates by score descending.
- Greedily pick: skip a candidate if its `path` is a prefix of (or is prefixed by) any already-selected candidate's path.
- If fewer than k diverse picks are available, fill from deferred candidates.

---

## 4. Pipeline

```
data/converted/sales-voice-inputs.md
         │
         ▼
[Stage 0] src/parse_voice_input.py
  • Parse markdown → list of VoiceInput(id, title, bg, raw_text)
  • LLM call per input (DeepSeek): extract clean product-need description
         │
         ▼
[Stage 1] src/load_pn_tree.py
  • Load output/advanced_pn_tree.json
  • DFS traversal → 337 named L2/L3/L4 PNNode objects
  • Per node: random sample 20 leaf PN descriptions (seed=42)
  • Build corpus text: name | path | pns
         │
         ▼
[Stage 2] src/recall.py  (reused, backward-compatible)
  • RecallIndex built from corpus_texts= kwarg (no OHProduct required)
  • BM25 top-60 ∪ dense cosine top-60 → deduplicated → trim to top-30
         │
         ▼
[Stage 3] src/rerank.py  (reused, prompt + format_fn swapped)
  • RerankClient(prompt_path=rerank_v2.txt, format_fn=format_candidates_block_v2)
  • Candidates formatted as: level=L3 | name=... | path=... | sample_pns=...
  • DeepSeek primary → MiniMax fallback
  • Returns per-candidate score 0.0–1.0
         │
         ▼
[Stage 4] src/confidence.py  (reused + extended)
  • score_to_level: same thresholds (High≥0.85, Medium 0.60–0.84, Low 0.40–0.59, drop <0.40)
  • keep_topk_diverse_tree(k=3): avoids ancestor-descendant pairs
         │
         ▼
output/pre_der_agent/
  matches_pre_der_<tag>.md   results_pre_der_<tag>.json   summary_pre_der_<tag>.md
```

### Architecture Snapshot

The following snapshot is merged from the restored architecture notes (2026-06-25) and kept here to avoid split ownership across multiple docs.

Input: `data/converted/sales-voice-inputs.md` (20 entries, BG: IDG/DCG/SSG explicit)

- [Stage 0] `src/parse_voice_input.py`
  - Parse markdown -> list of VoiceInput(id, title, bg, raw_text)
  - LLM call per input: extract clean product-focused description (strip TCV/dates/CRM actions)
  - Output: list of VoiceInput with `.description` field populated

- [Stage 1] `src/load_pn_tree.py`
  - Load `output/advanced_pn_tree.json`
  - DFS traversal: collect all named nodes at L2, L3, L4 (skip nodes with empty name)
  - Per node: record (name, level, full_path, pn_count, random_sample_20_pn_descriptions)
  - Build corpus text: "{name} | path: {l1} > {l2} > ... | pns: {desc1}, {desc2}, ..."
  - Single shared RecallIndex (BM25 + dense) across all nodes; no BG split

- [Stage 2] `src/recall.py` (reused unchanged)
  - For each voice input: recall top-60 via BM25 + top-60 via dense, union -> top-30 candidates

- [Stage 3] `src/rerank.py` (RerankClient reused, new prompt)
  - `prompts/rerank_v2.txt`: BG passed as soft context, candidate format includes level + path
  - Scoring 0.0-1.0, same semantics as the DER Refinement Agent
  - Provider: DeepSeek primary -> MiniMax fallback

- [Stage 4] `src/confidence.py` (reused unchanged)
  - `score_to_level`: same thresholds
  - `keep_topk_diverse`: extended to also exclude parent-child pairs from top-3

Output: `output/pre_der_agent/`

- `matches_pre_der_<tag>.md` - markdown table, one row per voice input
- `results_pre_der_<tag>.json` - full per-input JSON (extracted description, all scored candidates)
- `summary_pre_der_<tag>.md` - score/level/BG distribution stats

---

## 5. Confidence Thresholds

Same as the DER Refinement Agent (established in [ADR-0002](adr/0002-low-threshold-raised-to-0.40.md)):

| Score | Level |
|---|---|
| ≥ 0.85 | **High** |
| 0.60 ≤ s < 0.85 | **Medium** |
| 0.40 ≤ s < 0.60 | **Low** |
| < 0.40 | drop |

---

## 6. File Layout (Pre-DER Agent additions)

```
product-line-auto-selection/
├── docs/
│   ├── design.md              # DER Refinement Agent design (formerly V1.0)
│   └── design_v2.md           # this file (Pre-DER Agent)
├── src/
│   ├── parse_voice_input.py   # parse sales-voice-inputs.md, LLM extraction
│   ├── load_pn_tree.py        # load advanced_pn_tree.json → 337 PNNode objects
│   ├── recall.py              # + corpus_texts= kwarg (backward-compatible)
│   ├── rerank.py              # + prompt_path=, format_fn= params (backward-compatible)
│   └── confidence.py          # + keep_topk_diverse_tree()
├── prompts/
│   ├── rerank.txt             # DER Refinement Agent prompt
│   └── rerank_v2.txt          # Pre-DER Agent prompt (BG soft signal, level/path in candidates)
├── scripts/
│   ├── run_der_refinement_agent.py   # DER Refinement Agent batch runner
│   └── run_pre_der_agent.py          # Pre-DER Agent batch runner (--tag, --concurrency, --no-extract, --seed)
├── data/converted/
│   └── sales-voice-inputs.md  # 20 voice inputs (ID, BG, raw text)
└── output/pre_der_agent/      # all Pre-DER Agent run outputs
```

---

## 7. Running the Pipeline

```bash
# Default run with LLM description extraction (recommended)
python scripts/run_pre_der_agent.py --tag my_run

# Skip extraction, use raw voice text directly
python scripts/run_pre_der_agent.py --tag my_run --no-extract

# Parallel reranking (speeds up if you have many inputs)
python scripts/run_pre_der_agent.py --tag my_run --concurrency 4
```

---

## 8. Exp1 Results (2026-06-23)

**Dataset**: 20 voice inputs (IDG=9, DCG=3, SSG=8)

| Metric | Value |
|---|---|
| Match rate | 95% (19/20 inputs) |
| Zero-match inputs | 1 (#8 — "workstations to the opportunity we discussed yesterday", no product context) |
| High-confidence top-1 | 16/20 |
| Average score (kept slots) | 0.771 |
| Tree depth distribution | L2=8, L3=19, L4=20 |
| IDG match rate | 88.9% (8/9) |
| DCG match rate | 100% (3/3) |
| SSG match rate | 100% (8/8) |
| LLM provider | DeepSeek only (0 failures, 0 fallbacks) |
| Total wall time | ~123s (20 extraction + 20 rerank calls) |

**Zero-match analysis**: Input #8 says "please add 200 workstations to the opportunity we discussed yesterday" — no product or service context after extraction. This is a retrieval dead-end by design; the agent would need to fetch the prior opportunity from CRM.

---

## 9. Open Questions / Next Steps

1. **Human validation**: Review `output/pre_der_agent/matches_pre_der_exp1_extracted.md` — does the recommended L2/L3/L4 node match the salesperson's actual intent? This is the primary gate before broader rollout.
2. **Wiring into the DER Refinement Agent**: the Pre-DER Agent's L2/L3/L4 recommendations should ultimately seed the recall pool for the DER Refinement Agent (so that the refined top-3 starts from the Pre-DER proposals). This integration is **not yet implemented** in POC; today the two agents run independently. Tracked as a follow-up sprint item.
3. **Prompt tuning**: If certain node types are over- or under-matched (e.g. too many L2 for specific requests), adjust scoring guidance in `prompts/rerank_v2.txt`.
4. **Corpus enrichment**: Currently 20 random PNs per node. If recall misses key nodes, consider increasing to 50 or using TF-IDF selected PNs.
5. **Zero-match handling**: Input #8 shows a class of inputs that lack product context (CRM navigation commands). The agent should detect and prompt for clarification rather than attempting recall.
6. **Scale**: 20 inputs ran in ~2 minutes. At 200 inputs, add `--concurrency 4`; at 2,000+, add checkpoint logic (currently only the DER Refinement Agent has checkpointing).
