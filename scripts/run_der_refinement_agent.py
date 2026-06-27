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

from src.confidence import keep_topk_diverse, score_to_level
from src.field_rules import FieldRuleResult, apply_field_rules, inject_field_candidates
from src.load_data import DERRow, OHProduct, index_oh_by_bg, load_der, load_oh, stratified_sample
from src.recall import RecallIndex
from src.rerank import Candidate, RerankClient

OUTPUT_DIR = ROOT / "output" / "der_refinement_agent"
LOG_DIR = ROOT / "logs"

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


def build_candidate(p: OHProduct) -> Candidate:
    return Candidate(
        product_id=p.product_id,
        product_name=p.product_name,
        parent_product=p.parent_product,
        solution_category=p.solution_category,
        solution_sub_category=p.solution_sub_category,
        iso=p.iso,
    )


def render_md_table(rows: list[dict]) -> str:
    header = [
        "Opportunity ID", "BG",
        "#1 Product ID", "#1 Product Name", "#1 Parent", "#1 Score", "#1 Level",
        "#2 Product ID", "#2 Product Name", "#2 Parent", "#2 Score", "#2 Level",
        "#3 Product ID", "#3 Product Name", "#3 Parent", "#3 Score", "#3 Level",
    ]
    sep = ["---"] * len(header)
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    for row in rows:
        cells = [md_escape(row["opportunity_id"]), md_escape(row["bg"])]
        for slot in row["topk"]:
            cells.extend([
                md_escape(slot.get("product_id", "—")),
                md_escape(slot.get("product_name", "—")),
                md_escape(slot.get("parent_product", "—")),
                f"{slot.get('score', 0.0):.2f}" if slot.get("score") is not None else "—",
                md_escape(slot.get("level", "—")),
            ])
        while len(cells) < 2 + 3 * 5:
            cells.append("—")
        lines.append("| " + " | ".join(cells[: 2 + 3 * 5]) + " |")
    return "\n".join(lines)


