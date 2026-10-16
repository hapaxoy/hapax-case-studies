"""Pipeline tooling — evaluation against the derived key.

THE ONLY pipeline file permitted to reference the derived key or its CSV
source (validate_corpus.py rule 10's explicit whitelist) — every other
file in the pipeline is pipeline-facing and never touches it. This script
reads `data/answer_key/` purely to mark, side by side, what the matcher
path and the model path each produced; the key is never edited and never
feeds back into routing.

Produces:
  data/runs/evaluation.json       per-category x path x split scoring,
                                   the equivalence table, the predicted-vs-
                                   actual outcome table, and cost estimates.
  data/runs/evaluation_worksheet.md   every pipeline-vs-key mismatch (both
                                   paths), presence-only rows, the seeded
                                   R-category sample, and every
                                   both-paths-agree-against-key case
                                   (flagged adjudicate-first).

Deterministic: sorted keys, no timestamps, seeded sampling.

Run: `python evaluate.py`.
"""

from __future__ import annotations

import random

import config
import pipeline_common as pc
import router
import schemas

# --------------------------------------------------------------------------
# Pre-registered predictions — hardcoded here,
# never re-derived, so the "as-run" table is a genuine comparison against
# what was written down before the pipeline ran.
# --------------------------------------------------------------------------

PREDICTIONS = {
    "Governing Law": "A",
    "Document Name": "A",
    "Agreement Date": "A",
    "Parties": "P",
    "Anti-Assignment": "P",
    "License Grant": "P",
    "Insurance": "P",
    "Expiration Date": "R",
    "Cap on Liability": "R",
    "Audit Rights": "R",
    "IP Ownership Assignment": "R",
    "Non-Compete": "R",
}
R_CATEGORIES = sorted(c for c, p in PREDICTIONS.items() if p == "R")

PRICING_CONSTANTS = {
    "pricing_reference": (
        "Claude Sonnet 5 (claude-sonnet-5), checked against Anthropic's published prices "
        "on the run date 3 Jul 2026: list $3/$15 per MTok (input/output); "
        "introductory $2/$10 in force through 2026-08-31. Subagent token counts "
        "are input+output totals, so costs are reported as bands: all-input "
        "(lower), all-output (upper), and a stated 85/15 input/output split "
        "(central). Method B — all figures are estimates."
    ),
    "list_usd_per_mtok": {"input": 3.0, "output": 15.0},
    "introductory_usd_per_mtok": {"input": 2.0, "output": 10.0},
    "central_split_input_fraction": 0.85,
}


def cost_bands_usd(tokens: float) -> dict:
    """Method-B cost bands for a token total (input+output combined)."""
    split = PRICING_CONSTANTS["central_split_input_fraction"]
    bands = {}
    for label, prices in (("list", PRICING_CONSTANTS["list_usd_per_mtok"]),
                          ("introductory", PRICING_CONSTANTS["introductory_usd_per_mtok"])):
        lower = tokens * prices["input"] / 1e6
        upper = tokens * prices["output"] / 1e6
        central = tokens * (split * prices["input"] + (1 - split) * prices["output"]) / 1e6
        bands[label] = {"lower_usd": round(lower, 2), "central_usd": round(central, 2),
                        "upper_usd": round(upper, 2)}
    return bands


# --------------------------------------------------------------------------
# Key access (data/answer_key/) — confined to this file
# --------------------------------------------------------------------------

def load_key_records(paths: pc.Paths) -> dict[str, dict]:
    answer_key_dir = paths.data_dir / "answer_key"
    if not answer_key_dir.exists():
        pc.fail(f"{answer_key_dir} not found — run derive_answer_key.py first.")
    records = {}
    for path in sorted(answer_key_dir.glob("*.json")):
        rec = pc.read_json(path)
        records[rec["contract"]] = rec
    return records


# --------------------------------------------------------------------------
# Scoring (pure functions — directly unit-tested by test_pipeline.py)
# --------------------------------------------------------------------------

