"""Pipeline tooling — the matcher activation gate.

Four ordered checks, category by category:
  (1) Static checks on the matcher file's SOURCE TEXT ONLY (no import, no
      execution yet — the whole point of doing this first): imports
      resolve to the stdlib allowlist (re, datetime, string, math,
      unicodedata, typing, dataclasses); none of the forbidden tokens
      appear; TRUST equals the commission's; PROVENANCE["induced_from"]
      equals the commission's induction list; a `NoMatch` class is defined
      and raised somewhere. Any failure here stops the gate immediately —
      the matcher module is never imported.
  (2) The module is imported and its `self_test` is run with a loader that
      serves induction contract texts.
  (3) `match` is replayed over EVERY accepted extraction for the category
      (not just induction): disagreement (vs the accepted extraction,
      treated as reference) = FAIL; NoMatch = a coverage miss (counted,
      reported, not a failure).
  (4) One-sided matchers returning `present: False` anywhere during replay
      = FAIL (checked separately from ordinary disagreement).

Writes `data/runs/gate_results/<slug>.json`. On PASS, flips the category's
matcher state to active (active from the next batch, never retroactively).
On FAIL, flips it to 'failed' (frozen and reported). Never touches the
derived key (validate_corpus.py rule 10) — the gate's reference is the
accepted extraction store, not the answer key.

Run: `python regression_gate.py --category "Governing Law"`. Exit code
mirrors PASS (0) / FAIL (1).
"""

from __future__ import annotations

import argparse
import ast
import sys

import pipeline_common as pc
import schemas

ALLOWED_IMPORT_MODULES = {"re", "datetime", "string", "math", "unicodedata", "typing", "dataclasses"}
FORBIDDEN_TOKENS = [
    "open(", "import os", "import sys", "import pathlib", "import random",
    "import time", "requests", "socket", "subprocess", "eval(", "exec(",
]


def run_static_checks(source: str, commission: dict) -> dict:
    """Pure source-text analysis (regex substring search + ast.parse of the
    unexecuted source). Never imports or executes the matcher module."""
    errors: list[str] = []
    forbidden_found = [tok for tok in FORBIDDEN_TOKENS if tok in source]
    if forbidden_found:
        errors.append(f"forbidden token(s) found: {forbidden_found}")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "ok": False,
            "errors": errors + [f"matcher file does not parse as Python: {exc}"],
            "forbidden_tokens_found": forbidden_found,
            "imports_found": [], "disallowed_imports": [],
            "trust_value": None, "trust_ok": False,
            "provenance_induced_from_ok": False,
            "has_nomatch_class": False, "has_raise_nomatch": False,
        }

    imports_found: set[str] = set()
    trust_value = None
    provenance_value = None
    has_nomatch_class = False
    has_raise_nomatch = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports_found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports_found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TRUST":
                    try:
                        trust_value = ast.literal_eval(node.value)
                    except Exception:
                        trust_value = None
                if isinstance(target, ast.Name) and target.id == "PROVENANCE":
                    try:
                        provenance_value = ast.literal_eval(node.value)
                    except Exception:
                        provenance_value = None
        elif isinstance(node, ast.ClassDef) and node.name == "NoMatch":
            has_nomatch_class = True
        elif isinstance(node, ast.Raise):
            exc_node = node.exc
            name = None
            if isinstance(exc_node, ast.Name):
                name = exc_node.id
            elif isinstance(exc_node, ast.Call) and isinstance(exc_node.func, ast.Name):
                name = exc_node.func.id
            if name == "NoMatch":
                has_raise_nomatch = True

    disallowed_imports = sorted(imports_found - ALLOWED_IMPORT_MODULES)
    if disallowed_imports:
        errors.append(f"disallowed import(s) (stdlib allowlist only): {disallowed_imports}")

    trust_ok = trust_value == commission["trust"]
    if not trust_ok:
        errors.append(f"TRUST mismatch: matcher declares {trust_value!r}, commission is {commission['trust']!r}")

    induced_from_value = (
        provenance_value.get("induced_from") if isinstance(provenance_value, dict) else None
    )
    induced_from_ok = induced_from_value is not None and sorted(induced_from_value) == sorted(commission["induction"]["all"])
    if not induced_from_ok:
        errors.append(
            f"PROVENANCE['induced_from'] mismatch: matcher declares {induced_from_value!r}, "
            f"commission induction list is {commission['induction']['all']!r}"
        )

    if not has_nomatch_class:
        errors.append("no `class NoMatch` definition found")
    if not has_raise_nomatch:
        errors.append("no `raise NoMatch(...)` found anywhere in the file")

    return {
        "ok": not errors,
        "errors": errors,
        "forbidden_tokens_found": forbidden_found,
        "imports_found": sorted(imports_found),
        "disallowed_imports": disallowed_imports,
        "trust_value": trust_value,
        "trust_ok": trust_ok,
        "provenance_induced_from_ok": induced_from_ok,
        "has_nomatch_class": has_nomatch_class,
        "has_raise_nomatch": has_raise_nomatch,
    }


