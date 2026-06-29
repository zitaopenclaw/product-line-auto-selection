# Product_LIne_Entry_Agent — Copilot Studio Topic Configuration Spec

> Version: 0.2 (2026-06-29)  
> Owner: @tangzhi2  
> Status: active | Last issue resolved: DER HTTP 422 (scope null) on 2026-06-29

## §0 Metadata

| Key | Value |
|---|---|
| Bot ID | `90bf4480-f271-f111-ab0f-6045bd56018e` |
| Environment ID | `0dd9076f-7fbf-e21a-b965-e436f2ec8083` |
| Dataverse URL (inferred) | `https://rwa-iva-uat.crm.dynamics.com` |
| HF Space base URL | `https://zitangopenclaw-product-line-auto-selection.hf.space` |
| API auth header | `X-API-Key: product-line-entry-agent` |
| Browser profile dir | `C:\Users\tangzhi2\AppData\Local\Temp\chrome-cdp-pla` |
| Chrome CDP port | 9222 |
| Chrome flags | `--remote-debugging-port=9222 --remote-allow-origins=* --no-sandbox --disable-gpu` |

### DER Topic
- Topic ID: `085cab51-6060-46cd-97e1-569120d644af`
- State: ~95% configured, Save done with 2 non-blocking warnings (isRequired fields without errorMessage)

### Pre-DER Topic
- Topic ID: TBD (newly created blank, ID captured during run)
- State: blank canvas with name "OH Recommendation (Pre-DER)", Trigger default

### Acceptance Checklist
- [ ] DER topic: Save button disabled (no pending changes)
- [ ] Pre-DER topic: Save button disabled (no pending changes)
- [ ] Both topics: Topic checker = 0 blocking errors
- [ ] Test pane: DER 4 cases pass (incl. 1 negative)
- [ ] Test pane: Pre-DER 3 cases pass
- [ ] Publish successful
- [ ] Code fix verified: `app.py` coerces `scope/service_model` from `null` to `""` before request model use
- [ ] Optional cleanup reviewed: RAW `/recommend_der` body debug log in `app.py`

---

## §1 Design Anchors

Sources of truth for this spec:

| Fact | Source | Effect on spec |
|---|---|---|
| `/recommend_der` BG required, validated server-side (400 if invalid) | `app.py:207-209` | DER Card `business_group` isRequired=true |
| `/recommend` BG optional (soft signal), default empty | `app.py:130-132` | Pre-DER omits BG in body |
| Returns are PN tree L2/L3/L4 nodes (not flat OH products) | `app.py`, `CONTEXT.md` "Known gap" | Display shows `path_str` and `level` |
| Service Model: 6 fixed values | `field_rules.py:70-77` | DER Card ChoiceSet 6 options |
| Scope: 4 trigger substrings | `field_rules.py:80-85` | DER Card ChoiceSet 4 options |
| Confidence: High ≥ 0.85 / Medium 0.60-0.85 / Low 0.40-0.60 / drop < 0.40 | `confidence.py`, ADR-0002 | `level_label` returned in API response |
| Endpoint timeout: backend 50s / Copilot HTTP Request 60s | `app.py:37` | HTTP Request timeout = 60000 ms |
| Field IDs in Adaptive Card map to `Topic.<id>` PowerFx variables | Copilot Studio convention | Body formula references `Topic.<id>` directly |

### Discrepancies from earlier conversation
- **Pre-DER early plan** said "simple Adaptive Card (BG + free-form text)" → **Final**: free-text Question only, no BG, no Adaptive Card.
- **DER output naming**: API returns PN tree nodes, not OH line items. Display via `path_str` + `level`.

---

## §2 DER Topic Configuration

### 2.1 Trigger
- Type: **On Recognized Intent** (default)
- Description (for agent intent matching): "Recommends top-3 PN tree L2/L3/L4 nodes for a DER opportunity based on Business Group, Service Model, ARS, AI, Scope, and free-text business problem."

### 2.2 Node 1: Question + Adaptive Card

**Question prompt** (top of card): "Fill in the DER details to get top-3 PN tree node recommendations."

**Card JSON** (paste into Monaco editor, exact form):

