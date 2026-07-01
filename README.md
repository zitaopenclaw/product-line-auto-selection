---
title: Product Line Auto Selection
emoji: 🚀
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Product Line Auto Selection

FastAPI service that recommends Lenovo PN-tree service nodes (and, for IDG/ISG, matching
hardware catalog nodes) for a sales opportunity. Called by two Microsoft Copilot Studio
topics in Teams:

- `POST /recommend` — Pre-DER topic: free-form voice/text description → top-3 PN tree nodes
  (+ HW catalog nodes for IDG/ISG).
- `POST /recommend_der` — DER Input topic: structured DER form fields + description → same
  dual-output recommendation.
- `POST /feedback` — records which recommendation the seller picked, used to reweight future
  rankings (A/B tested).
- `GET /health` — liveness check.

All endpoints require an `X-API-Key` header. See `CONTEXT.md` for the domain glossary and
`docs/deployment.md` for the deployment architecture.
