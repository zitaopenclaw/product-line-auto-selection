"""Aggregate feedback JSONL → feedback_index.json.

Usage:
    python scripts/aggregate_feedback.py                   # default paths
    python scripts/aggregate_feedback.py --feedback-path output/feedback/feedback.jsonl \
                                          --index-path output/feedback/feedback_index.json
    python scripts/aggregate_feedback.py --dry-run         # print index without writing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.feedback_store import JsonlFeedbackStore
from src.feedback_aggregator import FeedbackAggregator

DEFAULT_FEEDBACK = ROOT / "output" / "feedback" / "feedback.jsonl"
DEFAULT_INDEX = ROOT / "output" / "feedback" / "feedback_index.json"


def run(feedback_path: Path, index_path: Path, dry_run: bool = False) -> dict:
    store = JsonlFeedbackStore(feedback_path)
    records = store.read_all()
    print(f"[aggregate] Loaded {len(records)} feedback records from {feedback_path}")

    agg = FeedbackAggregator(records)
    index = agg.build()
    print(f"[aggregate] Built index with {len(index)} node entries")

    if dry_run:
        print(json.dumps(index, indent=2, ensure_ascii=False))
    else:
        agg.save(index_path, index)
        print(f"[aggregate] Saved feedback_index → {index_path}")

    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate feedback JSONL → feedback_index.json")
    parser.add_argument("--feedback-path", type=Path, default=DEFAULT_FEEDBACK)
    parser.add_argument("--index-path", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--dry-run", action="store_true", help="Print index without writing")
    args = parser.parse_args()
    run(args.feedback_path, args.index_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
