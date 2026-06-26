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
        sys.exit(f"JSON not found: {json_path}. Run scripts/build_pre_der_pn_tree.py first.")

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