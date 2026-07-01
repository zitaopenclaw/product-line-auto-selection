# Product_LIne_Entry_Agent — Copilot Studio Topic Configuration Spec

> Version: 0.4 (2026-07-01)
> Owner: @tangzhi2
> Status: active | Last change: wired up hw_recommendations display (2026-07-01) — was computed by backend but silently dropped by Copilot Studio responseSchema/message since v0.3

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
- State: feedback loop nodes (v0.3) + hw_recommendations display (v0.4) added; all bot-facing strings in English

### Pre-DER Topic
- Topic ID: TBD (newly created blank, ID captured during run)
- State: blank canvas with name "OH Recommendation (Pre-DER)", Trigger default

### Acceptance Checklist
- [ ] DER topic: Save button disabled (no pending changes)
- [ ] Pre-DER topic: Save button disabled (no pending changes)
- [ ] Both topics: Topic checker = 0 blocking errors
- [ ] Test pane: DER 4 recommendation cases pass
- [ ] Test pane: DER feedback 4 cases pass (see §5)
- [ ] Test pane: Pre-DER 3 cases pass
- [ ] Publish successful
- [ ] Code fix verified: `app.py` coerces `scope/service_model` from `null` to `""` before request model use
- [ ] Feedback verified: `output/feedback/feedback.jsonl` receives entries after test pane interaction

---

## §1 Design Anchors

Sources of truth for this spec:

| Fact | Source | Effect on spec |
|---|---|---|
| `/recommend_der` BG required, validated server-side (400 if invalid) | `app.py` | DER Card `business_group` isRequired=true |
| `/recommend` BG optional (soft signal), default empty | `app.py` | Pre-DER omits BG in body |
| Returns are PN tree L2/L3/L4 nodes (not flat OH products) | `app.py`, CLAUDE.md | Display shows `path_str` and `level_label` |
| `node_key` required in `/feedback` `candidates_shown` | `src/feedback_store.py` | responseSchema of `/recommend_der` must declare `node_key: String` |
| Service Model: 6 fixed values | `src/field_rules.py` | DER Card ChoiceSet 6 options |
| Scope: 4 trigger substrings | `src/field_rules.py` | DER Card ChoiceSet 4 options |
| Confidence: High ≥ 0.85 / Medium 0.60-0.85 / Low 0.40-0.60 / drop < 0.40 | `src/confidence.py` | `level_label` returned in API response |
| Endpoint timeout: backend 50s / Copilot HTTP Request 60s | `app.py` | HTTP Request timeout = 60000 ms |
| Feedback endpoint timeout: 10s | `app.py` | `/feedback` HTTP Request timeout = 10000 ms |
| Feedback errors must not break main flow | design decision | Both `/feedback` HTTP Requests use `ContinueOnErrorBehavior` |
| A/B split: 90% B (feedback-weighted) / 10% A (control) | `app.py:_AB_B_RATIO` | Assigned server-side; `ab_group` returned in `/feedback` response |
| Feedback cold-start guard: N≥5 samples before signal applied | `src/feedback_aggregator.py:MIN_SAMPLES` | Small volume → no effect on rankings until threshold met |

### Discrepancies from earlier versions
- v0.2: DER topic had 3 nodes (Question card → HTTP → Message). v0.3 adds 4 feedback nodes inside `elseActions`.
- v0.2: responseSchema for `/recommend_der` missing `node_key`. Fixed in v0.3.
- v0.3: responseSchema and display message never declared `hw_recommendations` (IDG/ISG HW catalog output). Backend computed it correctly (`app.py`, verified in `tests/test_api.py::test_recommend_der_hw_pipeline_included_for_idg`), but Copilot Studio's HTTP Request node discarded the field entirely since it wasn't in `responseSchema` — this happened for **every** BG, not just SSG/DCG (BG-dependence was a red herring). Fixed in v0.4: added `hw_recommendations` to `responseSchema` and a new HW display node (4-A-2).
- **Pre-DER early plan** said "simple Adaptive Card (BG + free-form text)" → **Final**: free-text Question only, no BG, no Adaptive Card.

---

## §2 DER Topic — Full YAML (Code Editor, drop-in replacement)

> Paste this entire block into the DER topic's Code Editor (top-right `</>` button → select all → replace).

