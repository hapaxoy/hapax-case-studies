"""Pipeline tooling — prepare one stream batch for the extraction
agent.

For batch N (1-indexed, sizes 6,6,6,6,6,6,7,7 per pipeline_common.BATCH_SIZES):
  1. Refuses if batch N-1 has not been accepted yet (sequential discipline).
  2. Runs every currently *active* matcher over each contract in the batch.
     A successful match is recorded to the matcher-output store. A NoMatch
     puts the category on that contract's question list. A schema/span
     violation demotes the matcher immediately (permanent for the run) and
     also puts the category on the question list.
  3. Assigns shadow-regression categories per the pinned seeded-rotation
     rule (max 2 per contract), restricted to (contract, category) pairs
     where that category's matcher actually answered this batch — not
     NoMatch (corrected 3 Jul 2026 after a batch-2 preparation gap: a shadow
     on a NoMatch pair has no matcher answer to regress against) — and
     folds them into the question lists too (the LLM answers them like any
     other question; a separate "shadow" map in questions.json marks which
     entries are shadows).
  4. Writes data/runs/batches/batch_NN/: contract text copies, an empty
     out/ folder for the extraction agent's output, and questions.json.
     Prints the batch summary (path counts, questions per contract,
     projected reads).

This script is pipeline-facing: it never references the derived key or its
CSV source (validate_corpus.py rule 10). It only ever touches contract
text, the manifest, generated matchers, and its own run-state files.

Run: `python prepare_batch.py --batch N`. Exits 1 on any hard failure.
"""

from __future__ import annotations

import argparse
import shutil
from collections import defaultdict

import pipeline_common as pc
import schemas


def prepare_batch(paths: pc.Paths, batch_number: int) -> dict:
    """Core logic, factored out of main() so tests can drive it against a
    fixture Paths without touching real data. Returns a summary dict and
    writes the batch folder + updated matcher state."""
    manifest = pc.load_manifest(paths)
    state = pc.load_matcher_state(paths)

    if batch_number != state["last_accepted_batch"] + 1:
        pc.fail(
            f"sequential discipline: batch {batch_number} requested but "
            f"last accepted batch is {state['last_accepted_batch']} "
            f"(expected batch {state['last_accepted_batch'] + 1} next)."
        )

    contracts = pc.batch_contracts(manifest, batch_number)

    per_contract_questions: dict[str, list[str]] = {}
    per_contract_reasons: dict[str, dict[str, str]] = {}
    matcher_answered_counts: dict[str, int] = defaultdict(int)
    matcher_answered_contracts: dict[str, list[str]] = defaultdict(list)
    asked_counts: dict[str, int] = defaultdict(int)
    demotions_this_batch: list[tuple[str, str, list[str]]] = []

    for contract in contracts:
        text = pc.read_contract_text(paths, contract)
        asked: list[str] = []
        reasons: dict[str, str] = {}

        for category in schemas.CATEGORY_NAMES:
            info = state["categories"][category]
            if info["status"] == "active":
                module = pc.load_matcher_module(paths.project_dir / info["matcher_path"])
                matched, result = pc.call_matcher(module, text)
                if not matched:
                    asked.append(category)
                    reasons[category] = "no-match"
                    asked_counts[category] += 1
                    continue
                errors = pc.validate_matcher_output(category, result, text, info["trust"])
                if errors:
                    reason = (
                        f"batch {batch_number} prep, contract {contract}: "
                        f"matcher output invalid: {errors}"
                    )
                    pc.demote_category(state, category, batch_number, reason)
                    print(f"DEMOTION  {category}: {reason}")
                    demotions_this_batch.append((category, contract, errors))
                    asked.append(category)
                    reasons[category] = "no-match"
                    asked_counts[category] += 1
                else:
                    entry = dict(result)
                    entry["path"] = "matcher"
                    entry["matcher_id"] = info["matcher_id"]
                    entry["trust"] = info["trust"]
                    pc.merge_matcher_output(paths, contract, category, entry)
                    matcher_answered_counts[category] += 1
                    matcher_answered_contracts[category].append(contract)
            else:
                asked.append(category)
                reasons[category] = "no-matcher"
                asked_counts[category] += 1

        per_contract_questions[contract] = sorted(asked)
        per_contract_reasons[contract] = reasons

    # Shadow-regression assignment: active categories AS OF NOW (any
    # batch-prep demotions above have already flipped their status), over
    # the contracts the LLM is genuinely reading this batch (non-empty
    # question list before shadow additions) — further restricted, per
    # category, to contracts where that category's matcher actually
    # produced an answer this batch (matcher_answered_contracts). A shadow
    # on a NoMatch pair has nothing to regress against: the category is
    # already a plain question there, with no matcher answer to compare.
    active_categories_now = [
        name for name, info in state["categories"].items() if info["status"] == "active"
    ]
    llm_read_contracts = [c for c in contracts if per_contract_questions[c]]
    shadow_map, dropped_shadows = pc.assign_shadow_categories(
        active_categories_now, llm_read_contracts, dict(matcher_answered_contracts), batch_number
    )
    for contract, cats in shadow_map.items():
        for cat in cats:
            if cat not in per_contract_questions[contract]:
                per_contract_questions[contract].append(cat)
        per_contract_questions[contract] = sorted(per_contract_questions[contract])

    # Write the batch folder.
    batch_dir = paths.batches_dir / f"batch_{batch_number:02d}"
    out_dir = batch_dir / "out"
    if batch_dir.exists():
        print(f"NOTE: {batch_dir} already exists — contract copies and "
              f"questions.json will be overwritten; out/ is left untouched.")
    out_dir.mkdir(parents=True, exist_ok=True)
    for contract in contracts:
        shutil.copyfile(paths.contracts_dir / contract, batch_dir / contract)

    questions_doc = {
        "batch": batch_number,
        "contracts": {
            contract: {
                "questions": per_contract_questions[contract],
                "reasons": per_contract_reasons[contract],
            }
            for contract in contracts
        },
        "shadow": shadow_map,
        "dropped_shadows": sorted(dropped_shadows),
    }
    pc.write_json(batch_dir / "questions.json", questions_doc)

    pc.save_matcher_state(paths, state)

    summary = {
        "batch": batch_number,
        "contracts": contracts,
        "matcher_answered_counts": dict(matcher_answered_counts),
        "asked_counts": dict(asked_counts),
        "questions_per_contract": {c: len(per_contract_questions[c]) for c in contracts},
        "projected_reads": len(llm_read_contracts),
        "llm_read_contracts": llm_read_contracts,
        "shadow_map": shadow_map,
        "dropped_shadows": sorted(dropped_shadows),
        "demotions_this_batch": demotions_this_batch,
        "batch_dir": str(batch_dir),
    }
    return summary


