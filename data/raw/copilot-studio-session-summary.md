# Copilot Studio 配置会话总结
> 日期：2026-06-29  
> 环境：RWA-IVA-UAT  
> Bot：Product_Line_Entry_Agent

---

## 一、项目背景

**目标**：在 Copilot Studio 配置两个 Topic，调用部署在 Hugging Face Space 的 FastAPI 推荐系统，在 Microsoft Teams 里为 Lenovo 销售团队提供 PN tree L2/L3/L4 节点推荐。

**架构**：
```
Teams → Copilot Studio → HF Space FastAPI → Python 推荐 pipeline
```

**两个 Topic**：
- `OH Recommendation (Pre-DER)`：自由文本输入 → 调用 `/recommend`
- `OH Recommendation (DER Form)`：Adaptive Card 表单 → 调用 `/recommend_der`

**关键参数**：
```
Bot ID:       90bf4480-f271-f111-ab0f-6045bd56018e
Environment:  0dd9076f-7fbf-e21a-b965-e436f2ec8083 (RWA-IVA-UAT)
HF Space URL: https://zitangopenclaw-product-line-auto-selection.hf.space
API Key:      product-line-entry-agent (X-API-Key header)
Pre-DER EP:   POST /recommend
DER EP:       POST /recommend_der
Timeout:      60000ms（HF Space cold start ~45s）
```

---

## 二、工作方式

本次采用**人机共创模式**：
- Claude 提供详细操作步骤和所有内容（JSON、公式、值）
- 用户在 Copilot Studio UI 进行点击操作
- 用户截图，Claude 验证状态

---

## 三、Pre-DER Topic 配置（已完成 ✅）

### 3.1 节点结构
```
Trigger
  └─ User says a phrase（phrases 已配置）
  └─ Describe what the topic does
Question
  └─ "Describe the customer's need in a sentence or two..."
  └─ Identify: User's entire response
  └─ Save as: query (string)
HTTP Request
  └─ POST /recommend
  └─ Headers: X-API-Key, Content-Type
  └─ Body (Edit formula): {query: Topic.query, business_group: ""}
  └─ Response: From sample data → PreDerApiResponse (record)
  └─ Timeout: 60000ms
Message
  └─ fx: Concat(Topic.PreDerApiResponse.topk, name & " | " & path_str & " [" & level_label & ", score " & Text(score, "0.00") & "]" & Char(10))
```

### 3.2 Trigger Phrases
```
customer needs product recommendation
recommend a product
what product should I recommend
PC deployment for employees
laptop deployment service
managed PC deployment
product recommendation for customer
PN tree recommendation
match customer need to product
find product for customer
```

### 3.3 关键配置坑
| 问题 | 解决方案 |
|---|---|
| "Add a tool" 里找不到 HTTP Request | Advanced → Send HTTP request |
| Invoke an HTTP request 需要 Entra ID 认证 | 不用，用 Advanced 菜单里的原生版本 |
| Body 变量引用 `{Topic.query}` 有引号 | 切换到 Edit formula 模式，去掉引号：`Topic.query` |
| Schema 编辑器报错 | 用 "From sample data" 方式，粘贴真实 API 响应 JSON |
| Agent 走 Web Search 而不是 Topic | Settings → Generative AI → 改成 "No - Use classic orchestration" |
| Web Search 干扰 | Overview → Web Search → Disabled |
| Topic 不触发 | Trigger 节点加 Phrases（classic orchestration 需要精确匹配） |

### 3.4 测试结果
**输入**：`Customer needs managed PC deployment for 500 employees`

**输出**：
```
DaaS HW Lenovo | Digital Workplace Solutions > Managed & Professional Services > Lifecycle Services > DaaS HW Lenovo [High, score 0.90]
LDO Managed Services | ... > Persona-based Configuration & Experience > LDO Managed Services [Medium, score 0.80]
OS Deployment | Global Product Services > Deployment Services > OS Deployment [Medium, score 0.75]
```

**状态：✅ 端到端测试通过**

---

## 四、DER Topic 配置（核心配置已完成，问题已修复 ✅）

