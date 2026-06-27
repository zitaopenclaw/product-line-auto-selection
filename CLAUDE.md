# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Two agents operate as the **Pre-DER / DER Refinement Agent** pipeline (formerly V2.0 / V1.0):

- **Pre-DER Agent** (`scripts/run_pre_der_agent.py`) takes free-form sales voice inputs (`data/converted/sales-voice-inputs.md`), extracts a clean product-need description via LLM, and matches it against the **PN hierarchy tree** at L2 / L3 / L4 level. Returns a top-3 recommendation of OH tree nodes per input. Runs **before** the DER form is finalized.
- **DER Refinement Agent** (`scripts/run_der_refinement_agent.py`) takes structured DER form rows (`Approved DER in 2026.xlsx`) and matches them against the **flat OH product list** using a 3-stage pipeline: BM25 + dense-embedding recall → Helen's structured-field cascade → LLM rerank → confidence scoring. Returns a top-3 OH product recommendation per DER row.

Both agents share `src/` modules (recall, rerank, confidence). The Business Group (`IDG` / `DCG` / `SSG`) is a hard filter in the DER Refinement Agent; a soft signal only in the Pre-DER Agent (because the PN tree spans multiple BGs).

## Running the pipeline

All scripts must be run from the project root (not from inside `scripts/`), because `src/` imports are resolved via `sys.path.insert(0, ROOT)`.

```bash
# DER Refinement Agent (formerly V1.0) — POC run (default: 50 rows, 25 per BG, single-threaded)
python scripts/run_der_refinement_agent.py

# DER Refinement Agent — Large run
python scripts/run_der_refinement_agent.py --total 1000 --per-bg 500 --concurrency 10 --tag 1000

# DER Refinement Agent — Resume an interrupted run (checkpoint at logs/<tag>_progress.json)
python scripts/run_der_refinement_agent.py --tag 1000

# DER Refinement Agent — Fresh restart, ignoring checkpoint
python scripts/run_der_refinement_agent.py --tag 1000 --fresh

# Pre-DER Agent (formerly V2.0) — Default run with LLM description extraction
python scripts/run_pre_der_agent.py --tag my_run

# Pre-DER Agent — Skip extraction, use raw voice text directly
python scripts/run_pre_der_agent.py --tag my_run --no-extract

# Pre-DER Agent — Parallel reranking
python scripts/run_pre_der_agent.py --tag my_run --concurrency 4
```

The DER Refinement Agent checkpoints automatically every 20 rows. Output files are named `matches_<tag>.md`, `summary_<tag>.md`, `results_<tag>.json` in `output/der_refinement_agent/`.

## Environment setup

Copy `.env.example` to `.env` and fill in keys:

```
MINIMAX_API_KEY=...        # primary LLM (required)
MINIMAX_BASE_URL=...       # e.g. https://api.minimaxi.com/v1
MINIMAX_MODEL=...          # e.g. MiniMax-M3

DEEPSEEK_API_KEY=...       # fallback LLM (optional)
DEEPSEEK_BASE_URL=...      # e.g. https://api.deepseek.com/v1
DEEPSEEK_MODEL=...         # e.g. deepseek-chat
```

Install dependencies: `pip install -r requirements.txt` (pulls ~1 GB including `torch` and `sentence-transformers`).

## Architecture

```
src/
  load_data.py         -- load DER + OH from xlsx; partition OH by BG; stratified sampling (DER Refinement Agent)
  load_pn_tree.py      -- load advanced_pn_tree.json; DFS to 337 PNNode objects at L2/L3/L4 (Pre-DER Agent)
  parse_voice_input.py -- parse sales-voice-inputs.md; LLM extraction of clean product-need description (Pre-DER Agent)
  recall_common.py     -- tokenizer, BM25 builder, embedding text formatter, query deriver
  recall.py            -- RecallIndex: builds BM25 + bge-small-en-v1.5 embeddings, union recall
  rerank.py            -- RerankClient: calls MiniMax (primary) -> DeepSeek (fallback); renders prompt
  confidence.py        -- score_to_level (High/Medium/Low/drop); keep_topk; keep_topk_diverse; keep_topk_diverse_tree
  field_rules.py       -- structured field cascade (Helen's 6-field rule): apply_field_rules(), inject_field_candidates()

prompts/
  rerank.txt           -- DER Refinement Agent prompt (BG as hard filter; flat OH candidates)
  rerank_v2.txt        -- Pre-DER Agent prompt (BG as soft signal; PN tree L2/L3/L4 candidates with level + path)
  rerank_der_tree.txt  -- WIP / future variant: DER form matched against PN tree nodes (not yet wired to any pipeline)

scripts/
  run_der_refinement_agent.py        -- DER Refinement Agent batch runner (--total/--per-bg/--concurrency/--tag/--fresh)
  run_pre_der_agent.py               -- Pre-DER Agent batch runner (--tag/--concurrency/--no-extract/--seed)
  process_pre_der_inputs.py          -- one-shot preprocessor: raw talking script -> structured voice-inputs.md
  build_pre_der_pn_tree.py           -- builds output/advanced_pn_tree.json from Advanced PN List.xlsx
  validate_pn_tree.py                -- sanity-checks output/advanced_pn_tree.json
  generate_pre_der_ppt.py            -- generates PPT from Pre-DER Agent results
  apply_slide2_fonts_pre_der_ppt.py  -- reapplies slide-2 font sizes to slides 3-20
  convert_to_md.py                   -- xlsx to markdown converter (data exploration helper)
```