def print_summary(summary: dict) -> None:
    pc.announce(f"Batch {summary['batch']} summary")
    print(f"Contracts in batch: {len(summary['contracts'])}")
    print("\nPer-category: matcher-answered / LLM-asked (out of contracts in this batch):")
    for category in schemas.CATEGORY_NAMES:
        m = summary["matcher_answered_counts"].get(category, 0)
        a = summary["asked_counts"].get(category, 0)
        print(f"  {category:28s} matcher={m}   asked={a}")

    print("\nQuestions per contract (post shadow):")
    for contract, n in summary["questions_per_contract"].items():
        print(f"  {n:2d}  {contract}")

    print(f"\nProjected reads (contracts with a non-empty question list): {summary['projected_reads']}")
    if summary["llm_read_contracts"]:
        for c in summary["llm_read_contracts"]:
            print(f"  read: {c}")
    else:
        print("  (none — every category on every contract answered by a matcher)")

    if summary["shadow_map"]:
        print("\nShadow assignments:")
        for contract, cats in sorted(summary["shadow_map"].items()):
            print(f"  {contract}: {cats}")
    else:
        print("\nShadow assignments: none")
    if summary["dropped_shadows"]:
        print(f"Dropped shadows (no capacity): {summary['dropped_shadows']}")

    if summary["demotions_this_batch"]:
        print(f"\nDemotions during batch prep: {len(summary['demotions_this_batch'])}")
        for category, contract, errors in summary["demotions_this_batch"]:
            print(f"  {category} (triggered by {contract}): {errors}")
    else:
        print("\nDemotions during batch prep: none")

    print(f"\nBatch folder: {summary['batch_dir']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare one stream batch for the extraction agent.")
    parser.add_argument("--batch", type=int, required=True, help="1-indexed batch number (1-8)")
    args = parser.parse_args()

    paths = pc.default_paths()
    pc.assert_safe_output_paths(paths)

    summary = prepare_batch(paths, args.batch)
    print_summary(summary)
    print("\nprepare_batch.py completed successfully.")


if __name__ == "__main__":
    main()
