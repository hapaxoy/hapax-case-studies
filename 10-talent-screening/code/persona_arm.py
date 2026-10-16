"""Simulated-recruiter persona arm -- task generation (Project 10, Phase 3,
"the human arm").

Task generation for both arms runs from
`data/persona_subset.json` (12 personas x the 48-candidate stratified
subset): it needs only the persona roster and, for the assisted arm, the
assembled dossiers. The SCORING side -- comparing a persona's screening
response against the answer key to test pre-registrations 3, 4, 5, and 6 --
is not implemented here: marking is done by mark_results.py, and (like every
other script in this project except mark_results.py) this module never
reads data/answer_key.csv or data/answer_key_candidates.csv.

Two arms, same 48 candidates, same personas, same fixed time budget
(config.PERSONA_ARM_TIME_BUDGET_SECONDS -- see config.py for why that number
is a flagged judgment call):

  unaided  -- application text (CV + cover letter) + the bare requirement
              profile + the time-budget framing. No dossier. This is the
              persona reading the application cold, exactly as an unaided
              human recruiter would.
  assisted -- the same, PLUS the assembled dossier
              (data/dossiers/dossier_CNNN.json) placed beside the
              application. Requires Phase 3b's extraction run and
              assemble_dossiers.py to have produced that candidate's
              dossier; candidates without one are skipped with a clear log
              line, never silently dropped or faked.

Emits one task file per persona per arm (not one per persona-candidate pair
-- 12 personas x 2 arms = 24 files, each holding that persona's 48
candidate-tasks in application order), mirroring the batch-file convention
used everywhere else in this project:

  data/persona_tasks/unaided/persona_PNN.json
  data/persona_tasks/assisted/persona_PNN.json

Run: python persona_arm.py
"""
from __future__ import annotations

import json

import config


def log(message: str) -> None:
    print(f"[persona_arm] {message}", flush=True)


# ---------------------------------------------------------------------------
# Task-generation contract shared by both arms. This is what a persona
# simulation (an LLM role-playing the persona's traits, in the tender-case
# mould) receives alongside the per-candidate material.
# ---------------------------------------------------------------------------

def time_budget_framing(persona: dict) -> str:
    minutes = config.PERSONA_ARM_TIME_BUDGET_SECONDS / 60
    return (
        f"You are screening this application under a fixed time budget of "
        f"{minutes:g} minutes, same as every other application and every "
        f"other persona in this study -- a realistic constraint for a "
        f"recruiter working through a large applicant pool for one role. "
        f"Screen in a way consistent with your character: {persona['name']}, "
        f"{persona['tagline']} (strictness {persona['traits']['strictness']:.2f}, "
        f"keyword_reliance {persona['traits']['keyword_reliance']:.2f}, "
        f"time_discipline {persona['traits']['time_discipline']:.2f} -- see "
        f"config.py PERSONAS for what each trait means). You are a human "
        f"recruiter making a real screening judgment; unlike the extraction "
        f"workflow, you ARE expected to reach a decision."
    )


# The response contract every persona screening task asks for: the schema
# the marking script parses to test pre-registration 6 (the assistance
# claim), documented here so task generation and marking agree on it.
PERSONA_RESPONSE_CONTRACT = {
    "description": (
        "What a persona screening response should contain, for both arms. "
        "Not enforced or scored by this module -- Phase 4 builds the "
        "marking script that reads this schema against the answer key."
    ),
    "schema": {
        "candidate_id": "string",
        "persona_id": "string, e.g. 'P01'",
        "arm": "'unaided' or 'assisted'",
        "requirement_judgments": [
            {
                "requirement_id": "string, e.g. 'R01'",
                "believed_status": "the persona's own judgment -- free "
                                    "choice of evidenced / claimed_only / "
                                    "contradicted / absent / not_stated, "
                                    "since a human recruiter's read is not "
                                    "constrained to the extraction "
                                    "workflow's vocabulary",
                "note": "string or null -- optional free text",
            },
        ],
        "flags": {
            "vocabulary_notes": (
                "list of {requirement_id, note} -- any point where the "
                "persona recognised (or explicitly considered and "
                "dismissed) a displaced/adjacent-vocabulary skill as "
                "evidence for a requirement; feeds pre-registration 3 "
                "(hidden gems)"
            ),
            "claims_questioned": (
                "list of requirement_ids where the persona flagged a claim "
                "as thin/unsubstantiated rather than taking it at face "
                "value; feeds pre-registration 4 (stuffers)"
            ),
            "inconsistencies_noted": (
                "list of requirement_ids where the persona spotted a "
                "date/title/detail inconsistency; feeds the "
                "credential-inflation reading of the same pre-registration "
                "set"
            ),
            "borderline_calls": (
                "list of requirement_ids the persona explicitly called "
                "genuinely ambiguous / defensible either way, rather than "
                "forcing a clean pass/fail; feeds pre-registration 5's "
                "H-archetype reading"
            ),
        },
        "screening_decision": (
            "the persona's real recruiting decision for this candidate "
            "(e.g. advance / hold / decline, persona's own words) -- this "
            "is the one place in the whole pipeline where a verdict is "
            "expected and correct: the recruiter decides, per design.md S1. "
            "The workflow-under-test's no-verdict rule "
            "(validate_dossiers.py's banned-word scan) does NOT apply to "
            "persona responses."
        ),
        "time_budget_seconds": "echoed from the task for traceability",
    },
}