def score_entries(category: str, pairs: list[tuple[dict, dict]]) -> dict:
    """Score a list of (pipeline_entry, key_entry) pairs for one category.
    yes/no categories score on presence only. Extraction categories score
    on presence, plus answer accuracy over key-answerable rows only — a
    presence-only row (schemas.compare_category axis 'presence-only', the
    pre-registered span-without-answer rule) counts toward presence but is
    excluded from the answer-accuracy denominator by construction."""
    presence_correct = presence_total = 0
    answer_correct = answer_total = 0
    presence_only_count = 0
    for got, key in pairs:
        cmp = schemas.compare_category(category, got, key)
        presence_total += 1
        if cmp["axis"] == "presence":
            if cmp["match"]:
                presence_correct += 1
        elif cmp["axis"] == "presence-only":
            presence_only_count += 1
            presence_correct += 1  # both present is confirmed before this axis is reached
        elif cmp["axis"] == "answer":
            presence_correct += 1  # compare_category only reaches 'answer' once presence matched
            answer_total += 1
            if cmp["match"]:
                answer_correct += 1
    return {
        "n": len(pairs),
        "presence_correct": presence_correct,
        "presence_total": presence_total,
        "answer_correct": answer_correct,
        "answer_total": answer_total,
        "presence_only_count": presence_only_count,
    }


def overall_accuracy(category: str, scored: dict | None) -> float | None:
    """A single headline accuracy figure per category: presence accuracy
    for yes/no categories; answer accuracy over key-answerable rows for
    extraction categories (falling back to presence accuracy if there are
    no key-answerable rows in this slice, e.g. a small holdout sample)."""
    if scored is None or scored["n"] == 0:
        return None
    if schemas.KIND[category] == "yesno":
        return scored["presence_correct"] / scored["presence_total"] if scored["presence_total"] else None
    if scored["answer_total"] > 0:
        return scored["answer_correct"] / scored["answer_total"]
    return scored["presence_correct"] / scored["presence_total"] if scored["presence_total"] else None


def classify_actual(status: str, trust: str | None, holdout_coverage: float | None,
                     holdout_accuracy: float | None, stream_llm_accuracy: float | None,
                     stream_negatives: int = 1) -> str:
    """Pinned thresholds:
    R-actual = never activated or demoted (status != 'active').
    A-actual = two-sided active AND holdout coverage >= 95% AND holdout
    accuracy within 2 percentage points of the stream's LLM accuracy.
    P-actual = active, otherwise.

    Pre-registered clarification (3 Jul 2026, recorded
    after batch 1 and before any matcher existed): for a category with ZERO
    accepted stream negatives, the two-sided trust label is unreachable by
    construction (commissioning requires >= 3 negatives) while the
    pre-registered A definition is vacuously satisfiable — so the two-sided
    requirement is WAIVED exactly when stream_negatives == 0. The waiver is
    reported in the published table."""
    if status != "active":
        return "R"
    # A small epsilon guards the two pinned thresholds against ordinary
    # floating-point noise from ratios computed elsewhere (e.g. 0.92 - 0.90
    # != 0.02 exactly in IEEE 754) — the rule is "within 2 pp" / ">= 95%",
    # not "sensitive to the 16th decimal digit of a division".
    epsilon = 1e-9
    trust_ok = trust == "two-sided" or stream_negatives == 0
    if (
        trust_ok
        and holdout_coverage is not None and holdout_coverage >= 0.95 - epsilon
        and holdout_accuracy is not None and stream_llm_accuracy is not None
        and abs(holdout_accuracy - stream_llm_accuracy) <= 0.02 + epsilon
    ):
        return "A"
    return "P"


# --------------------------------------------------------------------------
# Assembling the stream/holdout scoring tables
# --------------------------------------------------------------------------

