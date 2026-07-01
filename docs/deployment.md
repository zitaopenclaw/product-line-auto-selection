# Deployment Architecture

## Overview

Production stack: **Sales (Teams) → Copilot Studio → HF Spaces Docker → FastAPI → Python pipeline**

Two Copilot Studio topics expose the two agents; a third endpoint captures feedback for both:
- **Pre-DER topic** → calls `/recommend` → Pre-DER Agent (voice input → PN tree L2/L3/L4 nodes, + HW catalog nodes for IDG/ISG)
- **DER Input topic** → calls `/recommend_der` → DER Input AI Agent (structured DER form → PN tree L2/L3/L4 nodes, + HW catalog nodes for IDG/ISG), then calls `/feedback` after the seller picks (or rejects) a recommendation

No Azure subscription required for hosting (HF Spaces runs independently); Copilot Studio itself requires a Power Platform / Microsoft 365 license.

## Architecture

```
┌─────────────────────────┐   HTTP POST + X-API-Key   ┌──────────────────────────────────────┐
│ Copilot Studio (Teams)  │ ────────────────────────> │ Hugging Face Spaces (Docker SDK)      │
│                         │                            │                                      │
│ Topic 1: Pre-DER        │ ──→ /recommend             │ FastAPI /recommend                    │
│ Topic 2: DER Input      │ ──→ /recommend_der         │      + /recommend_der                 │
│                         │ ──→ /feedback              │      + /feedback + /health            │
│                         │ <──────────────────────── │                                      │
└─────────────────────────┘  JSON { service_        │                                      │
                              recommendations,       │  startup (lifespan):                  │
                              hw_recommendations }   │  ├─ load_pn_nodes() → 337 nodes       │
                                                      │  ├─ init RerankClient (service)       │
                                                      │  └─ init HW RerankClient + hw_nodes   │
                                                      │     (IDG/ISG, if rerank_hw.txt exists)│
                                                      │                                      │
                                              │  first request per pipeline (lazy):   │
                                              │  ├─ _ensure_index() -- service PN tree │
                                              │  │  ├─ load pre-built index from      │
                                              │  │  │  data/index/ (baked in image)  │
                                              │  │  └─ or build if absent (~30s)     │
                                              │  └─ _ensure_hw_index(bg) -- IDG/ISG   │
                                              │     HW catalog, built lazily per BG   │
                                              │                                      │
                                              │  request -> recall → field cascade → │
                                              │  rerank → feedback-signal reweight → │
                                              │  diversity filter → top-3            │
                                              │                                      │
                                              │  /feedback -> append output/feedback/│
                                              │  feedback.jsonl (A/B group assigned)  │
                                              └──────────────────────────────────────┘
```

## Components

### 1. Hugging Face Space (Docker SDK)

- **Base image**: `python:3.11`
- **Framework**: FastAPI + uvicorn
- **Visibility**: Page UI requires HF login when set to Private; the `*.hf.space` API endpoint is publicly reachable by anyone with the URL — `APP_API_KEY` is the sole API access control
- **Hardware**: CPU Basic (2 vCPU / 16 GB RAM) — free tier
- **Auto-sleep**: Free tier spins down after 15 min idle; idle restart cold-starts in ~45s (model load + index check)
- **Persistent storage**: Ephemeral; index is pre-baked in the Docker image (see Dockerfile `RUN python deploy/build_index.py`)
- **Build**: HF auto-builds from git push; pip installs torch + sentence-transformers + pre-builds index (~10 min total)

### 2. FastAPI Service (`app.py`)

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | None | Health check |
| `/recommend` | POST | `X-API-Key` | Pre-DER: voice query → top-3 PN tree nodes (L2/L3/L4), + top-3 HW catalog nodes for IDG/ISG |
| `/recommend_der` | POST | `X-API-Key` | DER Input: structured DER fields → top-3 PN tree nodes (L2/L3/L4), + top-3 HW catalog nodes for IDG/ISG |
| `/feedback` | POST | `X-API-Key` | Records which of the top-3 the seller picked (or none); assigns an A/B group; appends to `output/feedback/feedback.jsonl` |

**`/recommend` request** (`business_group` is optional soft signal):

```json
{
  "query": "customer needs managed PC deployment service for 500 employees",
  "business_group": "IDG"
}
```

**`/recommend_der` request** (`business_group` required hard filter; remaining fields optional but improve field-cascade results):

