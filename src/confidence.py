from __future__ import annotations

HIGH_THRESHOLD = 0.85
MEDIUM_THRESHOLD = 0.60
LOW_THRESHOLD = 0.40


def score_to_level(score: float) -> str | None:
    if score is None:
        return None
    if score >= HIGH_THRESHOLD:
        return "High"
    if score >= MEDIUM_THRESHOLD:
        return "Medium"
    if score >= LOW_THRESHOLD:
        return "Low"
    return None


def keep_topk(scored: list[dict], k: int = 3) -> list[dict]:
    valid = [c for c in scored if score_to_level(c.get("score")) is not None]
    valid.sort(key=lambda c: -(c.get("score") or 0.0))
    return valid[:k]


def keep_topk_diverse(scored: list[dict], k: int = 3, parent_key: str = "parent_product") -> list[dict]:
    valid = [c for c in scored if score_to_level(c.get("score")) is not None]
    valid.sort(key=lambda c: -(c.get("score") or 0.0))

    result: list[dict] = []
    seen_parents: list[str] = []
    deferred: list[dict] = []

    for c in valid:
        if len(result) >= k:
            break
        parent = (c.get(parent_key) or "").strip() or "(none)"
        seen_count = seen_parents.count(parent)
        if seen_count >= 1:
            deferred.append(c)
            continue
        result.append(c)
        seen_parents.append(parent)

    if len(result) < k:
        for c in deferred:
            if len(result) >= k:
                break
            if c in result:
                continue
            result.append(c)
    if len(result) < k:
        for c in valid:
            if len(result) >= k:
                break
            if c in result:
                continue
            result.append(c)
    return result[:k]


def _is_ancestor_or_descendant(path_a: list[str], path_b: list[str]) -> bool:
    min_len = min(len(path_a), len(path_b))
    if min_len == 0 or path_a == path_b:
        return False
    return path_a[:min_len] == path_b[:min_len]


def keep_topk_diverse_tree(scored: list[dict], k: int = 3) -> list[dict]:
    """Top-k diverse selection that avoids ancestor-descendant pairs.

    Each candidate must have a 'path' field (list[str]).
    """
    valid = [c for c in scored if score_to_level(c.get("score")) is not None]
    valid.sort(key=lambda c: -(c.get("score") or 0.0))

    result: list[dict] = []
    deferred: list[dict] = []

    for c in valid:
        if len(result) >= k:
            break
        path_c = c.get("path") or []
        conflict = any(_is_ancestor_or_descendant(path_c, r.get("path") or []) for r in result)
        if conflict:
            deferred.append(c)
            continue
        result.append(c)

    if len(result) < k:
        for c in deferred:
            if len(result) >= k:
                break
            if c in result:
                continue
            result.append(c)

    if len(result) < k:
        for c in valid:
            if len(result) >= k:
                break
            if c in result:
                continue
            result.append(c)

    return result[:k]
