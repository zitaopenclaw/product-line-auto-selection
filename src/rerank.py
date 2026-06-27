from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from dotenv import load_dotenv

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "rerank.txt"

FormatFn = callable


@dataclass
class Candidate:
    product_id: str
    product_name: str
    parent_product: str | None = None
    solution_category: str | None = None
    solution_sub_category: str | None = None
    iso: str | None = None


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str


def load_prompt_template(path: Path = PROMPT_PATH) -> str:
    return path.read_text(encoding="utf-8")


def format_candidates_block(cands: Iterable[Candidate]) -> str:
    lines = []
    for i, c in enumerate(cands, 1):
        meta = []
        if c.parent_product:
            meta.append(f"parent={c.parent_product}")
        if c.solution_category:
            meta.append(f"category={c.solution_category}")
        if c.solution_sub_category:
            meta.append(f"subcat={c.solution_sub_category}")
        if c.iso:
            meta.append(f"ISO={c.iso}")
        meta_s = " | ".join(meta)
        lines.append(f"{i}. name={c.product_name}" + (f" | {meta_s}" if meta_s else ""))
    return "\n".join(lines)


def render_prompt(
    description: str,
    business_group: str,
    cands: list[Candidate],
    prompt_path: Path = PROMPT_PATH,
    format_fn=None,
) -> str:
    tmpl = load_prompt_template(prompt_path)
    block = (format_fn or format_candidates_block)(cands)
    return tmpl.format(
        business_group=business_group,
        description=(description or "").strip()[:2000],
        candidates_block=block,
        n_candidates=len(cands),
    )


def _extract_json(text: str) -> dict:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start:end + 1])
        raise


class RerankClient:
    def __init__(self, prompt_path: Path | None = None, format_fn=None):
        self._prompt_path = prompt_path or PROMPT_PATH
        self._format_fn = format_fn
        load_dotenv()
        self.api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
        self.base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1").rstrip("/")
        self.model = os.environ.get("MINIMAX_MODEL", "MiniMax-M3")
        if not self.api_key or self.api_key == "your_api_key_here":
            raise RuntimeError(
                "MINIMAX_API_KEY missing or unset. Check .env / environment."
            )
        self.fallback_api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.fallback_base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
        self.fallback_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self._stats_lock = threading.Lock()
        self._stats = {
            "minimax_ok": 0,
            "minimax_fail": 0,
            "fallback_ok": 0,
            "fallback_fail": 0,
        }

    def get_stats(self) -> dict:
        with self._stats_lock:
            return dict(self._stats)

    def _post(self, provider: ProviderConfig, payload: dict, timeout: int = 60) -> dict:
        url = f"{provider.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _call_provider(
        self,
        provider: ProviderConfig,
        description: str,
        business_group: str,
        cands: list[Candidate],
        max_retries: int = 3,
        sleep_s: float = 1.5,
    ) -> list[dict]:
        prompt = render_prompt(description, business_group, cands, self._prompt_path, self._format_fn)
        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": "You are a precise product-matching expert. Output strict JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
        }
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                data = self._post(provider, payload)
                content = data["choices"][0]["message"]["content"]
                parsed = _extract_json(content)
                items = parsed.get("candidates", [])
                out = []
                seen_nos = set()
                for item in items:
                    no = item.get("candidate_no")
                    if not isinstance(no, int):
                        try:
                            no = int(no)
                        except (TypeError, ValueError):
                            continue
                    if no < 1 or no > len(cands):
                        continue
                    if no in seen_nos:
                        continue
                    seen_nos.add(no)
                    cand = cands[no - 1]
                    try:
                        score = float(item.get("score", 0.0))
                    except (TypeError, ValueError):
                        score = 0.0
                    out.append({
                        "product_id": cand.product_id,
                        "score": max(0.0, min(1.0, score)),
                    })
                return out
            except Exception as e:
                last_err = e
                time.sleep(sleep_s * (attempt + 1))
        raise RuntimeError(f"provider {provider.name} failed after {max_retries} attempts: {last_err}")

    def rerank(
        self,
        description: str,
        business_group: str,
        cands: list[Candidate],
    ) -> list[dict]:
        if not cands:
            return []
        primary = ProviderConfig(
            name="minimax",
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
        )
        try:
            res = self._call_provider(primary, description, business_group, cands)
            with self._stats_lock:
                self._stats["minimax_ok"] += 1
            return res
        except Exception as primary_err:
            with self._stats_lock:
                self._stats["minimax_fail"] += 1
            if not self.fallback_api_key or self.fallback_api_key == "your_api_key_here":
                raise primary_err
            fallback = ProviderConfig(
                name="minimax",
                base_url=self.fallback_base_url,
                api_key=self.fallback_api_key,
                model=self.fallback_model,
            )
            try:
                res = self._call_provider(fallback, description, business_group, cands)
                with self._stats_lock:
                    self._stats["fallback_ok"] += 1
                return res
            except Exception as fb_err:
                with self._stats_lock:
                    self._stats["fallback_fail"] += 1
                raise RuntimeError(
                    f"Both primary and fallback failed. primary={primary_err}; fallback={fb_err}"
                ) from fb_err
