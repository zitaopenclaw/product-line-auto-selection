# Deployment Architecture

## Overview

Production stack: **Sales (Teams) → Copilot Studio → HF Spaces Docker → FastAPI → Python pipeline**

A single HTTPS endpoint exposes the Pre-DER Agent's recommendation logic. No Azure subscription required for hosting (HF Spaces runs independently); Copilot Studio itself requires a Power Platform / Microsoft 365 license.

## Architecture

```
┌─────────────┐     HTTP POST + X-API-Key     ┌──────────────────────────────────────┐
│ Copilot     │ ────────────────────────────> │ Hugging Face Spaces (Docker SDK)      │
│ Studio      │                                │                                      │
│ (Teams)     │ <──────────────────────────── │ FastAPI /recommend + /health          │
└─────────────┘       JSON { topk: [...] }    │                                      │
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
| `/recommend` | POST | `X-API-Key` | Take query string → return top-3 PN tree nodes |

Request body (`business_group` is optional but improves relevance as a soft signal):

```json
{
  "query": "customer needs managed PC deployment service for 500 employees",
  "business_group": "IDG"
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

- **Topic**: Single topic for voice-input → recommendation
- **HTTP Action**: POST to Space URL with `X-API-Key` header
  - Header name: `X-API-Key`
  - Header value: same as `APP_API_KEY` secret
- **Timeout**: Set HTTP Action timeout to ≥ 60s to tolerate idle cold-start (~45s)
- **Response parsing**: Extract `topk[0..2].name`, `.score`, `.level_label`, `.path_str`
- **Empty result handling**: If `topk` is empty (no candidates above threshold), show a fallback message ("No matching offering found — please describe the customer need in more detail")
- **Display**: Adaptive Card in Teams showing top-3 cards with name + path + confidence level

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
- **Multi-topic**: Add `/recommend_der` endpoint for DER Refinement Agent; add new topic in Copilot Studio
- **API key rotation**: Rotate `APP_API_KEY` in HF Secrets without redeploy
