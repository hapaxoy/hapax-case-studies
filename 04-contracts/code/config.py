"""Configuration for Project 4 (Contract Clause Extraction).

Every tunable for corpus preparation (and the pipeline that reuses
this module) lives here — archetype-style parameters, counts, and seeds are
never buried in generator logic.

This module holds constants and light validation ONLY. The join,
eligibility, and stratified-sampling logic lives in prepare_corpus.py.

Note on scope (rule 10, "answer-key isolation"):
this file must never name the clause-annotation CSV or the derived key
directory as literal path strings — only the derivation script, the
validator, and the (not-yet-written) evaluator may reference those, because
those are the only places the annotations are meant to exist inside the
pipeline. (This paragraph itself avoids spelling either identifier out, so
it does not trip the isolation scan it is describing.)
"""

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Reproducibility
# --------------------------------------------------------------------------

RANDOM_SEED = 42

# --------------------------------------------------------------------------
# CUAD source cache — read-only, never modified by anything in this
# codebase.
#
# CACHE_DIR defaults to cache/CUAD_v1 beside the code folder and can be
# pointed elsewhere with the CUAD_V1_DIR environment variable. The CUAD
# archive is a ~106 MB download kept outside the data/ tree; it is fully
# recoverable on any machine from data/manifest.json (source URL + zip
# MD5/SHA-256 are recorded there), so nothing about the pipeline's
# correctness depends on this exact path.
# --------------------------------------------------------------------------

CACHE_DIR = Path(os.environ.get(
    "CUAD_V1_DIR",
    Path(__file__).resolve().parent.parent / "cache" / "CUAD_v1",
))
EXTRACTED = CACHE_DIR / "extracted" / "CUAD_v1"
ZIP_PATH = CACHE_DIR / "CUAD_v1.zip"

ZIP_MD5 = "c38f490a984420b8a62600db401fafd5"
ZIP_SHA256 = "88b694d99007d39777fa44cd72daf8297773d285dc3eab0091ba32078888d18e"
ZIP_URL = "https://zenodo.org/records/4595826/files/CUAD_v1.zip?download=1"

# --------------------------------------------------------------------------
# Corpus selection
# --------------------------------------------------------------------------

STREAM_SIZE = 50
HOLDOUT_SIZE = 100
MAX_WORDS = 15_000

# Read once during calibration (spike, 3 Jul 2026); excluded from eligibility
# so the pipeline never re-reads the contract it was calibrated against.
SPIKE_CONTRACT = ("EmbarkComInc_19991008_S-1A_EX-10.10_6487661_EX-10.10_"
                  "Co-Branding Agreement.txt")

# Word-count bands used as the second stratification axis (alongside
# inferred contract type). Upper bound exclusive; bands are contiguous.
LENGTH_BANDS = [(0, 2500), (2500, 7000), (7000, 15000)]

# Ordered (pattern, label) list for filename-based contract-type inference.
# First match wins; matched against the uppercased filename. "IP" is
# deliberately last: it is a substring hazard (it would fire inside many
# unrelated words/tokens), so INTELLECTUAL PROPERTY is caught explicitly
# earlier and the bare "IP" pattern only mops up what nothing else caught.
TYPE_PATTERNS = [
    ("AFFILIATE", "Affiliate"),
    ("AGENCY", "Agency"),
    ("COLLABORATION", "Collaboration"),
    ("COOPERATION", "Collaboration"),
    ("CO-BRANDING", "Co-Branding"),
    ("COBRANDING", "Co-Branding"),
    ("CONSULTING", "Consulting"),
    ("DEVELOPMENT", "Development"),
    ("DISTRIBUTOR", "Distributor"),
    ("DISTRIBUTION", "Distributor"),
    ("ENDORSEMENT", "Endorsement"),
    ("FRANCHISE", "Franchise"),
    ("HOSTING", "Hosting"),
    ("INTELLECTUAL PROPERTY", "IP"),
    ("JOINT VENTURE", "Joint Venture"),
    ("JOINTVENTURE", "Joint Venture"),
    ("LICENSE", "License"),
    ("LICENSING", "License"),
    ("MAINTENANCE", "Maintenance"),
    ("MANUFACTURING", "Manufacturing"),
    ("MARKETING", "Marketing"),
    ("NON-COMPETE", "Non-Compete"),
    ("NO-SOLICIT", "Non-Compete"),
    ("NON-DISPARAGEMENT", "Non-Compete"),
    ("OUTSOURCING", "Outsourcing"),
    ("PROMOTION", "Promotion"),
    ("RESELLER", "Reseller"),
    ("SERVICE", "Service"),
    ("SPONSORSHIP", "Sponsorship"),
    ("SUPPLY", "Supply"),
    ("STRATEGIC ALLIANCE", "Strategic Alliance"),
    ("TRANSPORTATION", "Transportation"),
    ("IP", "IP"),  # last: substring hazard, see note above
]
TYPE_FALLBACK = "Other"

# --------------------------------------------------------------------------
# Pipeline tunables — live here so every tunable is in one file, even
# though the corpus-preparation scripts do not use them.
# --------------------------------------------------------------------------

N_INDUCTION = 6   # min accepted positives (and, for two-sided claims,
                  # negatives) before the overseer is commissioned
READ_CAP = 60     # hard cap on total LLM contract reads (50 stream + <=10
                  # retry/fallback reserve)

# --------------------------------------------------------------------------
# Light validation — no heavier logic belongs in this module.
# --------------------------------------------------------------------------

assert STREAM_SIZE + HOLDOUT_SIZE == 150, "stream + holdout must total 150"
assert len(ZIP_MD5) == 32, "ZIP_MD5 must be a 32-hex-digit MD5 checksum"
assert len(ZIP_SHA256) == 64, "ZIP_SHA256 must be a 64-hex-digit SHA-256 checksum"
assert LENGTH_BANDS == sorted(LENGTH_BANDS), "LENGTH_BANDS must be ascending"
assert all(lo < hi for lo, hi in LENGTH_BANDS), "each band needs lo < hi"
assert all(LENGTH_BANDS[i][1] == LENGTH_BANDS[i + 1][0]
           for i in range(len(LENGTH_BANDS) - 1)), "bands must be contiguous"
assert N_INDUCTION > 0 and READ_CAP >= STREAM_SIZE, "phase-3 tunables out of range"
