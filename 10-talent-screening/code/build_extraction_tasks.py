"""Build per-candidate extraction tasks for the dossier-extraction workflow
(Project 10, Phase 3, "the workflow under test").

Reads the written application prose from `data/applications_raw/batch_NN.json`
(Phase 2 output, session data -- never regenerated, only read) and the 12
frozen requirements from `code/config.py`, and emits one extraction task per
candidate plus 8-candidate batches for the extraction agents that run in
Phase 3b (a separate LLM run -- this script makes no LLM calls and
does not trigger one).

This script never reads `data/answer_key.csv` or `data/answer_key_candidates.csv`
-- per the portfolio's standing rule, nothing touches the key except the
marking script (Phase 5). The extraction agent must work from the application
text alone, exactly as a real extraction system would.

The extraction contract embedded in every task/batch is the load-bearing part
of this script: it tells the agent to *refuse to guess* (the
refuse-to-guess gate -- anything not explicitly and unambiguously stated
becomes `not_stated`, never an inference) and to *never rank, recommend, or
verdict* the candidate (the standing constraint -- the system
assists, it never decides). Every requirement's status classification must
carry a verbatim, source-tagged quote so `assemble_dossiers.py` can verify
citations against the actual application text later.

Run: python build_extraction_tasks.py   (after Phase 2's application prose
                                          batches exist under
                                          data/applications_raw/)

Outputs:
  data/extraction_tasks/task_CNNN.json     -- one per candidate (240)
  data/extraction_batches/batch_NN.json    -- 30 batches of 8, output
                                               contract embedded, same
                                               numbering as brief_batches

Ends with a self-validation pass (structural checks on what this script just
wrote -- every candidate present, every task carries all 12 requirements, no
answer-key vocabulary or fields leaked, batch counts reconcile). Exits 1 on
any failure, per the portfolio's "a dataset that fails validation is a bug"
rule.
"""
from __future__ import annotations

import json
import sys

import config


def log(message: str) -> None:
    print(f"[build_extraction_tasks] {message}", flush=True)


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    """Record a failure without stopping the run, mirroring
    validate_structured.py's convention -- every check gets a chance to
    report rather than hiding behind the first failure.
    """
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


# ---------------------------------------------------------------------------
# The extraction contract. This is what an extraction agent (or, in a real
# deployment, the extraction step of the workflow under test) receives
# alongside a candidate's application text and the 12-requirement profile.
# ---------------------------------------------------------------------------

STATUS_VOCABULARY = ["evidence_found", "claim_only", "contradiction", "not_stated"]
SOURCE_VOCABULARY = ["cv", "cover_letter"]

