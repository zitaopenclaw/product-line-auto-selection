from __future__ import annotations

import argparse
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.confidence import keep_topk_diverse_tree, score_to_level
from src.load_pn_tree import PNNode, load_pn_nodes, pn_node_embed_text
from src.parse_voice_input import VoiceInput, extract_descriptions, parse_voice_inputs_md
from src.pre_der_shared import format_candidates_block_v2, node_to_candidate
from src.recall import RecallIndex
from src.rerank import Candidate, RerankClient

PROMPT_V2_PATH = ROOT / "prompts" / "rerank_v2.txt"
OUTPUT_DIR = ROOT / "output" / "pre_der_agent"
LOG_DIR = ROOT / "logs"

RECALL_TOPK = 60
RERANK_TOPN = 30
DEFAULT_INPUT = ROOT / "data" / "converted" / "sales-voice-inputs.md"


def log(msg: str, log_path: Path, also_print: bool = True) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    if also_print:
        print(line, flush=True)


def md_escape(value) -> str:
    if value is None:
        return "—"
    s = str(value)
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    s = s.replace("|", "\\|")
    return s.strip() or "—"


def process_one(
    client: RerankClient,
    vi: VoiceInput,
    nodes: list[PNNode],
    index: RecallIndex,
) -> dict:
    out: dict = {
        "id": vi.id,
        "title": vi.title,
        "bg": vi.bg,
        "raw_text": vi.raw_text,
        "description": vi.description,
        "topk": [],
        "status": "ok",
        "error": None,
        "provider_used": None,
    }
    try:
        query = vi.description or vi.raw_text
        cand_indices = index.recall(query, topk=RECALL_TOPK)[:RERANK_TOPN]
        if not cand_indices:
            out["status"] = "skipped_no_candidates"
            return out

        cand_nodes = [nodes[j] for j in cand_indices]
        cand_objs = [node_to_candidate(n, j) for j, n in zip(cand_indices, cand_nodes)]

        before_stats = client.get_stats()
        scored_raw = client.rerank(query, vi.bg, cand_objs)
        after_stats = client.get_stats()

        if after_stats["minimax_ok"] > before_stats["minimax_ok"]:
            out["provider_used"] = "minimax"
        elif after_stats["fallback_ok"] > before_stats["fallback_ok"]:
            out["provider_used"] = "deepseek"
        else:
            out["provider_used"] = "unknown"

        by_idx = {str(j): n for j, n in zip(cand_indices, cand_nodes)}
        merged = []
        for s in scored_raw:
            n = by_idx.get(s["product_id"])
            if not n:
                continue
            merged.append({
                "node_key": n.node_key,
                "name": n.name,
                "level": f"L{n.level}",
                "path": n.path,
                "path_str": " > ".join(n.path),
                "pn_count": n.pn_count,
                "score": s["score"],
                "level_label": score_to_level(s["score"]),
            })

        out["topk"] = keep_topk_diverse_tree(merged, k=3)
    except Exception as e:
        out["status"] = "failed"
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def render_md_table(rows: list[dict]) -> str:
    header = [
        "#", "Title", "BG", "Extracted Description",
        "#1 Name", "#1 Level", "#1 Path", "#1 Score", "#1 Conf",
        "#2 Name", "#2 Level", "#2 Path", "#2 Score", "#2 Conf",
        "#3 Name", "#3 Level", "#3 Path", "#3 Score", "#3 Conf",
    ]
    sep = ["---"] * len(header)
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    for row in rows:
        cells = [
            str(row["id"]),
            md_escape(row["title"]),
            md_escape(row["bg"]),
            md_escape(row.get("description") or row.get("raw_text", "")[:120]),
        ]
        for slot in row["topk"]:
            cells.extend([
                md_escape(slot.get("name")),
                md_escape(slot.get("level")),
                md_escape(slot.get("path_str")),
                f"{slot.get('score', 0.0):.2f}",
                md_escape(slot.get("level_label")),
            ])
        while len(cells) < 4 + 3 * 5:
            cells.append("—")
        lines.append("| " + " | ".join(cells[: 4 + 3 * 5]) + " |")
    return "\n".join(lines)