```yaml
kind: AdaptiveDialog
modelDescription: "Match a DER opportunity to an OH product recommendation. Use when the user says: match DER, find OH product for DER, DER recommendation, I have a DER, recommend product for DER form. This topic collects DER form details and returns the top-3 matching OH products."
beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent:
    triggerQueries:
      - DER recommendation
      - recommend for DER
      - get product recommendation for DER
      - DER form recommendation
      - product line recommendation
      - fill DER form
      - DER product match
      - recommend OH product
      - structured recommendation
      - business group recommendation

  actions:
    # ── Node 1: Ask for Opportunity ID ───────────────────────────────────────
    - kind: Question
      id: question_gIjyHG
      interruptionPolicy:
        allowInterruption: true
      variable: init:Topic.OpptyID
      prompt: "Do you have any opportunity ID on hand? If so it's easy for me to fetch the data (NOW it's DUMMY process). "
      entity: StringPrebuiltEntity

    # ── Node 2: DER form Adaptive Card ───────────────────────────────────────
    - kind: AdaptiveCardPrompt
      id: qhjc7e
      card: |-
        {
          "type": "AdaptiveCard",
          "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
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
              "errorMessage": "Please select a Business Group",
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
              "valueOn": "Yes",
              "valueOff": "No"
            },
            {
              "type": "Input.Toggle",
              "id": "ai_flag",
              "title": "Involves Emerging Tech / AI",
              "valueOn": "Yes",
              "valueOff": "No"
            },
            {
              "type": "Input.Toggle",
              "id": "existing_expansion",
              "title": "Expansion of existing TruScale / managed contract",
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
              "errorMessage": "Please describe the business problem",
              "isMultiline": true
            }
          ],
          "actions": [
            { "type": "Action.Submit", "title": "Get recommendations" }
          ]
        }
      output:
        binding:
          actionSubmitId: Topic.actionSubmitId
          ai_flag: Topic.ai_flag
          ars_flag: Topic.ars_flag
          business_group: Topic.business_group
          existing_expansion: Topic.existing_expansion
          query: Topic.query
          scope: Topic.scope
          service_model: Topic.service_model
      outputType:
        properties:
          actionSubmitId: String
          ai_flag: String
          ars_flag: String
          business_group: String
          existing_expansion: String
          query: String
          scope: String
          service_model: String

    # ── Node 3: Call /recommend_der ───────────────────────────────────────────
    # v0.3 change: added node_key to responseSchema (required by /feedback)
    - kind: HttpRequestAction
      id: hbP5eP
      method: Post
      url: https://zitangopenclaw-product-line-auto-selection.hf.space/recommend_der
      headers:
        Content-Type: application/json
        X-API-Key: product-line-entry-agent
      body:
        kind: JsonRequestContent
        content: |-
          ={
            query: Topic.query,
            business_group: Topic.business_group,
            service_model: Topic.service_model,
            ars_flag: Topic.ars_flag,
            ai_flag: If(Topic.ai_flag = "Yes", "Yes", "No"),
            existing_expansion: If(Topic.existing_expansion = "Yes", true, false),
            scope: Topic.scope
          }
      errorHandling:
        kind: ContinueOnErrorBehavior
        statusCode: Topic.DerStatusCode
      requestTimeoutInMilliseconds: 60000
      response: Topic.DerApiResponse
      responseSchema:
        kind: Record
        properties:
          topk:
            type:
              kind: Table
              properties:
                category: String
                level: String
                level_label: String
                name: String
                node_key: String
                path_str: String
                score: Number
          hw_recommendations:
            type:
              kind: Table
              properties:
                category: String
                level: String
                level_label: String
                name: String
                node_key: String
                path_str: String
                score: Number

    # ── Node 4: Branch on results + feedback loop ─────────────────────────────
    - kind: ConditionGroup
      id: conditionGroup_lmu0Q4
      conditions:
        - id: conditionItem_qnbYu7
          condition: =IsEmpty(Topic.DerApiResponse.topk)
          actions:
            - kind: SendActivity
              id: sendActivity_9w3Gvb
              activity: Sorry, no matching OH products were found. Please try again with a different description.

      elseActions:
        # 4-A: Show recommendations
        - kind: SendActivity
          id: sendActivity_aG1xBI
          activity: |-
            Based on your DER fields (Service Model, ARS flag, and description) you just inputed, here are the top matching PN tree nodes: 
            {Concat(Topic.DerApiResponse.topk, name & " | " & path_str & " [" & level_label & ", score " & Text(score, "0.00") & "]" & Char(10))}

        # 4-A-2: Show HW recommendations (IDG / DCG-ISG only; empty table for other BGs)
        - kind: ConditionGroup
          id: conditionGroup_hw
          conditions:
            - id: conditionItem_hasHw
              condition: =Not(IsEmpty(Topic.DerApiResponse.hw_recommendations))
              actions:
                - kind: SendActivity
                  id: sendActivity_hwList
                  activity: |-
                    Matching hardware catalog items: 
                    {Concat(Topic.DerApiResponse.hw_recommendations, name & " | " & path_str & " [" & level_label & ", score " & Text(score, "0.00") & "]" & Char(10))}

        # 4-B: Feedback choice card (4 buttons, no input fields)
        - kind: AdaptiveCardPrompt
          id: adaptiveCard_feedback_choice
          card: |-
            {
              "type": "AdaptiveCard",
              "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
              "version": "1.5",
              "body": [
                {
                  "type": "TextBlock",
                  "text": "Which option do you prefer?",
                  "weight": "Bolder",
                  "size": "Medium",
                  "wrap": true
                }
              ],
              "actions": [
                { "type": "Action.Submit", "title": "Option 1", "data": { "FeedbackChoice": "Option 1" } },
                { "type": "Action.Submit", "title": "Option 2", "data": { "FeedbackChoice": "Option 2" } },
                { "type": "Action.Submit", "title": "Option 3", "data": { "FeedbackChoice": "Option 3" } },
                { "type": "Action.Submit", "title": "None of these", "data": { "FeedbackChoice": "None of these" } }
              ]
            }
          output:
            binding:
              actionSubmitId: Topic.FeedbackActionId
              FeedbackChoice: Topic.FeedbackChoice
          outputType:
            properties:
              actionSubmitId: String
              FeedbackChoice: String

        # 4-C: Branch on feedback choice
        - kind: ConditionGroup
          id: conditionGroup_feedback
          conditions:
            - id: conditionItem_negative
              condition: =Topic.FeedbackChoice = "None of these"
              actions:
                # 4-C-i: Ask for negative hint
                - kind: Question
                  id: question_negative_hint
                  interruptionPolicy:
                    allowInterruption: false
                  variable: init:Topic.NegativeHint
                  prompt: 'Could you briefly describe what you think the right direction is? (Type "skip" to skip this step)'
                  entity: StringPrebuiltEntity

                # 4-C-ii: POST negative feedback
                - kind: HttpRequestAction
                  id: httpRequest_feedback_neg
                  method: Post
                  url: https://zitangopenclaw-product-line-auto-selection.hf.space/feedback
                  headers:
                    Content-Type: application/json
                    X-API-Key: product-line-entry-agent
                  body:
                    kind: JsonRequestContent
                    content: |-
                      ={
                        opportunity_id: If(IsBlank(Topic.OpptyID), "unknown", Topic.OpptyID),
                        bg: Topic.business_group,
                        der_description: Topic.query,
                        scope: If(IsBlank(Topic.scope), "", Topic.scope),
                        service_model: If(IsBlank(Topic.service_model), "", Topic.service_model),
                        ars_flag: Topic.ars_flag = "Yes",
                        ai_flag: Topic.ai_flag = "Yes",
                        candidates_shown: Table(
                          {rank: 1, node_key: Index(Topic.DerApiResponse.topk, 1).node_key, score: Index(Topic.DerApiResponse.topk, 1).score, confidence: Index(Topic.DerApiResponse.topk, 1).level_label},
                          {rank: 2, node_key: Index(Topic.DerApiResponse.topk, 2).node_key, score: Index(Topic.DerApiResponse.topk, 2).score, confidence: Index(Topic.DerApiResponse.topk, 2).level_label},
                          {rank: 3, node_key: Index(Topic.DerApiResponse.topk, 3).node_key, score: Index(Topic.DerApiResponse.topk, 3).score, confidence: Index(Topic.DerApiResponse.topk, 3).level_label}
                        ),
                        user_selected_rank: Blank(),
                        is_negative: true,
                        negative_hint: If(Topic.NegativeHint = "skip" || IsBlank(Topic.NegativeHint), Blank(), Topic.NegativeHint)
                      }
                  errorHandling:
                    kind: ContinueOnErrorBehavior
                  requestTimeoutInMilliseconds: 10000
                  response: Topic.FeedbackResponse

          elseActions:
            # 4-C-iii: POST positive feedback
            - kind: HttpRequestAction
              id: httpRequest_feedback_pos
              method: Post
              url: https://zitangopenclaw-product-line-auto-selection.hf.space/feedback
              headers:
                Content-Type: application/json
                X-API-Key: product-line-entry-agent
              body:
                kind: JsonRequestContent
                content: |-
                  ={
                    opportunity_id: If(IsBlank(Topic.OpptyID), "unknown", Topic.OpptyID),
                    bg: Topic.business_group,
                    der_description: Topic.query,
                    scope: If(IsBlank(Topic.scope), "", Topic.scope),
                    service_model: If(IsBlank(Topic.service_model), "", Topic.service_model),
                    ars_flag: Topic.ars_flag = "Yes",
                    ai_flag: Topic.ai_flag = "Yes",
                    candidates_shown: Table(
                      {rank: 1, node_key: Index(Topic.DerApiResponse.topk, 1).node_key, score: Index(Topic.DerApiResponse.topk, 1).score, confidence: Index(Topic.DerApiResponse.topk, 1).level_label},
                      {rank: 2, node_key: Index(Topic.DerApiResponse.topk, 2).node_key, score: Index(Topic.DerApiResponse.topk, 2).score, confidence: Index(Topic.DerApiResponse.topk, 2).level_label},
                      {rank: 3, node_key: Index(Topic.DerApiResponse.topk, 3).node_key, score: Index(Topic.DerApiResponse.topk, 3).score, confidence: Index(Topic.DerApiResponse.topk, 3).level_label}
                    ),
                    user_selected_rank: Switch(Topic.FeedbackChoice, "Option 1", 1, "Option 2", 2, "Option 3", 3),
                    is_negative: false,
                    negative_hint: Blank()
                  }
              errorHandling:
                kind: ContinueOnErrorBehavior
              requestTimeoutInMilliseconds: 10000
              response: Topic.FeedbackResponse

        # 4-D: Thank you
        - kind: SendActivity
          id: sendActivity_feedback_thanks
          activity: Thanks for the feedback! Good luck with the rest of the form ✅

inputType: {}
outputType: {}
```

