# ADR-0003: Replace product_id String Return with candidate_no Positional Index

**Status**: Accepted  
**Date**: 2026-06-21

## Context

The original rerank prompt asked the LLM to return each candidate's `product_id` string verbatim:

```json
{"candidates": [{"product_id": "<id>", "score": 0.92}]}
```

This created two failure modes:

1. **Hallucinated ID**: LLM fabricates a product_id that doesn't exist → silently dropped by the parser, reducing the candidate pool without any signal.
2. **Swapped ID**: LLM returns a real but wrong product_id (confuses two similar products) → accepted by the parser, producing a score associated with the wrong product. This is the more dangerous failure because it produces plausible-looking but incorrect output that a human reviewer may not catch.

Additionally, `product_id` values (opaque internal codes) were printed in the candidates block for the LLM to read, even though they carry no semantic meaning for matching decisions.

## Decision

1. **Switch the LLM output field from `product_id` to `candidate_no`** — a 1-based integer corresponding to the position of the candidate in the list shown in the prompt.
2. **Parse by position**: `rerank.py` maps `candidate_no` back to the candidate object via `cands[no - 1]`, with bounds-checking (out-of-range → skip) and duplicate-checking (repeated no → skip).
3. **Remove `product_id=X` from the candidates block** in `format_candidates_block`. The LLM now only needs the sequential number to refer back to a candidate; printing the opaque ID added noise and was the string the old approach asked the LLM to memorise.

## Consequences

- LLM hallucination surface is reduced: fabricating an integer out of range is easier to detect and reject than fabricating an opaque string.
- Swapped-ID failures are eliminated: the LLM cannot confuse two product_ids because it never sees or returns them.
- Prompt tokens are slightly reduced (one field removed per candidate line).
- The `product_id` mapping now happens entirely on the code side, which is the correct place for it.
