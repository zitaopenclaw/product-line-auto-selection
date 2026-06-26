# Advanced PN Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Rename note (2026-06-27)**: the script referenced throughout this plan as `scripts/build_pn_tree.py` is now named `scripts/build_pre_der_pn_tree.py` (Pre-DER Agent pipeline rename). See [CONTEXT.md §"Agent Naming"](../../CONTEXT.md#agent-naming-historical-anchor). The body of this plan is preserved as a historical implementation record.

**Goal:** Build `scripts/build_pn_tree.py` that reads `data/raw/Advanced PN List.xlsx` and writes `output/advanced_pn_tree.json` — a nested OH tree of all 68,918 part numbers with `{pn, description}` leaves.

**Architecture:** Single-pass nested-dict build with openpyxl. Walk `OH L1 → OH L6` per row, create missing category nodes, attach PN to L6 leaf. After pass: post-order rollup of `pn_count`, alphabetical sort of siblings and PN lists, JSON serialize with `indent=2`. Inline assertions before write. Standalone validator script for sanity stats.

**Tech Stack:** Python 3, `openpyxl` (already a project dep), `json`, `argparse`, `datetime`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-18-advanced-pn-tree-design.md`

---

## File Structure

```
product-line-auto-selection/
├── scripts/
│   ├── build_pn_tree.py        # NEW — builds the OH tree JSON
│   └── validate_pn_tree.py     # NEW — sanity-checks the output JSON
└── output/
    └── advanced_pn_tree.json   # GENERATED — the snapshot output