```json
{
  "type": "AdaptiveCard",
  "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
  "version": "1.5",
  "body": [
    {
      "type": "TextBlock",
      "text": "DER Recommendation",
      "weight": "Bolder",
      "size": "Medium"
    },
    {
      "type": "Input.ChoiceSet",
      "id": "business_group",
      "label": "Business Group (required)",
      "isRequired": true,
      "errorMessage": "Required",
      "choices": [
        { "title": "IDG", "value": "IDG" },
        { "title": "DCG", "value": "DCG" },
        { "title": "SSG", "value": "SSG" }
      ]
    },
    {
      "type": "Input.ChoiceSet",
      "id": "service_model",
      "label": "Service Model",
      "choices": [
        { "title": "DaaS", "value": "DAAS" },
        { "title": "IaaS", "value": "IAAS" },
        { "title": "ISG Lease", "value": "ISG LEASE" },
        { "title": "Professional & Managed Services", "value": "PROF & MGD SERVICES" },
        { "title": "SaaS", "value": "SAAS" },
        { "title": "SI / Vertical", "value": "SI OR VERTICAL" }
      ]
    },
    {
      "type": "Input.Toggle",
      "id": "ars_flag",
      "title": "Asset Recovery Services (ARS) opportunity",
      "value": "false",
      "valueOn": "Yes",
      "valueOff": "No"
    },
    {
      "type": "Input.Toggle",
      "id": "ai_flag",
      "title": "Involves Emerging Tech / AI",
      "value": "false",
      "valueOn": "Yes",
      "valueOff": "No"
    },
    {
      "type": "Input.ChoiceSet",
      "id": "scope",
      "label": "Scope of opportunity",
      "choices": [
        { "title": "Standalone Asset Recovery Services", "value": "Standalone Asset Recovery Services Scope" },
        { "title": "Managed Services / TruScale", "value": "Managed Services or TruScale" },
        { "title": "Hardware Lease with Standard Services", "value": "Hardware Lease with Standard Services" },
        { "title": "Standalone Professional Services", "value": "Standalone Professional Services" }
      ]
    },
    {
      "type": "Input.Text",
      "id": "query",
      "label": "Describe the business problem or challenge (required)",
      "isRequired": true,
      "errorMessage": "Required",
      "isMultiline": true
    }
  ],
  "actions": [
    { "type": "Action.Submit", "title": "Get recommendations" }
  ]
}
```

### 2.3 Node 2: HTTP Request

| Field | Value |
|---|---|
| Display name | "Call /recommend_der" |
| Method | POST |
| URL | `https://zitangopenclaw-product-line-auto-selection.hf.space/recommend_der` |
| Header 1 | `X-API-Key` = `product-line-entry-agent` |
| Header 2 | `Content-Type` = `application/json` |
| Body (PowerFx) | `{query: Topic.query, business_group: Topic.business_group, service_model: Topic.service_model, ars_flag: Topic.ars_flag, ai_flag: Topic.ai_flag, scope: Topic.scope}` |
| Timeout (ms) | 60000 |
| Response handling | `Save response as: DerApiResponse` (record), Response data type: `topk` (table of records) |

Null-handling note (important): when optional DER fields are empty, use empty string `""` semantics for `scope`/`service_model`; avoid explicit JSON `null`. Current backend has defensive coercion (`null -> ""`) to prevent HTTP 422 regressions.

### 2.4 Node 3: Message (Send a Message)

| Field | Value |
|---|---|
| Type | Send a message |
| Modality | Text |
| Message (PowerFx) | `Concat(Topic.DerApiResponse.topk, name & " | " & path_str & " [" & level_label & ", score " & Text(score, "0.00") & "]" & Char(10))` |

---

## §3 Pre-DER Topic Configuration

### 3.1 Trigger
- Type: **On Recognized Intent** (default)
- Description: "Takes free-form sales voice input (raw transcript OK) and returns top-3 PN tree L2/L3/L4 nodes."

### 3.2 Node 1: Question (free text)

| Field | Value |
|---|---|
| Display name | "Capture customer need" |
| Text to display | "Describe the customer's need in a sentence or two. I'll match it against our PN tree." |
| Identify | User's entire response |
| Output | Variable `query` (string), captured via "Save user response as" |

### 3.3 Node 2: HTTP Request

| Field | Value |
|---|---|
| Display name | "Call /recommend" |
| Method | POST |
| URL | `https://zitangopenclaw-product-line-auto-selection.hf.space/recommend` |
| Header 1 | `X-API-Key` = `product-line-entry-agent` |
| Header 2 | `Content-Type` = `application/json` |
| Body (PowerFx) | `{query: Topic.query, business_group: ""}` |
| Timeout (ms) | 60000 |
| Response handling | `Save response as: PreDerApiResponse` (record), Response data type: `topk` (table of records) |

### 3.4 Node 3: Message (Send a Message)

| Field | Value |
|---|---|
| Type | Send a message |
| Modality | Text |
| Message (PowerFx) | `Concat(Topic.PreDerApiResponse.topk, name & " | " & path_str & " [" & level_label & ", score " & Text(score, "0.00") & "]" & Char(10))` |

---

## §4 Playwright Automation Strategy

### §4.1 Known gotchas (documented to prevent re-discovery)

