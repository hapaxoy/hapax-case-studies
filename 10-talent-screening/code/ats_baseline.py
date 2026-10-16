"""Arm 1 of the four-arm baseline comparison (Project 10) --
the deterministic ATS: a keyword/synonym matcher of the kind a real
applicant-tracking system runs, scored over the 240 written applications.

This is a RANKING tool -- deliberately the opposite shape from the Hapax
workflow under test ("no ranking, no shortlist, ... the
recruiter decides"). That is the whole point of the exhibit: arm 1's output
is a ranked list, clearly labelled as the baseline's own output, and it lives
only under data/baselines/ -- never inside a dossier, never presented as
system output.

LOUD WARNING, read before touching SYNONYM_TABLE below:
    The synonym lists in this file are built from the REQUIREMENT TEXT in
    config.REQUIREMENTS ONLY (the id/name/description a real ATS vendor
    would be handed when the client fills in a job-requirements form), plus
    plain-English synonyms a generic ATS vendor would plausibly ship for
    that vocabulary. This file must NEVER read config.DISPLACEMENT_TABLE --
    that table is key-side trap knowledge (the hidden-gem
    subplot), and copying its domain-specific phrasing into the ATS's own
    dictionary would rig pre-registration A2 (the ATS should plausibly MISS
    displaced vocabulary, not be handed the answer). A self-check assertion
    below (`assert_no_displacement_leak`) enforces this mechanically: every
    synonym string is checked against every displacement-table phrase.

Scoring scheme (documented, not buried in logic -- see CONFIG block):
    Each of the 12 requirements gets a binary hit flag per candidate: 1 if
    ANY of its synonyms appears as a case-insensitive substring anywhere in
    the scored text, 0 otherwise. This is a genuine simplification real
    keyword-matching ATSes share -- literal substring/keyword screens do not
    weigh repeat mentions, and multiple hits for the same requirement count
    once. The per-candidate score is a weighted sum of hit flags:
    must-have hits x3, desirable hits x2, constraint hits x1 (the
    pre-registered weighting). Two variants are scored:
      - full text (CV + cover letter concatenated) -- the "generous" primary
        configuration.
      - CV only -- the sensitivity check, since real ATSes often never
        ingest the cover letter at all.

Rank: descending by score, ties broken deterministically by candidate_id
ascending (see RANK_TIE_BREAK below) -- every candidate gets a unique rank,
so "no ties broken non-deterministically" (validate_baselines.py's check)
holds by construction.

This script never reads data/answer_key.csv or data/answer_key_candidates.csv
-- per the portfolio's standing rule, nothing but the marking script reads
the key. It only ever reads config.py (requirement text) and
data/applications_raw/ (written CV/letter prose).

Run: python ats_baseline.py

Outputs:
  data/baselines/ats_scores.csv          -- full-text variant (primary)
  data/baselines/ats_scores_cv_only.csv  -- CV-only sensitivity variant
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import config
from build_extraction_tasks import load_applications


def log(message: str) -> None:
    print(f"[ats_baseline] {message}", flush=True)


# ---------------------------------------------------------------------------
# CONFIG BLOCK -- every tunable for this baseline lives here, not buried in
# scoring logic below.
# ---------------------------------------------------------------------------

CATEGORY_WEIGHTS = {"must_have": 3, "desirable": 2, "constraint": 1}

OUTPUT_DIR = config.DATA_DIR / "baselines"
FULL_TEXT_OUTPUT_PATH = OUTPUT_DIR / "ats_scores.csv"
CV_ONLY_OUTPUT_PATH = OUTPUT_DIR / "ats_scores_cv_only.csv"

# Tie-break rule for the ranked list: sort by (score DESC, candidate_id ASC)
# and assign ranks 1..N in that order. candidate_id ("C001".."C240") sorts
# lexicographically identically to numeric order since it is always
# zero-padded to 3 digits, so this is a stable, fully deterministic,
# reproducible tie-break -- no random draw, no insertion-order accident.
RANK_TIE_BREAK = "candidate_id ascending"

# ---------------------------------------------------------------------------
# The synonym table -- built from config.REQUIREMENTS text only. See the
# module docstring's LOUD WARNING above. Every synonym here is either drawn
# directly from a requirement's own name/description, or is a plain-English
# industry-generic term/abbreviation a real ATS vendor's keyword dictionary
# would plausibly ship for that requirement -- never a phrase specific to
# this corpus's displacement or contradiction mechanics.
# ---------------------------------------------------------------------------

SYNONYM_TABLE = {
    "R01": [  # Phased-array / beamforming signal processing
        "phased array", "phased-array", "beamforming", "beam-forming",
        "beamformer", "antenna array", "array signal processing",
        "radar signal processing", "sonar signal processing",
    ],
    "R02": [  # Embedded DSP in C/C++
        "embedded", "c++", "c/c++", "firmware", "real-time embedded",
        "digital signal processing", "embedded systems",
        "embedded software",
    ],
    "R03": [  # Production Python
        "python", "production code", "software engineering",
        "unit testing", "unit tests", "test-driven", "ci/cd",
        "code review",
    ],
    "R04": [  # RF measurement experience
        "rf measurement", "network analyser", "network analyzer",
        "spectrum analyser", "spectrum analyzer", "anechoic chamber",
        "rf calibration", "rf front end", "vector network analyzer",
        "vna",
    ],
    "R05": [  # Relevant degree or demonstrated equivalent
        "electrical engineering", "physics", "applied mathematics",
        "electronic engineering", "bsc", "msc", "phd", "degree",
    ],
    "R06": [  # Kalman filtering / estimation theory
        "kalman filter", "kalman filtering", "state estimation",
        "estimation theory", "extended kalman filter", "ekf",
        "particle filter",
    ],
    "R07": [  # Satellite or airborne platform experience
        "satellite", "spaceborne", "airborne", "aircraft platform",
        "flight hardware", "space mission", "payload",
    ],
    "R08": [  # Team-lead experience
        "team lead", "technical lead", "engineering lead",
        "managed a team", "led a team", "line management", "supervisor",
    ],
    "R09": [  # Publications or open-source record
        "publication", "peer-reviewed", "peer reviewed", "open source",
        "open-source", "github", "conference paper", "journal",
    ],
    "R10": [  # EU work authorisation
        "eu work authorisation", "eu work authorization",
        "eligible to work in the eu", "work permit", "right to work",
        "eu citizen",
    ],
    "R11": [  # Working English
        "fluent english", "professional working proficiency",
        "native english", "c1 english", "c2 english", "working english",
    ],
    "R12": [  # Onsite in Oulu / relocation
        "oulu", "relocate", "relocation", "onsite", "willing to relocate",
        "based in finland",
    ],
}
assert set(SYNONYM_TABLE) == {r["id"] for r in config.REQUIREMENTS}, (
    "SYNONYM_TABLE must cover exactly the 12 frozen requirement ids")


def assert_no_displacement_leak() -> None:
    """Self-check: no synonym string anywhere in SYNONYM_TABLE equals any
    phrase in config.DISPLACEMENT_TABLE. This is the mechanical enforcement
    of the module docstring's LOUD WARNING -- re-run standalone by
    validate_baselines.py so this stays true even if SYNONYM_TABLE is
    edited later without re-reading this docstring.
    """
    displacement_phrases = {
        phrase.strip().lower()
        for phrases in config.DISPLACEMENT_TABLE.values()
        for phrase in phrases
    }
    leaks = []
    for req_id, synonyms in SYNONYM_TABLE.items():
        for synonym in synonyms:
            if synonym.strip().lower() in displacement_phrases:
                leaks.append((req_id, synonym))
    assert not leaks, (
        f"SYNONYM_TABLE leaks {len(leaks)} displacement-table phrase(s) "
        f"into the ATS's own dictionary -- key-side trap knowledge must "
        f"never be used to build the baseline: {leaks}")
    log(f"[ok] synonym-leak self-check: 0 of "
        f"{sum(len(v) for v in SYNONYM_TABLE.values())} synonym strings "
        "match a displacement-table phrase")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_candidate(text: str) -> dict[str, int]:
    """Binary hit flag per requirement: 1 if any synonym is a
    case-insensitive substring of `text`, 0 otherwise. Plain substring
    matching (not word-boundary regex) is a deliberate modelling choice --
    real keyword-matching ATSes commonly are this blunt, and the point of
    this baseline is to be realistically naive, not generously accurate.
    """
    lowered = text.lower()
    hits = {}
    for req_id, synonyms in SYNONYM_TABLE.items():
        hits[req_id] = int(any(syn in lowered for syn in synonyms))
    return hits


def weighted_total(hits: dict[str, int]) -> int:
    total = 0
    for req_id, hit in hits.items():
        category = config.REQUIREMENT_BY_ID[req_id]["category"]
        total += hit * CATEGORY_WEIGHTS[category]
    return total


def build_score_table(applications: dict[str, dict], *, cv_only: bool) -> pd.DataFrame:
    rows = []
    for candidate_id in sorted(applications, key=lambda c: int(c[1:])):
        application = applications[candidate_id]
        if cv_only:
            text = application["cv_markdown"]
        else:
            text = application["cv_markdown"] + "\n\n" + application["cover_letter_markdown"]
        hits = score_candidate(text)
        row = {"candidate_id": candidate_id}
        for req_id in SYNONYM_TABLE:
            row[f"{req_id}_hit"] = hits[req_id]
        row["total_score"] = weighted_total(hits)
        rows.append(row)

    df = pd.DataFrame(rows)
    # Deterministic tie-break: score DESC, candidate_id ASC, then rank 1..N
    # in that exact order -- see RANK_TIE_BREAK above.
    df["_candidate_num"] = df["candidate_id"].str[1:].astype(int)
    df = df.sort_values(["total_score", "_candidate_num"], ascending=[False, True]).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)
    df = df.drop(columns=["_candidate_num"])
    return df


def print_summary(df: pd.DataFrame, label: str) -> None:
    log(f"=== score distribution: {label} ===")
    log(f"n={len(df)}  mean={df['total_score'].mean():.2f}  "
        f"std={df['total_score'].std():.2f}  min={df['total_score'].min()}  "
        f"median={df['total_score'].median():.1f}  max={df['total_score'].max()}")
    top10 = df.sort_values("rank").head(10)
    log("top 10 by ATS rank:")
    for _, row in top10.iterrows():
        log(f"  rank {int(row['rank']):>3}  {row['candidate_id']}  "
            f"score={int(row['total_score'])}")


def main() -> None:
    assert_no_displacement_leak()

    log("loading Phase 2 applications from data/applications_raw/")
    applications = load_applications()
    assert len(applications) == config.N_CANDIDATES, (
        f"expected {config.N_CANDIDATES} applications, got "
        f"{len(applications)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assert OUTPUT_DIR != config.DATA_DIR / "applications_raw", (
        "output path must never equal an input path")

    log("scoring full-text variant (CV + cover letter, the 'generous' "
        "primary configuration)")
    full_df = build_score_table(applications, cv_only=False)
    full_df.to_csv(FULL_TEXT_OUTPUT_PATH, index=False)
    log(f"wrote {FULL_TEXT_OUTPUT_PATH} ({len(full_df)} rows)")
    print_summary(full_df, "full text (CV + cover letter)")

    log("scoring CV-only sensitivity variant")
    cv_df = build_score_table(applications, cv_only=True)
    cv_df.to_csv(CV_ONLY_OUTPUT_PATH, index=False)
    log(f"wrote {CV_ONLY_OUTPUT_PATH} ({len(cv_df)} rows)")
    print_summary(cv_df, "CV only (sensitivity check)")

    log("done.")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        sys.exit(f"[ats_baseline] ERROR: missing input file -- {exc}")
    except AssertionError as exc:
        sys.exit(f"[ats_baseline] ERROR: {exc}")
