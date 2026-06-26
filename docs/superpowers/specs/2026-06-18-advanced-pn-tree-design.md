# Advanced PN List — OH Tree Explorer

**Date**: 2026-06-18
**Status**: Approved (brainstorming complete, awaiting user spec review)

> **Rename note (2026-06-27)**: the script referenced throughout this spec as `scripts/build_pn_tree.py` is now named `scripts/build_pre_der_pn_tree.py` (Pre-DER Agent pipeline rename). See [CONTEXT.md §"Agent Naming"](../../CONTEXT.md#agent-naming-historical-anchor). The body of this spec is preserved as a historical design record.

## 1. Goal

Build a one-shot exploration tool that reads `data/raw/Advanced PN List.xlsx` and emits a single JSON file (`output/advanced_pn_tree.json`) containing the **Offering Hierarchy (OH) tree** of all 68,918 part numbers, organized as a nested 6-level structure with `{pn, description}` leaves.

The user wants to **browse** the SG/SSG (Solutions & Services Group) catalog by OH taxonomy. This is **exploration only** — not a pipeline component.

### Source-of-truth facts (verified)

| Property | Value |
|---|---|
| Sheet count | 1 (`Sheet1`) |
| Data rows | 68,918 |
| Total columns | 26 |
| `State` distribution | `Released` = 68,918 (100%) |
| `Business Unit` distinct | 4 (ISG 34,318 · PCSD 33,032 · ISU 1,132 · MBG 436) — **ignored per user** |
| PN distinct values | 68,918 (one row per PN) |
| PN Description distinct | 30,113 (some PNs share descriptions) |
| `OH L1` distinct | 6 |
| `OH L2` distinct | 9 |
| `OH L3` distinct | 50 |
| `OH L4` distinct | 276 |
| `OH L5` distinct | 115 |
| `OH L6` distinct | 39 (but **412 unique (L1..L6) paths** — L6 names recur under different parents) |

The 6 levels correspond to Lenovo's Offering Hierarchy (see `CONTEXT.md`).

## 2. Decisions (locked-in)

| Decision | Choice |
|---|---|
| BU scope | All 68,918 rows (Business Unit column ignored) |
| Output format | JSON tree |
| PN leaf payload | `{pn, description}` only (lean) |
| Intermediate node payload | `{name, pn_count, child_count, children}` |
| L6 leaves | Use `pns` array (not `children`) for clarity |
| Sibling ordering | Alphabetical by `name`; `pns` alphabetical by `pn` |
| Output location | `output/advanced_pn_tree.json` |
| Use case | Pure exploration, snapshot file |
| Dependencies | `openpyxl` only (already required by the project) |
| Approach | Single-pass nested dict build (Approach A) |

## 3. File layout

```
product-line-auto-selection/
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-06-18-advanced-pn-tree-design.md  # this file
├── scripts/
│   ├── build_pn_tree.py        # NEW — builds the OH tree JSON
│   └── validate_pn_tree.py     # NEW — sanity-checks the output JSON
└── output/
    └── advanced_pn_tree.json   # NEW — snapshot output
```

No other files are touched. `src/`, `prompts/`, `data/`, existing `scripts/` are unchanged.

## 4. JSON schema

### Top-level

```json
{
  "meta": {
    "source_file": "data/raw/Advanced PN List.xlsx",
    "sheet": "Sheet1",
    "level_columns": ["OH L1","OH L2","OH L3","OH L4","OH L5","OH L6"],
    "total_pns": 68918,
    "total_l1": 6,
    "empty_l_names": 64304,
    "empty_descriptions": 0,
    "generated_at": "2026-06-18T10:00:00Z"
  },
  "tree": [ ... L1 nodes, sorted by name ... ]
}
```

### L1–L5 nodes

```json
{
  "name": "Hardware Only Deployment",
  "pn_count": 27019,
  "child_count": 3,
  "children": [ ... child nodes ... ]
}
```

### L6 nodes

```json
{
  "name": "Server_CTO",
  "pn_count": 47,
  "child_count": 47,
  "pns": [
    {"pn": "7Q13104999", "description": "HW Install (Biz Hrs) SR250 V3"},
    {"pn": "7Q13104998", "description": "HW Install (Biz Hrs) SR250 V3"}
  ]
}
```

Note: "Server_CTO" is a recurring L6 name — it appears as ~6 separate L6 nodes in the tree under different (L1..L5) parents. The example above shows one such leaf (pn_count=47); other "Server_CTO" leaves will have different pn_count values. The total PN count for the "Server_CTO" name across all its occurrences in the tree is 16,964.

### PN entry

```json
{"pn": "<string>", "description": "<string>"}
```

### Invariants

1. `pns` only appears at L6. `children` always means "next-level OH category".
2. `pn_count` is a rollup: total PNs in the entire subtree below this node.
3. `child_count` is immediate: `len(children)` or `len(pns)`, whichever is present.
4. Siblings in `tree` are sorted by `name`. Items in `pns` are sorted by `pn`.
5. Empty `OH L_k` cells are kept as `""` and counted in `meta.empty_l_names`. (Real data: L5 has 30,451 empty cells, L6 has 33,853 empty cells — 64,304 total. These PNs have a partial hierarchy that ends at L4 or L5.)
6. Missing PN descriptions are stored as `""` and counted separately (printed to stderr).

## 5. Data flow

```
read xlsx (openpyxl, data_only=True, read_only=True)
        │
        ▼
for each row (skip header):
    l1..l6 = row[cols L1..L6]      # cols 7..12 (1-indexed)
    pn    = row[col PN]            # col 2
    desc  = row[col PN Description] # col 3

    walk/create nodes L1 → L6 in nested dict:
        tree[l1].children[l2].children[l3]
            .children[l4].children[l5]
            .pns.append({"pn": pn, "description": desc})
        │
        ▼
post-order traversal: compute pn_count for each node
        │
        ▼
sort siblings by name; sort pns by pn
        │
        ▼
build meta block (counts, timestamp)
        │
        ▼
inline self-checks (see §6)
        │
        ▼
json.dump(..., indent=2, ensure_ascii=False) → output/advanced_pn_tree.json
```

### Code structure (single file)

```
main()
 ├─ parse_args()                  # argparse, defaults match our paths
 ├─ load_rows()                   # openpyxl → list of dicts
 ├─ build_tree(rows)              # single pass → nested dict
 ├─ add_rollups(node)             # recursive: pn_count for every node
 ├─ sort_tree(node)               # recursive: sort children + pns
 ├─ build_meta(rows)              # totals, timestamp, source_file
 ├─ self_check(tree, rows)        # assertions before write (see §6)
 └─ write_json(out_path, meta, tree)
```

### CLI

```bash
python scripts/build_pn_tree.py \
    --input  "data/raw/Advanced PN List.xlsx" \
    --output output/advanced_pn_tree.json
```

Defaults match the values above; the script also runs with no args.

## 6. Validation

### Inline self-checks in `build_pn_tree.py`

Run at the end, **before** writing JSON. If any check fails → raise + non-zero exit; **no JSON written**.

- `sum(n["pn_count"] for n in tree) == len(rows)`
- `len(tree) == meta["total_l1"]`
- For every node: `len(node["children"]) == node["child_count"]` (or `len(pns) == child_count` at L6)
- All PNs in the tree are unique (`len({p["pn"] for ... }) == total_pns`)
- `max(depth(tree)) == 6`

### `scripts/validate_pn_tree.py`

Standalone validator. Loads `output/advanced_pn_tree.json` and prints:

- total PN count vs `meta.total_pns`
- count of nodes at each level (depth 1..6)
- distinct L1 names
- 3 sample leaf paths (L1 → … → L6 → sample PN)
- duplicate PN count (should be 0)
- size of the JSON file on disk

### Out of test scope

- No `pytest`, no unit test framework.
- No regression testing against the source xlsx (xlsx is the source of truth; JSON is derived).
- No fuzz / property-based testing.

## 7. Error handling

| Case | Behavior |
|---|---|
| Input file not found | argparse error + exit 1 |
| Sheet "Sheet1" missing | Error message naming the missing sheet + exit 1 |
| `OH L_k` is blank | Keep as `""`, bump `meta.empty_l_names`, log warning at end |
| PN missing or empty | Raise (data corruption; PN column is 100% populated in source) |
| Inline self-check fails | Raise + exit 1; **no JSON written** |

## 8. Success criteria

The build is "done" when **all** of the following hold:

1. `python scripts/build_pn_tree.py` exits 0.
2. `output/advanced_pn_tree.json` exists.
3. `meta.total_pns == 68918`.
4. Sum of `pn_count` at L1 = `meta.total_pns`.
5. Tree depth is exactly 6.
6. 6 distinct L1 names.
7. 0 duplicate PNs in the tree.
8. `python scripts/validate_pn_tree.py` runs and reports sane stats.
9. A spot-checked leaf path (`Global Product Services → Deployment Services → Hardware Only Deployment → Hardware Install → Hardware Install → Server_CTO`) contains PNs that match the original xlsx.

## 9. Non-goals

- No new product-matching pipeline integration.
- No filtering by BU, Product Group, Material Type, etc.
- No interactive UI, no query API — JSON is browsed with `jq` / Python `json.load`.
- No re-build automation / no Makefile target.
- No committing the JSON output by default — it's a derived artifact; regenerate from the xlsx when needed.