def _finalize_gate(paths: pc.Paths, state: dict, category: str, result: dict, passed: bool) -> None:
    pc.write_json(paths.gate_results_dir / f"{result['slug']}.json", result)
    info = state["categories"][category]
    if passed:
        info["status"] = "active"
        info["active_from_batch"] = state["last_accepted_batch"] + 1
        pc.record_history(
            state, category, state["last_accepted_batch"], "active",
            f"gate PASS; active from batch {info['active_from_batch']}",
        )
    else:
        info["status"] = "failed"
        info["failed_at_batch"] = state["last_accepted_batch"]
        pc.record_history(
            state, category, state["last_accepted_batch"], "failed",
            result.get("fail_reason", "gate FAIL"),
        )
    pc.save_matcher_state(paths, state)


def regression_gate(paths: pc.Paths, category: str) -> dict:
    if category not in schemas.CATEGORY_NAMES:
        pc.fail(f"unknown category: {category!r}. Must be one of {schemas.CATEGORY_NAMES}")

    state = pc.load_matcher_state(paths)
    info = state["categories"][category]
    if info["status"] != "commissioned":
        pc.fail(f"category {category!r} is not 'commissioned' (currently {info['status']!r}) — nothing to gate.")

    slug = pc.slugify(category)
    matcher_path = paths.project_dir / info["matcher_path"]
    if not matcher_path.exists():
        pc.fail(f"matcher file not found: {matcher_path} — the overseer has not written it yet.")

    commission_path = paths.commissions_dir / slug / "commission.json"
    commission = pc.read_json(commission_path)

    source = matcher_path.read_text(encoding="utf-8")
    static = run_static_checks(source, commission)

    result = {
        "category": category, "slug": slug, "matcher_path": str(matcher_path),
        "commission_id": commission["id"], "trust": commission["trust"],
        "static": static, "self_test": None, "replay": None, "pass": False,
        "fail_reason": None,
    }

    if not static["ok"]:
        result["fail_reason"] = f"static checks failed: {static['errors']}"
        _finalize_gate(paths, state, category, result, passed=False)
        return result

    # Static checks passed — safe to import and execute the module now.
    module = pc.load_matcher_module(matcher_path)

    def load_text(filename: str) -> str:
        text_path = paths.commissions_dir / slug / "contracts" / filename
        if not text_path.exists():
            raise FileNotFoundError(f"induction contract text not found: {text_path}")
        return text_path.read_text(encoding="utf-8")

    self_test_result = {"ok": True, "error": None}
    try:
        module.self_test(load_text)
    except Exception as exc:
        self_test_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result["self_test"] = self_test_result

    if not self_test_result["ok"]:
        result["fail_reason"] = f"self_test failed: {self_test_result['error']}"
        _finalize_gate(paths, state, category, result, passed=False)
        return result

    # Replay over every accepted extraction for the category.
    replay = {"total": 0, "matched": 0, "coverage_misses": 0,
              "disagreements": [], "one_sided_violations": []}
    trust = commission["trust"]
    all_records = pc.load_all_llm_extractions(paths)
    for contract in sorted(all_records.keys()):
        entry = all_records[contract]["categories"].get(category)
        if entry is None:
            continue
        replay["total"] += 1
        text = pc.read_contract_text(paths, contract)
        matched, matcher_result = pc.call_matcher(module, text)
        if not matched:
            replay["coverage_misses"] += 1
            continue
        # Schema/span validation only here — the one-sided discipline is
        # checked explicitly below, as its own numbered gate criterion
        # (criterion 4 above), so "two-sided" is passed to bypass that branch of
        # validate_matcher_output and isolate schema/span errors.
        errors = pc.validate_matcher_output(category, matcher_result, text, "two-sided")
        if errors:
            replay["disagreements"].append({"contract": contract, "reason": f"invalid output: {errors}"})
            continue
        if trust == "one-sided" and matcher_result.get("present") is False:
            replay["one_sided_violations"].append(contract)
            continue
        comparison = schemas.compare_category(category, matcher_result, entry)
        if comparison["match"]:
            replay["matched"] += 1
        else:
            replay["disagreements"].append({"contract": contract, "reason": comparison["detail"]})

    replay["coverage"] = (replay["matched"] / replay["total"]) if replay["total"] else None
    result["replay"] = replay

    passed = not replay["disagreements"] and not replay["one_sided_violations"]
    if not passed:
        reasons = []
        if replay["disagreements"]:
            reasons.append(f"{len(replay['disagreements'])} disagreement(s)")
        if replay["one_sided_violations"]:
            reasons.append(f"{len(replay['one_sided_violations'])} one-sided present:False violation(s)")
        result["fail_reason"] = "replay failed: " + ", ".join(reasons)
    result["pass"] = passed
    _finalize_gate(paths, state, category, result, passed=passed)
    return result