```json
{
  "query": "DaaS renewal with asset recovery for 800 seats",
  "business_group": "IDG",
  "service_model": "DAAS",
  "ars_flag": "Yes",
  "ai_flag": "No",
  "scope": "Standalone Asset Recovery Services Scope",
  "existing_expansion": true
}
```

Response (dual-output shape; `hw_recommendations` is present only when a canonical IDG/ISG
business group is detected — absent for SSG. `topk` mirrors `service_recommendations` for
backward compatibility):

```json
{
  "topk": [
    {
      "node_key": "L3|Global Product Services|Deployment Services|Hardware Only Deployment",
      "name": "Hardware Only Deployment",
      "level": "L3",
      "path": ["Global Product Services", "Deployment Services", "Hardware Only Deployment"],
      "path_str": "Global Product Services > Deployment Services > Hardware Only Deployment",
      "pn_count": 12,
      "score": 0.92,
      "level_label": "High"
    }
  ],
  "service_recommendations": [ "... same shape as topk ..." ],
  "hw_recommendations": [ "... same shape, from the IDG/ISG HW catalog tree ..." ]
}
```

**`/feedback` request**:

```json
{
  "opportunity_id": "unknown",
  "bg": "IDG",
  "der_description": "DaaS renewal with asset recovery for 800 seats",
  "scope": "Standalone Asset Recovery Services Scope",
  "service_model": "DAAS",
  "ars_flag": true,
  "ai_flag": false,
  "candidates_shown": [
    {"rank": 1, "node_key": "L3|...", "score": 0.92, "confidence": "High"}
  ],
  "user_selected_rank": 1,
  "is_negative": false,
  "negative_hint": null
}
```

Response: `{"status": "ok", "feedback_id": "<uuid>", "ab_group": "A" | "B"}`.

### 3. Index (pre-built in Docker image)

The `Dockerfile` runs `python deploy/build_index.py` at image build time. The index is baked in — no rebuild cost on cold start.

| File | Size | Type |
|---|---|---|
| `data/index/corpus.json` | ~160 KB | 337 node embed texts |
| `data/index/bm25.pkl` | ~185 KB | serialized BM25Okapi |
| `data/index/embeddings.npy` | ~500 KB | 337 × 384 float32 matrix |

If `data/index/` is somehow absent at runtime, `_ensure_index()` rebuilds it lazily on the first request (~30s penalty for that request only).

### 4. Copilot Studio Integration

Two topics, same endpoint base URL, same auth header.

#### Topic 1 — Pre-DER (voice input → PN tree node)
- **Trigger**: Seller speaks a free-form description of customer need
- **HTTP Action**: POST `/recommend` with `X-API-Key` header
- **Request fields**: `query` (required), `business_group` (optional, soft signal)
- **Response parsing**: Extract `topk[0..2].name`, `.score`, `.level_label`, `.path_str`
- **Empty result handling**: If `topk` is empty, prompt seller: "No matching offering found — please describe the customer need in more detail"
- **Display**: Adaptive Card in Teams showing top-3 nodes with name + path + confidence level

#### Topic 2 — DER Input (structured DER form → PN tree node)
- **Trigger**: Seller requests AI recommendation during or after DER form completion
- **Input method**: Copilot presents an **Adaptive Card form** in Teams; seller re-enters the key DER fields directly in the conversation (fields are not read from D365 automatically)
- **Adaptive Card fields**:
  | Field | Values |
  |---|---|
  | Business problem description | Free text (`query`) |
  | Business Group | IDG / DCG / SSG |
  | Service Model | DAAS / IAAS / ISG Lease / PROF & MGD SERVICES / SAAS / SI or Vertical |
  | ARS flag | Yes / No |
  | AI/Emerging Tech flag | Yes / No |
  | Scope | Full D365 scope string (dropdown or free text) |
  | Existing expansion | Yes / No / Not specified |
- **HTTP Action**: POST `/recommend_der` with `X-API-Key` header; Adaptive Card values map directly to request fields
- **Response parsing**: Same structure as `/recommend` — `topk[0..2].name`, `.score`, `.level_label`, `.path_str`, `.level`, `.path`
- **Comparison surface**: Both topics return the same L2/L3/L4 format; results can be compared side-by-side at the reporting layer

#### Shared settings
- **Timeout**: Set HTTP Action timeout to ≥ 60s to tolerate idle cold-start (~45s)
- **Auth header**: `X-API-Key: <APP_API_KEY secret>`

