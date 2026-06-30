from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_feedback_index(path: str | Path) -> dict[str, dict]:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def apply_feedback_signal(
    candidates: list[dict[str, Any]],
    index: dict[str, dict],
    bg: str,
    ab_group: str,
) -> list[dict[str, Any]]:
    """Return new candidate dicts with scores adjusted by feedback signal.

    A-group candidates are returned unchanged (control group).
    B-group candidates get signal δ added to their score, clamped to [0, 1].
    Original dicts are never mutated.
    """
    if ab_group != "B":
        return [dict(c) for c in candidates]

    result = []
    for c in candidates:
        c2 = dict(c)
        key = f"{bg}|{c['node_key']}"
        if key in index:
            signal = index[key].get("signal", 0.0)
            c2["score"] = min(1.0, max(0.0, c["score"] + signal))
        result.append(c2)
    return result