def build_summary(rows: list[dict], stats: dict, elapsed: float, tag: str) -> str:
    rows_with_any = sum(1 for r in rows if r["topk"])
    rows_with_zero = len(rows) - rows_with_any
    top1_level_dist: dict[str, int] = {"High": 0, "Medium": 0, "Low": 0, "None": 0}
    kept_level: dict[str, int] = {"High": 0, "Medium": 0, "Low": 0}
    score_buckets = {"≥0.85": 0, "0.60-0.84": 0, "0.40-0.59": 0, "<0.40": 0}
    tree_level_dist: dict[str, int] = {"L2": 0, "L3": 0, "L4": 0}
    all_scores: list[float] = []
    bg_counts: dict[str, int] = {}
    bg_with_match: dict[str, int] = {}

    for r in rows:
        bg = r["bg"]
        bg_counts[bg] = bg_counts.get(bg, 0) + 1
        topk = r["topk"]
        if not topk:
            top1_level_dist["None"] += 1
            continue
        bg_with_match[bg] = bg_with_match.get(bg, 0) + 1
        top1_lvl = topk[0].get("level_label") or "None"
        top1_level_dist[top1_lvl] = top1_level_dist.get(top1_lvl, 0) + 1
        for slot in topk:
            s = slot.get("score", 0.0) or 0.0
            all_scores.append(s)
            lvl = slot.get("level_label")
            if lvl in kept_level:
                kept_level[lvl] += 1
            tree_lvl = slot.get("level", "")
            if tree_lvl in tree_level_dist:
                tree_level_dist[tree_lvl] += 1
            if s >= 0.85:
                score_buckets["≥0.85"] += 1
            elif s >= 0.60:
                score_buckets["0.60-0.84"] += 1
            elif s >= 0.40:
                score_buckets["0.40-0.59"] += 1
            else:
                score_buckets["<0.40"] += 1

    avg = (sum(all_scores) / len(all_scores)) if all_scores else 0.0
    potential_slots = len(rows) * 3
    kept_slots = sum(kept_level.values())

    lines = [
        f"# Run Summary Pre-DER Agent — {tag}",
        "",
        f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Wall-clock elapsed: {elapsed:.1f}s",
        "",
        "## Row Coverage",
        "",
        f"- Inputs processed: {len(rows)}",
        f"- Inputs with ≥1 match: {rows_with_any} ({rows_with_any / max(1, len(rows)) * 100:.1f}%)",
        f"- Inputs with zero matches: {rows_with_zero}",
        "",
        "## BG Distribution & Coverage",
        "",
        "| BG | Inputs | With Match | Match Rate |",
        "| --- | --- | --- | --- |",
    ]
    for bg in sorted(bg_counts):
        rc = bg_counts[bg]
        wc = bg_with_match.get(bg, 0)
        lines.append(f"| {bg} | {rc} | {wc} | {wc / rc * 100:.1f}% |")

    lines += [
        "",
        "## Top-1 Confidence Distribution",
        "",
        "| Level | Count |",
        "| --- | --- |",
    ]
    for lvl in ["High", "Medium", "Low", "None"]:
        lines.append(f"| {lvl} | {top1_level_dist.get(lvl, 0)} |")

    lines += [
        "",
        "## Tree Depth Distribution (all kept slots)",
        "",
        "| OH Level | Count |",
        "| --- | --- |",
    ]
    for tl in ["L2", "L3", "L4"]:
        lines.append(f"| {tl} | {tree_level_dist.get(tl, 0)} |")

    lines += [
        "",
        "## Slot Coverage",
        "",
        f"- Potential slots (inputs × 3): {potential_slots}",
        f"- Kept slots: {kept_slots}",
        f"- Unfilled/Dropped: {potential_slots - kept_slots}",
        f"- Average score (kept): {avg:.3f}",
        "",
        "| Confidence | Count |",
        "| --- | --- |",
    ]
    for lvl in ["High", "Medium", "Low"]:
        lines.append(f"| {lvl} | {kept_level.get(lvl, 0)} |")

    lines += [
        "",
        "## Score Distribution (kept slots)",
        "",
        "| Bucket | Count |",
        "| --- | --- |",
    ]
    for bucket in ["≥0.85", "0.60-0.84", "0.40-0.59", "<0.40"]:
        lines.append(f"| {bucket} | {score_buckets[bucket]} |")

    lines += [
        "",
        "## LLM Provider Stats",
        "",
        f"- MiniMax OK: {stats.get('minimax_ok', 0)}",
        f"- MiniMax fail: {stats.get('minimax_fail', 0)}",
        f"- Fallback (DeepSeek) OK: {stats.get('fallback_ok', 0)}",
        f"- Fallback fail: {stats.get('fallback_fail', 0)}",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Pre-DER Agent pipeline (formerly V2.0): sales voice input → PN tree matching")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT), help="Path to sales-voice-inputs.md")
    parser.add_argument("--tag", type=str, default="pre_der_run", help="Label for output filenames")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent LLM rerank threads")
    parser.add_argument("--no-extract", action="store_true", help="Skip LLM description extraction; use raw voice text")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for PN sampling")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_path = LOG_DIR / f"{args.tag}_pre_der.log"
    results_path = OUTPUT_DIR / f"results_pre_der_{args.tag}.json"
    matches_path = OUTPUT_DIR / f"matches_pre_der_{args.tag}.md"
    summary_path = OUTPUT_DIR / f"summary_pre_der_{args.tag}.md"

    def _log(msg: str) -> None:
        log(msg, log_path)

    _log(f"=== Pre-DER Agent START (tag={args.tag}, concurrency={args.concurrency}, extract={not args.no_extract}) ===")
    t_start = time.time()

    _log("[1/4] Parsing voice inputs...")
    inputs = parse_voice_inputs_md(args.input)
    _log(f"  Parsed {len(inputs)} entries from {args.input}")

    _log("[2/4] Initializing rerank client + building PN tree index...")
    client = RerankClient(prompt_path=PROMPT_V2_PATH, format_fn=format_candidates_block_v2)
    _log(f"  Primary: {client.model} @ {client.base_url}")

    if not args.no_extract:
        _log("  Extracting descriptions via LLM...")
        inputs = extract_descriptions(inputs, verbose=True)
    else:
        _log("  --no-extract: using raw voice text as description")
        for vi in inputs:
            vi.description = vi.raw_text

    _log("  Loading PN tree nodes...")
    nodes = load_pn_nodes(random_seed=args.seed)
    _log(f"  Loaded {len(nodes)} named nodes (L2/L3/L4)")

    corpus_texts = [pn_node_embed_text(n) for n in nodes]
    _log("  Building recall index (BM25 + dense)...")
    t_idx = time.time()
    index = RecallIndex(corpus_texts=corpus_texts)
    _log(f"  Index built in {time.time() - t_idx:.1f}s")

    _log(f"[3/4] Processing {len(inputs)} inputs...")
    results: list[dict] = []
    done_count = 0

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        future_to_vi = {pool.submit(process_one, client, vi, nodes, index): vi for vi in inputs}
        for fut in as_completed(future_to_vi):
            vi = future_to_vi[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {
                    "id": vi.id,
                    "title": vi.title,
                    "bg": vi.bg,
                    "raw_text": vi.raw_text,
                    "description": vi.description,
                    "topk": [],
                    "status": "failed",
                    "error": f"{type(e).__name__}: {e}",
                    "provider_used": None,
                }
            results.append(res)
            done_count += 1
            _log(f"  [{done_count}/{len(inputs)}] #{vi.id} {vi.title[:50]} → status={res['status']} matches={len(res['topk'])}")

    # restore original order
    results.sort(key=lambda r: r["id"])

    _log("[4/4] Writing outputs...")
    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"  → {results_path}")

    matches_path.write_text(render_md_table(results), encoding="utf-8")
    _log(f"  → {matches_path}")

    elapsed = time.time() - t_start
    summary_path.write_text(build_summary(results, client.get_stats(), elapsed, args.tag), encoding="utf-8")
    _log(f"  → {summary_path}")

    _log(f"=== Pre-DER Agent DONE. Elapsed: {elapsed:.1f}s | Provider stats: {client.get_stats()} ===")


if __name__ == "__main__":
    main()