---

## §3 DER Topic — Node Change Log (v0.2 → v0.4)

| Node ID | Type | Status | Description |
|---|---|---|---|
| `question_gIjyHG` | Question | Unchanged | Ask for OpptyID |
| `qhjc7e` | AdaptiveCardPrompt | Unchanged | DER form card |
| `hbP5eP` | HttpRequestAction | **Changed** | v0.3: `responseSchema.topk` gained `node_key: String`; v0.4: `responseSchema` gained `hw_recommendations` table |
| `conditionGroup_lmu0Q4` | ConditionGroup | **Changed** | `elseActions` gained 4 feedback nodes + v0.4 HW display node |
| `sendActivity_aG1xBI` | SendActivity | Unchanged | Displays service recommendation results (`topk`) |
| `conditionGroup_hw` / `sendActivity_hwList` | ConditionGroup / SendActivity | **Added (v0.4)** | Shows HW recommendations when `hw_recommendations` is non-empty |
| `adaptiveCard_feedback_choice` | AdaptiveCardPrompt | **Added** | 4-button feedback card → `Topic.FeedbackChoice` |
| `conditionGroup_feedback` | ConditionGroup | **Added** | Branches positive/negative feedback by `FeedbackChoice` |
| `question_negative_hint` | Question | **Added** | Negative-feedback follow-up question (StringPrebuiltEntity, supports "skip") |
| `httpRequest_feedback_neg` | HttpRequestAction | **Added** | POST `/feedback`, `is_negative: true` |
| `httpRequest_feedback_pos` | HttpRequestAction | **Added** | POST `/feedback`, `user_selected_rank` mapped via Switch |
| `sendActivity_feedback_thanks` | SendActivity | **Added** | Thank-you message |

