"""Assemble per-candidate evidence dossiers from raw extraction-agent output
(Project 10, Phase 3, "the workflow under test").

Reads `data/extraction_raw/batch_NN.json` -- the extraction agents' filled-in
responses to the tasks `build_extraction_tasks.py` wrote, same batch/id
conventions -- and produces:

  data/dossiers/dossier_CNNN.json      -- one assembled dossier per candidate
  data/coverage_table.csv              -- aggregate coverage, ONE ROW PER
                                           CANDIDATE, IN APPLICATION ORDER
                                           (C001..C240). No sort is applied
                                           here: the design is explicit that
                                           the system draws no line through
                                           this table and emits no order --
                                           the reader may sort it themselves.
  data/dossiers/_citation_failures.json -- every quoted line that failed
                                           verbatim verification against the
                                           candidate's actual application
                                           text. Feeds pre-registration 2
                                           ("no invented evidence": < 1% of
                                           dossier evidence lines fail
                                           verification).

This script makes no LLM calls and never reads data/answer_key.csv or
data/answer_key_candidates.csv -- citation verification checks quotes against
the candidate's own application text (data/applications_raw/), not against
the key. Ground-truth marking is a separate, later, key-reading script
(mark_results.py).

Run this script with --partial when only some extraction batches exist, to
assemble what's available;
without --partial, any missing batch is an informative error, not a silent
partial dossier set.

Run: python assemble_dossiers.py [--partial]
"""
from __future__ import annotations

import argparse
import json
import re
import sys

import pandas as pd

import config


def log(message: str) -> None:
    print(f"[assemble_dossiers] {message}", flush=True)


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


REQUIRED_STATUSES = {"evidence_found", "claim_only", "contradiction", "not_stated"}
MUST_HAVE_IDS = set(config.MUST_HAVE_IDS)
DESIRABLE_IDS = set(config.DESIRABLE_IDS)
CONSTRAINT_IDS = set(config.CONSTRAINT_IDS)


# ---------------------------------------------------------------------------
# Loading raw extraction output.
# ---------------------------------------------------------------------------

def load_extraction_raw(partial: bool) -> dict[str, dict]:
    """Load every candidate's raw extraction response from
    data/extraction_raw/batch_NN.json. Returns {candidate_id: response}.

    Without --partial, any missing or malformed batch is a hard, informative
    error (mirrors the churn case's assemble_tickets.py convention). With
    --partial, missing batches are logged and skipped, and downstream steps
    only cover the candidates that are present.
    """
    raw_dir = config.DATA_DIR / "extraction_raw"
    responses: dict[str, dict] = {}
    missing_batches = []

    if not raw_dir.exists():
        raise SystemExit(
            f"[assemble_dossiers] ERROR: {raw_dir} does not exist. "
            "Extraction agents have not run yet -- this is expected before "
            "the extraction batches have run. "
            "Nothing to assemble."
        )

    for batch_num in range(1, config.N_BATCHES + 1):
        path = raw_dir / f"batch_{batch_num:02d}.json"
        if not path.exists():
            missing_batches.append(path.name)
            continue
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"[assemble_dossiers] ERROR: {path} is not valid JSON "
                f"({exc}). Fix or re-run this batch before continuing."
            ) from exc
        for response in batch:
            responses[response["candidate_id"]] = response

    if missing_batches and not partial:
        raise SystemExit(
            "[assemble_dossiers] ERROR: missing "
            f"{len(missing_batches)} extraction batch file(s) under "
            f"data/extraction_raw/: {missing_batches}. Re-run with "
            "--partial to assemble dossiers only for the candidates already "
            "extracted, or supply the missing batches."
        )
    if missing_batches:
        log(f"--partial: proceeding without {len(missing_batches)} "
            f"missing batch(es): {missing_batches}")

    return responses


def load_applications() -> dict[str, dict]:
    """Load every candidate's actual CV / cover-letter text for citation
    verification -- the ground truth for "does this quote really appear",
    which is the candidate's own application text, not the answer key.
    """
    applications: dict[str, dict] = {}
    for batch_num in range(1, config.N_BATCHES + 1):
        path = config.DATA_DIR / "applications_raw" / f"batch_{batch_num:02d}.json"
        if not path.exists():
            continue
        batch = json.loads(path.read_text(encoding="utf-8"))
        for candidate in batch:
            applications[candidate["candidate_id"]] = candidate
    return applications


# ---------------------------------------------------------------------------
# Citation verification -- whitespace-normalised verbatim substring check.
# ---------------------------------------------------------------------------

def normalise_whitespace(text: str) -> str:
    """Collapse all whitespace runs to a single space and strip ends, so a
    quote that wraps differently than the source (extra newline, doubled
    space) is not falsely flagged as invented.
    """
    return re.sub(r"\s+", " ", text).strip()


def verify_citation(quote: str, source: str, application: dict) -> bool:
    """True if `quote` appears verbatim (whitespace-normalised) in the named
    source document ('cv' or 'cover_letter') of this candidate's actual
    application.
    """
    if source == "cv":
        document = application.get("cv_markdown", "")
    elif source == "cover_letter":
        document = application.get("cover_letter_markdown", "")
    else:
        return False
    if not quote or not quote.strip():
        return False
    return normalise_whitespace(quote) in normalise_whitespace(document)


# ---------------------------------------------------------------------------
# Dossier assembly.
# ---------------------------------------------------------------------------

