from __future__ import annotations

import argparse
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.confidence import keep_topk_diverse_tree, score_to_level
from src.field_rules import apply_field_rules_tree, inject_field_candidates_tree
from src.load_data import DERRow, load_der, stratified_sample
from src.load_pn_tree import PNNode, load_pn_nodes, pn_node_embed_text
from src.pre_der_shared import format_candidates_block_v2, node_to_candidate
from src.recall import RecallIndex
from src.rerank import Candidate, RerankClient

OUTPUT_DIR = ROOT / "output" / "der_refinement_agent"
LOG_DIR = ROOT / "logs"
PROMPT_TREE_PATH = ROOT / "prompts" / "rerank_der_tree.txt"

RECALL_TOPK = 60
RERANK_TOPN = 30
CHECKPOINT_EVERY = 20


def log(msg: str, log_path: Path, also_print: bool = True) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    if also_print:
        print(line, flush=True)


def load_progress(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"completed_ids": [], "results": {}}


def save_progress(progress: dict, path: Path) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def md_escape(value) -> str:
    if value is None:
        return ""
    s = str(value)
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    s = s.replace("|", "\\|")
    return s.strip()



def process_one_tree(
    client: RerankClient,
    row: DERRow,
    nodes: list[PNNode],
    index: RecallIndex,
) -> dict:
    """Tree-mode variant: matches DER form description against PN hierarchy nodes (L2/L3/L4)."""
    out: dict = {
        "opportunity_id": row.opportunity_id,
        "bg": row.business_group,
        "description": row.description,
        "topk": [],
        "status": "ok",
        "error": None,
        "provider_used": None,
    }
    try:
        query = row.description or ""
        raw_recall = index.recall(query, topk=RECALL_TOPK)
        rules = apply_field_rules_tree(row, nodes)
        cand_indices = inject_field_candidates_tree(raw_recall, nodes, rules, max_candidates=RERANK_TOPN)
        if not cand_indices:
            out["status"] = "skipped_no_candidates"
            return out

        cand_nodes = [nodes[j] for j in cand_indices]
        cand_objs = [node_to_candidate(n, j) for j, n in zip(cand_indices, cand_nodes)]

        before_stats = client.get_stats()
        scored_raw = client.rerank(query, row.business_group, cand_objs)
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


def render_md_table_tree(rows: list[dict]) -> str:
    header = [
        "Opportunity ID", "BG", "Description",
        "#1 Name", "#1 Level", "#1 Path", "#1 Score", "#1 Conf",
        "#2 Name", "#2 Level", "#2 Path", "#2 Score", "#2 Conf",
        "#3 Name", "#3 Level", "#3 Path", "#3 Score", "#3 Conf",
    ]
    sep = ["---"] * len(header)
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    for row in rows:
        cells = [
            md_escape(row["opportunity_id"]),
            md_escape(row["bg"]),
            md_escape((row.get("description") or "")[:120]),
        ]
        for slot in row["topk"]:
            cells.extend([
                md_escape(slot.get("name")),
                md_escape(slot.get("level")),
                md_escape(slot.get("path_str")),
                f"{slot.get('score', 0.0):.2f}",
                md_escape(slot.get("level_label")),
            ])
        while len(cells) < 3 + 3 * 5:
            cells.append("—")
        lines.append("| " + " | ".join(cells[: 3 + 3 * 5]) + " |")
    return "\n".join(lines)