def print_summary(result: dict) -> None:
    pc.announce(f"Regression gate: {result['category']}")
    print(f"Commission:   {result['commission_id']}   trust: {result['trust']}")
    print(f"Static checks: {'PASS' if result['static']['ok'] else 'FAIL'}")
    if not result["static"]["ok"]:
        for e in result["static"]["errors"]:
            print(f"  - {e}")
    if result["self_test"] is not None:
        print(f"Self-test:     {'PASS' if result['self_test']['ok'] else 'FAIL'}")
        if not result["self_test"]["ok"]:
            print(f"  - {result['self_test']['error']}")
    if result["replay"] is not None:
        r = result["replay"]
        coverage_str = f"{r['coverage']:.1%}" if r["coverage"] is not None else "n/a"
        print(f"Replay:        total={r['total']} matched={r['matched']} "
              f"coverage_misses={r['coverage_misses']} coverage={coverage_str}")
        print(f"               disagreements={len(r['disagreements'])} "
              f"one_sided_violations={len(r['one_sided_violations'])}")
        for d in r["disagreements"]:
            print(f"  DISAGREE  {d['contract']}: {d['reason']}")
        for c in r["one_sided_violations"]:
            print(f"  ONE-SIDED VIOLATION  {c}")
    print(f"\nRESULT: {'PASS' if result['pass'] else 'FAIL'}")
    if result["fail_reason"]:
        print(f"Reason: {result['fail_reason']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the matcher activation gate for one category.")
    parser.add_argument("--category", required=True, help="exact category name, e.g. 'Governing Law'")
    args = parser.parse_args()

    paths = pc.default_paths()
    pc.assert_safe_output_paths(paths)

    result = regression_gate(paths, args.category)
    print_summary(result)
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    # cp1252 console guard (corpus filenames contain combining marks)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