def build_stream_scoring(stream_events: dict, key_records: dict) -> dict:
    """Per category, split stream answers into matcher-path and LLM-path
    (llm-discovery + llm-fallback collapsed into one 'llm' bucket for
    scoring — the routing distinction matters for cost/narrative, not for
    marking) and score each group."""
    result = {}
    for category in schemas.CATEGORY_NAMES:
        matcher_pairs, llm_pairs = [], []
        for contract, record in stream_events["records"].items():
            entry = record["categories"].get(category)
            if entry is None:
                continue
            key_record = key_records.get(contract)
            if key_record is None:
                continue
            key_entry = key_record["categories"][category]
            (matcher_pairs if entry["path"] == "matcher" else llm_pairs).append((entry, key_entry))
        result[category] = {
            "matcher": score_entries(category, matcher_pairs),
            "llm": score_entries(category, llm_pairs),
        }
    return result


def build_holdout_scoring(paths: pc.Paths, key_records: dict, active_categories: list[str]) -> dict:
    manifest = pc.load_manifest(paths)
    holdout = pc.holdout_contracts(manifest)
    result = {}
    for category in active_categories:
        pairs = []
        violations = 0
        answered = 0
        for contract in holdout:
            out = pc.load_matcher_output(paths, contract, holdout=True)
            if out is None:
                continue
            entry = out.get("categories", {}).get(category)
            if entry is None:
                continue
            if entry.get("violations"):
                violations += 1
                continue
            answered += 1
            key_record = key_records.get(contract)
            if key_record is None:
                continue
            pairs.append((entry, key_record["categories"][category]))
        scored = score_entries(category, pairs)
        scored["violations"] = violations
        scored["coverage"] = (answered / len(holdout)) if holdout else None
        result[category] = scored
    return result


def build_equivalence_and_predicted(stream_scoring: dict, holdout_scoring: dict, lifecycle: dict,
                                     negatives_by_category: dict[str, int]) -> tuple[list, list]:
    equivalence, predicted_vs_actual = [], []
    for category in schemas.CATEGORY_NAMES:
        info = lifecycle[category]
        status, trust = info["status"], info["trust"]
        holdout_scored = holdout_scoring.get(category)
        stream_llm_scored = stream_scoring[category]["llm"]
        holdout_coverage = holdout_scored["coverage"] if holdout_scored else None
        holdout_accuracy = overall_accuracy(category, holdout_scored) if holdout_scored else None
        stream_llm_accuracy = overall_accuracy(category, stream_llm_scored)
        stream_negatives = negatives_by_category.get(category, 0)
        actual = classify_actual(status, trust, holdout_coverage, holdout_accuracy,
                                 stream_llm_accuracy, stream_negatives)
        row = {
            "category": category,
            "predicted": PREDICTIONS[category],
            "actual": actual,
            "match": PREDICTIONS[category] == actual,
            "status": status,
            "trust": trust,
            "stream_accepted_negatives": stream_negatives,
            "two_sided_waiver_applied": status == "active" and trust != "two-sided" and stream_negatives == 0,
            "holdout_coverage": holdout_coverage,
            "holdout_accuracy": holdout_accuracy,
            "holdout_n": holdout_scored["n"] if holdout_scored else 0,
            "stream_llm_accuracy": stream_llm_accuracy,
            "stream_llm_n": stream_llm_scored["n"],
        }
        predicted_vs_actual.append(row)
        if status == "active":
            equivalence.append(dict(row))
    return equivalence, predicted_vs_actual


# --------------------------------------------------------------------------
# Costs (data/runs/extract_agent_log.json — written by the human
# orchestrator at run time; absent during pipeline-tooling development)
# --------------------------------------------------------------------------

