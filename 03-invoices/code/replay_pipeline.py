"""End-to-end replay of the README pipeline with byte-identity verification.

Runs every deterministic step in the documented order and verifies that the
published artefacts are reproduced exactly (manifest, stream_events,
evaluation, master_data, interactive page, parse log untouched), then
re-executes the notebook and checks for error outputs. Exit 1 on any failure.

Non-regenerable session artefacts (data/runs/llm_parses/, code/parsers_generated/,
data/runs/parse_agent_log.json) are read, never written — see README ⚠️.
Byte-identity of the corpus holds at the pinned Chrome version (manifest).

First run: 3 Jul 2026 — all steps exit 0, six of six hashes identical.
Takes ~15 minutes (Chrome renders all 198 documents).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
PROJ = CODE.parent
failures: list[str] = []


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(script: str, *args: str) -> int:
    r = subprocess.run([sys.executable, "-u", script, *args], cwd=str(CODE),
                       capture_output=True, text=True, timeout=1200)
    tail = (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr).strip() else ""
    print(f"  {script}: exit {r.returncode} -- {tail[:100]}", flush=True)
    if r.returncode != 0:
        failures.append(script)
        print((r.stdout + "\n" + r.stderr)[-1500:], flush=True)
    return r.returncode


TRACKED = {
    "manifest": PROJ / "data" / "manifest.json",
    "stream_events": PROJ / "data" / "runs" / "stream_events.json",
    "evaluation": PROJ / "data" / "runs" / "evaluation.json",
    "page": PROJ / "interactive" / "invoice-processing.html",
    "master": PROJ / "data" / "master_data.json",
    "parse_log": PROJ / "data" / "runs" / "parse_agent_log.json",
}

print("== snapshot pre-replay hashes ==", flush=True)
before = {k: sha(p) for k, p in TRACKED.items()}

print("== replay: README order ==", flush=True)
for step in ("generate_invoices.py", "validate_data.py", "export_master_data.py",
             "extract_text.py", "regression_gate.py", "router.py", "evaluate.py",
             "check_llm_parses.py", "build_interactive_data.py", "build_interactive.py",
             "verify_interactive.py"):
    run(step)

nb = PROJ / "notebooks" / "invoice_processing_analysis.ipynb"
r = subprocess.run([sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute",
                    "--inplace", str(nb)], capture_output=True, text=True, timeout=1200)
print(f"  nbconvert notebook: exit {r.returncode}", flush=True)
if r.returncode != 0:
    failures.append("nbconvert")
    print(r.stderr[-1500:], flush=True)

print("== compare post-replay hashes ==", flush=True)
after = {k: sha(p) for k, p in TRACKED.items()}
for k in before:
    same = before[k] == after[k]
    print(f"  {k}: {'IDENTICAL' if same else 'CHANGED'}", flush=True)
    if not same:
        failures.append(f"hash:{k}")

nbj = json.loads(nb.read_text(encoding="utf-8"))
nerr = sum(1 for c in nbj["cells"] for o in c.get("outputs", []) if o.get("output_type") == "error")
print(f"  notebook error outputs: {nerr}", flush=True)
if nerr:
    failures.append("notebook-errors")

print("\n" + ("REPLAY FAILED: " + ", ".join(failures) if failures else
      "END-TO-END REPLAY CLEAN: every documented step runs, every published artefact reproduced exactly"), flush=True)
sys.exit(1 if failures else 0)