def assemble_dossier(candidate_id: str, response: dict, application: dict,
                      citation_failures: list[dict]) -> dict:
    requirements_out = []
    req_by_id = {r["requirement_id"]: r for r in response.get("requirements", [])}

    for requirement in config.REQUIREMENTS:
        rid = requirement["id"]
        entry = req_by_id.get(rid)
        if entry is None:
            # Missing entirely from the extraction response -- structural
            # gap, not a citation problem. Recorded as not_stated with a
            # note; validate_dossiers.py's structural pass is the one that
            # actually fails a candidate over this, since this function's
            # job is to assemble what exists, not to silently drop rows.
            requirements_out.append({
                "requirement_id": rid,
                "category": requirement["category"],
                "name": requirement["name"],
                "status": "not_stated",
                "lines": [],
                "note": "MISSING FROM EXTRACTION RESPONSE",
            })
            continue

        verified_lines = []
        for line in entry.get("lines", []):
            quote = line.get("quote", "")
            source = line.get("source", "")
            is_verified = verify_citation(quote, source, application)
            verified_lines.append({
                "quote": quote,
                "source": source,
                "citation_verified": is_verified,
            })
            if not is_verified:
                citation_failures.append({
                    "candidate_id": candidate_id,
                    "requirement_id": rid,
                    "source": source,
                    "quote": quote,
                    "reason": "quote not found verbatim (whitespace-"
                              "normalised) in the candidate's "
                              f"{source or '<missing source>'} text",
                })

        requirements_out.append({
            "requirement_id": rid,
            "category": requirement["category"],
            "name": requirement["name"],
            "status": entry.get("status", "not_stated"),
            "lines": verified_lines,
            "note": entry.get("note"),
        })

    return {
        "candidate_id": candidate_id,
        "role": {
            "title": config.ROLE_TITLE,
            "company": config.COMPANY["name"],
            "location": config.COMPANY["city"],
        },
        "requirements": requirements_out,
        "ask_in_screening": response.get("ask_in_screening", []),
    }


def coverage_row(dossier: dict) -> dict:
    """One coverage-table row for this candidate. Counts only, no sort key,
    no ranking value -- the design rule "the system itself draws no line
    through the table" applies here as much as to the eventual page.
    """
    by_id = {r["requirement_id"]: r for r in dossier["requirements"]}

    def count(ids: set, status: str) -> int:
        return sum(1 for rid in ids if by_id[rid]["status"] == status)

    flags_count = sum(1 for r in dossier["requirements"]
                       if r["status"] == "contradiction")

    return {
        "candidate_id": dossier["candidate_id"],
        "must_have_evidence_found": count(MUST_HAVE_IDS, "evidence_found"),
        "must_have_claim_only": count(MUST_HAVE_IDS, "claim_only"),
        "must_have_contradiction": count(MUST_HAVE_IDS, "contradiction"),
        "must_have_not_stated": count(MUST_HAVE_IDS, "not_stated"),
        "desirable_evidence_found": count(DESIRABLE_IDS, "evidence_found"),
        "constraint_evidence_found": count(CONSTRAINT_IDS, "evidence_found"),
        "flags": flags_count,
        "asks": len(dossier.get("ask_in_screening", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial", action="store_true",
                         help="assemble dossiers only for candidates whose "
                              "extraction batch is present, instead of "
                              "erroring on any missing batch")
    args = parser.parse_args()

    log("loading raw extraction responses from data/extraction_raw/")
    responses = load_extraction_raw(args.partial)
    log(f"loaded {len(responses)} candidate extraction response(s)")

    log("loading applications for citation verification")
    applications = load_applications()

    dossiers_dir = config.DATA_DIR / "dossiers"
    dossiers_dir.mkdir(parents=True, exist_ok=True)

    citation_failures: list[dict] = []
    coverage_rows: list[dict] = []
    total_lines = 0

    # Application order: C001..C240, never sorted, matching every candidate
    # actually present in the loaded responses.
    ordered_ids = [f"C{i:03d}" for i in range(1, config.N_CANDIDATES + 1)
                   if f"C{i:03d}" in responses]

    for candidate_id in ordered_ids:
        response = responses[candidate_id]
        application = applications.get(candidate_id)
        if application is None:
            raise SystemExit(
                f"[assemble_dossiers] ERROR: no application text found for "
                f"{candidate_id} in data/applications_raw/ -- cannot verify "
                "citations. Is Phase 2 complete for this candidate?"
            )
        dossier = assemble_dossier(candidate_id, response, application,
                                    citation_failures)
        out_path = dossiers_dir / f"dossier_{candidate_id}.json"
        out_path.write_text(json.dumps(dossier, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        coverage_rows.append(coverage_row(dossier))
        total_lines += sum(len(r["lines"]) for r in dossier["requirements"])

    log(f"wrote {len(ordered_ids)} dossier file(s) to {dossiers_dir}")

    coverage_path = config.DATA_DIR / "coverage_table.csv"
    pd.DataFrame(coverage_rows).to_csv(coverage_path, index=False)
    log(f"wrote coverage table ({len(coverage_rows)} rows, application "
        f"order, unsorted) to {coverage_path}")

    failures_path = dossiers_dir / "_citation_failures.json"
    failures_path.write_text(
        json.dumps(citation_failures, indent=2, ensure_ascii=False),
        encoding="utf-8")
    failure_rate = (len(citation_failures) / total_lines * 100) if total_lines else 0.0
    log(f"citation verification: {len(citation_failures)} failure(s) out of "
        f"{total_lines} quoted line(s) ({failure_rate:.2f}%) -- written to "
        f"{failures_path}")
    log("this failure rate feeds pre-registration 2 (< 1% invented "
        "evidence) once the real extraction run happens")

    if FAILURES:
        sys.exit(1)


if __name__ == "__main__":
    main()
