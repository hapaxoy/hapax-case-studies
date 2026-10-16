"""Batch the 240 application briefs into 30 files of 8 for the
prose-writing agents, each batch carrying the output contract the
writer must return.

Mirrors the churn case's split_briefs.py / the tender case's
attempt_briefs pattern: Python decides batching, never the agent.

Run: python split_briefs.py   (after generate_structured.py and
                                validate_structured.py have passed)
"""
from __future__ import annotations

import json

import config


def log(message: str) -> None:
    print(f"[split_briefs] {message}", flush=True)


OUTPUT_CONTRACT = {
    "instructions": (
        "For each candidate brief in this batch, write ONE application: a "
        "CV and a substantive one-page cover letter (roughly the word "
        "count given in that candidate's cover_letter.target_length_words "
        "-- Finnish application convention treats the letter as real "
        "content, not a two-line note). Follow the brief exactly: write "
        "every item in evidence_to_write and cover_letter.evidence_in_letter "
        "as genuine, concrete, specific evidence (a named project, "
        "employer, or role detail) using the vocabulary_mode / phrase_to_use "
        "given; write every item in claims_only and "
        "cover_letter.claims_in_letter as a bare, unsubstantiated assertion "
        "(no project, no company, no detail); never write anything, "
        "anywhere in the application, that could read as evidence for an "
        "item in not_to_mention; if `contradiction` is set, plant it "
        "exactly as instructed and do not resolve or flag it; if "
        "`borderline` is set, write the evidence plainly, neither oversold "
        "nor hedged. Evidence or claims listed under cover_letter must "
        "appear ONLY in the letter, never restated or echoed in the CV. "
        "Never add a signal not listed in the brief. Never drop a signal "
        "that is listed. The style_seed is a stable per-candidate knob for "
        "tone/verbosity/register -- use it for variety across candidates, "
        "not for content decisions."
    ),
    "return_format": {
        "description": "Return a single JSON array, one object per "
                        "candidate in this batch, in the same order as "
                        "the batch's `briefs` list.",
        "schema": {
            "candidate_id": "string, must match the brief's candidate_id",
            "cv_markdown": "string: the full CV as Markdown (or plain "
                           "text with clear section headers) -- education, "
                           "work history, skills list, projects as "
                           "applicable",
            "cover_letter_markdown": "string: the full one-page cover "
                                     "letter as Markdown or plain text",
        },
    },
}


def main() -> None:
    log("loading briefs")
    briefs = []
    for num in range(1, config.N_CANDIDATES + 1):
        path = config.BRIEFS_DIR / f"brief_{num:03d}.json"
        briefs.append(json.loads(path.read_text(encoding="utf-8")))

    assert len(briefs) == config.N_CANDIDATES

    config.BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    log(f"writing {config.N_BATCHES} batches of {config.BRIEF_BATCH_SIZE} to "
        f"{config.BATCHES_DIR}")

    for batch_num in range(config.N_BATCHES):
        start = batch_num * config.BRIEF_BATCH_SIZE
        end = start + config.BRIEF_BATCH_SIZE
        chunk = briefs[start:end]
        batch = {
            "batch_id": f"batch_{batch_num + 1:02d}",
            "role": {"title": config.ROLE_TITLE, "company": config.COMPANY["name"],
                      "location": config.COMPANY["city"]},
            "output_contract": OUTPUT_CONTRACT,
            "briefs": chunk,
        }
        out_path = config.BATCHES_DIR / f"batch_{batch_num + 1:02d}.json"
        out_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")

    log(f"done: {config.N_BATCHES} batch files, "
        f"{sum(len(json.loads((config.BATCHES_DIR / f'batch_{i+1:02d}.json').read_text(encoding='utf-8'))['briefs']) for i in range(config.N_BATCHES))} "
        "briefs total")


if __name__ == "__main__":
    main()