| Operation | Gotcha | Workaround |
|---|---|---|
| Set Monaco editor JSON | `innerHTML` / `el.value = ...` alone doesn't propagate to React state | `ta.value = json; ta.dispatchEvent(new Event('input', {bubbles:true})); ta.dispatchEvent(new Event('change', {bubbles:true}))` |
| Modal "Save" button | mouse click / `dispatchEvent('click')` / mouse events all silently fail | `focus() → Enter keyDown + keyUp` |
| Find "Edit headers and body" button | not in `button[aria-label=...]` | locate `label` with text "Headers and body" → its sibling Edit button |
| Topics list direct navigation | `/topics` URL renders blank | trigger from left Topics tab in canvas, or refresh page |
| Question node Identify dropdown | option click sometimes needs 2 attempts | click once to expand, click again to select |
| Topic Save with 2 isRequired warnings | non-blocking, dialog appears | accept via "Save" text button (NOT close X icon) |
| Chrome auto-closing | can't detach Python process | `subprocess.Popen + DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP` |
| CDP connection hang | websocket lock-up after long sessions | respawn Chrome, reconnect `/json/version` |

### §4.2 Primitives library (`scripts/_copilot_primitives.py`)

Each primitive is contract-tested and returns `(ok: bool, info: dict)`.

- `navigate_to_topic(c, topic_id)` — direct URL navigation + wait for canvas
- `open_canvas(c)` — ensure canvas is loaded
- `scroll_to_node(c, label)` — scroll canvas until node with header text is in viewport
- `click_node(c, label)` — click a node's header to open its editor
- `add_node_after(c, after_node, kind)` — `kind` ∈ {Question, HTTP request, Send a message}; click "+" after `after_node`, select menuitem
- `fill_monaco(c, selector, json_text)` — paste JSON into Monaco editor textarea
- `click_modal_save_via_enter(c)` — known gotcha workaround
- `verify_save_clean(c)` — Save button disabled = no pending changes
- `save_topic(c, accept_warnings=True)` — full save cycle (click Save, accept errors if any)
- `set_question_identify(c, label)` — switch Question node Identify dropdown
- `set_question_output_variable(c, name)` — set "Save user response as"
- `set_http_request_url(c, url)` — set HTTP Request URL field
- `set_http_request_method(c, method)` — POST / GET / etc.
- `add_http_header(c, name, value)` — add a header row
- `edit_http_headers_body(c)` — open the Headers and body edit modal
- `set_http_body(c, body_text)` — paste PowerFx body
- `screenshot(c, name)` — save to `.playwright-mcp/run/<name>.png`

### §4.3 Execution runbooks

DER topic: 12 steps (see §2 node order)
Pre-DER topic: 8 steps (see §3 node order)

Each step = (action, verify, screenshot, checkpoint)

---

## §5 Test Plan

### DER Test Cases

| # | BG | ServiceModel | ARS | AI | Scope | Query | Expected |
|---|---|---|---|---|---|---|---|
| 1 | IDG | DAAS | Yes | No | (default) | "laptop management for 500 employees" | top-1 high-confidence DaaS node |
| 2 | DCG | IAAS | No | Yes | (default) | "GPU cluster for AI workloads" | top-1 high-confidence infra node |
| 3 | SSG | PROF & MGD SERVICES | No | No | Standalone Professional Services | "advisory engagement for cloud migration" | top-1 hits consulting |
| 4 | (leave blank) | - | - | - | - | "test" | Card rejects (Required error on BG and query) |

### Pre-DER Test Cases

| # | Query | Expected |
|---|---|---|
| 1 | "Customer needs managed PC deployment for 500 employees" | high-confidence top-1 |
| 2 | "Acme Manufacturing wants 1200 laptops with deployment services" | high-confidence top-1 |
| 3 | "AI workstation cluster for ML training, GPU heavy" | top-1 hits AI/ML node |

---

## §6 Checkpoint & Resume Protocol

File: `pac-setup/copilot-progress.json`

```json
{
  "der": {
    "canvas_loaded": true,
    "card_done": true,
    "http_done": true,
    "message_done": true,
    "saved": true
  },
  "pre_der": {
    "canvas_loaded": false,
    "renamed": false,
    "question_done": false,
    "http_done": false,
    "message_done": false,
    "saved": false
  },
  "last_updated": "2026-06-28T22:00:00Z"
}
```

Each step writes a checkpoint on success. Re-running the script reads checkpoints and skips completed steps.

---

## §7 Pre-Publish Self-Check

```
[ ] Topic checker: 0 errors for both topics
[ ] Save button disabled for both topics (clean state)
[ ] Test pane: all DER cases pass
[ ] Test pane: all Pre-DER cases pass
[ ] Known acceptable warnings: 2 isRequired warnings on DER (non-blocking)
[ ] Publish button enabled → click
[ ] Verify topic status = "Published"
```

---

## §8 Risks and Fallbacks

| Risk | Fallback |
|---|---|
| Microsoft changes UI; selectors break | Self-test primitives; failures → manual troubleshooting |
| Monaco JSON contains `&` gets PowerShell-escaped | Use raw JSON string, avoid PowerShell interpolation |
| HF Space cold-start 45s on first request | Inform user first call is slow, requires patience |
| Topic checker reports new errors | Review spec for drift; adjust JSON; retry |
| `Pac auth create` blocked by tenant CA policy (confirmed) | Fallback to Playwright/CDP (current path) |