EXTRACTION_CONTRACT = {
    "task": (
        "You are the extraction step of a candidate-screening support tool. "
        "For the one candidate in this task, read the CV and cover letter in "
        "full and classify, for EACH of the 12 requirements listed, exactly "
        "one status from this fixed vocabulary: evidence_found, claim_only, "
        "contradiction, not_stated. This is extraction, not evaluation -- you "
        "are locating and quoting what the text says, never judging whether "
        "the candidate is good enough."
    ),
    "status_definitions": {
        "evidence_found": (
            "The text gives a concrete, specific example of the requirement "
            "(a named project, employer, tool, or role detail) -- not just a "
            "keyword or a bare assertion."
        ),
        "claim_only": (
            "The requirement is asserted (e.g. listed as a skill, or "
            "claimed in a sentence) but with no concrete project, employer, "
            "or detail backing it up."
        ),
        "contradiction": (
            "Two statements in the application -- CV vs CV, letter vs "
            "letter, or CV vs letter -- cannot both be true at once about "
            "this requirement (e.g. a degree conferral date that is later "
            "than a job that required the degree; a claimed leadership "
            "title alongside a work-history entry that describes an "
            "individual-contributor role for the same employer and period). "
            "Quote both conflicting statements. Do not decide which "
            "statement is correct or resolve the conflict -- record that it "
            "exists."
        ),
        "not_stated": (
            "The text does not explicitly and unambiguously address the "
            "requirement, under any name for it, canonical or otherwise."
        ),
    },
    "refuse_to_guess_rule": (
        "REFUSE TO GUESS. If the requirement is not explicitly and "
        "unambiguously addressed in the text, the status is not_stated -- "
        "full stop. Never infer a requirement from a related or "
        "similar-sounding skill, a job title alone, general seniority, "
        "years of experience, or the prestige of an employer or university. "
        "A candidate whose job title was 'Senior RF Engineer' has NOT "
        "thereby evidenced hands-on RF measurement work unless the text "
        "itself describes that work. Where the text describes substantive "
        "work in different words from the requirement's own name, quote "
        "what the text actually says and let the quoted substance speak; "
        "what a description in adjacent vocabulary amounts to is a "
        "judgement call for the human recruiter, not something this "
        "extraction step resolves by guessing in either direction. When genuinely unsure between "
        "two statuses, choose the more conservative one (not_stated over "
        "claim_only, claim_only over evidence_found) and say so in the "
        "line's note."
    ),
    "no_verdict_rule": (
        "This tool never ranks, scores, shortlists, rejects, or recommends "
        "a candidate, and never characterises the candidate as a whole. Do "
        "not use words or phrases like recommend, reject, shortlist, rank, "
        "top candidate, best, worst, strong candidate, weak candidate, good "
        "fit, poor fit, hire, do not hire, suitable, unsuitable, pass, "
        "advance, or any other language that compares this candidate to "
        "others or states what should happen to their application. State "
        "only what the text shows, per requirement. The recruiter decides; "
        "this output is preparation, not a decision."
    ),
    "citation_rule": (
        "Every evidence_found, claim_only, or contradiction line must carry "
        "a VERBATIM quote: copied character-for-character from the CV or "
        "cover letter text given to you (leading/trailing whitespace may be "
        "trimmed, but do not paraphrase, summarise, correct, translate, or "
        "combine separate sentences). Tag every quote with its source: "
        "'cv' or 'cover_letter'. A quote that cannot be found verbatim in "
        "the source document will fail citation verification and be "
        "reported as invented evidence -- when in doubt, quote a shorter, "
        "exact fragment rather than a paraphrase."
    ),
    "ask_in_screening_rule": (
        "For EVERY must-have requirement (category 'must_have') whose "
        "status you set to not_stated, add one entry to the top-level "
        "ask_in_screening list: a plain, neutral, single-sentence question "
        "the recruiter could ask in a screening call to find out. Do not "
        "add ask_in_screening entries for desirable or constraint "
        "requirements, and do not add one for a must-have that is not "
        "not_stated. Questions must be neutral fact-finding, never leading "
        "and never implying a verdict (e.g. 'Can you describe your hands-on "
        "RF measurement experience, if any?' -- not 'Do you actually have "
        "RF experience, since your CV doesn't show it?')."
    ),
    "status_vocabulary": STATUS_VOCABULARY,
    "source_vocabulary": SOURCE_VOCABULARY,
    "return_format": {
        "description": (
            "Return a single JSON object for this one candidate (when "
            "extraction runs in a batch of 8, return a JSON array of 8 such "
            "objects, one per candidate, in the same order as the batch's "
            "`tasks` list)."
        ),
        "schema": {
            "candidate_id": "string, must match the task's candidate_id",
            "requirements": [
                {
                    "requirement_id": "string, e.g. 'R01'",
                    "status": "one of: " + ", ".join(STATUS_VOCABULARY),
                    "lines": [
                        {
                            "quote": "verbatim quote from the application "
                                     "text (see citation_rule)",
                            "source": "one of: " + ", ".join(SOURCE_VOCABULARY),
                        }
                    ],
                    "note": "string or null -- required and must explain "
                            "the conflict without resolving it when status "
                            "is 'contradiction'; optional free-text "
                            "otherwise (e.g. to flag a conservative-status "
                            "judgement call under refuse_to_guess_rule)",
                },
            ],
            "ask_in_screening": [
                {
                    "requirement_id": "string, e.g. 'R04'",
                    "question": "string -- see ask_in_screening_rule",
                },
            ],
        },
        "note": "The `requirements` array must contain exactly one entry "
                "per requirement given in this task, in the same order, "
                "covering all 12 requirement ids.",
    },
}


