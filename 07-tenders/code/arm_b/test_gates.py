"""Dry test for the Arm B gates (Project 7, Phase 4 build step).

Proves gates.py actually catches what the workflow design requires it to catch,
against a tiny synthetic fixture (code/arm_b/fixtures/) that is NOT part of
the Project 7 corpus -- a throwaway 3-requirement mini-tender and mini
facts library, structurally identical in shape to the real
company_facts.yaml so the real resolver/parsing code is exercised end to
end, not a mocked-out shortcut.

Five outcomes are asserted, one per fixture run directory under
code/arm_b/fixtures/runs/:
  - unanswered_row          -> coverage gate fails (UNANSWERED_ROW)
  - uncited_claim           -> facts gate fails (FABRICATION, eur_amount)
  - fabricated_cert         -> facts gate fails (FABRICATION, certification
                                 held=false -- proves the gate checks the
                                 held flag, not just substring containment)
  - cross_row_inconsistency -> consistency gate fails (CROSS_ROW_INCONSISTENCY)
                                 (this fixture ALSO trips the facts gate,
                                 since at most one of the two conflicting
                                 claims can be true against the single real
                                 fact -- documented, not a test bug: a false
                                 claim about a shared fact is simultaneously
                                 a fabrication AND inconsistent with its
                                 sibling row, and a correct implementation
                                 should flag both)
  - clean_pass              -> all three gates pass, zero bounces

A handful of resolve_fact_path() unit checks are included directly (the
top-level "references" alias, case-insensitive list-item matching) since
those are load-bearing for the facts gate and easy to silently break.

Run: python test_gates.py
Exits 0 if every assertion passes, 1 otherwise (matching
validate_structure.py elsewhere in this project).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gates import (  # noqa: E402
    FactPathError,
    load_facts,
    resolve_fact_path,
    run_gates,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RUNS_DIR = FIXTURES_DIR / "runs"
MINI_FACTS_PATH = FIXTURES_DIR / "mini_facts.yaml"

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def bounce_types(report: dict) -> set[str]:
    return {b["type"] for b in report["bounces"]}


def bounce_types_for(report: dict, matrix_id: str) -> set[str]:
    return {b["type"] for b in report["bounces"] if b.get("matrix_id") == matrix_id}


# ---------------------------------------------------------------------------
# 1. resolve_fact_path unit checks
# ---------------------------------------------------------------------------

def test_resolve_fact_path() -> None:
    print("\n== resolve_fact_path unit checks ==")
    facts = load_facts(MINI_FACTS_PATH)

    check(
        "plain dict path resolves",
        resolve_fact_path(facts, "company.employee_count") == 50,
    )
    check(
        "list-item path by code resolves (exact case)",
        resolve_fact_path(facts, "certifications.NMSB7310")["held"] is True,
    )
    check(
        "list-item path by code resolves (case-insensitive, documented example)",
        resolve_fact_path(facts, "certifications.nmsb7310")["held"] is True,
    )
    check(
        "nested list-item scalar path resolves",
        resolve_fact_path(facts, "reference_projects.REF01.value_eur") == 400000,
    )
    check(
        '"references" alias resolves to reference_projects (documented example)',
        resolve_fact_path(facts, "references.REF01.value_eur") == 400000,
    )
    check(
        "dict-keyed-by-kind path resolves",
        resolve_fact_path(facts, "insurances.liability.cover_eur") == 1000000,
    )
    check(
        "year-keyed list path resolves",
        resolve_fact_path(facts, "financials.2025.revenue_eur") == 5000000,
    )

    try:
        resolve_fact_path(facts, "certifications.NOPE")
        check("nonexistent path raises FactPathError", False, "did not raise")
    except FactPathError:
        check("nonexistent path raises FactPathError", True)


# ---------------------------------------------------------------------------
# 2. The five fixture outcomes
# ---------------------------------------------------------------------------

def test_unanswered_row() -> None:
    print("\n== fixture: unanswered_row (coverage gate) ==")
    report = run_gates(RUNS_DIR / "unanswered_row", MINI_FACTS_PATH)
    check("overall gate report fails", report["pass"] is False)
    check("coverage gate specifically fails", report["gates"]["coverage"] is False)
    check(
        "M003 bounced as UNANSWERED_ROW",
        "UNANSWERED_ROW" in bounce_types_for(report, "M003"),
        f"bounces: {report['bounces']}",
    )


def test_uncited_claim() -> None:
    print("\n== fixture: uncited_claim (facts gate, eur_amount) ==")
    report = run_gates(RUNS_DIR / "uncited_claim", MINI_FACTS_PATH)
    check("overall gate report fails", report["pass"] is False)
    check("facts gate specifically fails", report["gates"]["facts"] is False)
    check(
        "M002's uncited EUR claim bounced as FABRICATION",
        "FABRICATION" in bounce_types_for(report, "M002"),
        f"bounces: {report['bounces']}",
    )
    check(
        "coverage gate still passes (row IS answered, just uncited)",
        report["gates"]["coverage"] is True,
    )


def test_fabricated_cert() -> None:
    print("\n== fixture: fabricated_cert (facts gate, held=false) ==")
    report = run_gates(RUNS_DIR / "fabricated_cert", MINI_FACTS_PATH)
    check("overall gate report fails", report["pass"] is False)
    check("facts gate specifically fails", report["gates"]["facts"] is False)
    check(
        "M001's NMSB 73710 claim bounced as FABRICATION (held=false, not mere absence)",
        "FABRICATION" in bounce_types_for(report, "M001"),
        f"bounces: {report['bounces']}",
    )


def test_cross_row_inconsistency() -> None:
    print("\n== fixture: cross_row_inconsistency (consistency gate) ==")
    report = run_gates(RUNS_DIR / "cross_row_inconsistency", MINI_FACTS_PATH)
    check("overall gate report fails", report["pass"] is False)
    check("consistency gate specifically fails", report["gates"]["consistency"] is False)
    check(
        "CROSS_ROW_INCONSISTENCY bounce present",
        "CROSS_ROW_INCONSISTENCY" in bounce_types(report),
        f"bounces: {report['bounces']}",
    )
    # Documented, not a bug: the row claiming the wrong figure (M003, EUR
    # 4,500,000 against a true EUR 5,000,000) also fails the facts gate.
    check(
        "facts gate also (correctly) flags the wrong-valued row as FABRICATION",
        "FABRICATION" in bounce_types_for(report, "M003"),
        f"bounces: {report['bounces']}",
    )


def test_clean_pass() -> None:
    print("\n== fixture: clean_pass (all gates) ==")
    report = run_gates(RUNS_DIR / "clean_pass", MINI_FACTS_PATH)
    check("overall gate report passes", report["pass"] is True, f"bounces: {report['bounces']}")
    check("coverage gate passes", report["gates"]["coverage"] is True)
    check("facts gate passes", report["gates"]["facts"] is True)
    check("consistency gate passes", report["gates"]["consistency"] is True)
    check("zero bounces", report["bounces"] == [], f"bounces: {report['bounces']}")
    check("coverage_pct is 100.0", report["coverage_pct"] == 100.0)


def main() -> int:
    print("Running Arm B gates dry test against code/arm_b/fixtures/ ...")
    test_resolve_fact_path()
    test_unanswered_row()
    test_uncited_claim()
    test_fabricated_cert()
    test_cross_row_inconsistency()
    test_clean_pass()

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s) did not pass:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1

    print("ALL CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
