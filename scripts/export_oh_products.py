"""Export active OH products from xlsx to JSON files, partitioned by BG.

Writes:
  output/oh_products.json          -- all active OH products (combined)
  output/oh_products_IDG.json      -- IDG only
  output/oh_products_DCG.json      -- DCG only
  output/oh_products_SSG.json      -- SSG only

Run once locally before building the Docker image:
  python scripts/export_oh_products.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "output"

from src.load_data import load_oh


def main() -> None:
    print("Loading active OH products from xlsx...")
    products = load_oh(drop_retired=True)
    print(f"  Loaded {len(products)} active products")

    by_bg: dict[str, list] = {}
    for p in products:
        by_bg.setdefault(p.business_group, []).append(asdict(p))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Combined
    all_dicts = [asdict(p) for p in products]
    (OUTPUT_DIR / "oh_products.json").write_text(
        json.dumps(all_dicts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Saved oh_products.json ({len(all_dicts)} products)")

    # Per-BG
    for bg, items in sorted(by_bg.items()):
        fname = f"oh_products_{bg}.json"
        (OUTPUT_DIR / fname).write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Saved {fname} ({len(items)} products)")

    print("\nDone.")
    print(f"BG breakdown: { {bg: len(v) for bg, v in sorted(by_bg.items())} }")


if __name__ == "__main__":
    main()