# ---------------------------------------------------------------------------
# Loading Phase 2 output (applications) -- read-only, never modified.
# ---------------------------------------------------------------------------

def load_applications() -> dict[str, dict]:
    """Load every candidate's CV + cover-letter text from
    data/applications_raw/batch_NN.json. Raises an informative error (not a
    bare crash) if a batch is missing -- Phase 2 must be complete before this
    script can do anything useful.
    """
    applications: dict[str, dict] = {}
    missing_batches = []
    for batch_num in range(1, config.N_BATCHES + 1):
        path = config.DATA_DIR / "applications_raw" / f"batch_{batch_num:02d}.json"
        if not path.exists():
            missing_batches.append(path.name)
            continue
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"[build_extraction_tasks] ERROR: {path} is not valid JSON "
                f"({exc}). Fix or regenerate this batch before continuing."
            ) from exc
        for candidate in batch:
            applications[candidate["candidate_id"]] = candidate

    if missing_batches:
        raise SystemExit(
            "[build_extraction_tasks] ERROR: missing "
            f"{len(missing_batches)} application batch file(s) under "
            f"data/applications_raw/: {missing_batches}. Phase 2 "
            "(application prose) must be complete before extraction "
            "tasks can be built -- see README.md 'Pipeline order'."
        )
    return applications


