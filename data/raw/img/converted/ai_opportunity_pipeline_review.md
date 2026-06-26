# AI Opportunity Pipeline — 数据审阅文档

**来源图片**: `data/raw/img/AI opportunity pipelines.png`  
**邮件发件人**: Rachel Thomas4  
**邮件主题**: RE: Supporting Material for Investor Briefing  
**生成日期**: 2026-06-24  
**状态**: 草稿，待人工校对

---

## 汇总校验

| 指标 | 图片显示值 | CSV 计算值 | 是否一致 |
|---|---|---|---|
| 总机会数 | 133 | 133 | ✅ |
| 总 TCV ($M) | 307.8 | 307.73 | ⚠️ 差 $0.07M，需核对（可能图片四舍五入） |
| AI Library 占比 | 25% | — | 需计算验证 |
| Custom 占比 | 23% | — | 需计算验证 |
| 整体 Portfolio 占比 | 77% | — | 整体 portfolio 总数未包含在图片中 |

---

## 逐行数据（已读入 CSV）

| 类别 | 子类别 | 产品名 | Count | TCV ($M) | 校对状态 |
|---|---|---|---|---|---|
| AI Library | AI Library | Knowledge Super Agent | 2 | 0.07 | 待核对 |
| AI Library | AI Library | Computer Vision | 17 | 10.80 | 待核对 |
| AI Library | AI Library | Predictive Modelling for Oil & Gas | 4 | 224.90 | 待核对 |
| AI Library | AI Library | Edge Orchestration | 2 | 0.31 | 待核对 |
| AI Library | AI Library | Rabotolog | 1 | 5.53 | **⚠️ 拼写待核对** |
| AI Consulting | AI Consulting | AI Discover | 8 | 2.64 | 待核对 |
| AI Consulting | AI Consulting | AI Advisory | 6 | 0.27 | 待核对 |
| AI Driven Vertical | AI Driven Vertical | AI Fast Start | 27 | 0.51 | 待核对 |
| AI Driven Vertical | AI Driven Vertical | Sports | 21 | 35.80 | 待核对 |
| AI Driven Vertical | AI Driven Vertical | Manufacturing | 2 | 13.60 | 待核对 |
| AI Driven Vertical | AI Driven Vertical | Retail | **13** | 0.60 | **⚠️ Count 由汇总倒推，未直接读取** |
| Custom | Custom | Custom | 30 | 12.70 | 待核对 |

---

## 重点校对清单

### 必须人工核对项

1. **Rabotolog 拼写** — 列表头为旋转文字，可能是 "Rabotolog"，请对照原始邮件确认正式产品名称
2. **Retail Count = 13** — 该数字由 `133 - ∑其他Count(120) = 13` 倒推，未从图片直接读取。请对照原图确认
3. **TCV 总计差异** — CSV 计算值 307.73，图片显示 307.8，差 $0.07M。请检查各行小数是否有遗漏精度（如 0.27 是否实为 0.274 等）

### 可选验证项

4. **AI Library 占比 25%** — 对应 (2+17+4+2+1=26 机会) / 133 = 19.5%，与 25% 不符 → 该 25% 可能指 TCV 占比：(0.07+10.80+224.90+0.31+5.53=241.61) / 307.8 = 78.5%，也不符 → **需确认占比的口径定义**
5. **Custom 占比 23%** — 30/133 = 22.6% ≈ 23%，Count 占比基本吻合

---

## 字段说明

- `Category`: 一级分类（AI Library / AI Consulting / AI Driven Vertical / Custom）
- `Sub_Category`: 二级分类（当前与 Category 相同，保留以备后续细分）
- `Product_Name`: 具体产品/解决方案名称
- `Qualified_Opportunity_Count`: 合格机会数量（整数）
- `Qualified_Pipeline_TCV_$M`: 合格管道总合同价值，单位百万美元，保留 2 位小数

---

## 数字化操作说明

本 CSV 直接从图片视觉读取，无 OCR 工具介入，精度依赖 Claude 图片理解能力。旋转表头字段已尽力识别，高风险字段已在上方标注 ⚠️。
