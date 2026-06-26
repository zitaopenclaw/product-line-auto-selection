# Contract_Result — Summary Report

## 1. 概览

- **来源文件**: `data/raw/Contract_Result_20260616-2_UAT.xlsx` (Sheet: `Result 1`)
- **数据行数**: 695
- **唯一合同数 (Contract Number)**: 114
- **唯一机会数 (Opp-ID)**: 17
- **选中列数**: 23 (原表 66 列,已筛除 WBS/ECCN/重复字段/内部计费字段)
- **生成时间**: 一次性快照,重新运行 `scripts/convert_contract_to_md.py` 可刷新

## 2. 业务组 (Business Group) 分布

共 2 个 BG。

### Business Group

| Value | Count | % |
| --- | ---: | ---: |
| IDG | 661 | 95.1% |
| ISG | 34 | 4.9% |

> 注:本数据集使用 `IDG / ISG` 命名,与项目其他数据集中的 `IDG / DCG` 不完全一致。

## 3. 地理 (Geo) 分布

### Geo

| Value | Count | % |
| --- | ---: | ---: |
| EMEA | 234 | 33.7% |
| AP | 229 | 32.9% |
| NA | 218 | 31.4% |
| LA | 14 | 2.0% |

## 4. 销售组织 (Sales Org) 分布

### Sales Org (Top 10)

| Value | Count | % |
| --- | ---: | ---: |
| GB10 | 194 | 27.9% |
| US10 | 190 | 27.3% |
| AU10 | 114 | 16.4% |
| JP10 | 88 | 12.7% |
| NL10 | 43 | 6.2% |
| AU30 | 26 | 3.7% |
| CA10 | 14 | 2.0% |
| VE40 | 14 | 2.0% |
| US31 | 7 | 1.0% |
| FI10 | 1 | 0.1% |

## 5. Top 10 终端客户国家

### End Customer Country (Top 10)

| Value | Count | % |
| --- | ---: | ---: |
| US | 204 | 29.4% |
| GB | 194 | 27.9% |
| AU | 140 | 20.1% |
| JP | 89 | 12.8% |
| CZ | 36 | 5.2% |
| CA | 14 | 2.0% |
| VE | 14 | 2.0% |
| FI | 1 | 0.1% |
| FR | 1 | 0.1% |
| SE | 1 | 0.1% |

## 6. 服务模式 (Service Model) 分布

### Service Model

| Value | Count | % |
| --- | ---: | ---: |
| DAAS | 651 | 93.7% |
| IAAS | 27 | 3.9% |
| MSAAS | 9 | 1.3% |
| ISGLEASE | 7 | 1.0% |
| PROF & MGD SERVICES | 1 | 0.1% |

## 7. 协议类型 (Agreement Type) 分布

### Agreement Type

| Value | Count | % |
| --- | ---: | ---: |
| MLA | 441 | 63.5% |
| MSA | 254 | 36.5% |

## 8. 状态 (Status) 分布

### Status

| Value | Count | % |
| --- | ---: | ---: |
| E0003 | 636 | 91.5% |
| E0004 | 31 | 4.5% |
| E0001 | 28 | 4.0% |

## 9. 按货币汇总的合同金额

| Currency | Total Contract Price | # of Items |
| --- | ---: | ---: |
| USD | 378,342,520.67 | 218 |
| GBP | 7,668,389.27 | 194 |
| JPY | 413,596.00 | 89 |
| AUD | 247,952.38 | 132 |
| EUR | 132,942.04 | 38 |
| SEK | 345.00 | 1 |
| CHF | 11.00 | 1 |
| CAD | 1.60 | 12 |

## 10. 时间范围

- **合同 Created Date**: `2026-01-07 02:37:18.691407` ~ `2026-06-11 08:56:58.656766` (695 条)
- **Item Start Date**: `2022-06-17` ~ `2026-06-11` (695 条)
- **Item End Date**: `2022-09-17` ~ `2030-06-10` (695 条)

## 11. 示例合同 (各 BG 3 条)

### IDG

| Contract # | Opp-ID | Service Model | Agreement | Geo | Country | Status | Price | Cur | Item Start | Item End |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| ES00109686 | OPP-0001143655 | DAAS | MSA | EMEA | GB | E0003 | 2,905.18 | GBP | 2026-06-11 | 2030-06-10 |
| ES00109686 | OPP-0001143655 | DAAS | MSA | EMEA | GB | E0003 | 2,856.98 | GBP | 2026-06-11 | 2030-06-10 |
| ES00109686 | OPP-0001143655 | DAAS | MSA | EMEA | GB | E0003 | 7.59 | GBP | 2026-06-11 | 2030-06-10 |

### ISG

| Contract # | Opp-ID | Service Model | Agreement | Geo | Country | Status | Price | Cur | Item Start | Item End |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| ES00109691 | OPP-0000349369 | MSAAS | MSA | AP | AU | E0003 | 3,604.94 | AUD | 2025-02-17 | 2029-09-17 |
| ES00109691 | OPP-0000349369 | MSAAS | MSA | AP | AU | E0003 | 2,656.49 | AUD | 2025-02-17 | 2029-09-17 |
| ES00109691 | OPP-0000349369 | MSAAS | MSA | AP | AU | E0003 | 948.45 | AUD | 2025-02-17 | 2029-09-17 |

## 12. 数据观察

- 共 695 条 item,归属于 114 个合同、17 个机会 — 平均每合同 6.1 条 item,每机会 40.9 条 item。
- BG 高度集中于 `IDG` (95.1%),`ISG` 仅 34 条。
- 完整转储见 `Contract_Result_20260616-2_UAT.md`。
- 源文件中另含 `Query` sheet,内容为生成该报表的 SQL 语句,本报告未纳入。
