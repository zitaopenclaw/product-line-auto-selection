# ADR-0004: Rename V1.0 / V2.0 to Named Agents

**Status**: Accepted  
**Date**: 2026-06-27

## Context

Through 2026-06-25 the two pipelines were referred to informally as "V1.0" and "V2.0". These labels leaked into output directories (`output/v1.0/`), log files, meeting notes, and prompt file names (`rerank_v2.txt`). On 2026-06-27 they were renamed to align with deal-desk workflow language.

## Decision

| Old label | New canonical name | Role |
|---|---|---|
| V1.0 / v1.0 | **DER Input AI Agent** | Recommends PN tree L2/L3/L4 nodes for a finalized DER form. Runs on `Approved DER in 2026.xlsx`. Default mode: tree. Legacy flat mode (OH product list) retained but deprecated. |
| V2.0 / v2.0 | **Pre-DER Agent** | Recommends PN tree L2/L3/L4 nodes before the DER form is finalized, from free-form sales voice input. Runs on `data/converted/sales-voice-inputs.md`. |

## Decode key for old references

- `V1.0`, `v1.0`, `output/v1.0/`, `run.py`, `rerank.txt` prompt → **DER Input AI Agent**
- `V2.0`, `v2.0`, `output/v2.0/`, `run_v2.py`, `rerank_v2.txt` prompt → **Pre-DER Agent**
- `[V1.0]` / `[V2.0 changed this]` qualifiers in older prose → `[DER Input AI Agent]` / `[Pre-DER Agent]`
- `DER Refinement Agent` (used briefly Jun 27 before final rename) → **DER Input AI Agent**

## Notes

Prompt file names (`rerank_v2.txt`, `rerank_der_tree.txt`) retain their original suffixes as internal labels and were not renamed to avoid breaking existing script references.