### Topic Variable List (complete as of v0.4)

| Variable | Type | Source |
|---|---|---|
| `Topic.OpptyID` | String | `question_gIjyHG` Question |
| `Topic.actionSubmitId` | String | `qhjc7e` AdaptiveCardPrompt |
| `Topic.business_group` | String | `qhjc7e` AdaptiveCardPrompt |
| `Topic.service_model` | String | `qhjc7e` AdaptiveCardPrompt |
| `Topic.ars_flag` | String ("Yes"/"No") | `qhjc7e` AdaptiveCardPrompt |
| `Topic.ai_flag` | String ("Yes"/"No") | `qhjc7e` AdaptiveCardPrompt |
| `Topic.existing_expansion` | String ("Yes"/"No") | `qhjc7e` AdaptiveCardPrompt |
| `Topic.scope` | String | `qhjc7e` AdaptiveCardPrompt |
| `Topic.query` | String | `qhjc7e` AdaptiveCardPrompt |
| `Topic.DerStatusCode` | Number | `hbP5eP` errorHandling |
| `Topic.DerApiResponse` | Record | `hbP5eP` response |
| `Topic.FeedbackActionId` | String | `adaptiveCard_feedback_choice` |
| `Topic.FeedbackChoice` | String ("Option 1"/"Option 2"/"Option 3"/"None of these") | `adaptiveCard_feedback_choice` |
| `Topic.NegativeHint` | String | `question_negative_hint` |
| `Topic.FeedbackResponse` | Record | `httpRequest_feedback_neg` / `httpRequest_feedback_pos` |

