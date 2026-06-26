# Testing & CI/CD Pipeline — Design Doc

> **Date**: 2026-06-27
> **Status**: Approved
> **Owner**: TBD

## 1. Goal

Establish a **test-driven development (TDD) workflow** and a **CI/CD pipeline** for the product-line-auto-selection project so that:

1. All future code changes are protected by automated regression tests
2. Every pull request is verified before merge via GitHub Actions
3. The team's development discipline follows RED → GREEN → REFACTOR
4. The pre-existing pipeline (Stage 4 DER Refinement Agent + Stage 5 Pre-DER Agent) remains stable

## 2. Background

The project currently has:

- Two pipeline agents (`scripts/run_der_refinement_agent.py` and `scripts/run_pre_der_agent.py`)
- 8 source modules in `src/` (load_data, load_pn_tree, parse_voice_input, recall_common, recall, rerank, confidence, field_rules)
- **Zero automated tests** — changes are validated only by manual end-to-end runs
- **No CI/CD** — `.github/` directory does not exist
- **No git remote** — local repo only, no GitHub connection

## 3. Approach: Plan B (Standard)

Selected after comparing three options (lightweight, standard, full coverage).

### 3.1 Test Categories

| Marker | Includes | CI default | Manual |
|---|---|---|---|
| (none) | confidence, field_rules, recall_common, load_data, load_pn_tree, rerank (mocked), parse_voice_input (mocked) | ✅ | ✅ |
| `@pytest.mark.slow` | recall.py (sentence-transformers model load) | ❌ | ✅ |
| `@pytest.mark.integration` | End-to-end real API tests | ❌ | ✅ |

### 3.2 Test Directory Structure

```
tests/
  conftest.py                 — shared fixtures (mocked LLM client, sample data)
  fixtures/
    sample_oh.xlsx            — ~10 OH products across 2 BGs
    sample_der.xlsx           — ~10 DER rows including structured fields
    sample_pn_tree.json       — minimal PN tree (3 L1 → ~5 L2/L3 nodes)
  test_confidence.py          — 12 cases
  test_field_rules.py         — 10 cases
  test_recall_common.py       — 8 cases
  test_load_data.py           — 8 cases
  test_load_pn_tree.py        — 5 cases
  test_recall.py              — 5 cases (@slow)
  test_rerank.py              — 8 cases (mocked)
  test_parse_voice_input.py   — 6 cases (mocked)
```

### 3.3 Test Inventory by Module

**`test_confidence.py`** — pure functions
- `score_to_level`: 4 threshold boundaries (0.85, 0.60, 0.40, drop); `None` and 0.0/1.0 edge cases
- `keep_topk`: sort by score desc, drop sub-threshold, empty input
- `keep_topk_diverse`: parent uniqueness, deferred fill, k overflow
- `keep_topk_diverse_tree`: ancestor-descendant conflict detection

**`test_field_rules.py`** — pure functions
- `apply_field_rules`: each of 6 fields independently triggered; combined cases (ARS=Yes + AI=Yes)
- `inject_field_candidates`: ordering (guaranteed > boosted > recall); `max_per_parent=2` cap

**`test_recall_common.py`** — pure functions
- `tokenize`: lowercase, alphanumeric, punctuation handling
- `bm25_topk`: relevance ordering, edge cases (empty query, k > corpus)
- `oh_embed_text`: field assembly
- `derive_query_text`: max_chars truncation

**`test_load_data.py`** — xlsx fixture
- `load_der`: header mapping, field coercion, row skip on missing required
- `load_oh`: retire filter, missing-field handling
- `index_oh_by_bg`: grouping correctness
- `stratified_sample`: per-BG count, seed determinism

**`test_load_pn_tree.py`** — JSON fixture
- `load_pn_nodes`: level filtering (L2/L3/L4 only), path construction
- `_collect_leaf_descs`: PN description collection
- `pn_node_embed_text`: format

**`test_recall.py`** — `@slow`
- `RecallIndex` build: BM25 + dense embeddings
- `recall`: union deduplication, top-k truncation, empty description

**`test_rerank.py`** — mocked
- `format_candidates_block`: all metadata fields
- `render_prompt`: template substitution
- `_extract_json`: clean JSON / code-fenced / malformed
- `RerankClient.rerank`: primary success, fallback, both fail
- Provider stats tracking

**`test_parse_voice_input.py`** — mocked
- `parse_voice_inputs_md`: delimiter parsing, BG extraction
- `_llm_extract`: mock API → returns extracted text
- Multi-entry markdown split

**Total: ~62 test cases; CI runs ~50 (excluding `@slow` and `@integration`).**

## 4. CI/CD Pipeline

### 4.1 GitHub Actions Workflow

`.github/workflows/test.yml`:

```yaml
on: [pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: actions/cache@v4
        with:
          path: ~/.cache/huggingface
          key: models-${{ hashFiles('requirements.txt') }}
      - run: pip install -r requirements.txt pytest pytest-cov
      - run: pytest --cov=src --cov-fail-under=70 -x
```

### 4.2 Trigger Strategy

- **Trigger**: `pull_request` only (per user preference; not push to main)
- **Branch filter**: All branches
- **No nightly**: skip for v1, can add later

### 4.3 Coverage

- **Tool**: `pytest-cov`
- **Source**: `src/`
- **Threshold**: 70% line coverage (`--cov-fail-under=70`)
- **Report**: terminal + XML (for future Codecov integration)

## 5. TDD Workflow

### 5.1 Development Rule (added to CLAUDE.md)

All future feature work and bug fixes follow:

1. **RED** — Write the test first; verify it fails
2. **GREEN** — Write the minimal implementation; verify the test passes
3. **REFACTOR** — Improve code while keeping tests green

### 5.2 Test Commands (added to CLAUDE.md)

- `pytest -x` — run all fast tests (skip `@slow` and `@integration`)
- `pytest -x --runslow` — include `recall.py` model tests
- `pytest --cov=src --cov-report=term-missing -x` — with coverage
- `pytest tests/test_xxx.py -x` — run a specific file

## 6. Configuration

### 6.1 `pyproject.toml` (new file)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: tests that load ML models (CI default skip)",
    "integration: tests that call real APIs (CI default skip)",
]

[tool.coverage.run]
source = ["src"]
omit = ["*/__pycache__/*", "src/__pycache__/*"]
```

### 6.2 `requirements-dev.txt` (new file)

```
pytest>=8.0
pytest-cov>=5.0
```

## 7. GitHub Repository Setup

The project has a local git repo but no remote. Steps to complete:

1. **User creates GitHub repo** at github.com (empty, no README/LICENSE)
2. **Local setup** (executed by the agent):
   ```bash
   git add .
   git commit -m "Initial commit: project + test infrastructure"
   git remote add origin https://github.com/<user>/<repo>.git
   git push -u origin main
   ```
3. **Verify** — first PR triggers CI; green status confirms setup

## 8. Out of Scope

- Pre-commit hooks (not requested; can be added later)
- Nightly integration tests (defer until core coverage is solid)
- Codecov.io upload (defer; XML is generated for future use)
- Coverage > 70% (current focus is coverage of public behaviors, not raw %)

## 9. Open Questions

None — all decisions approved during brainstorming phase.

## 10. References

- `docs/adr/0003-candidate-no-positional-index.md` — context for rerank tests
- `docs/design_v2.md` — pipeline architecture under test
- `CONTEXT.md` — domain glossary (DER, OH, BG, PN)
