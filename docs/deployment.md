# Deployment Architecture

## Overview

Production stack: **Sales (Teams) → Copilot Studio → HF Spaces Docker → FastAPI → Python pipeline**

Two Copilot Studio topics expose the two agents:
- **Pre-DER topic** → calls `/recommend` → Pre-DER Agent (voice input → PN tree L2/L3/L4 nodes)
- **DER Input topic** → calls `/recommend_der` → DER Input AI Agent (structured DER form → PN tree L2/L3/L4 nodes)

No Azure subscription required for hosting (HF Spaces runs independently); Copilot Studio itself requires a Power Platform / Microsoft 365 license.

## Architecture

```
┌─────────────────────────┐   HTTP POST + X-API-Key   ┌──────────────────────────────────────┐
│ Copilot Studio (Teams)  │ ────────────────────────> │ Hugging Face Spaces (Docker SDK)      │
│                         │                            │                                      │
│ Topic 1: Pre-DER        │ ──→ /recommend             │ FastAPI /recommend                    │
│ Topic 2: DER Input      │ ──→ /recommend_der         │      + /recommend_der + /health       │
│                         │ <──────────────────────── │                                      │
└─────────────────────────┘   JSON { topk: [...] }    │                                      │
                                              │  startup (lifespan):                  │
                                              │  ├─ load_pn_nodes() → 337 nodes       │
                                              │  └─ init RerankClient                │
                                              │                                      │
                                              │  first request (lazy):               │
                                              │  └─ _ensure_index()                  │
                                              │     ├─ load pre-built index from      │
                                              │     │  data/index/ (baked in image)  │
                                              │     └─ or build if absent (~30s)     │
                                              │                                      │
                                              │  request -> recall → rerank → top-3  │
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
| `/recommend` | POST | `X-API-Key` | Pre-DER: voice query → top-3 PN tree nodes (L2/L3/L4) |
| `/recommend_der` | POST | `X-API-Key` | DER Input: structured DER fields → top-3 PN tree nodes (L2/L3/L4) |

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

Response (real example from test run):

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
  ]
}
```

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
- **File size limits**: HF rejects git files > 10 MiB. Raw `.xlsx` and index binaries are excluded from git (`.gitignore` covers `data/raw/*.xlsx` and `data/index/`); they never touch HF git.
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
- **Feedback loop**: Capture seller accepts/rejects in Copilot Studio → store in Dataverse → fine-tune recall or rerank weights
- **API key rotation**: Rotate `APP_API_KEY` in HF Secrets without redeploy