def build_summary_tree(rows: list[dict], stats: dict, elapsed: float, tag: str) -> str:
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
        f"# Run Summary DER Input AI Agent (tree mode) — {tag}",
        "",
        f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Wall-clock elapsed: {elapsed:.1f}s ({elapsed / 60:.1f} min)",
        "",
        "## Row Coverage",
        "",
        f"- Rows processed: {len(rows)}",
        f"- Rows with ≥1 match: {rows_with_any} ({rows_with_any / max(1, len(rows)) * 100:.1f}%)",
        f"- Rows with zero matches: {rows_with_zero}",
        "",
        "## BG Distribution & Coverage",
        "",
        "| BG | Rows | With Match | Match Rate |",
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
        f"- Potential slots (rows × 3): {potential_slots}",
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
    parser = argparse.ArgumentParser(description="DER Input AI Agent pipeline")
    parser.add_argument("--total", type=int, default=50, help="Max rows to process (default: 50)")
    parser.add_argument("--per-bg", type=int, default=25, help="Max rows per Business Group (default: 25)")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent LLM threads (default: 1)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fresh", action="store_true", help="Ignore checkpoint and restart")
    parser.add_argument("--tag", type=str, default="run", help="Label used in output filenames (default: run)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_path = LOG_DIR / f"{args.tag}.log"
    progress_path = LOG_DIR / f"{args.tag}_progress.json"
    results_path = OUTPUT_DIR / f"results_{args.tag}.json"
    matches_path = OUTPUT_DIR / f"matches_{args.tag}.md"
    summary_path = OUTPUT_DIR / f"summary_{args.tag}.md"

    def _log(msg: str) -> None:
        log(msg, log_path)

    if args.fresh and progress_path.exists():
        progress_path.unlink()
        _log("Fresh run: removed existing checkpoint")

    _log(f"=== DER Input AI Agent START (total={args.total}, per_bg={args.per_bg}, concurrency={args.concurrency}, tag={args.tag}) ===")
    t_start = time.time()

    _log("[1/5] Loading DER data...")
    der = load_der()
    _log(f"  DER={len(der)} rows")

    _log("[2/5] Stratified sampling...")
    sample: list[DERRow] = stratified_sample(der, per_bg=args.per_bg, seed=args.seed)
    if len(sample) > args.total:
        sample = sample[: args.total]
    _log(f"  Sample size: {len(sample)} (target {args.total})")

    _log("[3/5] Loading PN tree nodes...")
    t_idx = time.time()
    nodes = load_pn_nodes()
    _log(f"  Loaded {len(nodes)} named nodes (L2/L3/L4)")
    corpus_texts = [pn_node_embed_text(n) for n in nodes]
    _log("  Building PN tree recall index (BM25 + dense)...")
    tree_index = RecallIndex(corpus_texts=corpus_texts)
    _log(f"  Index built in {time.time() - t_idx:.1f}s")

    _log("[4/5] Initializing rerank client (tree mode → rerank_der_tree.txt)...")
    client = RerankClient(prompt_path=PROMPT_TREE_PATH, format_fn=format_candidates_block_v2)
    _log(f"  Primary: {client.model} @ {client.base_url}")
    _log(f"  Fallback: {client.fallback_model} @ {client.fallback_base_url} (enabled={bool(client.fallback_api_key)})")

    _log("[5/5] Processing (tree mode)...")
    progress = load_progress(progress_path)
    completed_ids: set[str] = set(progress.get("completed_ids", []))
    results: dict[str, dict] = progress.get("results", {})
    pending: list[DERRow] = [
        r for r in sample
        if r.opportunity_id not in completed_ids
        or results.get(r.opportunity_id, {}).get("status") in ("failed", "skipped_no_candidates")
    ]
    _log(f"  Already done: {len(completed_ids)} | Pending: {len(pending)} | Total: {len(sample)}")

    if pending:
        done_count = 0
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            future_to_row = {pool.submit(process_one_tree, client, row, nodes, tree_index): row for row in pending}
            for fut in as_completed(future_to_row):
                row = future_to_row[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {
                        "opportunity_id": row.opportunity_id,
                        "bg": row.business_group,
                        "description": row.description,
                        "topk": [],
                        "status": "failed",
                        "error": f"{type(e).__name__}: {e}",
                        "provider_used": None,
                    }
                results[row.opportunity_id] = res
                completed_ids.add(row.opportunity_id)
                done_count += 1
                if done_count % 10 == 0 or done_count == len(pending):
                    elapsed = time.time() - t_start
                    rate = done_count / max(1e-6, elapsed)
                    eta = (len(pending) - done_count) / max(1e-6, rate)
                    _log(f"  progress {done_count}/{len(pending)} | elapsed={elapsed:.0f}s | rate={rate:.2f}/s | eta={eta:.0f}s | stats={client.get_stats()}")
                if done_count % CHECKPOINT_EVERY == 0 or done_count == len(pending):
                    save_progress({"completed_ids": list(completed_ids), "results": results}, progress_path)

    save_progress({"completed_ids": list(completed_ids), "results": results}, progress_path)
    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"  Checkpoint + JSON saved")

    _log("[final] Rendering outputs (tree mode)...")
    ordered = []
    for r in sample:
        res = results.get(r.opportunity_id, {})
        ordered.append({
            "opportunity_id": r.opportunity_id,
            "bg": r.business_group,
            "description": res.get("description", r.description or ""),
            "topk": res.get("topk", []),
        })
    matches_path.write_text(render_md_table_tree(ordered), encoding="utf-8")
    elapsed = time.time() - t_start
    summary_path.write_text(build_summary_tree(ordered, client.get_stats(), elapsed, args.tag), encoding="utf-8")

    _log(f"  Wrote {matches_path}")
    _log(f"  Wrote {summary_path}")
    _log(f"=== DER Input AI Agent DONE. Total elapsed: {elapsed:.1f}s ({elapsed / 60:.1f} min) ===")
    _log(f"Final stats: {client.get_stats()}")


if __name__ == "__main__":
    main()
