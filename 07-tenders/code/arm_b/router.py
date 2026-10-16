"""Arm B routing (workflow step 5) -- Project 7.

After gates.py has been run at least once against a run_dir, router.py
decides the run's terminal state and writes signoff.json -- "the thing a
named human signs". It never edits matrix.json or any
response_v*.json; it only reads the artifacts gates.py and the run-agent
already produced.

The routing, applied verbatim:
  - gate_report says pass=True, response.no_bid=False  -> status "submitted",
    bid_no_bid "BID".
  - gate_report says pass=True, response.no_bid=True    -> status "no_bid",
    bid_no_bid "NO_BID".
  - No gate_report has passed and the run-agent has already produced
    response_v{MAX_ITERATIONS}.json (the protocol's cap) -> status "stuck",
    bid_no_bid "UNRESOLVED", recorded honestly rather than forced to a
    false pass.
  - No gate_report has passed and the cap has not been reached -> NOT a
    terminal state; router.py refuses to write signoff.json and tells the
    run-agent to keep iterating.

Usage:
    python router.py <run_dir>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ARM_B_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ARM_B_DIR))
from gates import MAX_ITERATIONS  # noqa: E402  (reuse the same constant)


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Required file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc


def list_gate_reports(run_dir: Path) -> list[tuple[int, Path]]:
    reports = []
    for path in run_dir.glob("gate_report_*.json"):
        match = re.match(r"gate_report_(\d+)\.json$", path.name)
        if match:
            reports.append((int(match.group(1)), path))
    return sorted(reports)


def list_response_versions(run_dir: Path) -> list[int]:
    versions = []
    for path in run_dir.glob("response_v*.json"):
        match = re.match(r"response_v(\d+)\.json$", path.name)
        if match:
            versions.append(int(match.group(1)))
    return sorted(versions)


def infer_tender_id(run_dir: Path, matrix: list[dict]) -> str:
    """run_NN <-> T{NN} by convention. Falls back to reading
    tender_id off matrix rows if a future matrix.json variant carries one,
    since neither the run-agent nor matrix.json is required to name it."""
    match = re.match(r"run_(\d+)$", run_dir.name)
    if match:
        return f"T{match.group(1)}"
    for row in matrix:
        if row.get("tender_id"):
            return row["tender_id"]
    return "UNKNOWN"


def route(run_dir: Path) -> dict:
    matrix_path = run_dir / "matrix.json"
    matrix = load_json(matrix_path)
    if not isinstance(matrix, list):
        raise SystemExit(f"{matrix_path} must be a JSON array of matrix rows")

    gate_reports = list_gate_reports(run_dir)
    if not gate_reports:
        raise SystemExit(
            f"No gate_report_*.json found in {run_dir} -- run gates.py at "
            f"least once before router.py."
        )

    response_versions = list_response_versions(run_dir)
    total_bounces = 0
    passing_report = None
    latest_iteration = 0

    for iteration, path in gate_reports:
        report = load_json(path)
        total_bounces += len(report.get("bounces", []))
        latest_iteration = max(latest_iteration, iteration)
        if report.get("pass"):
            passing_report = (iteration, report)

    tender_id = infer_tender_id(run_dir, matrix)

    if passing_report is not None:
        iteration, report = passing_report
        response_path = run_dir / f"response_v{iteration}.json"
        response = load_json(response_path)
        no_bid = bool(response.get("no_bid"))
        return {
            "tender_id": tender_id,
            "status": "no_bid" if no_bid else "submitted",
            "bid_no_bid": "NO_BID" if no_bid else "BID",
            "coverage_pct": report.get("coverage_pct"),
            "gates_passed": True,
            "bounce_count": total_bounces,
            "iterations": iteration,
            "unresolved_flags": [],
            "no_bid_reason": response.get("no_bid_reason") if no_bid else None,
        }

    # No passing report yet.
    max_response_version = max(response_versions) if response_versions else 0
    if max_response_version >= MAX_ITERATIONS or latest_iteration >= MAX_ITERATIONS:
        latest_report_path = run_dir / f"gate_report_{latest_iteration}.json"
        latest_report = load_json(latest_report_path)
        open_bounce_types = sorted({b.get("type", "UNKNOWN") for b in latest_report.get("bounces", [])})
        return {
            "tender_id": tender_id,
            "status": "stuck",
            "bid_no_bid": "UNRESOLVED",
            "coverage_pct": latest_report.get("coverage_pct"),
            "gates_passed": False,
            "bounce_count": total_bounces,
            "iterations": latest_iteration,
            "unresolved_flags": ["max_iterations_exceeded"] + open_bounce_types,
            "no_bid_reason": None,
        }

    # Not terminal -- refuse to write a signoff.
    raise SystemExit(
        f"[router] run {run_dir.name} has not passed gates yet (latest iteration "
        f"{latest_iteration}/{MAX_ITERATIONS}). Not a terminal state -- the "
        f"run-agent should revise response_v{latest_iteration}.json per its "
        f"gate_report and resubmit. router.py will not write signoff.json "
        f"until gates pass or the iteration cap is reached."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()

    run_dir: Path = args.run_dir
    if not run_dir.is_dir():
        raise SystemExit(f"Not a directory: {run_dir}")

    try:
        signoff = route(run_dir)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[router] ERROR: {exc}", file=sys.stderr)
        return 2

    out_path = run_dir / "signoff.json"
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(signoff, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(f"[router] {run_dir.name}: status={signoff['status']} "
          f"bid_no_bid={signoff['bid_no_bid']} coverage={signoff['coverage_pct']}% "
          f"bounces={signoff['bounce_count']} iterations={signoff['iterations']}")
    print(f"[router] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