---

## §4 Pre-DER Topic Configuration (unchanged)

### 4.1 Trigger
- Type: **On Recognized Intent** (default)
- Description: "Takes free-form sales voice input (raw transcript OK) and returns top-3 PN tree L2/L3/L4 nodes."

### 4.2 Node 1: Question (free text)

| Field | Value |
|---|---|
| Display name | "Capture customer need" |
| Text to display | "Describe the customer's need in a sentence or two. I'll match it against our PN tree." |
| Identify | User's entire response |
| Output | Variable `query` (string), captured via "Save user response as" |

### 4.3 Node 2: HTTP Request

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

### 4.4 Node 3: Message (Send a Message)

| Field | Value |
|---|---|
| Type | Send a message |
| Modality | Text |
| Message (PowerFx) | `Concat(Topic.PreDerApiResponse.topk, name & " \| " & path_str & " [" & level_label & ", score " & Text(score, "0.00") & "]" & Char(10))` |

---

## §5 Test Plan

### DER Recommendation Tests (existing)

| # | BG | ServiceModel | ARS | AI | Scope | Query | Expected |
|---|---|---|---|---|---|---|---|
| 1 | IDG | DAAS | Yes | No | (default) | "laptop management for 500 employees" | top-1 high-confidence DaaS node |
| 2 | DCG | IAAS | No | Yes | (default) | "GPU cluster for AI workloads" | top-1 high-confidence infra node |
| 3 | SSG | PROF & MGD SERVICES | No | No | Standalone Professional Services | "advisory engagement for cloud migration" | top-1 hits consulting |
| 4 | (leave blank) | - | - | - | - | "test" | Card rejects (Required error on BG and query) |

### DER Feedback Tests (added in v0.3)

| # | Action | Expected in Copilot | Expected in `feedback.jsonl` |
|---|---|---|---|
| F-1 | After a normal recommendation, click "Option 1" | Shows "Thanks for the feedback! Good luck with the rest of the form ✅" | `user_selected_rank=1, is_negative=false, ab_group∈{A,B}` |
| F-2 | Click "Option 2" | Shows thank-you message | `user_selected_rank=2, is_negative=false` |
| F-3 | Click "None of these" → type "should be HW Lease" | Shows thank-you message | `is_negative=true, negative_hint="should be HW Lease"` |
| F-4 | Click "None of these" → type "skip" | Shows thank-you message | `is_negative=true, negative_hint=null` |

### Pre-DER Tests (existing)

| # | Query | Expected |
|---|---|---|
| 1 | "Customer needs managed PC deployment for 500 employees" | high-confidence top-1 |
| 2 | "Acme Manufacturing wants 1200 laptops with deployment services" | high-confidence top-1 |
| 3 | "AI workstation cluster for ML training, GPU heavy" | top-1 hits AI/ML node |