## Deployment Steps

### Prerequisites

1. [Hugging Face account](https://huggingface.co) (personal is fine)
2. HF access token with `write` permission ([settings/tokens](https://huggingface.co/settings/tokens))
3. MiniMax API key (primary LLM); DeepSeek API key (optional fallback)

### Push Code to HF Space

```bash
# Add remote (one-time setup)
git remote add hf https://huggingface.co/spaces/<user>/<space-name>

# Push current main branch to HF
# Note: --force overwrites whatever is on HF main; safe for first push or re-deploy
git push hf main:main --force
```

> **Note on large files**: `data/raw/*.xlsx` and `data/index/` are excluded via `.gitignore` and `.dockerignore`. HF will build the Docker image from source — the index is pre-built inside the image via `RUN python deploy/build_index.py`.

### Configure Secrets

In Space Settings → Repository Secrets, add:

| Key | Required | Value |
|---|---|---|
| `MINIMAX_API_KEY` | ✅ required | your MiniMax key (primary LLM) |
| `MINIMAX_BASE_URL` | ✅ required | `https://api.minimaxi.com/v1` |
| `MINIMAX_MODEL` | ✅ required | `MiniMax-M3` |
| `DEEPSEEK_API_KEY` | optional | your DeepSeek key (fallback LLM) |
| `DEEPSEEK_BASE_URL` | optional | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | optional | `deepseek-chat` |
| `APP_API_KEY` | ✅ required | your custom API key (used in `X-API-Key` header) |

### Verify

```powershell
# PowerShell
Invoke-RestMethod -Uri "https://<user>-<space-name>.hf.space/recommend" `
  -Method Post `
  -Headers @{"X-API-Key"="<APP_API_KEY>"; "Content-Type"="application/json"} `
  -Body '{"query": "laptop management service", "business_group": "IDG"}'
```

## Known Issues

- **Cold start (idle restart)**: After 15 min idle, HF restarts the container. Startup takes ~45s (model load; index is pre-baked so no rebuild). The *first request* after restart will be slow.
- **Fresh deploy build time**: ~10 min (pip install torch + sentence-transformers + index pre-build via `RUN python deploy/build_index.py`).
- **HF Spaces free tier**: Space sleeps after 15 min idle. Upgrade to CPU Upgrade ($0.03/hr) for always-on.
- **Feedback data is not persistent**: `output/feedback/feedback.jsonl` lives on the Space's ephemeral filesystem — it is wiped on every container restart/redeploy (see "Persistent storage: Ephemeral" above). Aggregate/export it periodically if feedback history needs to survive a restart.
- **File size limits**: HF rejects any pushed commit whose history contains a file > 10 MiB, even if that file isn't in the current tree — the pre-receive hook scans the full history being pushed, not just the diff. If `main`'s git history ever picks up a large blob (e.g. from merging in an old/unrelated branch), pushing straight `main` to the `hf` remote will be rejected; push a branch with clean lineage (no large blob in its ancestry) to `hf:main` instead. Raw `.xlsx` and index binaries are excluded from git going forward (`.gitignore` covers `data/raw/*` and `data/index/`).
- **Page file (Windows local)**: `python deploy/build_index.py` may fail with `OSError 1455` on Windows if page file is too small. Reduce `batch_size` in the script.

## Scale Limits

| Metric | Limit | Mitigation |
|---|---|---|
| Concurrent requests | ~10 | Free tier single-container |
| Max request duration | 300s | HF Spaces default |
| Storage | 50 GB | Plenty for this workload |
| Bandwidth | Free tier includes 100 GB/mo | POC scale fine |

## Future Options

- **Production**: Move to Azure Container Apps for tighter integration with Copilot Studio / Teams via Managed Identity (no static API key needed); or Modal/Render for simpler always-on hosting
- **API key rotation**: Rotate `APP_API_KEY` in HF Secrets without redeploy

> Note: the feedback loop (seller accepts/rejects → reweighted rankings) that used to be listed
> here as a future option is now implemented — see the `/feedback` endpoint above and
> `src/feedback_signal.py` / `src/feedback_aggregator.py`. It currently writes to a JSONL file
> on the (ephemeral) HF Space filesystem rather than Dataverse — persisting it externally
> (Dataverse or similar) so feedback survives a Space restart is a natural next step.
