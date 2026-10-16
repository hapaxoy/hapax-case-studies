"""Configuration for the talent-screening corpus generator (Project 10, Phase 1).

Every tunable lives here: RANDOM_SEED, the requirement profile (12 requirements),
the vocabulary-displacement table for the hidden-gem archetype,
the archetype table (exact counts), demographic-stratum name
pools and target proportions, the fictional employer, the 12 recruiter-persona
definitions and the 48-application persona subset, and every evidence-location
and status vocabulary used downstream.

Per the Hapax core generation pattern: this module controls STRUCTURE only.
No CV prose, no cover-letter prose, no chat transcript language is written
here or by generate_structured.py -- that is Phase 2/3 LLM-agent
work, constrained to never add or remove what this file
plants.

Every application is a
CV *and* a substantive one-page cover letter (Finnish application
convention). "cover_letter" is therefore a first-class evidence location
alongside work_history / project_description / skills_list, and some planted
evidence items are deliberately LETTER-ONLY -- present nowhere else in the
application. The clearest use of this is the hidden-gem archetype (F): half
of F's 18 candidates have their displaced skill surface only in the letter,
which is a strictly harder plant than displacement alone. Keyword stuffers
(D) also lean on the letter, since unsubstantiated claims naturally "bloom"
in motivational prose. See LETTER_ONLY_* constants below.

The employer, **Kaikuvaara Oy**, is a fictional Finnish remote-sensing
instruments maker headquartered in Oulu. "Kaiku" (echo) + "vaara"
(fell/hill) reads naturally as a company name while evoking radar/sonar echo
returns.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Global
# ---------------------------------------------------------------------------

RANDOM_SEED = 42  # fully reproducible: every RNG draw below is keyed off this
                  # plus a deterministic per-dimension/per-candidate salt via
                  # deterministic_rng() in generate_structured.py, so a re-run
                  # is byte-identical.

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
BRIEFS_DIR = DATA_DIR / "briefs"
BATCHES_DIR = DATA_DIR / "brief_batches"
ANSWER_KEY_PATH = DATA_DIR / "answer_key.csv"
ANSWER_KEY_CANDIDATES_PATH = DATA_DIR / "answer_key_candidates.csv"
PERSONA_SUBSET_PATH = DATA_DIR / "persona_subset.json"

# The corpus's fictional "now": applications are being screened in autumn
# 2026. No generated date (graduation, employment, career gap) may fall
# after this year -- validate_structured.py enforces this at year
# granularity (no month-level dates are generated anywhere in this corpus).
CORPUS_NOW_YEAR = 2026

N_CANDIDATES = 240
BRIEF_BATCH_SIZE = 8
N_BATCHES = N_CANDIDATES // BRIEF_BATCH_SIZE
assert N_CANDIDATES % BRIEF_BATCH_SIZE == 0

# ---------------------------------------------------------------------------
# The company and role
# ---------------------------------------------------------------------------

COMPANY = {
    "name": "Kaikuvaara Oy",
    "city": "Oulu",
    "country": "Finland",
    "sector": "Remote-sensing instruments (spaceborne and airborne radar / "
              "optical payload electronics)",
    "employee_count": 140,
    "description": (
        "Kaikuvaara Oy designs and builds signal-processing electronics for "
        "spaceborne and airborne remote-sensing instruments -- SAR and "
        "scatterometer payloads, optical-instrument readout chains, and the "
        "ground-segment hardware that processes their downlinked data. "
        "Based in Oulu, drawing on the city's wireless and photonics "
        "engineering base."
    ),
}

ROLE_TITLE = "Senior Signal Processing Engineer"

# ---------------------------------------------------------------------------
# The requirement profile: 12 requirements, frozen before generation.
# Five must-have technical, four desirable, three constraints.
# ---------------------------------------------------------------------------

REQUIREMENTS = [
    {"id": "R01", "category": "must_have",
     "name": "Phased-array / beamforming signal processing",
     "description": "Hands-on experience designing or implementing "
                     "phased-array or beamforming signal-processing "
                     "algorithms (e.g. for radar, sonar, or comms arrays)."},
    {"id": "R02", "category": "must_have",
     "name": "Embedded DSP in C/C++",
     "description": "Production embedded signal-processing software written "
                     "in C or C++, running on real hardware under real "
                     "timing constraints."},
    {"id": "R03", "category": "must_have",
     "name": "Production Python",
     "description": "Python written to production/engineering standards "
                     "(tested, maintained, used by others) -- not one-off "
                     "analysis scripts."},
    {"id": "R04", "category": "must_have",
     "name": "RF measurement experience",
     "description": "Hands-on RF test-bench work: network analysers, "
                     "spectrum analysers, anechoic-chamber measurement, "
                     "calibration of RF front ends."},
    {"id": "R05", "category": "must_have",
     "name": "Relevant degree or demonstrated equivalent",
     "description": "A degree in electrical engineering, physics, applied "
                     "mathematics or a closely adjacent field, or "
                     "demonstrated equivalent competence without one."},
    {"id": "R06", "category": "desirable",
     "name": "Kalman filtering / estimation theory",
     "description": "Applied experience with Kalman filters or related "
                     "state-estimation techniques."},
    {"id": "R07", "category": "desirable",
     "name": "Satellite or airborne platform experience",
     "description": "Work on instruments or systems that flew on a "
                     "satellite or aircraft platform."},
    {"id": "R08", "category": "desirable",
     "name": "Team-lead experience",
     "description": "Formal technical leadership of a team (not just "
                     "senior individual-contributor work)."},
    {"id": "R09", "category": "desirable",
     "name": "Publications or open-source record",
     "description": "Peer-reviewed publications or a substantive "
                     "open-source contribution record."},
    {"id": "R10", "category": "constraint",
     "name": "EU work authorisation",
     "description": "Legally able to work in the EU without sponsorship."},
    {"id": "R11", "category": "constraint",
     "name": "Working English",
     "description": "Professional working fluency in English (the "
                     "company's working language)."},
    {"id": "R12", "category": "constraint",
     "name": "Onsite in Oulu / relocation",
     "description": "Willing to work onsite in Oulu, relocating if not "
                     "already local; the role is not remote."},
]
REQUIREMENT_BY_ID = {r["id"]: r for r in REQUIREMENTS}
MUST_HAVE_IDS = [r["id"] for r in REQUIREMENTS if r["category"] == "must_have"]
DESIRABLE_IDS = [r["id"] for r in REQUIREMENTS if r["category"] == "desirable"]
CONSTRAINT_IDS = [r["id"] for r in REQUIREMENTS if r["category"] == "constraint"]
assert len(MUST_HAVE_IDS) == 5 and len(DESIRABLE_IDS) == 4 and len(CONSTRAINT_IDS) == 3
assert len(REQUIREMENTS) == 12

# ---------------------------------------------------------------------------
# Ground-truth status vocabulary and evidence-location vocabulary.
# ---------------------------------------------------------------------------

STATUSES = ["evidenced", "claimed_only", "contradicted", "absent", "not_stated"]

# "cover_letter" added mid-build: every application is now
# CV + a substantive one-page cover letter, and some evidence lives only
# there. The other three locations are CV sections.
LOCATIONS = ["work_history", "project_description", "skills_list", "cover_letter"]

# ---------------------------------------------------------------------------
# Vocabulary displacement table -- the hidden-gem (F) subplot. Only R01, R02,
# R03 carry a displacement table (the three worked examples);
# validate_structured.py asserts every F candidate's displaced phrase is
# drawn from exactly this table and is never the canonical requirement name
# or description text.
# ---------------------------------------------------------------------------

DISPLACEMENT_TABLE = {
    "R01": [
        "automotive FMCW radar DSP",
        "beamforming for 5G massive-MIMO base stations",
        "sonar array processing (towed-array beamforming)",
        "acoustic beamforming for hearing-aid microphone arrays",
    ],
    "R02": [
        "sensor-fusion firmware for drone flight controllers",
        "real-time audio DSP firmware for hearing aids",
        "engine-control-unit embedded software",
        "embedded signal pipeline for a medical ECG/EEG front end",
    ],
    "R03": [
        "a physics PhD's side-project tooling that became the group's "
        "shared analysis pipeline",
        "internal data-pipeline scripts at a research institute that grew "
        "into a maintained internal package",
        "an open-source contribution to a scientific Python library in the "
        "numpy/scipy ecosystem",
        "automation and analysis scripts for a particle-physics detector "
        "collaboration",
    ],
}
DISPLACEMENT_REQUIREMENT_IDS = list(DISPLACEMENT_TABLE.keys())
assert DISPLACEMENT_REQUIREMENT_IDS == ["R01", "R02", "R03"]
for _rid, _phrases in DISPLACEMENT_TABLE.items():
    _canonical = REQUIREMENT_BY_ID[_rid]["name"].lower()
    for _p in _phrases:
        assert _canonical not in _p.lower(), (
            f"displaced phrase for {_rid} leaks the canonical term: {_p!r}")

# ---------------------------------------------------------------------------
# Credential-inflation (E) contradiction templates -- exactly two mechanisms,
# assigned alternately across E's 15 candidates. Self-defending: only E rows
# may carry a non-null contradiction in the generated key
# (validate_structured.py asserts this).
# ---------------------------------------------------------------------------

CONTRADICTION_TEMPLATES = [
    {
        "code": "degree_date",
        "requirement_id": "R05",
        "label": "Degree conferral date contradicts a job that required it",
        "instruction": (
            "State a PhD (or Master's) conferral year in the education "
            "section. Separately, in the work-history entry immediately "
            "following graduation, describe a role whose stated start date "
            "requires the degree to have already been finished at least a "
            "year before it was actually conferred. Do not resolve or "
            "flag the discrepancy -- just let both dates stand as written."
        ),
    },
    {
        "code": "title_inflation",
        "requirement_id": "R08",
        "label": "Claimed leadership title contradicted by the work-history entry",
        "instruction": (
            "In the cover letter or CV summary, claim a leadership title "
            "for a specific employer and period (e.g. 'led a team of "
            "engineers as Head of DSP at <employer>'). In the work-history "
            "entry for that same employer and period, give a plain "
            "individual-contributor title with no direct reports "
            "mentioned, and keep the tenure too short to be plausible for "
            "that scope of leadership. Do not resolve or flag the "
            "discrepancy -- just let both stand as written."
        ),
    },
]
CONTRADICTION_BY_CODE = {c["code"]: c for c in CONTRADICTION_TEMPLATES}
assert len(CONTRADICTION_TEMPLATES) == 2

# ---------------------------------------------------------------------------
# Genuine-borderline (H) templates -- exactly two mechanisms, rotated across
# H's 12 candidates. Each is genuinely defensible either way; the key records
# `borderline_note` rather than forcing a status.
# ---------------------------------------------------------------------------

BORDERLINE_TEMPLATES = [
    {
        "code": "academic_rf",
        "requirement_id": "R04",
        "label": "RF measurement experience is real but purely academic",
        "instruction": (
            "Describe genuine RF measurement work (network-analyser "
            "calibration, antenna pattern measurement) done entirely in a "
            "university CubeSat or ground-station project, with no "
            "industrial employer attached. Write it plainly as a project, "
            "neither oversold nor hedged."
        ),
        "borderline_note": (
            "Real RF measurement work, but gained in an academic CubeSat "
            "project rather than an industrial test bench -- defensible "
            "either way whether it counts as meeting the requirement at "
            "senior level."
        ),
    },
    {
        "code": "hobby_phased_array",
        "requirement_id": "R01",
        "label": "Phased-array experience is real but an unreviewed hobby project",
        "instruction": (
            "Describe a genuine, technically detailed personal/hobby "
            "project building a small (e.g. 4-element) beamforming "
            "demonstrator, with no employer, publication, or peer review "
            "behind it. Write it plainly as a side project, neither "
            "oversold nor hedged."
        ),
        "borderline_note": (
            "Real phased-array work and technically credible, but a "
            "solo hobby project with no employer or peer review behind it "
            "-- defensible either way whether it meets the bar at senior "
            "level."
        ),
    },
]
BORDERLINE_BY_CODE = {b["code"]: b for b in BORDERLINE_TEMPLATES}
assert len(BORDERLINE_TEMPLATES) == 2

# ---------------------------------------------------------------------------
# The archetype table (exact counts -- sum must be 240).
# `desirable_profile` / `constraint_profile` give the per-requirement status
# probabilities used for R06-R09 / R10-R12 (drawn independently per
# requirement per candidate); must-have handling is archetype-specific logic
# in generate_structured.py, not a flat profile, because the archetypes are
# defined by structural rules (exactly one absent, all five claimed, etc.)
# rather than independent per-item draws.
# ---------------------------------------------------------------------------

# Shared baseline profile for desirables/constraints on the "otherwise
# ordinary" archetypes (A, C, E, F, G, H): a believable mixed CV.
_STRONG_DESIRABLE_PROFILE = {
    "evidenced": 0.35, "claimed_only": 0.15, "not_stated": 0.40, "absent": 0.10,
}
_STRONG_CONSTRAINT_PROFILE = {
    "evidenced": 0.85, "claimed_only": 0.0, "not_stated": 0.15, "absent": 0.0,
}
_WEAK_DESIRABLE_PROFILE = {
    "evidenced": 0.05, "claimed_only": 0.10, "not_stated": 0.35, "absent": 0.50,
}
_WEAK_CONSTRAINT_PROFILE = {
    "evidenced": 0.55, "claimed_only": 0.0, "not_stated": 0.30, "absent": 0.15,
}
_OFFROLE_CONSTRAINT_PROFILE = {
    "evidenced": 0.35, "claimed_only": 0.0, "not_stated": 0.55, "absent": 0.10,
}
for _prof in (_STRONG_DESIRABLE_PROFILE, _STRONG_CONSTRAINT_PROFILE,
              _WEAK_DESIRABLE_PROFILE, _WEAK_CONSTRAINT_PROFILE,
              _OFFROLE_CONSTRAINT_PROFILE):
    assert abs(sum(_prof.values()) - 1.0) < 1e-9

ARCHETYPES = [
    {"id": "A", "label": "Clear fit", "n": 21,
     "must_have_rule": "all_evidenced",
     "desirable_profile": _STRONG_DESIRABLE_PROFILE,
     "constraint_profile": _STRONG_CONSTRAINT_PROFILE,
     "description": "All must-haves evidenced plainly."},
    {"id": "B", "label": "Clear miss", "n": 87,
     "must_have_rule": "clear_miss",
     "desirable_profile": _WEAK_DESIRABLE_PROFILE,
     "constraint_profile": _STRONG_CONSTRAINT_PROFILE,
     "description": "Fails >= 3 must-haves, no disguise."},
    {"id": "C", "label": "Near miss", "n": 36,
     "must_have_rule": "near_miss",
     "desirable_profile": _STRONG_DESIRABLE_PROFILE,
     "constraint_profile": _STRONG_CONSTRAINT_PROFILE,
     "description": "Exactly one must-have genuinely absent."},
    {"id": "D", "label": "Keyword stuffer", "n": 22,
     "must_have_rule": "all_claimed_only",
     "desirable_profile": {"evidenced": 0.0, "claimed_only": 0.70,
                            "not_stated": 0.30, "absent": 0.0},
     "constraint_profile": _STRONG_CONSTRAINT_PROFILE,
     "description": "Claims everything; evidence thin or circular."},
    {"id": "E", "label": "Credential inflation", "n": 15,
     "must_have_rule": "credential_inflation",
     "desirable_profile": _STRONG_DESIRABLE_PROFILE,
     "constraint_profile": _STRONG_CONSTRAINT_PROFILE,
     "description": "Title/degree claims contradicted by dates or "
                     "internal details."},
    {"id": "F", "label": "Hidden gem", "n": 18,
     "must_have_rule": "displaced",
     "desirable_profile": _STRONG_DESIRABLE_PROFILE,
     "constraint_profile": _STRONG_CONSTRAINT_PROFILE,
     "description": "Fully qualified, but one skill lives under displaced "
                     "vocabulary."},
    {"id": "G", "label": "Nonlinear path", "n": 15,
     "must_have_rule": "all_evidenced",
     "desirable_profile": _STRONG_DESIRABLE_PROFILE,
     "constraint_profile": _STRONG_CONSTRAINT_PROFILE,
     "description": "Career gaps (parental leave, retraining), competence "
                     "intact.", "forced_career_gap": True},
    {"id": "H", "label": "Genuine borderline", "n": 12,
     "must_have_rule": "borderline",
     "desirable_profile": _STRONG_DESIRABLE_PROFILE,
     "constraint_profile": _STRONG_CONSTRAINT_PROFILE,
     "description": "One requirement is genuinely defensible either way; "
                     "the key records that, not a resolved verdict."},
    {"id": "OFFROLE", "label": "Off-role applicant", "n": 14,
     "must_have_rule": "offrole",
     "desirable_profile": {"evidenced": 0.0, "claimed_only": 0.0,
                            "not_stated": 0.30, "absent": 0.70},
     "constraint_profile": _OFFROLE_CONSTRAINT_PROFILE,
     "description": "The realistic noise floor: applicants from unrelated "
                     "fields."},
]
ARCHETYPE_BY_ID = {a["id"]: a for a in ARCHETYPES}
assert sum(a["n"] for a in ARCHETYPES) == N_CANDIDATES
assert [a["id"] for a in ARCHETYPES] == ["A", "B", "C", "D", "E", "F", "G", "H", "OFFROLE"]

# Self-defending assertions: the mechanisms that define D / E / F / H must be
# reachable by exactly one archetype each. A later config edit that, say,
# gives B a `must_have_rule` of "displaced" trips this immediately rather
# than silently producing an uncatchable trap.
_RULE_OWNERS = {}
for _a in ARCHETYPES:
    _RULE_OWNERS.setdefault(_a["must_have_rule"], []).append(_a["id"])
assert _RULE_OWNERS["all_claimed_only"] == ["D"], _RULE_OWNERS
assert _RULE_OWNERS["credential_inflation"] == ["E"], _RULE_OWNERS
assert _RULE_OWNERS["displaced"] == ["F"], _RULE_OWNERS
assert _RULE_OWNERS["borderline"] == ["H"], _RULE_OWNERS
assert _RULE_OWNERS["offrole"] == ["OFFROLE"], _RULE_OWNERS
assert sorted(_RULE_OWNERS["all_evidenced"]) == ["A", "G"], _RULE_OWNERS
assert set(a.get("forced_career_gap", False) for a in ARCHETYPES if a["id"] != "G") == {False}
assert ARCHETYPE_BY_ID["G"]["forced_career_gap"] is True

# ---------------------------------------------------------------------------
# Displacement placement -- which of F's 18 candidates get which displaced
# requirement (6 each of R01/R02/R03, the three worked examples), and
# which of those are LETTER-ONLY (half of F, the
# deliberately-good plant). Within each group of 6: 3 letter-only
# (cover_letter), 2 project_description, 1 work_history -- exact, not
# probabilistic, so the headline "9 of 18 F candidates are letter-only" is a
# frozen number, not a seed-dependent one.
# ---------------------------------------------------------------------------

F_DISPLACEMENT_PLAN = []
for _rid in DISPLACEMENT_REQUIREMENT_IDS:
    F_DISPLACEMENT_PLAN += [(_rid, "cover_letter")] * 3
    F_DISPLACEMENT_PLAN += [(_rid, "project_description")] * 2
    F_DISPLACEMENT_PLAN += [(_rid, "work_history")] * 1
assert len(F_DISPLACEMENT_PLAN) == ARCHETYPE_BY_ID["F"]["n"] == 18
assert sum(1 for _, loc in F_DISPLACEMENT_PLAN if loc == "cover_letter") == 9

# ---------------------------------------------------------------------------
# Baseline evidence-location distribution for ordinary evidenced must-have /
# desirable items (every archetype except F's displaced item, which uses
# F_DISPLACEMENT_PLAN above, and D's claims, which use
# D_CLAIM_LOCATION_PROFILE below). A modest cover_letter share here is what
# lets letter-only evidence show up incidentally across A/C/E/G/H too, not
# only in the F narrative.
# ---------------------------------------------------------------------------

BASELINE_EVIDENCE_LOCATION_PROFILE = {
    "work_history": 0.45, "project_description": 0.30,
    "skills_list": 0.10, "cover_letter": 0.15,
}
assert abs(sum(BASELINE_EVIDENCE_LOCATION_PROFILE.values()) - 1.0) < 1e-9

# D (keyword stuffer): "stuffers bloom in letters" --
# claimed-only items skew toward the cover letter rather than the skills
# list alone.
D_CLAIM_LOCATION_PROFILE = {"cover_letter": 0.60, "skills_list": 0.40}
assert abs(sum(D_CLAIM_LOCATION_PROFILE.values()) - 1.0) < 1e-9

# ---------------------------------------------------------------------------
# Career-gap flag -- exact per-archetype counts (not probabilities), designed
# so the TRUE ("fully qualified": A/F/G) rate inside the gap=True population
# matches the overall population rate to within a fraction of a percentage
# point, despite G's gap flag being forced to 100% by the archetype's own
# story. A and F are
# deliberately gap-free (their narrative doesn't call for it); H is kept
# gap-free too, to avoid compounding two designed ambiguities in one
# candidate.
# ---------------------------------------------------------------------------

CAREER_GAP_COUNTS = {
    "A": 0, "B": 26, "C": 11, "D": 7, "E": 4, "F": 0, "G": 15, "H": 0, "OFFROLE": 4,
}
assert set(CAREER_GAP_COUNTS) == set(ARCHETYPE_BY_ID)
for _aid, _cnt in CAREER_GAP_COUNTS.items():
    assert 0 <= _cnt <= ARCHETYPE_BY_ID[_aid]["n"]
assert CAREER_GAP_COUNTS["G"] == ARCHETYPE_BY_ID["G"]["n"]  # G is forced to 100%
TOTAL_CAREER_GAP = sum(CAREER_GAP_COUNTS.values())
assert TOTAL_CAREER_GAP == 67

CAREER_GAP_REASONS = [
    "parental leave",
    "caregiving leave",
    "career break for further study / retraining",
    "extended illness recovery",
    "sabbatical / travel",
    "redundancy followed by a slow requalification period",
]

# "Fully qualified" archetypes for the orthogonality/parity arithmetic above
# and for validate_structured.py's balance check.
FULLY_QUALIFIED_ARCHETYPES = ["A", "F", "G"]

# ---------------------------------------------------------------------------
# Demographic strata -- name-origin x gender name pools (~20 names per pool),
# surname pools per name-origin, and global target proportions for each
# stratum dimension. Names are invented, generic, and not modelled on any
# real individual.
# ---------------------------------------------------------------------------

NAME_ORIGINS = ["finnish", "non_finnish_european", "non_european"]
GENDERS = ["male", "female"]

NAME_ORIGIN_TARGET_COUNTS = {"finnish": 100, "non_finnish_european": 80, "non_european": 60}
assert sum(NAME_ORIGIN_TARGET_COUNTS.values()) == N_CANDIDATES
GENDER_TARGET_COUNTS = {"male": 120, "female": 120}
assert sum(GENDER_TARGET_COUNTS.values()) == N_CANDIDATES

FIRST_NAMES = {
    ("finnish", "male"): [
        "Mikko", "Juha", "Antti", "Jussi", "Ville", "Matti", "Sami", "Tomi",
        "Jari", "Petri", "Timo", "Heikki", "Jukka", "Marko", "Pekka", "Kari",
        "Esa", "Hannu", "Olli", "Aleksi",
    ],
    ("finnish", "female"): [
        "Anna", "Laura", "Sanna", "Elina", "Riikka", "Johanna", "Outi",
        "Marja", "Tiina", "Kaisa", "Hanna", "Minna", "Paivi", "Satu", "Anne",
        "Marika", "Heidi", "Kirsi", "Katja", "Emilia",
    ],
    ("non_finnish_european", "male"): [
        "Lukas", "Matteo", "Jan", "Pierre", "Erik", "Stefan", "Marco",
        "Tomas", "Nils", "Andrei", "Dimitri", "Pawel", "Henrik", "Sven",
        "Klaus", "Giovanni", "Rasmus", "Karel", "Bartosz", "Ludvig",
    ],
    ("non_finnish_european", "female"): [
        "Sofia", "Emma", "Marie", "Ingrid", "Klara", "Elena", "Anja",
        "Katarina", "Zofia", "Nadia", "Anneke", "Greta", "Livia", "Marta",
        "Freja", "Camille", "Isabel", "Kristina", "Aleksandra", "Sanne",
    ],
    ("non_european", "male"): [
        "Arjun", "Wei", "Kenji", "Diego", "Ahmed", "Chinedu", "Hiroshi",
        "Rahul", "Carlos", "Kwame", "Amir", "Raj", "Feng", "Santiago",
        "Tunde", "Farid", "Ravi", "Jian", "Mateus", "Omar",
    ],
    ("non_european", "female"): [
        "Priya", "Mei", "Fatima", "Ana", "Ngozi", "Yuki", "Aisha", "Camila",
        "Zara", "Chidinma", "Leila", "Sana", "Ling", "Valentina", "Amara",
        "Noor", "Meera", "Xinyi", "Adaeze", "Rosa",
    ],
}
for _pool in FIRST_NAMES.values():
    assert len(_pool) == 20

SURNAMES = {
    "finnish": [
        "Virtanen", "Korhonen", "Makinen", "Nieminen", "Makela", "Hamalainen",
        "Laine", "Heikkinen", "Koskinen", "Jarvinen", "Lehtonen", "Lehtinen",
        "Saarinen", "Salminen", "Heinonen", "Niemi", "Kinnunen", "Salo",
        "Turunen", "Rantanen",
    ],
    "non_finnish_european": [
        "Nowak", "Muller", "Rossi", "Dubois", "Andersson", "Novak",
        "Kowalski", "Popescu", "Larsen", "Fischer", "Moreau", "Bianchi",
        "Horvath", "Berg", "Kovac", "Lindgren", "Schneider", "Petrov",
        "Kallas", "Jensen",
    ],
    "non_european": [
        "Sharma", "Chen", "Kim", "Silva", "Okafor", "Tanaka", "Khan",
        "Souza", "Patel", "Nwosu", "Hassan", "Reddy", "Wang", "Fernandez",
        "Adeyemi", "Rahman", "Gupta", "Li", "Costa", "Abara",
    ],
}
for _pool in SURNAMES.values():
    assert len(_pool) == 20

# Graduation-year bands (age proxy), four bands, 60 candidates each.
GRAD_YEAR_BANDS = [
    {"id": "1998_2006", "range": (1998, 2006)},
    {"id": "2007_2013", "range": (2007, 2013)},
    {"id": "2014_2018", "range": (2014, 2018)},
    {"id": "2019_2024", "range": (2019, 2024)},
]
GRAD_YEAR_BAND_TARGET_COUNTS = {b["id"]: 60 for b in GRAD_YEAR_BANDS}
assert sum(GRAD_YEAR_BAND_TARGET_COUNTS.values()) == N_CANDIDATES
assert all(b["range"][1] <= CORPUS_NOW_YEAR for b in GRAD_YEAR_BANDS), (
    "a graduation-year band extends past CORPUS_NOW_YEAR -- "
    "build_career_skeleton's gap-clamping logic assumes no candidate "
    "graduates after the corpus's 'now'")

# Degree country -- assigned independently of name-origin (a Finnish-named
# candidate can hold a foreign degree and vice versa; that independence is
# itself part of the realism, not just a formality).
DEGREE_COUNTRIES = ["finland", "other_eu", "non_eu"]
DEGREE_COUNTRY_TARGET_COUNTS = {"finland": 100, "other_eu": 80, "non_eu": 60}
assert sum(DEGREE_COUNTRY_TARGET_COUNTS.values()) == N_CANDIDATES

UNIVERSITIES_BY_DEGREE_COUNTRY = {
    "finland": ["Kallavesi University of Technology", "Oulujoki University", "Tammerkoski University",
                "Kymijoki University of Technology", "Merihaka University"],
    "other_eu": ["TU Maasdelta", "Roslagen Royal Institute of Technology", "Limmat Institute of Technology Zurich",
                 "Politecnico del Naviglio", "Rheinmark Technical University Aachen",
                 "Gotaalv University of Technology"],
    "non_eu": ["CRIT", "Salsette Institute of Technology Bombay",
               "Sakura National University", "Yangtze Delta Institute of Technology",
               "Credit River University", "Bukak National University"],
}

# ---------------------------------------------------------------------------
# Employers -- invented, plausible signal-processing-adjacent companies for
# work-history entries that carry planted evidence, and a small pool of
# generic off-role industries/employers for the noise-floor archetype.
# ---------------------------------------------------------------------------

SIGNAL_PROCESSING_EMPLOYERS = [
    "Nordkom Radar Systems", "Aurinko Avionics", "Baltic Sensor Networks",
    "Hohtola Photonics", "Meridian Defence Electronics", "Hallaharju Space Systems",
    "Sumuvire Wireless", "Polaris RF Labs", "Tuulikallio Embedded Systems",
    "Tuulenkaari Satellite Systems", "Sinikaari Optics", "Kajanti Avionics",
    "Fenno Radar Technologies", "Vireo Sensor Systems", "Boreal Photonics",
]

OFFROLE_PROFESSIONS = [
    {"field": "marketing", "employer_pool": ["a regional marketing agency",
                                              "a consumer-goods brand team"],
     "title": "Marketing Analyst"},
    {"field": "mechanical_engineering",
     "employer_pool": ["a heavy-machinery manufacturer",
                        "an HVAC systems contractor"],
     "title": "Mechanical Design Engineer"},
    {"field": "sales", "employer_pool": ["a B2B software vendor",
                                          "an industrial-equipment distributor"],
     "title": "Account Executive"},
    {"field": "web_development",
     "employer_pool": ["a small web agency", "an e-commerce platform"],
     "title": "Frontend Developer"},
    {"field": "teaching", "employer_pool": ["a secondary school",
                                             "a vocational college"],
     "title": "Mathematics Teacher"},
    {"field": "finance", "employer_pool": ["a regional bank",
                                            "an accounting firm"],
     "title": "Financial Analyst"},
]

# ---------------------------------------------------------------------------
# Style seeds -- one per candidate for CV/letter realism variance, deterministic
# range so the prose-writing agent has a stable per-candidate knob for
# tone/verbosity without needing its own randomness.
# ---------------------------------------------------------------------------

STYLE_SEED_RANGE = (1000, 9999)
COVER_LETTER_LENGTH_RANGE_WORDS = (320, 480)  # "substantive one page"

# ---------------------------------------------------------------------------
# The 12 recruiter personas -- seeded traits: strictness,
# keyword_reliance, time_discipline, all floats in [0, 1]. These parameters
# drive the human-arm simulation; Phase 1
# only fixes the persona roster and the 48-application stratified subset.
#
#   strictness        how harshly ambiguous/borderline evidence is judged
#                      (high strictness -> H's borderline candidates and
#                      D's thin claims get flagged rather than waved through)
#   keyword_reliance   how much the persona pattern-matches on literal CV
#                      keywords rather than reading for substance (high
#                      reliance -> more likely fooled by D, more likely to
#                      miss F's displaced-vocabulary evidence)
#   time_discipline    how evenly the persona spends the fixed time budget
#                      across all requirements/applications vs front-loading
#                      attention on the first few and skimming the rest
# ---------------------------------------------------------------------------

PERSONAS = [
    {"id": "P01", "name": "Reetta Mustonen", "tagline": "the strict keyword-sceptic",
     "traits": {"strictness": 0.80, "keyword_reliance": 0.20, "time_discipline": 0.65}},
    {"id": "P02", "name": "Joonas Virtanen", "tagline": "the fast keyword-matcher",
     "traits": {"strictness": 0.35, "keyword_reliance": 0.85, "time_discipline": 0.55}},
    {"id": "P03", "name": "Camille Lefevre", "tagline": "the careful generalist",
     "traits": {"strictness": 0.55, "keyword_reliance": 0.40, "time_discipline": 0.75}},
    {"id": "P04", "name": "Onni Koivisto", "tagline": "the lenient enthusiast",
     "traits": {"strictness": 0.25, "keyword_reliance": 0.45, "time_discipline": 0.50}},
    {"id": "P05", "name": "Alina Petrova", "tagline": "the deadline-rusher",
     "traits": {"strictness": 0.45, "keyword_reliance": 0.60, "time_discipline": 0.25}},
    {"id": "P06", "name": "Teemu Lahtinen", "tagline": "the by-the-book checklist reader",
     "traits": {"strictness": 0.70, "keyword_reliance": 0.35, "time_discipline": 0.80}},
    {"id": "P07", "name": "Ines Alves", "tagline": "the letter-skimmer",
     "traits": {"strictness": 0.40, "keyword_reliance": 0.55, "time_discipline": 0.45}},
    {"id": "P08", "name": "Sampo Rautio", "tagline": "the sceptical veteran",
     "traits": {"strictness": 0.85, "keyword_reliance": 0.30, "time_discipline": 0.70}},
    {"id": "P09", "name": "Wei Zhang", "tagline": "the balanced pragmatist",
     "traits": {"strictness": 0.50, "keyword_reliance": 0.50, "time_discipline": 0.60}},
    {"id": "P10", "name": "Noora Peltola", "tagline": "the front-loader",
     "traits": {"strictness": 0.60, "keyword_reliance": 0.40, "time_discipline": 0.30}},
    {"id": "P11", "name": "Rasmus Berg", "tagline": "the credential-trusting reader",
     "traits": {"strictness": 0.30, "keyword_reliance": 0.65, "time_discipline": 0.55}},
    {"id": "P12", "name": "Aisha Bello", "tagline": "the meticulous slow reader",
     "traits": {"strictness": 0.75, "keyword_reliance": 0.25, "time_discipline": 0.85}},
]
assert len(PERSONAS) == 12
PERSONA_BY_ID = {p["id"]: p for p in PERSONAS}

# 48-application persona-arm subset, stratified proportionally across the 9
# archetypes (largest-remainder rounding of n_archetype * 48/240 = 0.2):
# A4, B18, C7, D4, E3, F4, G3, H2, OFFROLE3 (sum 48). Exact counts fixed here
# rather than left to a rounding routine at run time, so the subset size per
# archetype is a frozen number.
PERSONA_SUBSET_SIZE = 48
PERSONA_SUBSET_COUNTS_BY_ARCHETYPE = {
    "A": 4, "B": 18, "C": 7, "D": 4, "E": 3, "F": 4, "G": 3, "H": 2, "OFFROLE": 3,
}
assert sum(PERSONA_SUBSET_COUNTS_BY_ARCHETYPE.values()) == PERSONA_SUBSET_SIZE
assert set(PERSONA_SUBSET_COUNTS_BY_ARCHETYPE) == set(ARCHETYPE_BY_ID)
for _aid, _cnt in PERSONA_SUBSET_COUNTS_BY_ARCHETYPE.items():
    assert _cnt <= ARCHETYPE_BY_ID[_aid]["n"]

# Fixed time budget for the persona-arm screening simulation ("seeded
# recruiter personas ... time budget fixed"). The design names the trait
# but not its value; the value is a judgment call made
# when the persona arm was built. The SAME budget
# applies to every persona and every candidate in both arms ("fixed" means
# constant across the arm, not persona-specific -- time_discipline is what
# already varies how well each persona uses it). Deliberately distinct from
# the interactive page's game-mode speed ("90 seconds each"),
# which is a reader-experience number for the published explorer, not a
# corpus-generation or persona-simulation parameter.
PERSONA_ARM_TIME_BUDGET_SECONDS = 240  # 4 minutes per application

# ---------------------------------------------------------------------------
# Small deterministic helpers shared by generate_structured.py and
# validate_structured.py (kept here so both read the identical logic).
# ---------------------------------------------------------------------------


def deterministic_rng(*parts) -> np.random.Generator:
    """A fresh, reproducible RNG keyed off RANDOM_SEED plus salt parts.

    Every part is hashed into the seed via a large-prime multiply-and-add so
    distinct salts (e.g. a dimension name and a candidate index) never
    collide by coincidence. Accepts ints or strings.
    """
    seed = RANDOM_SEED
    for i, part in enumerate(parts):
        if isinstance(part, str):
            part = sum((j + 1) * ord(ch) for j, ch in enumerate(part))
        seed = (seed * 1_000_003 + (i + 1) * 97 + int(part)) % (2**32 - 1)
    return np.random.default_rng(seed)


def largest_remainder_split(total: int, proportions: dict) -> dict:
    """Round `total` into integer buckets matching `proportions` as closely
    as integer rounding allows, using the largest-remainder (Hamilton)
    method so the counts always sum exactly to `total`. Deterministic:
    fractional-remainder ties are broken by key order.
    """
    raw = {k: total * p for k, p in proportions.items()}
    floors = {k: int(np.floor(v)) for k, v in raw.items()}
    remainder = total - sum(floors.values())
    order = sorted(raw.keys(), key=lambda k: (-(raw[k] - floors[k]), k))
    for k in order[:remainder]:
        floors[k] += 1
    assert sum(floors.values()) == total
    return floors
