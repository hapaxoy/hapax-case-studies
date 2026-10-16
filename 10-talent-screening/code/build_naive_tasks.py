"""Arm 2 of the four-arm baseline comparison (Project 10) --
the naive local LLM: one plain prompt per candidate, no workflow discipline
at all. This models "the way a bought model gets used without a workflow":
no refuse-to-guess gate, no citation rule, no verdict ban, no ask-in-screening
rule -- the contract is minimal on purpose ("the naive arm is
allowed to be naive").

Reuses `build_extraction_tasks.load_applications()` to read the same Phase 2
corpus (`data/applications_raw/batch_NN.json`) that every other arm reads,
rather than re-implementing the loader. This script makes no LLM calls; the
Haiku runs for this arm are launched separately as a distinct step.

This script never reads data/answer_key.csv or data/answer_key_candidates.csv.

Run: python build_naive_tasks.py

Outputs:
  data/naive_batches/batch_NN.json   -- 30 batches of 8, same batching as
                                         every other arm's task batches
"""
from __future__ import annotations

import json
import sys

import config
from build_extraction_tasks import load_applications


def log(message: str) -> None:
    print(f"[build_naive_tasks] {message}", flush=True)


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


# ---------------------------------------------------------------------------
# The naive contract -- deliberately minimal. No status-definition prose, no
# refuse-to-guess rule, no citation rule, no no-verdict rule, no
# ask-in-screening rule. Just the plain pre-registered prompt,
# verbatim, plus the smallest output contract that lets marking parse a
# response at all.
# ---------------------------------------------------------------------------

NAIVE_PROMPT = (
    "Assess which of the requirements this candidate meets, based on their "
    "application."
)
MET_VOCABULARY = ["yes", "partial", "no"]

NAIVE_OUTPUT_CONTRACT = {
    "task": NAIVE_PROMPT,
    "met_vocabulary": MET_VOCABULARY,
    "return_format": {
        "description": (
            "Return a single JSON object for this one candidate (when run "
            "in a batch of 8, return a JSON array of 8 such objects, one "
            "per candidate, in the same order as the batch's `tasks` list)."
        ),
        "schema": {
            "candidate_id": "string, must match the task's candidate_id",
            "requirements": [
                {
                    "requirement_id": "string, e.g. 'R01'",
                    "met": "one of: " + ", ".join(MET_VOCABULARY),
                    "reason": "one-line free-text reason",
                },
            ],
        },
        "note": "The `requirements` array must contain exactly one entry "
                "per requirement given in this task, in the same order, "
                "covering all 12 requirement ids.",
    },
}


def requirement_profile_for_naive() -> list[dict]:
    """The 12-requirement profile as the naive agent sees it: id, category,
    canonical name, description -- identical fields to the extraction and
    disciplined arms (arms 3/4), since the ONLY thing that should differ
    between "naive" and "disciplined" is the contract, not the requirement
    information given.
    """
    return [
        {
            "id": r["id"],
            "category": r["category"],
            "name": r["name"],
            "description": r["description"],
        }
        for r in config.REQUIREMENTS
    ]


def build_task(candidate_id: str, application: dict) -> dict:
    return {
        "candidate_id": candidate_id,
        "role": {
            "title": config.ROLE_TITLE,
            "company": config.COMPANY["name"],
            "location": config.COMPANY["city"],
        },
        "application": {
            "cv_markdown": application["cv_markdown"],
            "cover_letter_markdown": application["cover_letter_markdown"],
        },
        "requirements": requirement_profile_for_naive(),
        "instructions": NAIVE_PROMPT,
    }


def validate_outputs(candidate_ids: list[str]) -> None:
    log("=== self-validation: naive-arm batches ===")

    batches_dir = config.DATA_DIR / "naive_batches"
    batch_files = sorted(batches_dir.glob("batch_*.json"))
    check(len(batch_files) == config.N_BATCHES,
          f"naive_batches has exactly {config.N_BATCHES} batch files "
          f"(got {len(batch_files)})")

    required_req_ids = [r["id"] for r in config.REQUIREMENTS]
    seen_in_batches: list[str] = []
    bad_batch_size = 0
    bad_requirements_count = 0
    for batch_path in batch_files:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        if len(batch["tasks"]) != config.BRIEF_BATCH_SIZE:
            bad_batch_size += 1
        for task in batch["tasks"]:
            seen_in_batches.append(task["candidate_id"])
            req_ids = [r["id"] for r in task["requirements"]]
            if req_ids != required_req_ids:
                bad_requirements_count += 1

    check(bad_batch_size == 0,
          f"every batch holds exactly {config.BRIEF_BATCH_SIZE} tasks "
          f"(got {bad_batch_size} batches with the wrong size)")
    check(sorted(seen_in_batches) == sorted(candidate_ids),
          "every candidate appears exactly once across all naive batches, "
          "and no others do")
    check(bad_requirements_count == 0,
          "every task carries exactly the 12 requirement ids, in config "
          f"order (got {bad_requirements_count} mismatches)")

    # Contract-hygiene check: the naive contract must NOT accidentally carry
    # any of the disciplined arm's discipline vocabulary (refuse-to-guess,
    # citation, no-verdict, ask-in-screening) -- if it did, this would no
    # longer be "the way a bought model gets used without a workflow".
    disciplined_only_terms = {
        "refuse_to_guess", "citation_rule", "no_verdict_rule",
        "ask_in_screening", "verbatim quote", "evidence_found",
    }
    blob = json.dumps(NAIVE_OUTPUT_CONTRACT).lower()
    leaked = [t for t in disciplined_only_terms if t.lower() in blob]
    check(len(leaked) == 0,
          f"naive contract carries none of the disciplined arm's discipline "
          f"vocabulary (got: {leaked})")


def main() -> None:
    log("loading Phase 2 applications from data/applications_raw/")
    applications = load_applications()
    check(len(applications) == config.N_CANDIDATES,
          f"loaded {config.N_CANDIDATES} applications (got {len(applications)})")

    candidate_ids = [f"C{i:03d}" for i in range(1, config.N_CANDIDATES + 1)]

    batches_dir = config.DATA_DIR / "naive_batches"
    assert batches_dir != config.DATA_DIR / "applications_raw", (
        "output path must never equal an input path")
    batches_dir.mkdir(parents=True, exist_ok=True)
    log(f"writing {config.N_BATCHES} batches of {config.BRIEF_BATCH_SIZE} "
        f"to {batches_dir}")

    tasks_by_id = {cid: build_task(cid, applications[cid]) for cid in candidate_ids}

    for batch_num in range(config.N_BATCHES):
        start = batch_num * config.BRIEF_BATCH_SIZE
        end = start + config.BRIEF_BATCH_SIZE
        chunk_ids = candidate_ids[start:end]
        batch = {
            "batch_id": f"batch_{batch_num + 1:02d}",
            "arm": "naive_local_llm",
            "role": {
                "title": config.ROLE_TITLE,
                "company": config.COMPANY["name"],
                "location": config.COMPANY["city"],
            },
            "output_contract": NAIVE_OUTPUT_CONTRACT,
            "tasks": [tasks_by_id[cid] for cid in chunk_ids],
        }
        out_path = batches_dir / f"batch_{batch_num + 1:02d}.json"
        out_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")

    validate_outputs(candidate_ids)

    if FAILURES:
        log(f"FAILED: {len(FAILURES)} check(s) did not pass -- see [FAIL] "
            "lines above")
        sys.exit(1)

    log(f"done: {config.N_CANDIDATES} candidates across {config.N_BATCHES} "
        "naive-arm batches, all self-validation checks passed")


if __name__ == "__main__":
    main()
