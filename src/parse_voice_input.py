from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
from dotenv import load_dotenv

EXTRACT_PROMPT = """\
Extract a concise 1–3 sentence description of what products or services the customer needs.
Focus on: product type (laptops, servers, tablets, software, services), quantity if mentioned, \
and service scope (deployment, managed services, support, consulting, etc.).
Ignore: customer company names, TCV amounts, dollar values, close dates, CRM actions \
(create/update/open opportunity), probability, and stage labels.
Return only the description text, no preamble, no bullet points.

Sales voice input:
{raw_text}
"""

_DELIMITER_RE = re.compile(r"^[⸻―—\-]{1,}\s*$")
_ENTRY_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$")
_BG_RE = re.compile(r"^BG:\s*(\S+)", re.IGNORECASE)


@dataclass
class VoiceInput:
    id: int
    title: str
    bg: str
    raw_text: str
    description: str = ""


def parse_voice_inputs_md(path: str | Path) -> list[VoiceInput]:
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()

    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _DELIMITER_RE.match(line):
            sections.append(current)
            current = []
        else:
            current.append(line)
    sections.append(current)

    inputs: list[VoiceInput] = []
    for section in sections:
        # strip leading blank lines
        while section and not section[0].strip():
            section.pop(0)
        if not section:
            continue
        m = _ENTRY_RE.match(section[0])
        if not m:
            continue
        entry_id = int(m.group(1))
        title = m.group(2).strip()

        bg = ""
        voice_lines: list[str] = []
        skip_next = False
        for i, line in enumerate(section[1:], 1):
            if bg == "" and _BG_RE.match(line):
                bg = _BG_RE.match(line).group(1)
                continue
            if re.match(r"^Sales voice input\s*$", line, re.IGNORECASE):
                skip_next = False
                continue
            voice_lines.append(line)

        raw_text = "\n".join(voice_lines).strip()
        if raw_text:
            inputs.append(VoiceInput(id=entry_id, title=title, bg=bg, raw_text=raw_text))

    return inputs


def _llm_extract(raw_text: str, api_key: str, base_url: str, model: str, retries: int = 3) -> str:
    prompt = EXTRACT_PROMPT.format(raw_text=raw_text)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise assistant. Output only the requested text."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"LLM extraction failed after {retries} attempts: {last_err}")


def extract_descriptions(inputs: list[VoiceInput], verbose: bool = True) -> list[VoiceInput]:
    load_dotenv()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip()
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()
    if not api_key or api_key == "your_api_key_here":
        raise RuntimeError("DEEPSEEK_API_KEY missing. Check .env")

    for vi in inputs:
        if verbose:
            print(f"  [extract] #{vi.id} {vi.title[:50]}...", flush=True)
        vi.description = _llm_extract(vi.raw_text, api_key, base_url, model)
        if verbose:
            print(f"    → {vi.description[:120]}", flush=True)
    return inputs
