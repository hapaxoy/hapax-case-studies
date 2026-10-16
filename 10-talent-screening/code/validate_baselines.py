"""Validation for the four-arm baseline comparison's task-generation side
(Project 10): arm 1 (ATS), arm 2 (naive local LLM), arm 3
(disciplined local LLM). Arm 4 (the full workflow) is already validated by
`validate_dossiers.py`.

Checks:
  1. ATS synonym lists contain no displacement-table phrase -- re-runs
     `ats_baseline.assert_no_displacement_leak()` standalone, so this stays
     true even if `ats_baseline.py`'s SYNONYM_TABLE is edited later without
     re-running the generator.
  2. Naive-arm and disciplined-arm batch files cover all 240 candidates
     exactly once each (no gaps, no duplicates, no extras).
  3. The ATS rank column has no ties broken non-deterministically: every
     rank 1..240 appears exactly once (the documented tie-break is
     `candidate_id ascending` on equal score -- see ats_baseline.py's
     RANK_TIE_BREAK constant).

Exits 1 on any failure, per the portfolio's "a dataset that fails validation
is a bug, not a judgment call" rule.

This script never reads data/answer_key.csv or data/answer_key_candidates.csv.

Run: python validate_baselines.py
"""
from __future__ import annotations

import json
import sys

import pandas as pd

import config
from ats_baseline import (
    CV_ONLY_OUTPUT_PATH,
    FULL_TEXT_OUTPUT_PATH,
    RANK_TIE_BREAK,
    assert_no_displacement_leak,
)

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


def log(message: str) -> None:
    print(f"[validate_baselines] {message}", flush=True)


CANDIDATE_IDS = [f"C{i:03d}" for i in range(1, config.N_CANDIDATES + 1)]


def check_ats_synonym_leak() -> None:
    log("=== check 1: ATS synonym lists vs displacement table ===")
    try:
        assert_no_displacement_leak()
        check(True, "ats_baseline.SYNONYM_TABLE contains no "
                     "displacement-table phrase (re-run standalone)")
    except AssertionError as exc:
        check(False, f"ats_baseline.SYNONYM_TABLE leaks displacement-table "
                       f"vocabulary: {exc}")


def _check_batch_coverage(dir_name: str, label: str) -> None:
    batches_dir = config.DATA_DIR / dir_name
    batch_files = sorted(batches_dir.glob("*.json"))
    check(len(batch_files) == config.N_BATCHES,
          f"{label}: {dir_name}/ has exactly {config.N_BATCHES} batch "
          f"files (got {len(batch_files)})")

    if not batch_files:
        check(False, f"{label}: no batch files found under {dir_name}/ "
                       "-- has the builder script run?")
        return

    seen: list[str] = []
    bad_size = 0
    for path in batch_files:
        batch = json.loads(path.read_text(encoding="utf-8"))
        tasks = batch.get("tasks", [])
        if len(tasks) != config.BRIEF_BATCH_SIZE:
            bad_size += 1
        seen.extend(t["candidate_id"] for t in tasks)

    check(bad_size == 0,
          f"{label}: every batch holds exactly {config.BRIEF_BATCH_SIZE} "
          f"tasks (got {bad_size} batches with the wrong size)")

    duplicates = sorted({c for c in seen if seen.count(c) > 1})
    missing = sorted(set(CANDIDATE_IDS) - set(seen))
    unexpected = sorted(set(seen) - set(CANDIDATE_IDS))

    check(len(duplicates) == 0,
          f"{label}: no candidate appears more than once across all "
          f"batches (got {len(duplicates)} duplicated: {duplicates[:10]})")
    check(len(missing) == 0,
          f"{label}: no candidate is missing from the batches "
          f"(got {len(missing)} missing: {missing[:10]})")
    check(len(unexpected) == 0,
          f"{label}: no unrecognised candidate_id appears in the batches "
          f"(got {len(unexpected)}: {unexpected[:10]})")
    check(sorted(seen) == CANDIDATE_IDS,
          f"{label}: all {config.N_CANDIDATES} candidates covered exactly "
          "once, no others")


def check_naive_and_disciplined_coverage() -> None:
    log("=== check 2: naive-arm and disciplined-arm batch coverage ===")
    _check_batch_coverage("naive_batches", "naive arm (arm 2)")
    _check_batch_coverage("disciplined_batches", "disciplined arm (arm 3)")


def _check_rank_determinism(csv_path, label: str) -> None:
    if not csv_path.exists():
        check(False, f"{label}: {csv_path.name} does not exist -- has "
                       "ats_baseline.py run?")
        return
    df = pd.read_csv(csv_path)
    check(len(df) == config.N_CANDIDATES,
          f"{label}: {csv_path.name} has exactly {config.N_CANDIDATES} "
          f"rows (got {len(df)})")
    ranks = df["rank"].tolist()
    expected_ranks = list(range(1, config.N_CANDIDATES + 1))
    check(sorted(ranks) == expected_ranks,
          f"{label}: rank column is a permutation of 1..{config.N_CANDIDATES} "
          f"with no duplicate or missing rank (tie-break: {RANK_TIE_BREAK})")

    # Re-derive the documented tie-break independently of ats_baseline.py's
    # own sort, so this check would catch a future change to the sort logic
    # that silently reintroduced non-deterministic ties.
    recomputed = df.copy()
    recomputed["_num"] = recomputed["candidate_id"].str[1:].astype(int)
    recomputed = recomputed.sort_values(
        ["total_score", "_num"], ascending=[False, True]).reset_index(drop=True)
    recomputed_rank = {
        row.candidate_id: i + 1 for i, row in enumerate(recomputed.itertuples())
    }
    mismatches = [
        cid for cid, rank in zip(df["candidate_id"], df["rank"])
        if recomputed_rank[cid] != rank
    ]
    check(len(mismatches) == 0,
          f"{label}: every row's rank matches the documented deterministic "
          f"tie-break ({RANK_TIE_BREAK}) recomputed independently "
          f"(got {len(mismatches)} mismatch(es): {mismatches[:10]})")


def check_ats_rank_determinism() -> None:
    log("=== check 3: ATS rank tie-break determinism ===")
    _check_rank_determinism(FULL_TEXT_OUTPUT_PATH, "ATS full-text variant")
    _check_rank_determinism(CV_ONLY_OUTPUT_PATH, "ATS CV-only variant")


def main() -> None:
    check_ats_synonym_leak()
    check_naive_and_disciplined_coverage()
    check_ats_rank_determinism()

    if FAILURES:
        log(f"FAILED: {len(FAILURES)} check(s) did not pass -- see [FAIL] "
            "lines above")
        sys.exit(1)

    log("all baseline-harness checks passed")


if __name__ == "__main__":
    main()