### 4.1 节点结构
```
Trigger
  └─ User says a phrase（phrases 已配置）
Adaptive Card
  └─ JSON card（见 §4.2）
  └─ Outputs: query, business_group, service_model, ars_flag, ai_flag, scope, actionSubmitId
HTTP Request（已修复）
  └─ POST /recommend_der
  └─ Headers: X-API-Key, Content-Type
  └─ Body: JSON content + PowerFx Record
  └─ Response: From sample data → DerApiResponse (record)
  └─ Timeout: 60000ms
[调试节点 × 3]（需清理）
[硬编码测试节点 × 1]（需清理）
Condition
  └─ DerApiResponse.topk is empty → fallback Message
  └─ All other conditions → 正常 Message（Concat 公式）
```

### 4.2 Adaptive Card JSON
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
      "errorMessage": "Please describe the business problem",
      "isMultiline": true
    }
  ],
  "actions": [
    { "type": "Action.Submit", "title": "Get recommendations" }
  ]
}
```

### 4.3 DER Topic 问题已解决 ✅

**现象**：`CountRows(Topic.DerApiResponse.topk) = 0`，topk 始终为空

**诊断过程（保留）**：

| 测试 | Body 方式 | CountRows | 结论 |
|---|---|---|---|
| 硬编码字符串值 | JSON content + PowerFx Record | 3 ✅ | API 正常 |
| 变量引用（修复前） | JSON content + PowerFx Record | 0 ❌ | 触发 422，topk 为空 |
| 变量引用（修复后） | JSON content + PowerFx Record | 3 ✅ | 已恢复正常 |

**最终 root cause**：
1. HF API `/recommend_der` 本身完全正常（PowerShell 测试有返回）
2. 硬编码 Body 时 CountRows = 3，结果正确显示
3. 变量值本身正确（调试 Message 节点确认：query/bg/sm/ars/ai 全部有值）
4. **根因是 `scope` 为空时传入 `null`，而不是空字符串 `""`，导致请求失败（422）并出现 topk 为空**

**修复方式**：
- 服务端在 `app.py` 的 DER 请求模型中增加字段校验，对 `scope/service_model` 做 `null -> ""` 规范化。
- 业务逻辑仍按空值语义处理（后续匹配中可继续作为可选字段）。

**当前状态**：
- 问题已关闭，DER Topic 不再把该问题作为 blocker。

### 4.4 DER Topic Trigger Phrases
```
DER recommendation
recommend for DER
get product recommendation for DER
DER form recommendation
product line recommendation
fill DER form
DER product match
recommend OH product
structured recommendation
business group recommendation
```

### 4.5 Message 节点公式（All other conditions）
```
Concat(Topic.DerApiResponse.topk, name & " | " & path_str & " [" & level_label & ", score " & Text(score, "0.00") & "]" & Char(10))
```

---

## 五、Agent 全局设置

| 设置 | 值 |
|---|---|
| Orchestration | No - Use classic orchestration |
| Web Search | Disabled |
| Model | GPT-4.1 |
| Publish 状态 | Published 2026-06-29 |

---

## 六、下一步工作

### 优先级 1（已完成）：关闭 DER Topic 变量传值问题 ✅

- 结论：`scope` 为空时必须为 `""`，不能为 `null`。
- 根因：空值字段被序列化为 `null` 后触发 DER 请求失败（422），表现为 `CountRows(topk)=0`。
- 修复：服务端已加入 `null -> ""` 规范化逻辑。

### 优先级 2：清理调试节点
删除 DER Topic 里的临时调试节点：
- 变量调试 Message（3个）
- 硬编码测试 Message（1个）
- 可选：清理 `app.py` 中用于排查的 RAW body 日志输出（若已不再需要）。

### 优先级 3：完整测试
- DER Topic 4个测试用例（见 copilot-studio-topic-config.md §5）
- Pre-DER Topic 剩余 2个测试用例
- Publish 并在 Teams 里验证

### 已解决问题摘要

| 问题 | 根因 | 修复方案 | 状态 |
|---|---|---|---|
| DER Topic `topk` 为空 | `scope` 空值传成 `null` 导致请求失败 | 服务端将 `scope/service_model` 的 `null` 规范化为 `""` | ✅ 已解决 |

---

## 七、重要文件

| 文件 | 内容 |
|---|---|
| `docs/copilot-studio-topic-config.md` | Topic 配置规格，包含所有 JSON、公式、已知坑 |
| `docs/deployment.md` | HF Space 部署架构，API 端点规格 |
| `docs/design.md` | DER Refinement Agent 设计文档 |
| `docs/design_v2.md` | Pre-DER Agent 设计文档 |
| `docs/field-logic.md` | Helen 结构化字段级联逻辑 |
