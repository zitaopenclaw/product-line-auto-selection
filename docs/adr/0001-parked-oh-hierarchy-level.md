# Parked: OH Node Level — Should matching target only leaf nodes?

**Status**: Parked — not in scope for current phase

## Question

The OH xlsx contains ~2,049 active nodes across multiple hierarchy levels (parent nodes and leaf nodes). The current system matches against all active nodes indiscriminately. The question is whether matching to an intermediate/parent node is useful or whether the system should only surface leaf nodes.

## Why it may matter later

Matching to a high-level parent node (e.g., "Cloud Services") is far less actionable for quoting than matching to a leaf node (e.g., "Azure Stack HCI Deployment Service"). If intermediate nodes are included in the candidate pool, scores may be diluted or misleading.

## Deferred because

The current POC and 1000-row run are focused on validating end-to-end pipeline correctness and score distribution. Node-level filtering is a refinement that depends on first understanding actual match quality.