def requirement_profile() -> list[dict]:
    return [
        {"id": r["id"], "category": r["category"], "name": r["name"],
         "description": r["description"]}
        for r in config.REQUIREMENTS
    ]


def load_persona_subset() -> dict:
    if not config.PERSONA_SUBSET_PATH.exists():
        raise SystemExit(
            f"[persona_arm] ERROR: {config.PERSONA_SUBSET_PATH} not found "
            "-- run generate_structured.py first (Phase 1)."
        )
    return json.loads(config.PERSONA_SUBSET_PATH.read_text(encoding="utf-8"))


def load_applications(candidate_ids: list[str]) -> dict[str, dict]:
    applications: dict[str, dict] = {}
    for batch_num in range(1, config.N_BATCHES + 1):
        path = config.DATA_DIR / "applications_raw" / f"batch_{batch_num:02d}.json"
        if not path.exists():
            continue
        batch = json.loads(path.read_text(encoding="utf-8"))
        for candidate in batch:
            if candidate["candidate_id"] in candidate_ids:
                applications[candidate["candidate_id"]] = candidate
    missing = [cid for cid in candidate_ids if cid not in applications]
    if missing:
        raise SystemExit(
            "[persona_arm] ERROR: missing application text for "
            f"{len(missing)} persona-subset candidate(s): {missing}. Phase "
            "2 must be complete for the whole persona subset."
        )
    return applications


def load_dossiers(candidate_ids: list[str]) -> dict[str, dict]:
    """Best-effort load of assembled dossiers for the assisted arm. Returns
    only the candidates that actually have one -- callers must handle a
    partial (or empty) result gracefully, never crash on it.
    """
    dossiers_dir = config.DATA_DIR / "dossiers"
    dossiers: dict[str, dict] = {}
    if not dossiers_dir.exists():
        return dossiers
    for candidate_id in candidate_ids:
        path = dossiers_dir / f"dossier_{candidate_id}.json"
        if path.exists():
            dossiers[candidate_id] = json.loads(path.read_text(encoding="utf-8"))
    return dossiers


def build_candidate_entry(candidate_id: str, application: dict,
                           dossier: dict | None) -> dict:
    entry = {
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
        "requirements": requirement_profile(),
    }
    if dossier is not None:
        entry["dossier"] = dossier
    return entry


def build_persona_file(persona: dict, arm: str, candidate_ids: list[str],
                        applications: dict[str, dict],
                        dossiers: dict[str, dict]) -> dict | None:
    candidates = []
    for candidate_id in candidate_ids:
        if arm == "assisted" and candidate_id not in dossiers:
            continue  # no dossier yet -- skip, never fabricate one
        dossier = dossiers.get(candidate_id) if arm == "assisted" else None
        candidates.append(build_candidate_entry(
            candidate_id, applications[candidate_id], dossier))

    if not candidates:
        return None

    return {
        "persona": persona,
        "arm": arm,
        "time_budget_seconds": config.PERSONA_ARM_TIME_BUDGET_SECONDS,
        "instructions": time_budget_framing(persona),
        "response_contract": PERSONA_RESPONSE_CONTRACT,
        "candidates": candidates,
    }