def build_summary(rows: list[dict], stats: dict, elapsed: float, tag: str) -> str:
    rows_processed = len(rows)
    rows_with_any = sum(1 for r in rows if r["topk"])
    rows_with_zero = rows_processed - rows_with_any
    top1_level = {"High": 0, "Medium": 0, "Low": 0, "None": 0}
    kept_level = {"High": 0, "Medium": 0, "Low": 0}
    score_buckets = {"≥0.85": 0, "0.60-0.84": 0, "0.40-0.59": 0, "<0.40": 0}
    all_scores: list[float] = []
    bg_counts: dict[str, int] = {}
    bg_with_match: dict[str, int] = {}
    parent_uniqueness = {"k3_unique": 0, "k3_partial": 0, "k3_same": 0}

    for r in rows:
        bg = r["bg"]
        bg_counts[bg] = bg_counts.get(bg, 0) + 1
        topk = r["topk"]
        if not topk:
            top1_level["None"] += 1
            continue
        bg_with_match[bg] = bg_with_match.get(bg, 0) + 1
        top1_lvl = topk[0].get("level") or "None"
        top1_level[top1_lvl] = top1_level.get(top1_lvl, 0) + 1
        parents = [t.get("parent_product") or "(none)" for t in topk]
        if len(set(parents)) == len(parents):
            parent_uniqueness["k3_unique"] += 1
        elif len(set(parents)) == 1:
            parent_uniqueness["k3_same"] += 1
        else:
            parent_uniqueness["k3_partial"] += 1
        for slot in topk:
            s = slot.get("score", 0.0) or 0.0
            all_scores.append(s)
            lvl = slot.get("level")
            if lvl in kept_level:
                kept_level[lvl] += 1
            if s >= 0.85:
                score_buckets["≥0.85"] += 1
            elif s >= 0.60:
                score_buckets["0.60-0.84"] += 1
            elif s >= 0.40:
                score_buckets["0.40-0.59"] += 1
            else:
                score_buckets["<0.40"] += 1

    potential_slots = rows_processed * 3
    kept_slots = sum(kept_level.values())
    avg = (sum(all_scores) / len(all_scores)) if all_scores else 0.0

    lines = [
        f"# Run Summary — {tag}",
        "",
        f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Wall-clock elapsed: {elapsed:.1f}s ({elapsed / 60:.1f} min)",
        "",
        "## Row Coverage",
        "",
        f"- Rows processed: {rows_processed}",
        f"- Rows with at least one kept candidate: {rows_with_any} ({rows_with_any / max(1, rows_processed) * 100:.1f}%)",
        f"- Rows with zero kept candidates: {rows_with_zero}",
        "",
        "## BG Distribution & Coverage",
        "",
        "| BG | Rows | With Match | Match Rate |",
        "| --- | --- | --- | --- |",
    ]
    for bg in sorted(bg_counts):
        rc = bg_counts.get(bg, 0)
        wc = bg_with_match.get(bg, 0)
        lines.append(f"| {bg} | {rc} | {wc} | {wc / rc * 100:.1f}% |")

    lines += [
        "",
        "## Top-1 Level Distribution",
        "",
        "| Top-1 Level | Count |",
        "| --- | --- |",
    ]
    for lvl in ["High", "Medium", "Low", "None"]:
        lines.append(f"| {lvl} | {top1_level.get(lvl, 0)} |")

    lines += [
        "",
        "## Slot Coverage",
        "",
        f"- Potential slots (rows × 3): {potential_slots}",
        f"- Kept slots: {kept_slots}",
        f"- Unfilled/Dropped slots: {potential_slots - kept_slots}",
        f"- Average score (kept slots): {avg:.3f}",
        "",
        "| Level | Count |",
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
        "## Diversity (Top-3 parent_product uniqueness)",
        "",
        f"- All 3 unique parents: {parent_uniqueness['k3_unique']}",
        f"- 2 unique parents: {parent_uniqueness['k3_partial']}",
        f"- All 3 same parent: {parent_uniqueness['k3_same']}",
        "",
        "## LLM Provider Stats",
        "",
        f"- MiniMax OK: {stats.get('minimax_ok', 0)}",
        f"- MiniMax fail: {stats.get('minimax_fail', 0)}",
        f"- Fallback (DeepSeek) OK: {stats.get('fallback_ok', 0)}",
        f"- Fallback fail: {stats.get('fallback_fail', 0)}",
    ]
    return "\n".join(lines)