def requirement_profile_for_extraction() -> list[dict]:
    """The 12-requirement profile as the extraction agent sees it: id,
    category, canonical name, description -- no ground-truth status, no
    archetype, nothing from the answer key.
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
        "requirements": requirement_profile_for_extraction(),
        "extraction_contract": EXTRACTION_CONTRACT,
    }


# ---------------------------------------------------------------------------
# Self-validation of what this script just wrote. Deliberately conservative:
# checks structure and vocabulary hygiene, not extraction quality (there is
# no extraction output at this stage -- that is Phase 3b, a separate LLM run).
# ---------------------------------------------------------------------------

def validate_outputs(candidate_ids: list[str]) -> None:
    log("=== self-validation: extraction tasks ===")

    tasks_dir = config.DATA_DIR / "extraction_tasks"
    task_files = sorted(tasks_dir.glob("task_C*.json"))
    check(len(task_files) == config.N_CANDIDATES,
          f"extraction_tasks has exactly {config.N_CANDIDATES} task files "
          f"(got {len(task_files)})")

    required_req_ids = [r["id"] for r in config.REQUIREMENTS]
    # Distinctive answer-key-only vocabulary (deliberately excludes ordinary
    # English words like "evidenced" that legitimately appear in the
    # extraction contract's own instructional prose).
    answer_key_terms = {"claimed_only", "archetype", "borderline_note",
                         "displaced_phrase", "fully_qualified",
                         "letter_only_evidence_count", "must_have_pass_count"}

    bad_candidate_count = 0
    bad_requirements_count = 0
    leaked_answer_key_terms = 0
    for candidate_id in candidate_ids:
        path = tasks_dir / f"task_{candidate_id}.json"
        if not path.exists():
            bad_candidate_count += 1
            continue
        task = json.loads(path.read_text(encoding="utf-8"))
        if task.get("candidate_id") != candidate_id:
            bad_candidate_count += 1
        req_ids = [r["id"] for r in task.get("requirements", [])]
        if req_ids != required_req_ids:
            bad_requirements_count += 1
        # A cheap but real check that no answer-key-only vocabulary leaked
        # into the task (would indicate this script accidentally read the
        # key rather than the requirement profile / application text).
        blob = json.dumps(task).lower()
        if any(term in blob for term in answer_key_terms):
            leaked_answer_key_terms += 1

    check(bad_candidate_count == 0,
          f"every task file's candidate_id matches its filename and exists "
          f"(got {bad_candidate_count} mismatched/missing)")
    check(bad_requirements_count == 0,
          "every task carries exactly the 12 requirement ids, in config "
          f"order (got {bad_requirements_count} mismatches)")
    check(leaked_answer_key_terms == 0,
          "no answer-key-only vocabulary appears in any task file "
          f"(got {leaked_answer_key_terms} tasks with a leaked term)")

    batches_dir = config.DATA_DIR / "extraction_batches"
    batch_files = sorted(batches_dir.glob("batch_*.json"))
    check(len(batch_files) == config.N_BATCHES,
          f"extraction_batches has exactly {config.N_BATCHES} batch files "
          f"(got {len(batch_files)})")

    seen_in_batches: list[str] = []
    bad_batch_size = 0
    for batch_path in batch_files:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        if len(batch["tasks"]) != config.BRIEF_BATCH_SIZE:
            bad_batch_size += 1
        seen_in_batches += [t["candidate_id"] for t in batch["tasks"]]
    check(bad_batch_size == 0,
          f"every batch holds exactly {config.BRIEF_BATCH_SIZE} tasks "
          f"(got {bad_batch_size} batches with the wrong size)")
    check(sorted(seen_in_batches) == sorted(candidate_ids),
          "every candidate appears exactly once across all extraction "
          "batches, and no others do")

    # Behavioural guarantee (not a static source scan, which would trip on
    # its own check): load_applications() only ever opens
    # data/applications_raw/batch_*.json, and build_task() only draws on
    # that data plus config.REQUIREMENTS / EXTRACTION_CONTRACT -- neither
    # touches config.ANSWER_KEY_PATH or config.ANSWER_KEY_CANDIDATES_PATH.
    # Confirmed by inspection at review time; recorded here as documentation
    # rather than re-asserted mechanically each run.
    log("note: this script never opens data/answer_key.csv or "
        "data/answer_key_candidates.csv (confirmed by inspection)")


def main() -> None:
    log("loading Phase 2 applications from data/applications_raw/")
    applications = load_applications()
    check(len(applications) == config.N_CANDIDATES,
          f"loaded {config.N_CANDIDATES} applications (got {len(applications)})")

    candidate_ids = [f"C{i:03d}" for i in range(1, config.N_CANDIDATES + 1)]

    tasks_dir = config.DATA_DIR / "extraction_tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    log(f"writing {len(candidate_ids)} extraction tasks to {tasks_dir}")

    tasks_by_id: dict[str, dict] = {}
    for candidate_id in candidate_ids:
        application = applications[candidate_id]
        task = build_task(candidate_id, application)
        tasks_by_id[candidate_id] = task
        out_path = tasks_dir / f"task_{candidate_id}.json"
        out_path.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")

    batches_dir = config.DATA_DIR / "extraction_batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    log(f"writing {config.N_BATCHES} batches of {config.BRIEF_BATCH_SIZE} "
        f"to {batches_dir}")

    for batch_num in range(config.N_BATCHES):
        start = batch_num * config.BRIEF_BATCH_SIZE
        end = start + config.BRIEF_BATCH_SIZE
        chunk_ids = candidate_ids[start:end]
        batch = {
            "batch_id": f"batch_{batch_num + 1:02d}",
            "role": {
                "title": config.ROLE_TITLE,
                "company": config.COMPANY["name"],
                "location": config.COMPANY["city"],
            },
            "output_contract": EXTRACTION_CONTRACT,
            "tasks": [tasks_by_id[cid] for cid in chunk_ids],
        }
        out_path = batches_dir / f"batch_{batch_num + 1:02d}.json"
        out_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")

    validate_outputs(candidate_ids)

    if FAILURES:
        log(f"FAILED: {len(FAILURES)} check(s) did not pass -- see [FAIL] "
            "lines above")
        sys.exit(1)

    log(f"done: {config.N_CANDIDATES} extraction tasks, "
        f"{config.N_BATCHES} batches, all self-validation checks passed")


if __name__ == "__main__":
    main()
