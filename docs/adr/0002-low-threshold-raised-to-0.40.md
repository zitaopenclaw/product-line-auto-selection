# ADR-0002: Raise Low Confidence Threshold from 0.30 to 0.40

**Status**: Accepted  
**Date**: 2026-06-21

## Context

The system applies three confidence thresholds to LLM rerank scores before keeping a candidate slot:

| Level | Score range |
|---|---|
| High | ≥ 0.85 |
| Medium | 0.60 – 0.85 |
| Low | ≥ threshold (previously 0.30) |
| Drop | < threshold |

After the 1000-row production run, the score distribution of kept slots was analysed:

```
0.30–0.39 : 190 slots (13.7%)
0.40–0.44 :  59 slots  (4.3%)
0.45–0.49 :  75 slots  (5.4%)
0.50–0.59 : 102 slots  (7.4%)
0.60–0.84 : 259 slots (18.7%)
≥ 0.85    : 702 slots (50.6%)
```

Two findings drove the decision:

1. **The < 0.30 bucket is always empty.** The LLM never outputs a score below 0.30, which means the original 0.30 threshold was doing no filtering at all.

2. **The 0.30–0.39 range shows floor-clustering.** 190 slots — 3× the next band (59 slots at 0.40–0.44) — pile up just above 0.30. This shape indicates the LLM is assigning "I have to give something above floor" scores, not genuine relevance signals.

## Decision

Raise `LOW_THRESHOLD` from **0.30 to 0.40**, removing the 190 floor-clustered slots while leaving the smoother 0.40+ distribution intact.

**Impact**: 190 slots dropped (13.7% of 1387 kept slots). Kept slots fall from 1387 to 1197. The High and Medium thresholds (0.85 / 0.60) are unchanged.

## Alternatives Considered

- **0.45**: Drops 249 slots. The additional 59 slots (0.40–0.44) are not clearly artefacts; the cliff at 0.40 is the cleaner cut.
- **0.50**: Drops 324 slots. Too aggressive — removes a meaningful portion of the Low band without clear evidence they are noise.
- **Keep 0.30**: Retains 190 slots that are statistically indistinguishable from LLM minimum behaviour.

## Consequences

- Human reviewers will see fewer Low-level recommendations, reducing noise in the output table.
- Zero-match rate will rise slightly (rows whose only candidates scored 0.30–0.39 will now show no match).
- If future prompt changes cause the LLM to use scores below 0.40 meaningfully, this threshold should be re-evaluated.