def build_costs(paths: pc.Paths) -> dict:
    costs = {
        "estimate": True,
        "available": False,
        "pricing_reference": PRICING_CONSTANTS["pricing_reference"],
    }
    if not paths.extract_agent_log_path.exists():
        costs["note"] = (
            "data/runs/extract_agent_log.json not found — written by the human "
            "orchestrator at run time; cost figures are unavailable until then."
        )
        return costs
    log_doc = pc.read_json(paths.extract_agent_log_path)
    batches = log_doc.get("batches", [])
    total_tokens = log_doc.get("total_tokens")
    # Per-read means must use EXTRACTION tokens only — the grand total also
    # contains overseer runs and the calibration spike, which are not reads.
    extraction_tokens = log_doc.get("extraction_tokens_measured", total_tokens)
    overseer_tokens = log_doc.get("overseer_tokens_measured")
    total_reads = log_doc.get("total_reads") or sum(b.get("reads", 0) + b.get("retries", 0) for b in batches)
    if total_tokens is None or not total_reads:
        costs["note"] = (
            "extract_agent_log.json present but missing the total_tokens / "
            "reads fields evaluate.py expects."
        )
        return costs
    mean_tokens_per_read = extraction_tokens / total_reads
    holdout_size = len(pc.holdout_contracts(pc.load_manifest(paths)))
    counterfactual_tokens = mean_tokens_per_read * holdout_size
    costs.update({
        "available": True,
        "total_measured_subagent_tokens": total_tokens,
        "extraction_tokens_measured": extraction_tokens,
        "overseer_tokens_measured": overseer_tokens,
        "unmeasured_note": log_doc.get("total_tokens_note"),
        "total_reads": total_reads,
        "mean_tokens_per_read": mean_tokens_per_read,
        "mean_tokens_per_read_basis": "extraction tokens only (excludes overseer runs and the spike)",
        "run_cost_bands_total": cost_bands_usd(total_tokens),
        "run_cost_bands_extraction_only": cost_bands_usd(extraction_tokens),
        "holdout_counterfactual_tokens_if_fully_read": counterfactual_tokens,
        "holdout_counterfactual_cost_bands": cost_bands_usd(counterfactual_tokens),
        "holdout_counterfactual_note": (
            "What reading all 100 holdout contracts with the model would cost at the "
            "stream's mean tokens-per-read. Stream reads averaged a NARROWED scope "
            "(matcher-retired categories excluded), so this understates a true "
            "full-scope counterfactual; stated as the conservative basis. The matcher "
            "path answered its holdout categories at zero marginal token cost."
        ),
        "matcher_path_tokens": 0,
        "pricing_bands": PRICING_CONSTANTS,
    })
    return costs


# --------------------------------------------------------------------------
# Disagreement worksheet
# --------------------------------------------------------------------------

def locate_context(contract_text: str, span: str, window: int = 300) -> str | None:
    """Best-effort +/-window-char context around the first verbatim (or
    whitespace-flexible) occurrence of `span` in `contract_text`."""
    import re
    if not span or not span.strip():
        return None
    idx = contract_text.find(span)
    if idx != -1:
        start, end = idx, idx + len(span)
    else:
        parts = [re.escape(p) for p in span.split()]
        if not parts:
            return None
        match = re.search(r"\s+".join(parts), contract_text)
        if not match:
            return None
        start, end = match.start(), match.end()
    lo, hi = max(0, start - window), min(len(contract_text), end + window)
    return contract_text[lo:hi]


def _first_span(entry: dict) -> str | None:
    spans = entry.get("spans") or []
    return spans[0] if spans else None


def _write_row(lines: list[str], paths: pc.Paths, contract: str, category: str, path: str,
               got: dict, key: dict, axis: str, detail: str) -> None:
    lines.append(f"### {category} / `{contract}` (path: {path}, axis: {axis})")
    lines.append(f"- pipeline: {got}")
    lines.append(f"- key:      {key}")
    lines.append(f"- detail:   {detail}")
    span = _first_span(got) or _first_span(key)
    if span:
        context = locate_context(pc.read_contract_text(paths, contract), span)
        if context:
            lines.append(f"- context (+/-300 chars around the best-matching span):\n\n  > {context.strip()}\n")
        else:
            lines.append("- context: span not locatable verbatim in the contract text")
    else:
        lines.append("- context: no span available")
    lines.append("")


