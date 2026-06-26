# Advanced PN List — Summary Report

## 1. 概览

- **来源文件**: `data/raw/Advanced PN List.xlsx` (Sheet: `Sheet1`)
- **总行数**: 68,918
- **总列数**: 26
- **生成时间**: 一次性快照,重新运行 `scripts/convert_advanced_pn_to_md.py` 可刷新

## 2. 业务单元 (Business Unit) 分布

共 4 个 BU,合计 68,918 行。

### BU 分布

| Value | Count | % |
| --- | ---: | ---: |
| ISG | 34318 | 49.8% |
| PCSD | 33032 | 47.9% |
| ISU | 1132 | 1.6% |
| MBG | 436 | 0.6% |

> 注:本数据集 BU 标签为 `ISG / ISU / MBG / PCSD`,与项目其他数据集中的 `IDG / DCG` 命名体系不同。

## 3. 物料类型 (Material Type) 分布

### Material Type

| Value | Count | % |
| --- | ---: | ---: |
| ZITR | 56969 | 82.7% |
| ZDIE | 9220 | 13.4% |
| ZREV | 1210 | 1.8% |
| <NULL> | 738 | 1.1% |
| ZPPN | 701 | 1.0% |
| SUBS | 31 | 0.0% |
| ZXMT | 29 | 0.0% |
| ZSEL | 16 | 0.0% |
| ZDUM | 4 | 0.0% |

## 4. 产品组 (Product Group) 分布

### Product Group

| Value | Count | % |
| --- | ---: | ---: |
| Service | 51350 | 74.5% |
| Software | 17225 | 25.0% |
| Hardware | 343 | 0.5% |

## 5. 状态 (State) 分布

### State

| Value | Count | % |
| --- | ---: | ---: |
| Released | 68918 | 100.0% |

## 6. Top 10 OH L1 类别

### OH L1 (Top 10)

| Value | Count | % |
| --- | ---: | ---: |
| Global Product Services | 30180 | 43.8% |
| Digital Workplace Solutions | 24986 | 36.3% |
| Sustainability Services | 11954 | 17.3% |
| Vertical Solutions | 1182 | 1.7% |
| Hybrid Cloud Services | 475 | 0.7% |
| AI Solutions | 141 | 0.2% |

## 7. Top 10 OH L2 类别

### OH L2 (Top 10)

| Value | Count | % |
| --- | ---: | ---: |
| Deployment Services | 28181 | 40.9% |
| Software & Cloud Services | 17146 | 24.9% |
| Sustainability Services | 11954 | 17.3% |
| Managed & Professional Services | 8284 | 12.0% |
| Configuration Services | 1972 | 2.9% |
| Vertical Solutions | 1182 | 1.7% |
| AI Managed & Professional Services | 141 | 0.2% |
| TruScale HCS | 31 | 0.0% |
| Support Services | 27 | 0.0% |

## 8. 数据来源 (Data Source) 分布

### Data Source

| Value | Count | % |
| --- | ---: | ---: |
| ISG Windchill | 34318 | 49.8% |
| PCSD Windchill | 34120 | 49.5% |
| MBG Windchill | 441 | 0.6% |
| Manual | 39 | 0.1% |

## 9. Announce Date 范围

- **最早**: `2011-12-12`
- **最晚**: `9999-12-31`
- **非空记录数**: 65,552 / 68,918 (95.1%)

## 10. 各 BU 示例 (每 BU 3 条)

### ISG

| PN | Description | OH L1 | OH L2 | Material Type | State |
| --- | --- | --- | --- | --- | --- |
| `SUB7B74180` | TruScale Infrastructure Services Fix | Hybrid Cloud Services | TruScale HCS | SUBS | Released |
| `SUB7B74179` | IaaS Storage As Service | Hybrid Cloud Services | TruScale HCS | SUBS | Released |
| `SUB7B74178` | IaaS Back Up As Service | Hybrid Cloud Services | TruScale HCS | SUBS | Released |

### ISU

| PN | Description | OH L1 | OH L2 | Material Type | State |
| --- | --- | --- | --- | --- | --- |
| `40CGPOSUF1` | U-Frame + Tilt Head Combo Kit | Vertical Solutions | Vertical Solutions |  | Released |
| `40CGP0SVE1` | X12 POS Power VESA Mount | Vertical Solutions | Vertical Solutions |  | Released |
| `40CGP0SST1` | POS Adjustable Stand | Vertical Solutions | Vertical Solutions |  | Released |

### MBG

| PN | Description | OH L1 | OH L2 | Material Type | State |
| --- | --- | --- | --- | --- | --- |
| `PG38C08475` | CP ACCY CS CVR SWAROVSKI BR TP EQUATOR25 | Sustainability Services | Sustainability Services | ZITR | Released |
| `PG38C08419` | CP ACCY CS CVR BR TP URUS25 | Sustainability Services | Sustainability Services | ZITR | Released |
| `PG38C08263` | CP ACCY S-WATCH XT2547-2BS+VS BR ZH NAND | Sustainability Services | Sustainability Services | ZITR | Released |

### PCSD

| PN | Description | OH L1 | OH L2 | Material Type | State |
| --- | --- | --- | --- | --- | --- |
| `YAIRFRGTWS` | AirFreight uplift per Workstations | Global Product Services | Deployment Services | ZITR | Released |
| `XXXX003608` | Absolute | Digital Workplace Solutions | Software & Cloud Services | ZSEL | Released |
| `XXXX003607` | Absolute | Digital Workplace Solutions | Software & Cloud Services | ZSEL | Released |

## 11. 数据观察

- 数据规模较大 (68,918 行),完整转储见 `Advanced PN List.md`。
- BU 分布呈两极:`ISG` (34,318) 与 `PCSD` (33,032) 合计占比 97.7%,`ISU` 与 `MBG` 体量很小。
- 共 3 个 Product Group,共 6 个 OH L1 类别。
- ⚠️ Announce Date 字段含哨兵值 `9999-12-31`,可能为 '未发布/未填' 占位符,统计时间范围时请剔除。
- 完整字段说明请参考源文件 `Sheet1` 表头。