def process_one(client: RerankClient, row: DERRow, indexes: dict[str, RecallIndex]) -> dict:
    out: dict = {
        "opportunity_id": row.opportunity_id,
        "bg": row.business_group,
        "description_len": len(row.description or ""),
        "topk": [],
        "status": "ok",
        "error": None,
        "provider_used": None,
        "field_guaranteed": 0,
        "field_boosted": 0,
    }
    idx = indexes.get(row.business_group)
    if idx is None:
        out["status"] = "skipped_no_index"
        return out
    try:
        raw_recall = idx.recall(row.description or "", topk=RECALL_TOPK)
        # Apply Helen's structured-field cascade to inject high-certainty candidates.
        rules = apply_field_rules(row, idx.products)
        cand_indices = inject_field_candidates(raw_recall, idx.products, rules, max_candidates=RERANK_TOPN)
        out["field_guaranteed"] = len(rules.guaranteed_ids)
        out["field_boosted"] = len(rules.boosted_ids)
        cand_products = [idx.products[j] for j in cand_indices]
        cand_objs = [build_candidate(p) for p in cand_products]
        if not cand_objs:
            out["status"] = "skipped_no_candidates"
            return out
        before_stats = client.get_stats()
        scored = client.rerank(row.description or "", row.business_group, cand_objs)
        after_stats = client.get_stats()
        if after_stats["minimax_ok"] > before_stats["minimax_ok"]:
            out["provider_used"] = "minimax"
        elif after_stats["fallback_ok"] > before_stats["fallback_ok"]:
            out["provider_used"] = "deepseek"
        else:
            out["provider_used"] = "unknown"
        by_id = {p.product_id: p for p in cand_products}
        merged = []
        for s in scored:
            p = by_id.get(s["product_id"])
            if not p:
                continue
            merged.append({
                "product_id": p.product_id,
                "product_name": p.product_name,
                "parent_product": p.parent_product,
                "score": s["score"],
                "level": score_to_level(s["score"]) or "None",
            })
        out["topk"] = keep_topk_diverse(merged, k=3)
    except Exception as e:
        out["status"] = "failed"
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def main():
    parser = argparse.ArgumentParser(description="DER Refinement Agent pipeline (formerly V1.0)")
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

    _log(f"=== DER Refinement Agent START (total={args.total}, per_bg={args.per_bg}, concurrency={args.concurrency}, tag={args.tag}) ===")
    t_start = time.time()

    _log("[1/5] Loading data...")
    der = load_der()
    oh = load_oh(drop_retired=True)
    oh_by_bg = index_oh_by_bg(oh)
    _log(f"  DER={len(der)}  OH(active)={len(oh)}  BG={ {k: len(v) for k, v in oh_by_bg.items()} }")

    _log("[2/5] Stratified sampling...")
    sample: list[DERRow] = stratified_sample(der, per_bg=args.per_bg, seed=args.seed)
    if len(sample) > args.total:
        sample = sample[: args.total]
    _log(f"  Sample size: {len(sample)} (target {args.total})")

    _log("[3/5] Building recall indexes...")
    t_idx = time.time()
    sample_by_bg: dict[str, list[DERRow]] = {}
    for r in sample:
        sample_by_bg.setdefault(r.business_group, []).append(r)
    indexes: dict[str, RecallIndex] = {}
    for bg, items in sample_by_bg.items():
        pool = oh_by_bg.get(bg, [])
        if not pool:
            _log(f"  WARNING: no OH pool for BG={bg}")
            continue
        _log(f"  Building index for BG={bg} ({len(pool)} products, {len(items)} queries)")
        indexes[bg] = RecallIndex(pool)
    _log(f"  Index build took {time.time() - t_idx:.1f}s")

    _log("[4/5] Initializing rerank client...")
    client = RerankClient()
    _log(f"  Primary: {client.model} @ {client.base_url}")
    _log(f"  Fallback: {client.fallback_model} @ {client.fallback_base_url} (enabled={bool(client.fallback_api_key)})")

    _log("[5/5] Processing...")
    progress = load_progress(progress_path)
    completed_ids: set[str] = set(progress.get("completed_ids", []))
    results: dict[str, dict] = progress.get("results", {})

    pending: list[DERRow] = [
        r for r in sample
        if r.opportunity_id not in completed_ids
        or results.get(r.opportunity_id, {}).get("status") in ("failed", "skipped_no_index")
    ]
    _log(f"  Already done: {len(completed_ids)} | Pending: {len(pending)} | Total: {len(sample)}")

    if pending:
        done_count = 0
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            future_to_row = {pool.submit(process_one, client, row, indexes): row for row in pending}
            for fut in as_completed(future_to_row):
                row = future_to_row[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {
                        "opportunity_id": row.opportunity_id,
                        "bg": row.business_group,
                        "description_len": len(row.description or ""),
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

    _log("[final] Rendering outputs...")
    ordered = []
    for r in sample:
        res = results.get(r.opportunity_id, {})
        ordered.append({"opportunity_id": r.opportunity_id, "bg": r.business_group, "topk": res.get("topk", [])})

    matches_path.write_text(render_md_table(ordered), encoding="utf-8")
    _log(f"  Wrote {matches_path}")

    elapsed = time.time() - t_start
    summary_path.write_text(build_summary(ordered, client.get_stats(), elapsed, args.tag), encoding="utf-8")
    _log(f"  Wrote {summary_path}")

    _log(f"=== DER Refinement Agent DONE. Total elapsed: {elapsed:.1f}s ({elapsed / 60:.1f} min) ===")
    _log(f"Final stats: {client.get_stats()}")


if __name__ == "__main__":
    main()
