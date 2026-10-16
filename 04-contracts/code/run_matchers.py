"""Pipeline tooling — run every active matcher over a held-out
set.

Runs all *active* matchers over the 100 holdout contracts (never read by
the model) and writes
`data/runs/matcher_outputs_holdout/<stem>.json`, one file per contract,
accumulated per category, in the same shape as the stream's matcher-output
store. Same validation as the stream (schema shape, verbatim spans,
one-sided discipline) — but a violation here does NOT demote anything (the
stream is over, there is nothing left to fall back to); it is recorded and
reported as a holdout failure. Also writes a per-category coverage summary
(answered vs NoMatch vs violation) to `data/runs/holdout_coverage.json`.

Pipeline-facing: never references the derived key (validate_corpus.py rule
10) — this script only ever measures what the matchers themselves say.

Run: `python run_matchers.py --set holdout`.
"""

from __future__ import annotations

import argparse

import pipeline_common as pc


def run_matchers_holdout(paths: pc.Paths) -> dict:
    manifest = pc.load_manifest(paths)
    holdout = pc.holdout_contracts(manifest)
    state = pc.load_matcher_state(paths)
    active_categories = sorted(
        cat for cat, info in state["categories"].items() if info["status"] == "active"
    )

    coverage = {
        cat: {"answered": 0, "nomatch": 0, "violations": 0, "total": len(holdout)}
        for cat in active_categories
    }
    violations_log: list[dict] = []

    for contract in holdout:
        text = pc.read_contract_text(paths, contract)
        for cat in active_categories:
            info = state["categories"][cat]
            module = pc.load_matcher_module(paths.project_dir / info["matcher_path"])
            matched, result = pc.call_matcher(module, text)
            if not matched:
                coverage[cat]["nomatch"] += 1
                continue
            errors = pc.validate_matcher_output(cat, result, text, info["trust"])
            entry = dict(result)
            entry["path"] = "matcher"
            entry["matcher_id"] = info["matcher_id"]
            entry["trust"] = info["trust"]
            if errors:
                entry["violations"] = errors
                coverage[cat]["violations"] += 1
                violations_log.append({"contract": contract, "category": cat, "errors": errors})
                print(f"HOLDOUT VIOLATION  {cat} / {contract}: {errors}")
            else:
                coverage[cat]["answered"] += 1
            pc.merge_matcher_output(paths, contract, cat, entry, holdout=True)

    pc.write_json(paths.holdout_coverage_path, {
        "holdout_size": len(holdout),
        "active_categories": active_categories,
        "coverage": coverage,
        "violations": violations_log,
    })

    return {
        "holdout_size": len(holdout),
        "active_categories": active_categories,
        "coverage": coverage,
        "violations": violations_log,
    }


def print_summary(summary: dict) -> None:
    pc.announce("Holdout matcher run")
    print(f"Holdout size: {summary['holdout_size']}")
    if not summary["active_categories"]:
        print("No active matchers yet — nothing to run.")
        return
    print("\nPer-category coverage (answered / nomatch / violations / total):")
    for cat in summary["active_categories"]:
        c = summary["coverage"][cat]
        print(f"  {cat:28s} answered={c['answered']:3d} nomatch={c['nomatch']:3d} "
              f"violations={c['violations']:3d} total={c['total']:3d}")
    if summary["violations"]:
        print(f"\nHoldout violations (recorded, not demoted — the stream is over): {len(summary['violations'])}")
        for v in summary["violations"]:
            print(f"  {v['category']} / {v['contract']}: {v['errors']}")
    else:
        print("\nHoldout violations: none")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run every active matcher over a held-out set.")
    parser.add_argument("--set", required=True, choices=["holdout"], help="only 'holdout' is supported")
    args = parser.parse_args()

    paths = pc.default_paths()
    pc.assert_safe_output_paths(paths)

    summary = run_matchers_holdout(paths)
    print_summary(summary)
    print("\nrun_matchers.py completed successfully.")


if __name__ == "__main__":
    main()
