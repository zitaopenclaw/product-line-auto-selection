from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class FeedbackRecord:
    feedback_id: str
    timestamp: str
    opportunity_id: str
    bg: str
    der_description: str
    scope: str
    service_model: str
    ars_flag: bool
    ai_flag: bool
    candidates_shown: list[dict]
    user_selected_rank: Optional[int]
    is_negative: bool
    negative_hint: Optional[str]
    ab_group: str  # "A" (control) or "B" (feedback-weighted)


class FeedbackStore(ABC):
    @abstractmethod
    def write(self, record: FeedbackRecord) -> None: ...

    @abstractmethod
    def read_all(self) -> list[dict[str, Any]]: ...


class JsonlFeedbackStore(FeedbackStore):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def write(self, record: FeedbackRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        records = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records