```

No other files are modified. `src/`, `prompts/`, `data/`, existing `scripts/` are untouched.

**Single responsibility per file**:
- `build_pn_tree.py` — read xlsx, build tree, write JSON. No validation/inspection logic.
- `validate_pn_tree.py` — read JSON, print sanity stats. No mutation.

---

## Task 1: Scaffold `build_pn_tree.py` with CLI and `load_rows()`

**Files:**
- Create: `scripts/build_pn_tree.py`

- [ ] **Step 1: Create the script with CLI + load_rows skeleton**

Create `scripts/build_pn_tree.py`:

```python
"""Build the OH tree JSON from data/raw/Advanced PN List.xlsx.

Single-pass: walk L1..L6 path per row, attach {pn, description} to L6 leaf,
then roll up counts, sort, and serialize to JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "raw" / "Advanced PN List.xlsx"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "advanced_pn_tree.json"

COL_BUSINESS_UNIT = 1   # "Business Unit" — ignored per user decision
COL_PN = 2              # "PN"
COL_PN_DESC = 3         # "PN Description"
COL_LEVEL_START = 7     # "OH L1" begins at column 7 (1-indexed)
COL_LEVEL_END = 12      # "OH L6" ends at column 12 (1-indexed, inclusive)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                   help="Path to Advanced PN List.xlsx")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                   help="Path to write the tree JSON")
    return p.parse_args()


def load_rows(input_path: Path) -> list[dict[str, Any]]:
    """Read the xlsx and return a list of row dicts.

    Each row dict has keys: pn, description, l1..l6.
    """
    if not input_path.exists():
        sys.exit(f"Input file not found: {input_path}")

    wb = openpyxl.load_workbook(input_path, data_only=True, read_only=True)
    if "Sheet1" not in wb.sheetnames:
        sys.exit(f"Sheet 'Sheet1' not found in {input_path.name}")
    ws = wb["Sheet1"]

    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)

    out: list[dict[str, Any]] = []
    for raw in rows_iter:
        # Pad short rows so indexing doesn't crash; missing cols become None.
        raw_list = list(raw) + [None] * (COL_LEVEL_END - len(raw))
        pn = raw_list[COL_PN - 1]
        if pn is None or (isinstance(pn, str) and pn.strip() == ""):
            sys.exit(f"Row with missing PN encountered (col {COL_PN}); aborting.")
        out.append({
            "pn": str(pn).strip(),
            "description": "" if raw_list[COL_PN_DESC - 1] is None
                           else str(raw_list[COL_PN_DESC - 1]).strip(),
            "l1": raw_list[COL_LEVEL_START - 1] or "",
            "l2": raw_list[COL_LEVEL_START] or "",
            "l3": raw_list[COL_LEVEL_START + 1] or "",
            "l4": raw_list[COL_LEVEL_START + 2] or "",
            "l5": raw_list[COL_LEVEL_START + 3] or "",
            "l6": raw_list[COL_LEVEL_START + 4] or "",
        })
    return out


def main() -> None:
    args = parse_args()
    rows = load_rows(args.input)
    print(f"Loaded {len(rows)} rows from {args.input}", file=sys.stderr)
    # Placeholder; full pipeline lands in later tasks.
    print("build_tree / add_rollups / sort_tree / write_json — coming next",
          file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script with defaults and verify the row count**

Run from the project root:

```bash
python scripts/build_pn_tree.py
```

Expected stderr output:

```
Loaded 68918 rows from D:\zita\opencode\product-line-auto-selection\data\raw\Advanced PN List.xlsx
build_tree / add_rollups / sort_tree / write_json — coming next
```

Expected exit code: 0.

- [ ] **Step 3: Confirm no JSON file is written yet**

```bash
Test-Path "output/advanced_pn_tree.json"
```

Expected: `False`. (No JSON yet — full pipeline comes in later tasks.)

---

## Task 2: Implement `build_tree(rows)` — single-pass nested dict

**Files:**
- Modify: `scripts/build_pn_tree.py`

- [ ] **Step 1: Add `build_tree` function**

Add to `scripts/build_pn_tree.py` (above `def main`):

```python
def build_tree(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Single-pass build of the L1..L6 nested tree.

    Returns a list of L1 nodes. Each intermediate node is:
        {"name": str, "pn_count": 0, "child_count": 0, "children": [...]}
    Each L6 node additionally has a "pns" array:
        {"name": str, "pn_count": 0, "child_count": 0,
         "pns": [{"pn": str, "description": str}, ...]}
    Rollups and sorting are applied by later functions.
    """
    # Level-name → children-dict map for easy "find or create".
    tree: list[dict[str, Any]] = []

    # Stack tracks the currently-active node at each depth (0..5).
    # depth 0 = root list (L1 entries), depth 5 = L6 node.
    by_path: dict[tuple[str, ...], dict[str, Any]] = {}

    for r in rows:
        levels = (str(r["l1"] or "").strip(),
                  str(r["l2"] or "").strip(),
                  str(r["l3"] or "").strip(),
                  str(r["l4"] or "").strip(),
                  str(r["l5"] or "").strip(),
                  str(r["l6"] or "").strip())

        # Walk L1..L5 creating category nodes as needed.
        for depth in range(5):
            path = levels[: depth + 1]
            node = by_path.get(path)
            if node is None:
                node = {"name": levels[depth], "pn_count": 0,
                        "child_count": 0, "children": []}
                by_path[path] = node
                if depth == 0:
                    tree.append(node)
                else:
                    parent = by_path[levels[:depth]]
                    parent["children"].append(node)

        # Create the L6 leaf (PN container).
        l6_path = levels
        l6_node = by_path.get(l6_path)
        if l6_node is None:
            l6_node = {"name": levels[5], "pn_count": 0,
                       "child_count": 0, "pns": []}
            by_path[l6_path] = l6_node
            parent = by_path[levels[:5]]
            parent["children"].append(l6_node)

        l6_node["pns"].append({"pn": r["pn"], "description": r["description"]})

    return tree
```

- [ ] **Step 2: Wire `build_tree` into `main`**

Replace the `main` function in `scripts/build_pn_tree.py` with:

```python
def main() -> None:
    args = parse_args()
    rows = load_rows(args.input)
    print(f"Loaded {len(rows)} rows from {args.input}", file=sys.stderr)

    tree = build_tree(rows)
    total_l1 = len(tree)
    total_l6_leaves = _count_l6_leaves(tree)
    total_pn_attached = _count_attached_pns(tree)
    print(f"Tree: {total_l1} L1 nodes, {total_l6_leaves} L6 leaves, "
          f"{total_pn_attached} PNs attached", file=sys.stderr)


