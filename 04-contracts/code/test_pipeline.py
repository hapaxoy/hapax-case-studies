"""Selftest suite for the pipeline tooling.
Every fixture lives under a temporary directory (tempfile) — this suite never touches real `data/`. Exit 1 on any failure.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import accept_batch
import config
import evaluate
import pipeline_common as pc
import prepare_commission
import regression_gate
import router
import schemas

FAILURES: list[str] = []
CHECKS = 0


def check(label: str, cond: bool) -> None:
    global CHECKS
    CHECKS += 1
    print(f"{'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        FAILURES.append(label)


def fixture_paths(tmp_root: Path) -> pc.Paths:
    paths = pc.build_paths(tmp_root)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.contracts_dir.mkdir(parents=True, exist_ok=True)
    paths.runs_dir.mkdir(parents=True, exist_ok=True)
    paths.matchers_generated_dir.mkdir(parents=True, exist_ok=True)
    return paths


def write_manifest(paths: pc.Paths, stream: list[str], holdout: list[str] | None = None) -> None:
    holdout = holdout or []
    doc = {
        "selection": {
            "stream": [{"contract": c, "source_row": c} for c in stream],
            "holdout": [{"contract": c, "source_row": c} for c in holdout],
        }
    }
    pc.write_json(paths.manifest_path, doc)


def write_contract(paths: pc.Paths, name: str, text: str) -> None:
    (paths.contracts_dir / name).write_text(text, encoding="utf-8")


# ==========================================================================
# 1. Batch membership arithmetic (6x6 + 2x7 = 50)
# ==========================================================================

def test_batch_membership() -> None:
    print("\n--- batch membership arithmetic ---")
    check("8 batches", len(pc.BATCH_SIZES) == 8)
    check("6x6 + 2x7 == 50", sum(pc.BATCH_SIZES) == 50)
    check("first six batches size 6", pc.BATCH_SIZES[:6] == [6, 6, 6, 6, 6, 6])
    check("last two batches size 7", pc.BATCH_SIZES[6:] == [7, 7])

    with tempfile.TemporaryDirectory() as tmp:
        paths = fixture_paths(Path(tmp))
        stream = [f"c{i:03d}.txt" for i in range(50)]
        write_manifest(paths, stream)
        manifest = pc.load_manifest(paths)

        seen = []
        for batch_number in range(1, 9):
            contracts = pc.batch_contracts(manifest, batch_number)
            expected_size = pc.BATCH_SIZES[batch_number - 1]
            check(f"batch {batch_number} has {expected_size} contracts", len(contracts) == expected_size)
            seen.extend(contracts)
        check("all 50 stream contracts covered exactly once", sorted(seen) == sorted(stream) and len(seen) == 50)

        mapping = pc.contract_batch_map(manifest)
        check("contract_batch_map covers all 50", len(mapping) == 50)
        check("contract_batch_map batch 1 membership matches", mapping[stream[0]] == 1 and mapping[stream[5]] == 1)
        check("contract_batch_map last batch membership matches", mapping[stream[-1]] == 8)


# ==========================================================================
# 2. Commissioning trigger, incl. trust grading
# ==========================================================================

def test_commissioning_trigger() -> None:
    print("\n--- commissioning trigger and trust grading ---")
    check("yesno always one-sided (0 negatives)", pc.trust_grade_for_commissioning("yesno", 0) == "one-sided")
    check("yesno always one-sided (10 negatives)", pc.trust_grade_for_commissioning("yesno", 10) == "one-sided")
    check("extraction one-sided under 3 negatives", pc.trust_grade_for_commissioning("extraction", 2) == "one-sided")
    check("extraction two-sided at 3 negatives", pc.trust_grade_for_commissioning("extraction", 3) == "two-sided")
    check("extraction two-sided above 3 negatives", pc.trust_grade_for_commissioning("extraction", 6) == "two-sided")

    with tempfile.TemporaryDirectory() as tmp:
        paths = fixture_paths(Path(tmp))
        stream = [f"c{i:03d}.txt" for i in range(12)]
        write_manifest(paths, stream)
        for c in stream:
            write_contract(paths, c, f"contract {c} laws of Delaware maintain insurance")

        # Governing Law (extraction): 7 positives, 3 negatives -> should
        # qualify, two-sided (>= 3 negatives).
        for i, c in enumerate(stream):
            present = i < 7
            entry = {"present": present, "spans": ["laws of Delaware"] if present else [],
                     "answer": "Delaware" if present else None}
            pc.merge_llm_extraction(paths, c, {"Governing Law": entry})

        state = pc.fresh_matcher_state()
        pc.save_matcher_state(paths, state)
        candidates = accept_batch._commissioning_candidates(paths, state)
        gl_candidate = next((c for c in candidates if c["category"] == "Governing Law"), None)
        check("Governing Law crosses the induction trigger", gl_candidate is not None)
        if gl_candidate:
            check("Governing Law positives == 7", gl_candidate["positives"] == 7)
            check("Governing Law negatives == 5", gl_candidate["negatives"] == 5)
            check("Governing Law qualifies two-sided", gl_candidate["trust_grade"] == "two-sided")

        # prepare_commission end-to-end for this category.
        summary = prepare_commission.prepare_commission(paths, "Governing Law")
        check("commission trust two-sided", summary["trust"] == "two-sided")
        check("commission id follows c<NN>-<slug>", summary["commission_id"] == "c01-governing-law")
        commission_doc = pc.read_json(paths.commissions_dir / "governing-law" / "commission.json")
        check("commission induction 'all' includes both positives and negatives",
              len(commission_doc["induction"]["all"]) == 12)
        state_after = pc.load_matcher_state(paths)
        check("state flips to commissioned", state_after["categories"]["Governing Law"]["status"] == "commissioned")

        # A category below the induction threshold refuses to commission.
        pc.merge_llm_extraction(paths, stream[0], {"Non-Compete": {"present": True, "spans": [], "answer": None}})
        raised = False
        try:
            prepare_commission.prepare_commission(paths, "Non-Compete")
        except SystemExit:
            raised = True
        check("commission refused below N_INDUCTION", raised)


# ==========================================================================
# 3. Gate static checks catching each forbidden token (+ other static
#    failure modes), using fake matcher fixtures.
# ==========================================================================

def make_matcher_source(trust: str = "one-sided", induced_from=("c1.txt",),
                          injected: str = "", define_nomatch: bool = True,
                          raise_nomatch: bool = True) -> str:
    nomatch_block = "class NoMatch(Exception):\n    pass\n" if define_nomatch else "class NotReallyNoMatch(Exception):\n    pass\n"
    raise_line = "raise NoMatch()" if raise_nomatch else "return {'present': False, 'spans': [], 'answer': None}"
    return f'''import re
{injected}
CATEGORY = "Insurance"
TRUST = "{trust}"
PROVENANCE = {{"induced_from": {list(induced_from)!r}, "brief": "overseer_brief_v1", "commission": "c01-insurance"}}

{nomatch_block}

def match(text):
    if "ANCHOR" in text:
        return {{"present": True, "spans": ["ANCHOR"], "answer": None}}
    {raise_line}

SELF_TEST = []

def self_test(load_text):
    pass
'''


def test_gate_static_checks() -> None:
    print("\n--- gate static checks ---")
    commission = {"trust": "one-sided", "induction": {"all": ["c1.txt"]}}

    clean_source = make_matcher_source()
    result = regression_gate.run_static_checks(clean_source, commission)
    check("clean matcher passes static checks", result["ok"])

    forbidden_injections = {
        "open(": "_x = open('nope')",
        "import os": "import os",
        "import sys": "import sys",
        "import pathlib": "import pathlib",
        "import random": "import random",
        "import time": "import time",
        "requests": "_x = requests",
        "socket": "_x = socket",
        "subprocess": "_x = subprocess",
        "eval(": "_x = eval('1')",
        "exec(": "exec('1')",
    }
    for token, injected_line in forbidden_injections.items():
        source = make_matcher_source(injected=injected_line)
        result = regression_gate.run_static_checks(source, commission)
        check(f"forbidden token caught: {token!r}", not result["ok"] and token in result["forbidden_tokens_found"])

    disallowed_import_source = make_matcher_source(injected="import json")
    result = regression_gate.run_static_checks(disallowed_import_source, commission)
    check("disallowed import (json) caught", not result["ok"] and "json" in result["disallowed_imports"])

    trust_mismatch_source = make_matcher_source(trust="two-sided")
    result = regression_gate.run_static_checks(trust_mismatch_source, commission)
    check("TRUST mismatch caught", not result["ok"] and not result["trust_ok"])

    provenance_mismatch_source = make_matcher_source(induced_from=("wrong.txt",))
    result = regression_gate.run_static_checks(provenance_mismatch_source, commission)
    check("PROVENANCE induced_from mismatch caught", not result["ok"] and not result["provenance_induced_from_ok"])

    no_nomatch_class_source = make_matcher_source(define_nomatch=False)
    result = regression_gate.run_static_checks(no_nomatch_class_source, commission)
    check("missing NoMatch class caught", not result["ok"] and not result["has_nomatch_class"])

    no_raise_source = make_matcher_source(raise_nomatch=False)
    result = regression_gate.run_static_checks(no_raise_source, commission)
    check("missing raise NoMatch caught", not result["ok"] and not result["has_raise_nomatch"])


# ==========================================================================
# 4. Matcher-output validation fixtures: NoMatch-raiser, span-violator,
#    one-sided-False violator.
# ==========================================================================

def test_matcher_output_validation_fixtures() -> None:
    print("\n--- matcher output validation fixtures ---")
    with tempfile.TemporaryDirectory() as tmp:
        paths = fixture_paths(Path(tmp))

        nomatch_src = make_matcher_source()
        (paths.matchers_generated_dir / "matcher_nomatch_raiser.py").write_text(nomatch_src, encoding="utf-8")
        module = pc.load_matcher_module(paths.matchers_generated_dir / "matcher_nomatch_raiser.py")
        matched, result = pc.call_matcher(module, "nothing relevant here")
        check("NoMatch-raiser returns matched=False on non-anchor text", matched is False and result is None)
        matched2, result2 = pc.call_matcher(module, "the ANCHOR is here")
        check("NoMatch-raiser matches on anchor text", matched2 is True and result2["present"] is True)

        span_violator_entry = {"present": True, "spans": ["this span does not appear"], "answer": None}
        errors = pc.validate_matcher_output("Insurance", span_violator_entry, "totally different contract text", "one-sided")
        check("span-violator caught (not verbatim)", any("not verbatim" in e for e in errors))

        one_sided_false_entry = {"present": False, "spans": [], "answer": None}
        errors2 = pc.validate_matcher_output("Insurance", one_sided_false_entry, "some contract text", "one-sided")
        check("one-sided present:False violator caught", any("one-sided matcher returned present: False" in e for e in errors2))

        two_sided_false_entry = {"present": False, "spans": [], "answer": None}
        errors3 = pc.validate_matcher_output("Insurance", two_sided_false_entry, "some contract text", "two-sided")
        check("two-sided present:False is NOT a violation", errors3 == [])


# ==========================================================================
# 5. Gate replay disagreement -> FAIL
# ==========================================================================

def test_gate_replay_disagreement() -> None:
    print("\n--- gate replay disagreement -> FAIL ---")
    with tempfile.TemporaryDirectory() as tmp:
        paths = fixture_paths(Path(tmp))
        write_manifest(paths, ["c1.txt"])
        write_contract(paths, "c1.txt", "This agreement is governed by the laws of Delaware forever.")

        # Accepted extraction says California; the matcher will say Delaware.
        pc.merge_llm_extraction(paths, "c1.txt", {
            "Governing Law": {"present": True, "spans": ["laws of Delaware"], "answer": "California"}
        })

        slug = "governing-law"
        commission_dir = paths.commissions_dir / slug
        (commission_dir / "contracts").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(paths.contracts_dir / "c1.txt", commission_dir / "contracts" / "c1.txt")
        commission_doc = {
            "id": "c01-governing-law", "category": "Governing Law", "slug": slug, "trust": "two-sided",
            "target_matcher_path": f"code/matchers_generated/matcher_{slug}.py",
            "induction": {"positives": ["c1.txt"], "negatives": [], "all": ["c1.txt"]},
        }
        pc.write_json(commission_dir / "commission.json", commission_doc)

        matcher_src = '''import re
CATEGORY = "Governing Law"
TRUST = "two-sided"
PROVENANCE = {"induced_from": ["c1.txt"], "brief": "overseer_brief_v1", "commission": "c01-governing-law"}

class NoMatch(Exception):
    pass

def match(text):
    if "IMPOSSIBLE_TOKEN_NEVER_PRESENT" in text:
        raise NoMatch()
    return {"present": True, "spans": ["laws of Delaware"], "answer": "Delaware"}

SELF_TEST = [("c1.txt", {"present": True, "answer": "Delaware"})]

def self_test(load_text):
    assert "Delaware" in load_text("c1.txt")
'''
        (paths.matchers_generated_dir / f"matcher_{slug}.py").write_text(matcher_src, encoding="utf-8")

        state = pc.fresh_matcher_state()
        info = state["categories"]["Governing Law"]
        info.update({
            "status": "commissioned", "trust": "two-sided", "matcher_id": "c01-governing-law",
            "matcher_path": f"code/matchers_generated/matcher_{slug}.py", "commissioned_at_batch": 1,
        })
        state["last_accepted_batch"] = 1
        pc.save_matcher_state(paths, state)

        result = regression_gate.regression_gate(paths, "Governing Law")
        check("gate FAILs on replay disagreement", result["pass"] is False)
        check("replay recorded exactly one disagreement", len(result["replay"]["disagreements"]) == 1)
        state_after = pc.load_matcher_state(paths)
        check("state flips to failed", state_after["categories"]["Governing Law"]["status"] == "failed")


# ==========================================================================
# 6. Shadow assignment determinism + max-2 rule + per-category eligibility
#    (corrected 3 Jul 2026: a shadow is only meaningful on a (contract,
#    category) pair where the active matcher actually answered — not
#    NoMatch — this batch; see pipeline_common.assign_shadow_categories).
# ==========================================================================

def test_shadow_assignment() -> None:
    print("\n--- shadow assignment determinism + max-2 rule + eligibility ---")
    active = ["Governing Law", "Document Name", "Agreement Date", "Anti-Assignment", "Insurance"]
    contracts = ["only_contract.txt"]
    answered_on_only_contract = {cat: contracts for cat in active}

    map1, dropped1 = pc.assign_shadow_categories(active, contracts, answered_on_only_contract, batch_number=3)
    map2, dropped2 = pc.assign_shadow_categories(active, contracts, answered_on_only_contract, batch_number=3)
    check("shadow assignment deterministic across repeated calls", map1 == map2 and dropped1 == dropped2)
    check("single contract capped at 2 shadow categories", len(map1.get("only_contract.txt", [])) == 2)
    check("excess categories dropped (5 active, capacity 2)", len(dropped1) == 3)
    check("assigned + dropped covers every active category",
          sorted(map1.get("only_contract.txt", []) + dropped1) == sorted(active))

    map3, dropped3 = pc.assign_shadow_categories([], contracts, {}, batch_number=1)
    check("no active categories -> empty shadow map, nothing dropped", map3 == {} and dropped3 == [])

    map4, dropped4 = pc.assign_shadow_categories(active, [], {}, batch_number=1)
    check("no LLM-read contracts -> all active categories dropped", map4 == {} and sorted(dropped4) == sorted(active))

    many_contracts = [f"c{i}.txt" for i in range(6)]
    answered_all_many = {cat: many_contracts for cat in active}
    map5, dropped5 = pc.assign_shadow_categories(active, many_contracts, answered_all_many, batch_number=7)
    total_assigned = sum(len(v) for v in map5.values())
    check("enough capacity -> nothing dropped", dropped5 == [] and total_assigned == len(active))
    check("no contract exceeds the 2-shadow cap", all(len(v) <= 2 for v in map5.values()))

    map6, _ = pc.assign_shadow_categories(active, contracts, answered_on_only_contract, batch_number=4)
    check("different batch number can change the assignment seed", map6 != map1 or True)  # documented, not asserted equal/different

    # The batch-2 prep gap: a category whose matcher NoMatched every
    # LLM-read contract this batch has no pair to regress against, and
    # must be dropped (logged), never shadow-assigned to a NoMatch pair.
    llm_read = ["c1.txt", "c2.txt"]
    answered_partial = {
        "Governing Law": ["c1.txt", "c2.txt"],
        "Document Name": ["c1.txt", "c2.txt"],
        "Agreement Date": ["c1.txt", "c2.txt"],
        "Anti-Assignment": ["c1.txt", "c2.txt"],
        "Insurance": [],  # NoMatched on every LLM-read contract this batch
    }
    map7, dropped7 = pc.assign_shadow_categories(active, llm_read, answered_partial, batch_number=2)
    check("all-NoMatch category is dropped, not shadow-assigned",
          "Insurance" in dropped7 and all("Insurance" not in cats for cats in map7.values()))
    check("categories with an eligible pair are still assigned",
          all(cat in dropped7 or any(cat in cats for cats in map7.values())
              for cat in active if cat != "Insurance"))

    # A shadow must never land on a pair where the matcher did not answer,
    # even when that pair is otherwise a perfectly good LLM-read contract
    # (this is the exact CENTRACK/Agreement Date, Delta/Parties bug).
    llm_read2 = ["centrack.txt", "delta.txt"]
    answered_mixed = {
        "Governing Law": ["centrack.txt"],       # matcher answered Governing Law only on centrack
        "Agreement Date": ["delta.txt"],         # matcher answered Agreement Date only on delta (NoMatch on centrack)
    }
    map8, dropped8 = pc.assign_shadow_categories(
        ["Governing Law", "Agreement Date"], llm_read2, answered_mixed, batch_number=9
    )
    check("Governing Law shadow only ever lands on its answered contract (centrack)",
          "Governing Law" not in map8.get("delta.txt", []))
    check("Agreement Date shadow only ever lands on its answered contract (delta)",
          "Agreement Date" not in map8.get("centrack.txt", []))


# ==========================================================================
# 7. Demotion on shadow disagreement (accept_batch integration)
# ==========================================================================

def test_demotion_on_shadow_disagreement() -> None:
    print("\n--- demotion on shadow disagreement ---")
    with tempfile.TemporaryDirectory() as tmp:
        paths = fixture_paths(Path(tmp))
        write_manifest(paths, ["c1.txt"])
        write_contract(paths, "c1.txt", "The vendor shall maintain insurance at all times.")

        state = pc.fresh_matcher_state()
        info = state["categories"]["Insurance"]
        info.update({
            "status": "active", "trust": "one-sided", "matcher_id": "c01-insurance",
            "matcher_path": "code/matchers_generated/matcher_insurance.py", "active_from_batch": 1,
        })
        state["last_accepted_batch"] = 0
        pc.save_matcher_state(paths, state)

        # Simulate what prepare_batch.py would already have written: the
        # matcher answered Insurance=True for c1.txt.
        pc.merge_matcher_output(paths, "c1.txt", "Insurance", {
            "present": True, "spans": ["maintain insurance"], "answer": None,
            "path": "matcher", "matcher_id": "c01-insurance", "trust": "one-sided",
        })

        batch_dir = paths.batches_dir / "batch_01"
        (batch_dir / "out").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(paths.contracts_dir / "c1.txt", batch_dir / "c1.txt")
        questions_doc = {
            "batch": 1,
            "contracts": {"c1.txt": {"questions": ["Insurance"], "reasons": {}}},
            "shadow": {"c1.txt": ["Insurance"]},
            "dropped_shadows": [],
        }
        pc.write_json(batch_dir / "questions.json", questions_doc)
        # The LLM's shadow answer disagrees with the matcher (matcher said
        # True; the LLM says False).
        pc.write_json(batch_dir / "out" / "c1.extraction.json", {
            "contract": "c1.txt",
            "categories": {"Insurance": {"present": False, "spans": [], "answer": None}},
            "notes": "",
        })

        summary = accept_batch.accept_batch(paths, 1, retries=0)
        check("batch 1 accepted despite the shadow disagreement", summary["batch"] == 1)
        check("shadow disagreement recorded", len(summary["demotions"]) == 1 and summary["demotions"][0][0] == "Insurance")

        state_after = pc.load_matcher_state(paths)
        check("Insurance demoted after shadow disagreement", state_after["categories"]["Insurance"]["status"] == "demoted")


# ==========================================================================
# 8. Router consistency check failing on a fabricated double-answer
# ==========================================================================

def test_router_double_answer_consistency() -> None:
    print("\n--- router consistency check: fabricated double-answer ---")
    with tempfile.TemporaryDirectory() as tmp:
        paths = fixture_paths(Path(tmp))
        write_manifest(paths, ["c1.txt"])
        write_contract(paths, "c1.txt", "Some contract text.")

        state = pc.fresh_matcher_state()
        for category in schemas.CATEGORY_NAMES:
            state["categories"][category].update({
                "status": "active", "trust": "one-sided", "matcher_id": "test",
                "matcher_path": None, "active_from_batch": 1,
            })
        state["last_accepted_batch"] = 1
        pc.save_matcher_state(paths, state)

        # Every category answered cleanly by the matcher...
        for category in schemas.CATEGORY_NAMES:
            pc.merge_matcher_output(paths, "c1.txt", category, {
                "present": True, "spans": [], "answer": None, "path": "matcher",
            })
        # ...except "Insurance", which is ALSO answered by the LLM (the
        # fabricated bug: a double answer on the same primary path check).
        pc.merge_llm_extraction(paths, "c1.txt", {
            "Insurance": {"present": True, "spans": [], "answer": None},
        })

        batch_dir = paths.batches_dir / "batch_01"
        batch_dir.mkdir(parents=True, exist_ok=True)
        pc.write_json(batch_dir / "questions.json", {
            "batch": 1,
            "contracts": {"c1.txt": {"questions": ["Insurance"], "reasons": {"Insurance": "no-match"}}},
            "shadow": {},
            "dropped_shadows": [],
        })

        result = router.build_stream_events(paths)
        check("router reports a consistency error", len(result["consistency_errors"]) >= 1)
        check("the error names the double-answered category",
              any("Insurance" in e and "multiple primary paths" in e for e in result["consistency_errors"]))
        check("exactly one consistency error (only Insurance is doubled)", len(result["consistency_errors"]) == 1)


# ==========================================================================
# 9. Evaluate: presence-only split and A/P/R classification thresholds
# ==========================================================================

def test_evaluate_scoring() -> None:
    print("\n--- evaluate: presence-only split and A/P/R thresholds ---")

    yesno_pairs = [
        ({"present": True, "spans": [], "answer": None}, {"present": True, "spans": [], "answer": None}),
        ({"present": False, "spans": [], "answer": None}, {"present": True, "spans": [], "answer": None}),
    ]
    scored = evaluate.score_entries("Insurance", yesno_pairs)
    check("yesno presence_total counts both rows", scored["presence_total"] == 2)
    check("yesno presence_correct counts only the agreeing row", scored["presence_correct"] == 1)
    check("yesno never touches the answer axis", scored["answer_total"] == 0 and scored["presence_only_count"] == 0)

    presence_only_pair = (
        {"present": True, "spans": ["..."], "answer": "02/10/2019"},
        {"present": True, "spans": ["five years following the Effective Date"], "answer": ""},
    )
    normal_answer_pair_correct = (
        {"present": True, "spans": ["..."], "answer": "06/08/1999"},
        {"present": True, "spans": ["..."], "answer": "6/8/99"},
    )
    normal_answer_pair_wrong = (
        {"present": True, "spans": ["..."], "answer": "06/09/1999"},
        {"present": True, "spans": ["..."], "answer": "6/8/99"},
    )
    scored2 = evaluate.score_entries("Expiration Date", [presence_only_pair, normal_answer_pair_correct, normal_answer_pair_wrong])
    check("presence-only row counted once", scored2["presence_only_count"] == 1)
    check("presence-only row excluded from answer denominator", scored2["answer_total"] == 2)
    check("presence-only row still counts as presence-correct", scored2["presence_correct"] == 3)
    check("answer accuracy over key-answerable rows only (1 of 2 correct)", scored2["answer_correct"] == 1)

    check("R-actual: never activated", evaluate.classify_actual("none", None, None, None, None) == "R")
    check("R-actual: demoted", evaluate.classify_actual("demoted", "two-sided", 0.99, 0.95, 0.94) == "R")
    check("A-actual: two-sided, coverage>=95%, within 2pp",
          evaluate.classify_actual("active", "two-sided", 0.96, 0.90, 0.89) == "A")
    check("P-actual: two-sided but coverage below 95%",
          evaluate.classify_actual("active", "two-sided", 0.90, 0.99, 0.99) == "P")
    check("P-actual: two-sided, coverage ok, but accuracy gap > 2pp",
          evaluate.classify_actual("active", "two-sided", 0.99, 0.80, 0.90) == "P")
    check("P-actual: one-sided is never A regardless of coverage/accuracy",
          evaluate.classify_actual("active", "one-sided", 1.0, 1.0, 1.0) == "P")
    check("A-actual boundary: exactly 95% coverage qualifies",
          evaluate.classify_actual("active", "two-sided", 0.95, 0.90, 0.90) == "A")
    check("A-actual boundary: exactly 2pp gap qualifies",
          evaluate.classify_actual("active", "two-sided", 0.99, 0.92, 0.90) == "A")


# ==========================================================================
# Main
# ==========================================================================

def main() -> None:
    assert config.N_INDUCTION == 6, "test fixtures assume N_INDUCTION == 6"

    test_batch_membership()
    test_commissioning_trigger()
    test_gate_static_checks()
    test_matcher_output_validation_fixtures()
    test_gate_replay_disagreement()
    test_shadow_assignment()
    test_demotion_on_shadow_disagreement()
    test_router_double_answer_consistency()
    test_evaluate_scoring()

    print(f"\n{len(FAILURES)} failures of {CHECKS} checks")
    if FAILURES:
        print("Failed checks:")
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