def main() -> None:
    subset = load_persona_subset()
    candidate_ids = subset["candidate_ids"]  # application order, not sorted
    personas = subset["personas"]
    log(f"persona subset: {len(candidate_ids)} candidates, "
        f"{len(personas)} personas, "
        f"{config.PERSONA_ARM_TIME_BUDGET_SECONDS}s fixed time budget")

    applications = load_applications(candidate_ids)

    unaided_dir = config.DATA_DIR / "persona_tasks" / "unaided"
    assisted_dir = config.DATA_DIR / "persona_tasks" / "assisted"
    unaided_dir.mkdir(parents=True, exist_ok=True)
    assisted_dir.mkdir(parents=True, exist_ok=True)

    dossiers = load_dossiers(candidate_ids)
    if dossiers:
        log(f"found {len(dossiers)}/{len(candidate_ids)} assembled dossiers "
            "for the persona subset")
    else:
        log("no assembled dossiers found -- the assisted arm cannot be "
            "built yet (expected before Phase 3b's extraction run and "
            "assemble_dossiers.py have both completed). Building the "
            "unaided arm only.")

    unaided_written = 0
    assisted_written = 0
    for persona in personas:
        unaided_task = build_persona_file(persona, "unaided", candidate_ids,
                                           applications, dossiers)
        if unaided_task is not None:
            out_path = unaided_dir / f"persona_{persona['id']}.json"
            out_path.write_text(json.dumps(unaided_task, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
            unaided_written += 1

        assisted_task = build_persona_file(persona, "assisted", candidate_ids,
                                            applications, dossiers)
        if assisted_task is not None:
            out_path = assisted_dir / f"persona_{persona['id']}.json"
            out_path.write_text(json.dumps(assisted_task, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
            assisted_written += 1

    log(f"wrote {unaided_written}/{len(personas)} unaided persona task "
        f"file(s) to {unaided_dir}")
    log(f"wrote {assisted_written}/{len(personas)} assisted persona task "
        f"file(s) to {assisted_dir}")
    if assisted_written == 0:
        log("assisted arm: 0 files written -- re-run this script after "
            "assemble_dossiers.py has produced dossiers for the persona "
            "subset")


# ---------------------------------------------------------------------------
# Scoring stub. Documented contract only: this function intentionally
# raises. Marking lives in mark_results.py, so that the answer-key
# boundary stays in one script and no scoring interpretation is baked
# in here.
# ---------------------------------------------------------------------------

def score_persona_response(response: dict, answer_key_row: dict) -> dict:
    """Score one persona response against one candidate's answer-key row.

    NOT IMPLEMENTED -- marking is done by mark_results.py. This is the
    ONLY function in this module that would ever receive answer-key data;
    it is a stub precisely so that boundary is visible and enforced by
    inspection.

    Intended contract, for whoever implements this:
      response         -- one persona's PERSONA_RESPONSE_CONTRACT-shaped
                           dict for one candidate (see above)
      answer_key_row    -- that candidate's rows from data/answer_key.csv
                           (12 rows, one per requirement) plus its
                           data/answer_key_candidates.csv summary row
      returns           -- a dict of per-pre-registration boolean/metric
                           contributions for this one (persona, candidate,
                           arm) triple, e.g.:
                             {"hidden_gem_recognised": bool | None,   # pre-reg 3, only meaningful for archetype F
                              "stuffer_claims_questioned": float | None,  # pre-reg 4, fraction of D's claimed
                                                                          # must-haves the persona questioned
                              "inflation_spotted": bool | None,       # archetype E
                              "borderline_identified": bool | None,   # archetype H
                              "requirement_agreement": dict}          # per-requirement persona-vs-key agreement,
                                                                       # for the parity check (pre-registration 5)
      Aggregation across all (persona, candidate) pairs within an arm, and
      the unaided-vs-assisted comparison for pre-registration 6, is a
      separate marking-script concern, not this function's.
    """
    raise NotImplementedError(
        "score_persona_response is a documented stub. Marking is done by "
        "mark_results.py -- do not implement ad hoc inside persona_arm.py."
    )


if __name__ == "__main__":
    main()
