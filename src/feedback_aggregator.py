from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

MIN_SAMPLES = 5
DELTA_CAP = 0.15


class FeedbackAggregator:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        # Only B-group records influence the signal
        self._records = [r for r in records if r.get("ab_group") == "B"]

    def build(self) -> dict[str, dict]:
        """Aggregate feedback records into a signal index keyed by 'BG|node_key'."""
        counts: dict[str, dict] = defaultdict(lambda: {"pos": 0, "neg": 0})

        for rec in self._records:
            bg = rec.get("bg", "")
            selected_rank = rec.get("user_selected_rank")
            is_negative = rec.get("is_negative", False)
            candidates = rec.get("candidates_shown", [])

            if is_negative or selected_rank is None:
                # Negative signal for every candidate shown
                for c in candidates:
                    key = f"{bg}|{c['node_key']}"
                    counts[key]["neg"] += 1
            else:
                # Positive signal only for the selected node
                for c in candidates:
                    if c["rank"] == selected_rank:
                        key = f"{bg}|{c['node_key']}"
                        counts[key]["pos"] += 1
                        break

        index: dict[str, dict] = {}
        for key, cnt in counts.items():
            pos, neg = cnt["pos"], cnt["neg"]
            total = pos + neg
            if total < MIN_SAMPLES:
                signal = 0.0
            else:
                signal = (pos - neg) / total * DELTA_CAP
            index[key] = {"pos": pos, "neg": neg, "signal": round(signal, 6)}

        return index

    def save(self, path: str | Path, index: dict[str, dict]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