def build_worksheet(paths: pc.Paths, stream_events: dict, key_records: dict) -> tuple[str, dict]:
    lines = [
        "# Evaluation disagreement worksheet",
        "",
        "Generated by evaluate.py. Every pipeline-vs-key mismatch (both paths), "
        "presence-only rows (key carries a span but no computed answer), the "
        "seeded R-category disagreement sample, and every both-paths-agree-"
        "against-key case (flagged adjudicate-first).",
        "",
    ]

    mismatch_rows, presence_only_rows = [], []

    for contract, record in sorted(stream_events["records"].items()):
        key_record = key_records.get(contract)
        if key_record is None:
            continue
        for category, entry in record["categories"].items():
            key_entry = key_record["categories"][category]
            cmp = schemas.compare_category(category, entry, key_entry)
            row = (contract, category, entry["path"], entry, key_entry, cmp["axis"], cmp["detail"])
            if not cmp["match"]:
                mismatch_rows.append(row)
            elif cmp["axis"] == "presence-only":
                presence_only_rows.append(row)

    manifest = pc.load_manifest(paths)
    for contract in pc.holdout_contracts(manifest):
        out = pc.load_matcher_output(paths, contract, holdout=True)
        if not out:
            continue
        key_record = key_records.get(contract)
        if key_record is None:
            continue
        for category, entry in out.get("categories", {}).items():
            if entry.get("violations"):
                continue
            key_entry = key_record["categories"][category]
            cmp = schemas.compare_category(category, entry, key_entry)
            row = (contract, category, "matcher (holdout)", entry, key_entry, cmp["axis"], cmp["detail"])
            if not cmp["match"]:
                mismatch_rows.append(row)
            elif cmp["axis"] == "presence-only":
                presence_only_rows.append(row)

    lines.append(f"## Mismatches ({len(mismatch_rows)})\n")
    for contract, category, path, got, key, axis, detail in mismatch_rows:
        _write_row(lines, paths, contract, category, path, got, key, axis, detail)

    lines.append(f"\n## Presence-only rows ({len(presence_only_rows)})\n")
    for contract, category, path, got, key, axis, detail in presence_only_rows:
        _write_row(lines, paths, contract, category, path, got, key, axis, detail)

    adjudicate_first_rows = []
    for contract, record in sorted(stream_events["records"].items()):
        key_record = key_records.get(contract)
        if key_record is None:
            continue
        for category, shadow in record.get("shadow", {}).items():
            if not shadow["agree"]:
                continue
            key_entry = key_record["categories"][category]
            cmp_matcher = schemas.compare_category(category, shadow["matcher_answer"], key_entry)
            cmp_llm = schemas.compare_category(category, shadow["llm_answer"], key_entry)
            if not cmp_matcher["match"] and not cmp_llm["match"]:
                adjudicate_first_rows.append((contract, category, shadow["matcher_answer"], shadow["llm_answer"], key_entry))

    lines.append(f"\n## Adjudicate-first — both paths agree with each other but both disagree with the key ({len(adjudicate_first_rows)})\n")
    for contract, category, matcher_answer, llm_answer, key_entry in adjudicate_first_rows:
        lines.append(f"- **{category}** / `{contract}` — matcher={matcher_answer} llm-shadow={llm_answer} key={key_entry}")

    r_mismatches = sorted(
        (row for row in mismatch_rows if row[1] in R_CATEGORIES and row[2] != "matcher (holdout)"),
        key=lambda r: (r[0], r[1]),
    )
    rng = random.Random(config.RANDOM_SEED)
    sample = rng.sample(r_mismatches, min(20, len(r_mismatches))) if r_mismatches else []
    lines.append(f"\n## Seeded R-category disagreement sample ({len(sample)} of {len(r_mismatches)})\n")
    for contract, category, path, got, key, axis, detail in sample:
        _write_row(lines, paths, contract, category, path, got, key, axis, detail)

    counts = {
        "mismatches": len(mismatch_rows),
        "presence_only": len(presence_only_rows),
        "adjudicate_first": len(adjudicate_first_rows),
        "r_category_mismatches_total": len(r_mismatches),
        "r_category_sample": len(sample),
    }
    return "\n".join(lines) + "\n", counts


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def evaluate(paths: pc.Paths) -> dict:
    key_records = load_key_records(paths)
    stream_events = router.build_stream_events(paths)
    if stream_events["consistency_errors"]:
        pc.fail(
            "router's stream replay reports consistency errors — evaluate.py refuses "
            f"to mark an inconsistent stream: {stream_events['consistency_errors']}"
        )

    state = pc.load_matcher_state(paths)
    lifecycle = {
        category: {"status": info["status"], "trust": info["trust"]}
        for category, info in state["categories"].items()
    }
    active_categories = sorted(c for c, info in lifecycle.items() if info["status"] == "active")

    # Accepted stream negatives per category (the same store commissioning
    # counted from) — drives the pre-registered two-sided-waiver rule.
    negatives_by_category: dict[str, int] = {c: 0 for c in schemas.CATEGORY_NAMES}
    for rec in pc.load_all_llm_extractions(paths).values():
        for category, entry in rec.get("categories", {}).items():
            if category in negatives_by_category and entry.get("present") is False:
                negatives_by_category[category] += 1

    stream_scoring = build_stream_scoring(stream_events, key_records)
    holdout_scoring = build_holdout_scoring(paths, key_records, active_categories)
    equivalence, predicted_vs_actual = build_equivalence_and_predicted(
        stream_scoring, holdout_scoring, lifecycle, negatives_by_category)
    costs = build_costs(paths)
    worksheet_text, worksheet_counts = build_worksheet(paths, stream_events, key_records)

    paths.evaluation_worksheet_path.parent.mkdir(parents=True, exist_ok=True)
    paths.evaluation_worksheet_path.write_text(worksheet_text, encoding="utf-8")

    result = {
        "stream_size": len(pc.stream_contracts(pc.load_manifest(paths))),
        "holdout_size": len(pc.holdout_contracts(pc.load_manifest(paths))),
        "predictions": PREDICTIONS,
        "stream_scoring": stream_scoring,
        "holdout_scoring": holdout_scoring,
        "equivalence_table": equivalence,
        "predicted_vs_actual": predicted_vs_actual,
        "costs": costs,
        "worksheet_counts": worksheet_counts,
        "worksheet_path": str(paths.evaluation_worksheet_path),
    }
    pc.write_json(paths.evaluation_path, result)
    return result


