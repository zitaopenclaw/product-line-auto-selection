from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
PN_TREE_PATH = _ROOT / "output" / "advanced_pn_tree.json"
_HW_TREE_PATHS = {
    "IDG": _ROOT / "output" / "idg_pn_tree.json",
    "ISG": _ROOT / "output" / "isg_pn_tree.json",
}
_HW_MAX_DEPTH = {
    "IDG": 4,  # index L2/L3/L4
    "ISG": 3,  # file only has 3 levels; index L2/L3
}


@dataclass
class PNNode:
    name: str
    level: int                           # 2, 3, or 4
    path: list[str]                      # ancestor names from L1 down to this node
    pn_count: int
    sampled_pn_descs: list[str] = field(default_factory=list)
    source_bg: str = ""                  # "IDG" | "ISG" | "" (SSG/service tree)

    @property
    def node_key(self) -> str:
        prefix = f"{self.source_bg}|" if self.source_bg else ""
        return f"{prefix}L{self.level}|{'|'.join(self.path)}"


def _collect_leaf_descs(node: dict) -> list[str]:
    descs: list[str] = []
    if "pns" in node:
        for pn in node["pns"]:
            d = (pn.get("description") or "").strip()
            if d:
                descs.append(d)
    for child in node.get("children", []):
        descs.extend(_collect_leaf_descs(child))
    return descs


def _dfs(
    node: dict,
    depth: int,
    path: list[str],
    out: list[PNNode],
    rng: random.Random,
    max_depth: int = 4,
    source_bg: str = "",
) -> None:
    name = (node.get("name") or "").strip()
    current_path = path + ([name] if name else [])

    if depth >= 2 and name:
        all_descs = _collect_leaf_descs(node)
        sample = rng.sample(all_descs, min(20, len(all_descs))) if all_descs else []
        out.append(PNNode(
            name=name,
            level=depth,
            path=current_path,
            pn_count=node.get("pn_count", 0),
            sampled_pn_descs=sample,
            source_bg=source_bg,
        ))

    if depth < max_depth:
        for child in node.get("children", []):
            _dfs(child, depth + 1, current_path, out, rng,
                 max_depth=max_depth, source_bg=source_bg)


def load_pn_nodes(json_path: str | Path = PN_TREE_PATH, random_seed: int = 42) -> list[PNNode]:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    rng = random.Random(random_seed)
    nodes: list[PNNode] = []
    for l1_node in data.get("tree", []):
        _dfs(l1_node, depth=1, path=[], out=nodes, rng=rng)
    return nodes


def load_hw_nodes(bg: str, random_seed: int = 42) -> list[PNNode]:
    """Load HW catalog nodes for IDG or ISG. Hard-filtered by BG by design.

    IDG: L2/L3/L4 nodes from idg_pn_tree.json
    ISG: L2/L3 nodes from isg_pn_tree.json
    """
    if bg not in _HW_TREE_PATHS:
        raise ValueError(f"No HW catalog for BG={bg!r}. Supported: {list(_HW_TREE_PATHS)}")
    json_path = _HW_TREE_PATHS[bg]
    if not json_path.exists():
        raise FileNotFoundError(
            f"HW tree not found: {json_path}. "
            f"Run scripts/build_{bg.lower()}_tree.py first."
        )
    data = json.loads(json_path.read_text(encoding="utf-8"))
    rng = random.Random(random_seed)
    nodes: list[PNNode] = []
    max_depth = _HW_MAX_DEPTH[bg]
    for l1_node in data.get("tree", []):
        _dfs(l1_node, depth=1, path=[], out=nodes, rng=rng,
             max_depth=max_depth, source_bg=bg)
    return nodes


def pn_node_embed_text(node: PNNode) -> str:
    path_str = " > ".join(node.path)
    parts = [node.name, f"path: {path_str}"]
    if node.sampled_pn_descs:
        parts.append("pns: " + ", ".join(node.sampled_pn_descs[:20]))
    return " | ".join(parts)
