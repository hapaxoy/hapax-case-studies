"""Arm 3 of the four-arm baseline comparison (Project 10) --
the disciplined local LLM: the workflow's own extraction contract (refuse-to-
guess, verbatim citations, no verdicts, ask-in-screening), run on the same
small model as arm 2 (Haiku, as stand-in for "a local model"). This arm
isolates the case's hero claim: if it lands near arm 4 (the full workflow,
already run on Sonnet) and far above arm 2 (the naive prompt on the same
model), the delta is the DISCIPLINE, not the parameter count.

Deliberately thin: this module owns no contract logic of its own. It imports
`load_applications`, `requirement_profile_for_extraction`, `build_task`, and
`EXTRACTION_CONTRACT` straight from `build_extraction_tasks.py` so arms 3 and
4 run the byte-identical contract on the byte-identical per-candidate task
content -- the ONLY difference between this script's output and
`data/extraction_batches/` is the output-path instruction embedded in each
batch (telling whoever launches the Haiku run where to write results), plus
an `arm` label. Task content, requirement profile, and `output_contract` are
produced by the exact same functions arm 4 already used.

This script never reads data/answer_key.csv or data/answer_key_candidates.csv.

Run: python build_disciplined_tasks.py   (after
                                           data/applications_raw/ exists --
                                           same precondition as
                                           build_extraction_tasks.py)

Outputs:
  data/disciplined_batches/batch_NN.json   -- 30 batches of 8, same contract
                                               as data/extraction_batches/,
                                               output_path pointed at
                                               data/disciplined_raw/
"""
from __future__ import annotations

import json
import sys

import config
from build_extraction_tasks import (
    EXTRACTION_CONTRACT,
    build_task,
    load_applications,
)


def log(message: str) -> None:
    print(f"[build_disciplined_tasks] {message}", flush=True)


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


def validate_outputs(candidate_ids: list[str]) -> None:
    log("=== self-validation: disciplined-arm batches ===")

    batches_dir = config.DATA_DIR / "disciplined_batches"
    batch_files = sorted(batches_dir.glob("batch_*.json"))
    check(len(batch_files) == config.N_BATCHES,
          f"disciplined_batches has exactly {config.N_BATCHES} batch files "
          f"(got {len(batch_files)})")

    extraction_batches_dir = config.DATA_DIR / "extraction_batches"
    required_req_ids = [r["id"] for r in config.REQUIREMENTS]
    seen_in_batches: list[str] = []
    bad_batch_size = 0
    bad_requirements_count = 0
    contract_mismatches = 0
    for batch_path in batch_files:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        if len(batch["tasks"]) != config.BRIEF_BATCH_SIZE:
            bad_batch_size += 1
        if batch["output_contract"] != EXTRACTION_CONTRACT:
            contract_mismatches += 1
        for task in batch["tasks"]:
            seen_in_batches.append(task["candidate_id"])
            req_ids = [r["id"] for r in task["requirements"]]
            if req_ids != required_req_ids:
                bad_requirements_count += 1

        # Same contract as arm 4's extraction_batches, byte-for-byte, task
        # content included -- the only allowed differences are the
        # batch-level arm label and output_path instruction.
        sibling_path = extraction_batches_dir / batch_path.name
        if sibling_path.exists():
            sibling = json.loads(sibling_path.read_text(encoding="utf-8"))
            if sibling["tasks"] != batch["tasks"]:
                contract_mismatches += 1

    check(bad_batch_size == 0,
          f"every batch holds exactly {config.BRIEF_BATCH_SIZE} tasks "
          f"(got {bad_batch_size} batches with the wrong size)")
    check(sorted(seen_in_batches) == sorted(candidate_ids),
          "every candidate appears exactly once across all disciplined "
          "batches, and no others do")
    check(bad_requirements_count == 0,
          "every task carries exactly the 12 requirement ids, in config "
          f"order (got {bad_requirements_count} mismatches)")
    check(contract_mismatches == 0,
          "every disciplined batch's output_contract and task content is "
          "byte-identical to the matching data/extraction_batches/ batch "
          f"(got {contract_mismatches} mismatch(es))")


def main() -> None:
    log("loading Phase 2 applications from data/applications_raw/ "
        "(same loader as build_extraction_tasks.py)")
    applications = load_applications()
    check(len(applications) == config.N_CANDIDATES,
          f"loaded {config.N_CANDIDATES} applications (got {len(applications)})")

    candidate_ids = [f"C{i:03d}" for i in range(1, config.N_CANDIDATES + 1)]

    batches_dir = config.DATA_DIR / "disciplined_batches"
    assert batches_dir != config.DATA_DIR / "applications_raw", (
        "output path must never equal an input path")
    assert batches_dir != config.DATA_DIR / "extraction_batches", (
        "arm 3 must write to its own directory, not arm 4's"
    )
    batches_dir.mkdir(parents=True, exist_ok=True)
    log(f"writing {config.N_BATCHES} batches of {config.BRIEF_BATCH_SIZE} "
        f"to {batches_dir} (contract identical to data/extraction_batches/)")

    tasks_by_id = {cid: build_task(cid, applications[cid]) for cid in candidate_ids}

    for batch_num in range(config.N_BATCHES):
        start = batch_num * config.BRIEF_BATCH_SIZE
        end = start + config.BRIEF_BATCH_SIZE
        chunk_ids = candidate_ids[start:end]
        batch_id = f"batch_{batch_num + 1:02d}"
        batch = {
            "batch_id": batch_id,
            "arm": "disciplined_local_llm",
            "output_path": f"data/disciplined_raw/{batch_id}.json",
            "note": (
                "This batch's requirements and output_contract are "
                "byte-identical to data/extraction_batches/" + batch_id +
                ".json (arm 4, the full workflow). This arm runs the "
                "SAME contract on a smaller model (Haiku) to isolate the "
                "effect of workflow discipline from model size -- write "
                "your response to data/disciplined_raw/, never to "
                "data/extraction_raw/ (arm 4's output directory)."
            ),
            "role": {
                "title": config.ROLE_TITLE,
                "company": config.COMPANY["name"],
                "location": config.COMPANY["city"],
            },
            "output_contract": EXTRACTION_CONTRACT,
            "tasks": [tasks_by_id[cid] for cid in chunk_ids],
        }
        out_path = batches_dir / f"{batch_id}.json"
        out_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")

    validate_outputs(candidate_ids)

    if FAILURES:
        log(f"FAILED: {len(FAILURES)} check(s) did not pass -- see [FAIL] "
            "lines above")
        sys.exit(1)

    log(f"done: {config.N_CANDIDATES} candidates across {config.N_BATCHES} "
        "disciplined-arm batches, all self-validation checks passed")


if __name__ == "__main__":
    main()