---

## §6 Feedback Loop Operations

### Trigger aggregation manually

```bash
# Preview current feedback count (no write)
python scripts/aggregate_feedback.py --dry-run

# Run aggregation for real, updates feedback_index.json
python scripts/aggregate_feedback.py
```

Output files:
- `output/feedback/feedback.jsonl` — raw feedback records (append-only)
- `output/feedback/feedback_index.json` — aggregated signal index (overwritten each daily batch)

### Signal mechanism

| Parameter | Value | Meaning |
|---|---|---|
| `MIN_SAMPLES` | 5 | No adjustment applied when a node has fewer than 5 feedback samples |
| `DELTA_CAP` | ±0.15 | Maximum adjustment to the LLM score |
| Formula | `(pos-neg)/(pos+neg) × 0.15` | Signal normalization |
| A/B split | 90% B / 10% A | Group B gets feedback weighting; group A is the control |

---

## §7 Playwright Automation Strategy

### §7.1 Known gotchas

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
| AdaptiveCardPrompt with data-only buttons | `Action.Submit` with `data` payload (no Input.* fields) — binding must match data key exactly | Key in `data: {FeedbackChoice: ...}` must match binding key `FeedbackChoice: Topic.FeedbackChoice` |

### §7.2 Primitives library (`scripts/_copilot_primitives.py`)

Each primitive returns `(ok: bool, info: dict)`.

- `navigate_to_topic(c, topic_id)` — direct URL navigation + wait for canvas
- `open_canvas(c)` — ensure canvas is loaded
- `scroll_to_node(c, label)` — scroll canvas until node is in viewport
- `click_node(c, label)` — click a node's header to open its editor
- `add_node_after(c, after_node, kind)` — `kind` ∈ {Question, HTTP request, Send a message, Adaptive Card}
- `fill_monaco(c, selector, json_text)` — paste JSON into Monaco editor textarea
- `click_modal_save_via_enter(c)` — known gotcha workaround
- `verify_save_clean(c)` — Save button disabled = no pending changes
- `save_topic(c, accept_warnings=True)` — full save cycle
- `set_question_identify(c, label)` — switch Question node Identify dropdown
- `set_question_output_variable(c, name)` — set "Save user response as"
- `set_http_request_url(c, url)` — set HTTP Request URL field
- `set_http_request_method(c, method)` — POST / GET / etc.
- `add_http_header(c, name, value)` — add a header row
- `edit_http_headers_body(c)` — open the Headers and body edit modal
- `set_http_body(c, body_text)` — paste PowerFx body
- `screenshot(c, name)` — save to `.playwright-mcp/run/<name>.png`

---

## §8 Pre-Publish Self-Check

```
[ ] Topic checker: 0 errors for both topics
[ ] Save button disabled for both topics (clean state)
[ ] Test pane: all DER recommendation cases pass (4 cases)
[ ] Test pane: all DER feedback cases pass (4 cases: F-1 to F-4)
[ ] Test pane: all Pre-DER cases pass (3 cases)
[ ] feedback.jsonl: entries appear after Test pane feedback interaction
[ ] Known acceptable warnings: 2 isRequired warnings on DER (non-blocking)
[ ] Publish button enabled → click
[ ] Verify topic status = "Published"
```

---

## §9 Risks and Fallbacks

| Risk | Fallback |
|---|---|
| Microsoft changes UI; selectors break | Self-test primitives; failures → manual troubleshooting |
| Monaco JSON contains `&` gets PowerShell-escaped | Use raw JSON string, avoid PowerShell interpolation |
| HF Space cold-start 45s on first request | Inform user first call is slow, requires patience |
| Topic checker reports new errors | Review spec for drift; adjust YAML; retry |
| `Pac auth create` blocked by tenant CA policy (confirmed) | Fallback to Playwright/CDP (current path) |
| `/feedback` call fails (network/timeout) | `ContinueOnErrorBehavior` ensures main flow unaffected; entry simply not written |
| `topk` has < 3 items; `Index(topk, 3)` returns blank record | `node_key`/`score`/`confidence` become blank — aggregator ignores blank node_keys silently |
| Feedback volume < MIN_SAMPLES (5) per node | Signal = 0; rankings unchanged until threshold met — expected in early rollout |