## Key design decisions

- **BG hard filter (DER Refinement Agent)**: recall indexes are built per-BG. A DER row only searches within its own BG's OH product pool.
- **BG as soft signal (Pre-DER Agent)**: the PN hierarchy tree spans multiple BGs (e.g. "Global Product Services" covers both IDG and DCG), so BG is passed to the rerank prompt as a soft preference rather than a hard partition.
- **Two-stage recall**: BM25 (keyword) and dense cosine (bge-small, CPU-friendly) are each run top-60 and union-deduped into a pool of up to 60 candidates.
- **Structured field cascade** (`src/field_rules.py`, DER Refinement Agent only): Helen's 6-field rule (BG, Service Model, ARS flag, AI flag, existing expansion, Scope) injects guaranteed/boosted OH products at the head of the pool before the LLM sees it. Guaranteed products are those with 100%-certain field signals (e.g. ARS=Yes). At most 2 products sharing the same parent are injected to preserve recommendation diversity.
- **Candidate trim**: the merged pool is trimmed to top-30 candidates for the LLM rerank call.
- **LLM rerank**: sends up to 30 candidates in one prompt using positional `candidate_no` (not product_id strings) to eliminate hallucination risk. Gets back `{candidates: [{candidate_no, score}]}`. Response JSON is extracted with fallback regex if wrapped in code fences.
- **Confidence thresholds**: High >= 0.85 / Medium 0.60-0.85 / Low 0.40-0.60 / drop < 0.40 (defined in `confidence.py`).
- **Diversity** (`keep_topk_diverse` / `keep_topk_diverse_tree`): always applied — avoids returning 3 products/nodes that share the same parent or are ancestor-descendant in the tree.
- **Checkpointing** (DER Refinement Agent): `run_der_refinement_agent.py` writes `logs/<tag>_progress.json` every 20 rows and resumes from it automatically.

## Data files

Raw xlsx files live in `data/raw/`. The pipeline reads them directly -- do not rename or move them. Active OH products are those where `Status != "Retired"` (column 16).

## Output

DER Refinement Agent results land in `output/der_refinement_agent/`, named by `--tag` (default `run`):
- `matches_<tag>.md` -- markdown table, one row per DER opportunity, top-3 products
- `summary_<tag>.md` -- score/level distribution statistics
- `results_<tag>.json` -- full per-row JSON (includes error info, provider used)

Pre-DER Agent results land in `output/pre_der_agent/`, named by `--tag` (default `pre_der_run`):
- `matches_pre_der_<tag>.md` -- markdown table, one row per voice input, top-3 tree nodes
- `summary_pre_der_<tag>.md` -- score/level distribution statistics
- `results_pre_der_<tag>.json` -- full per-row JSON (includes error info, provider used)

## TDD Development Workflow

**All future code changes must follow TDD.** Tests live in `tests/`, mirroring the `src/` structure. CI runs automatically on every pull request.

### Workflow: RED → GREEN → REFACTOR

1. **RED** — Write a failing test that describes the desired behavior.
2. **GREEN** — Write the minimal code to make the test pass.
3. **REFACTOR** — Improve the code while keeping tests green.

### Test Commands

| Command | Purpose |
|---|---|
| `pytest -x` | Run all fast tests (skips `@slow` and `@integration`) |
| `pytest -m slow` | Run only slow tests (model-loading) |
| `pytest -m integration` | Run only integration tests (real APIs) |
| `pytest -m "not slow and not integration"` | Explicit form of `pytest -x` |
| `pytest --cov=src --cov-fail-under=70` | With coverage gate (CI uses this) |
| `pytest tests/test_X.py -v` | Run a single file |

### Markers

- `@pytest.mark.slow` — Tests that load ML models (sentence-transformers, ~20s import overhead). Not run in CI.
- `@pytest.mark.integration` — Tests that call real LLM APIs. Requires valid API keys. Not run in CI.

### Coverage Threshold

CI fails if `src/` coverage drops below **70%**. Currently at ~92% (see `pytest --cov=src`).

### Adding a New Test

1. Create `tests/test_<module>.py`
2. Match the public function/class names from `src/<module>.py`
3. Use existing fixtures from `tests/conftest.py` (`sample_oh_path`, `sample_der_path`, etc.)
4. Run `pytest tests/test_<module>.py -v` to verify
5. Run full suite: `pytest -x`