def print_summary(result: dict) -> None:
    pc.announce("Predicted vs actual")
    for row in result["predicted_vs_actual"]:
        flag = "OK" if row["match"] else "MISS"
        print(f"  {row['category']:28s} predicted={row['predicted']} actual={row['actual']}  [{flag}]  "
              f"status={row['status']}")

    pc.announce("Equivalence table (active categories)")
    if not result["equivalence_table"]:
        print("  (no active matchers yet)")
    for row in result["equivalence_table"]:
        hc = f"{row['holdout_coverage']:.1%}" if row["holdout_coverage"] is not None else "n/a"
        ha = f"{row['holdout_accuracy']:.1%}" if row["holdout_accuracy"] is not None else "n/a"
        sa = f"{row['stream_llm_accuracy']:.1%}" if row["stream_llm_accuracy"] is not None else "n/a"
        print(f"  {row['category']:28s} holdout coverage={hc:>6s} accuracy={ha:>6s}   stream LLM accuracy={sa:>6s}")

    pc.announce("Worksheet counts")
    for k, v in result["worksheet_counts"].items():
        print(f"  {k}: {v}")

    pc.announce("Costs")
    print(f"  estimate: {result['costs'].get('estimate')}   available: {result['costs'].get('available')}")
    if result["costs"].get("note"):
        print(f"  note: {result['costs']['note']}")


def main() -> None:
    paths = pc.default_paths()
    pc.assert_safe_output_paths(paths)

    result = evaluate(paths)
    print_summary(result)
    print(f"\nWrote {paths.evaluation_path}")
    print(f"Wrote {paths.evaluation_worksheet_path}")
    print("evaluate.py completed successfully.")


if __name__ == "__main__":
    main()
