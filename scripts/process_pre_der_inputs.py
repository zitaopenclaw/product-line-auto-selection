"""
One-shot converter: data/raw/sales-oppty-talking-script.md → data/converted/sales-voice-inputs.md

Run from project root: python scripts/process_pre_der_inputs.py
Reads the raw talking script (numbered entries with "Sales voice input" headers) and
strips the validation/agent-behavior sections, writing the cleaned voice-input blocks
to the converted file used by run_pre_der_agent.py.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "sales-oppty-talking-script.md"
DST = ROOT / "data" / "converted" / "sales-voice-inputs.md"

lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
voice_starts = [i for i, line in enumerate(lines) if line.strip() == "Sales voice input"]

result = ["# Sales Opportunity Talking Script\n\n"]
for start_idx in voice_starts:
    result.append("⸻\n")
    for j in range(start_idx - 1, -1, -1):
        if re.match(r"^\d+\. ", lines[j].strip()):
            result.append(lines[j])
            break
    result.append("Sales voice input\n")
    end_idx = start_idx + 1
    while end_idx < len(lines) and not (
        "Expected" in lines[end_idx]
        and ("data extraction" in lines[end_idx] or "agent behavior" in lines[end_idx])
    ):
        result.append(lines[end_idx])
        end_idx += 1
result.append("⸻\n")

DST.write_text("".join(result), encoding="utf-8")
print(f"Written {len(voice_starts)} entries → {DST}")