def _count_l6_leaves(tree: list[dict[str, Any]]) -> int:
    n = 0
    stack: list[dict[str, Any]] = list(tree)
    while stack:
        node = stack.pop()
        if "pns" in node:
            n += 1
        else:
            stack.extend(node.get("children", []))
    return n


def _count_attached_pns(tree: list[dict[str, Any]]) -> int:
    n = 0
    stack: list[dict[str, Any]] = list(tree)
    while stack:
        node = stack.pop()
        if "pns" in node:
            n += len(node["pns"])
        else:
            stack.extend(node.get("children", []))
    return n
```

- [ ] **Step 3: Run the script and verify counts**

```bash
python scripts/build_pn_tree.py
```

Expected stderr:

```
Loaded 68918 rows from D:\zita\opencode\product-line-auto-selection\data\raw\Advanced PN List.xlsx
Tree: 6 L1 nodes, 412 L6 leaves, 68918 PNs attached
```

Note: L6 names are NOT globally unique — the same L6 name can appear under different (L1..L5) parents. The data has only 39 distinct L6 *name strings* but 412 unique (L1..L6) *paths*, so the tree has 412 L6 leaf nodes.

Expected exit code: 0.

If counts differ, the L1 list will be wrong (should be 6) or the L6 leaf count (should be 412) or attached PN count (should be 68,918). Investigate before proceeding.

---

## Task 3: Implement `add_rollups(node)` and `sort_tree(node)`

**Files:**
- Modify: `scripts/build_pn_tree.py`

- [ ] **Step 1: Add the two helpers**

Add to `scripts/build_pn_tree.py` (above `def main`):

```python
def add_rollups(node: dict[str, Any]) -> int:
    """Recursively set pn_count and child_count on every node. Returns pn_count."""
    if "pns" in node:
        node["child_count"] = len(node["pns"])
        node["pn_count"] = len(node["pns"])
        return node["pn_count"]

    total_pn = 0
    for child in node.get("children", []):
        total_pn += add_rollups(child)
    node["pn_count"] = total_pn
    node["child_count"] = len(node.get("children", []))
    return total_pn


def add_rollups_tree(tree: list[dict[str, Any]]) -> None:
    for n in tree:
        add_rollups(n)


def sort_tree(node: dict[str, Any]) -> None:
    """Recursively sort children by name and pns by pn."""
    if "pns" in node:
        node["pns"].sort(key=lambda p: p["pn"])
        return
    node["children"].sort(key=lambda c: c["name"])
    for c in node.get("children", []):
        sort_tree(c)


def sort_tree_root(tree: list[dict[str, Any]]) -> None:
    tree.sort(key=lambda n: n["name"])
    for n in tree:
        sort_tree(n)
```

- [ ] **Step 2: Wire `add_rollups_tree` and `sort_tree_root` into `main`**

Replace `main` in `scripts/build_pn_tree.py` with:

```python
def main() -> None:
    args = parse_args()
    rows = load_rows(args.input)
    print(f"Loaded {len(rows)} rows from {args.input}", file=sys.stderr)

    tree = build_tree(rows)
    print(f"Tree built: {len(tree)} L1 nodes, "
          f"{_count_l6_leaves(tree)} L6 leaves, "
          f"{_count_attached_pns(tree)} PNs attached", file=sys.stderr)

    add_rollups_tree(tree)
    sort_tree_root(tree)
    print("Rollups + sorting applied", file=sys.stderr)
```

- [ ] **Step 3: Run and verify rollups**

```bash
python scripts/build_pn_tree.py
```

Expected stderr:

```
Loaded 68918 rows from D:\zita\opencode\product-line-auto-selection\data\raw\Advanced PN List.xlsx
Tree built: 6 L1 nodes, 412 L6 leaves, 68918 PNs attached
Rollups + sorting applied
```

Expected exit code: 0.

---

## Task 4: Add `build_meta`, `self_check`, and `write_json`

**Files:**
- Modify: `scripts/build_pn_tree.py`

- [ ] **Step 1: Add `build_meta`, `self_check`, `write_json`**

Add to `scripts/build_pn_tree.py` (above `def main`):

```python
LEVEL_COLUMNS = ["OH L1", "OH L2", "OH L3", "OH L4", "OH L5", "OH L6"]


