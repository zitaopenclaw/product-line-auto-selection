# Deployment Architecture

## Overview

Production stack: **Sales (Teams) → Copilot Studio → HF Spaces Docker → FastAPI → Python pipeline**

A single HTTPS endpoint exposes the Pre-DER Agent's recommendation logic. No Azure subscription required.

## Architecture

```
┌─────────────┐     HTTP POST + X-API-Key     ┌──────────────────────────────────────┐
│ Copilot     │ ────────────────────────────> │ Hugging Face Spaces (Docker SDK)      │
│ Studio      │                                │                                      │
│ (Teams)     │ <──────────────────────────── │ FastAPI /recommend + /health          │
└─────────────┘       JSON { topk: [...] }    │                                      │
                                              │  startup (lifespan):                  │
                                              │  ├─ load_pn_nodes() → 337 nodes       │
                                              │  ├─ build index (if absent)           │
                                              │  │  ├─ BM25                          │
                                              │  │  ├─ bge-small embeddings          │
                                              │  │  └─ save to data/index/           │
                                              │  └─ init RerankClient                │
                                              │                                      │
                                              │  request -> recall → rerank → top-3  │
                                              └──────────────────────────────────────┘
```

## Components

### 1. Hugging Face Space (Docker SDK)

- **Base image**: `python:3.11-slim`
- **Framework**: FastAPI + uvicorn
- **Visibility**: Private (requires `X-API-Key` header)
- **Hardware**: CPU Basic (2 vCPU / 16 GB RAM) — free tier
- **Auto-sleep**: Free tier spins down after 15 min idle; first request cold-starts (~45s)
- **Persistent storage**: Ephemeral; index rebuilt on cold start
- **Build**: HF auto-builds from git push; pip installs torch + sentence-transformers (~8 min)

### 2. FastAPI Service (`app.py`)

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | None | Health check |
| `/recommend` | POST | `X-API-Key` | Take query string → return top-3 PN tree nodes |

Request body:

```json
{"query": "customer needs laptop management service"}
```

Response:

```json
{
  "topk": [
    {
      "node_key": "L3|L1|Services|Smart Device Support",
      "name": "Smart Device Support",
      "level": "L3",
      "path": ["L1", "Services", "Smart Device Support"],
      "path_str": "L1 > Services > Smart Device Support",
      "pn_count": 42,
      "score": 0.92,
      "level_label": "High"
    }
  ]
}
```

### 3. Index (built at startup)

Built inside the container on first cold start:

| File | Size | Type |
|---|---|---|
| `corpus.json` | ~160 KB | 337 node embed texts |
| `bm25.pkl` | ~185 KB | serialized BM25Okapi |
| `embeddings.npy` | ~500 KB | 337 × 384 float32 matrix |

To pre-build locally (saves ~30s cold start):

```bash
python deploy/build_index.py
```

### 4. Copilot Studio Integration

- **Topic**: Single topic for voice-input → recommendation
- **HTTP Action**: POST to Space URL with `X-API-Key` header
- **Response parsing**: Extract `topk[0..2].name`, `.score`, `.level_label`
- **Display**: Adaptive Card in Teams

## Deployment Steps

### Prerequisites

1. [Hugging Face account](https://huggingface.co) (personal is fine)
2. HF access token with `write` permission ([settings/tokens](https://huggingface.co/settings/tokens))
3. DeepSeek API key (or MiniMax)

### Push Code to HF Space

```bash
# Add remote and push (orphan branch to avoid history bloat)
git remote add hf https://huggingface.co/spaces/<user>/<space-name>
git checkout --orphan deploy/hf
git add -A
git commit -m "deploy"
git push hf deploy/hf:main --force
git checkout main
```

### Configure Secrets

In Space Settings → Repository Secrets, add:

| Key | Value |
|---|---|
| `DEEPSEEK_API_KEY` | your DeepSeek key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | `deepseek-chat` |
| `APP_API_KEY` | your custom API key (used in `X-API-Key` header) |

### Verify

```bash
curl -X POST https://<user>-<space-name>.hf.space/recommend \
  -H "X-API-Key: <APP_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query": "laptop management service"}'
```

## Known Issues

- **Cold start**: First request after idle period takes ~45s (pip install pip + index build). Subsequent requests are fast (~3-5s).
- **HF Spaces free tier**: Space sleeps after 15 min idle. Upgrade to CPU Upgrade ($0.03/hr) for always-on.
- **File size limits**: HF rejects git files > 10 MiB and binary files (`.pkl`, `.npy`, `.png`). Index is built at startup to avoid this.
- **Page file (Windows local)**: `python deploy/build_index.py` may fail with `OSError 1455` on Windows if page file is too small. Reduce `batch_size` in the script.

## Scale Limits

| Metric | Limit | Mitigation |
|---|---|---|
| Concurrent requests | ~10 | Free tier single-container |
| Max request duration | 300s | HF Spaces default |
| Storage | 50 GB | Plenty for this workload |
| Bandwidth | Free tier includes 100 GB/mo | POC scale fine |

## Future Options

- **Production**: Move to Modal or Render paid for higher reliability and always-on
- **Multi-topic**: Add `/recommend_der` endpoint for DER Refinement Agent; add new topic in Copilot Studio
- **API key rotation**: Rotate `APP_API_KEY` in HF Secrets without redeploy