def build_meta(rows: list[dict[str, Any]]) -> dict[str, Any]:
    empty_l_names = sum(
        1 for r in rows
        for k in ("l1", "l2", "l3", "l4", "l5", "l6")
        if not str(r.get(k) or "").strip()
    )
    empty_descriptions = sum(1 for r in rows if not r["description"])
    return {
        "source_file": "data/raw/Advanced PN List.xlsx",
        "sheet": "Sheet1",
        "level_columns": LEVEL_COLUMNS,
        "total_pns": len(rows),
        "total_l1": 0,  # filled in by main() after tree built
        "empty_l_names": empty_l_names,
        "empty_descriptions": empty_descriptions,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _walk(node):
    # Accepts either a dict node or a list of nodes (the top-level tree).
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
        return
    yield node
    for c in node.get("children", []):
        yield from _walk(c)


def self_check(tree: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    """Raise ValueError if any invariant is broken. No JSON written if so.

    Uses explicit raises (not assert) so the checks survive `python -O`.
    """
    total_pn = sum(n["pn_count"] for n in tree)
    if total_pn != meta["total_pns"]:
        raise ValueError(
            f"pn_count rollup ({total_pn}) != meta.total_pns ({meta['total_pns']})")

    if len(tree) != 6:
        raise ValueError(f"Expected 6 L1 nodes, got {len(tree)}")

    # depth() returns distance from this node to its deepest leaf.
    # Leaf returns 1; each level above adds 1; L1 returns the max depth.
    def depth(n: dict[str, Any]) -> int:
        if "pns" in n:
            return 1
        return 1 + max((depth(c) for c in n.get("children", [])), default=0)
    depths = [depth(n) for n in tree]
    if max(depths) != 6:
        raise ValueError(f"Max tree depth is {max(depths)}, expected 6")

    for n in _walk(tree):
        if "pns" in n:
            if n["child_count"] != len(n["pns"]):
                raise ValueError(
                    f"child_count mismatch at L6 '{n['name']}': "
                    f"{n['child_count']} vs {len(n['pns'])}")
        else:
            if n["child_count"] != len(n.get("children", [])):
                raise ValueError(
                    f"child_count mismatch at '{n['name']}': "
                    f"{n['child_count']} vs {len(n.get('children', []))}")

    seen: set[str] = set()
    for n in _walk(tree):
        for p in n.get("pns", []):
            if p["pn"] in seen:
                raise ValueError(f"Duplicate PN: {p['pn']}")
            seen.add(p["pn"])
    if len(seen) != meta["total_pns"]:
        raise ValueError(
            f"Distinct PNs ({len(seen)}) != meta.total_pns ({meta['total_pns']})")


def write_json(out_path: Path, meta: dict[str, Any], tree: list[dict[str, Any]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "tree": tree}
    # Atomic write: dump to .tmp, then os.replace. A crash mid-write never
    # leaves a half-written advanced_pn_tree.json on disk.
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, out_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    print(f"Wrote {out_path}", file=sys.stderr)
```

- [ ] **Step 2: Wire meta, self_check, and write_json into `main`**

Replace `main` in `scripts/build_pn_tree.py` with:

```python
def main() -> None:
    args = parse_args()
    rows = load_rows(args.input)
    print(f"Loaded {len(rows)} rows from {args.input}", file=sys.stderr)

    tree = build_tree(rows)
    print(f"Tree built: {len(tree)} L1 nodes, "
          f"{_count_l6_leaves(tree)} L6 leaves, "
          f"{_count_attached_pns(tree)} PNs attached", file=sys.stderr)

    add_rollups_tree(tree)
    sort_tree_root(tree)

    meta = build_meta(rows)
    meta["total_l1"] = len(tree)

    self_check(tree, meta)
    print("Self-checks passed", file=sys.stderr)

    if meta["empty_l_names"]:
        print(f"Warning: {meta['empty_l_names']} empty OH level cells "
              f"(of {6 * meta['total_pns']} possible).", file=sys.stderr)
    if meta["empty_descriptions"]:
        print(f"Warning: {meta['empty_descriptions']} PNs with empty description.",
              file=sys.stderr)

    write_json(args.output, meta, tree)
```

- [ ] **Step 3: Run and verify the JSON is written**

```bash
python scripts/build_pn_tree.py
```

Expected stderr:

```
Loaded 68918 rows from D:\zita\opencode\product-line-auto-selection\data\raw\Advanced PN List.xlsx
Tree built: 6 L1 nodes, 412 L6 leaves, 68918 PNs attached
Self-checks passed
Warning: 64304 empty OH level cells (of 413508 possible).
Wrote D:\zita\opencode\product-line-auto-selection\output\advanced_pn_tree.json
```

Expected exit code: 0.

- [ ] **Step 4: Spot-check the output**

```bash
python -c "import json; d = json.load(open('output/advanced_pn_tree.json', encoding='utf-8')); print(d['meta']); print('L1 names:', [n['name'] for n in d['tree']])"
```

Expected output:

```
{'source_file': 'data/raw/Advanced PN List.xlsx', 'sheet': 'Sheet1', 'level_columns': ['OH L1', 'OH L2', 'OH L3', 'OH L4', 'OH L5', 'OH L6'], 'total_pns': 68918, 'total_l1': 6, 'empty_l_names': 64304, 'empty_descriptions': 0, 'generated_at': '...'}
L1 names: ['AI Solutions', 'Digital Workplace Solutions', 'Global Product Services', 'Hybrid Cloud Services', 'Sustainability Services', 'Vertical Solutions']
```

(The order may vary if alphabetical sort is different in your locale; the 6 names must match.)

---

## Task 5: Create `validate_pn_tree.py`

**Files:**
- Create: `scripts/validate_pn_tree.py`

- [ ] **Step 1: Create the validator script**

Create `scripts/validate_pn_tree.py`:

```python
"""Standalone sanity-check for output/advanced_pn_tree.json.

Prints aggregate stats and 3 sample leaf paths. Does not modify the JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = REPO_ROOT / "output" / "advanced_pn_tree.json"


def _walk(node: dict, depth: int, counts: list[int]) -> None:
    while len(counts) < depth:
        counts.append(0)
    counts[depth - 1] += 1
    for c in node.get("children", []):
        _walk(c, depth + 1, counts)


def _collect_leaf_paths(node: dict, path: list[str], out: list[list[str]]) -> None:
    new_path = path + [node["name"]]
    if "pns" in node:
        out.append(new_path)
        return
    for c in node.get("children", []):
        _collect_leaf_paths(c, new_path, out)


def main() -> None:
    json_path = DEFAULT_JSON
    if not json_path.exists():
        sys.exit(f"JSON not found: {json_path}. Run scripts/build_pn_tree.py first.")

    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)

    meta = data["meta"]
    tree = data["tree"]

    # Per-level node counts.
    level_counts: list[int] = []
    for n in tree:
        _walk(n, 1, level_counts)

    # Distinct PNs across the tree.
    seen: set[str] = set()
    def _gather(node: dict) -> None:
        for p in node.get("pns", []):
            seen.add(p["pn"])
        for c in node.get("children", []):
            _gather(c)
    for n in tree:
        _gather(n)

    # Leaf paths.
    leaf_paths: list[list[str]] = []
    for n in tree:
        _collect_leaf_paths(n, [], leaf_paths)

    print("=" * 60)
    print(f"File:        {json_path}")
    print(f"Size:        {json_path.stat().st_size / (1024 * 1024):.2f} MB")
    print(f"meta.total_pns:    {meta['total_pns']}")
    print(f"distinct PNs:      {len(seen)}  (should equal meta.total_pns)")
    print(f"meta.total_l1:     {meta['total_l1']}")
    print(f"nodes per level:   {level_counts}  (expect [6, 11, 50, 276, 355, 412])")
    print(f"leaf paths (L6):   {len(leaf_paths)}")
    print(f"max depth:         {_depth_of(tree)}")
    print(f"L1 names:          {[n['name'] for n in tree]}")
    print()
    print("Sample leaf paths (L1 -> L2 -> ... -> L6):")
    # pick 3 spread-out leaf paths deterministically.
    sample_idx = [0, len(leaf_paths) // 2, len(leaf_paths) - 1]
    for i in sample_idx:
        print(f"  {' -> '.join(leaf_paths[i])}")
    print("=" * 60)


def _depth_of(tree: list[dict]) -> int:
    def d(n: dict) -> int:
        # Distance from this node to its deepest leaf. Leaf=1, L1=max.
        if "pns" in n:
            return 1
        return 1 + max((d(c) for c in n.get("children", [])), default=0)
    return max((d(n) for n in tree), default=0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the validator**

```bash
python scripts/validate_pn_tree.py
```

Expected output (numbers must match; ordering may vary):

```
============================================================
File:        D:\zita\opencode\product-line-auto-selection\output\advanced_pn_tree.json
Size:        13.05 MB   (actual on disk; depends on description length)
meta.total_pns:    68918
distinct PNs:      68918  (should equal meta.total_pns)
meta.total_l1:     6
nodes per level:   [6, 11, 50, 276, 355, 412]
leaf paths (L6):   412
max depth:         6
L1 names:          ['AI Solutions', 'Digital Workplace Solutions', 'Global Product Services', 'Hybrid Cloud Services', 'Sustainability Services', 'Vertical Solutions']
...
```

Note: `nodes per level` is the count of TREE NODES at each depth, not the count of distinct name strings. L2 names recur under multiple L1s (9 unique strings → 11 nodes), L5 names recur heavily (114 unique strings → 355 nodes), L6 names recur across paths (38 unique strings → 412 nodes). L1/L3/L4 names are globally unique within their parent context.

- [ ] **Step 3: Verify sample leaf paths reference real PNs**

Pick one of the sample leaf paths printed by the validator and verify it exists in the source xlsx. (Pick a path with all 6 levels populated — many leaves have empty L5 or L6, so choose a fully-populated one.)

```bash
python -c "
import openpyxl
wb = openpyxl.load_workbook(r'data\raw\Advanced PN List.xlsx', data_only=True, read_only=True)
ws = wb['Sheet1']
rows = list(ws.iter_rows(values_only=True))
# Pick a fully-populated 6-level path from the validator's sample output
target = ['AI Solutions', 'AI Managed & Professional Services', 'AI Managed Services', 'Enterprise AI Managed Services', 'Agentic AI Managed Services', 'HBB_PN']
# Columns 7..12 (1-indexed) = OH L1..L6
target_cols = [6, 7, 8, 9, 10, 11]  # 0-indexed
hits = [r for r in rows[1:] if all(r[c] == t for c, t in zip(target_cols, target))]
print(f'matching rows in xlsx for target path: {len(hits)}')
print('first 3 PNs:', [r[1] for r in hits[:3]])
"
```

Expected: `matching rows in xlsx for target path: 3` (small N for this specific path — pick a path with many rows if you want a bigger number), and the first 3 PNs are real.

---

## Task 6: Final smoke test

**Files:** (none modified)

- [ ] **Step 1: Re-run both scripts end-to-end**

```bash
Remove-Item output\advanced_pn_tree.json -ErrorAction SilentlyContinue
python scripts/build_pn_tree.py
python scripts/validate_pn_tree.py
```

Expected: build prints all 4 lines, validator prints the stats block. No errors.

- [ ] **Step 2: Verify all 9 success criteria from the spec**

Confirm each by re-reading the relevant output:

| # | Criterion | Verified by |
|---|---|---|
| 1 | `build_pn_tree.py` exits 0 | Last command above |
| 2 | JSON file exists | `Get-ChildItem output/advanced_pn_tree.json` |
| 3 | `meta.total_pns == 68918` | Validator output |
| 4 | Sum of `pn_count` at L1 = `meta.total_pns` | Validator output |
| 5 | Tree depth = 6 | Validator output |
| 6 | 6 distinct L1 names | Validator output |
| 7 | 0 duplicate PNs | Validator output |
| 8 | JSON loads cleanly | Validator ran without error |
| 9 | Spot-checked leaf path matches xlsx | Task 5 Step 3 |

- [ ] **Step 3: Done**

No commit step (project is not a git repo per environment). If a git repo is initialized later, the suggested commit message is:

```
feat: add advanced PN OH tree explorer (build_pn_tree + validate_pn_tree)
```
