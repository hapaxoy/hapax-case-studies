"""Phase 1 deterministic structure generator for Project 10 (Talent Screening).

Builds, in order:
  1. The 240-candidate roster: archetype assignment, demographic strata
     (name-origin x gender, graduation-year band, degree country, career-gap
     flag), all assigned orthogonally to qualification truth.
  2. Per-candidate x per-requirement ground truth (status, evidence location,
     displaced vocabulary, contradiction, borderline note) -> answer_key.csv.
  3. A per-candidate summary key -> answer_key_candidates.csv.
  4. One prose-writing brief per candidate -> data/briefs/brief_NNN.json.
  5. The 48-application persona-arm subset -> data/persona_subset.json.

Everything here is deterministic given RANDOM_SEED in config.py. No CV prose,
cover-letter prose, or chat transcript language is generated -- this script
produces only the STRUCTURE that the prose-writing agent will dramatise
into prose, per the Hapax core generation pattern: Python controls structure,
LLM agents write only prose and may never add or remove a planted signal.

Run: python generate_structured.py
Then: python validate_structured.py   (exits 1 on any coherence failure)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import config


def log(message: str) -> None:
    """Progress print, flushed immediately so the run stays legible."""
    print(f"[generate_structured] {message}", flush=True)


# ---------------------------------------------------------------------------
# Step 1: candidate roster -- archetype assignment
# ---------------------------------------------------------------------------

def build_candidate_ids_and_archetypes() -> pd.DataFrame:
    """One row per candidate with a fixed candidate_id and archetype, in an
    order shuffled independently of any demographic-assignment RNG stream
    below (so archetype order carries no demographic information).
    """
    rows = []
    counter = 1
    for archetype in config.ARCHETYPES:
        for _ in range(archetype["n"]):
            rows.append({"archetype": archetype["id"], "_seq": counter})
            counter += 1
    df = pd.DataFrame(rows)
    assert len(df) == config.N_CANDIDATES

    # Shuffle candidate_id assignment so archetype isn't correlated with a
    # candidate's numeric id in any way a reader might over-interpret; the
    # shuffle itself uses its own RNG stream, independent of every
    # demographic-dimension stream below.
    rng = config.deterministic_rng("candidate_id_shuffle")
    shuffled_ids = list(range(1, config.N_CANDIDATES + 1))
    rng.shuffle(shuffled_ids)
    df["candidate_id"] = [f"C{i:03d}" for i in shuffled_ids]
    df = df.sort_values("candidate_id").reset_index(drop=True)
    df = df.drop(columns=["_seq"])
    return df


# ---------------------------------------------------------------------------
# Step 2: demographic strata -- assigned orthogonally to qualification truth
# ---------------------------------------------------------------------------

def assign_stratum_proportional(df: pd.DataFrame, column: str,
                                 target_counts: dict, dimension_salt: str) -> pd.Series:
    """Assign a categorical stratum to every candidate such that, WITHIN
    EVERY ARCHETYPE, the level proportions match the global target
    proportions as closely as integer rounding allows (largest-remainder
    method per archetype). Because every archetype gets a proportional
    slice of every level, and qualification truth is purely a function of
    archetype, this construction makes the stratum independent of
    qualification truth by construction -- not just in aggregate, but for
    any archetype subset.

    Which specific candidates within an archetype get which level is
    decided by a dimension-specific RNG stream (independent of every other
    dimension's stream and of the archetype-shuffle stream), so the
    dimensions are not accidentally correlated with each other either.
    """
    total = len(df)
    global_proportions = {k: v / total for k, v in target_counts.items()}
    values = pd.Series(index=df.index, dtype=object)

    for archetype_id, group in df.groupby("archetype", sort=True):
        n = len(group)
        counts = config.largest_remainder_split(n, global_proportions)
        level_pool = []
        for level, cnt in counts.items():
            level_pool += [level] * cnt
        assert len(level_pool) == n

        rng = config.deterministic_rng(dimension_salt, archetype_id)
        rng.shuffle(level_pool)
        values.loc[group.index] = level_pool

    assert values.notna().all()
    return values


def assign_career_gap(df: pd.DataFrame) -> pd.DataFrame:
    """Career-gap flag: exact per-archetype counts from
    config.CAREER_GAP_COUNTS (not a proportional-to-global-target draw,
    because G's archetype forces 100% gap by its own definition -- see the
    worked arithmetic in config.py for why the
    resulting gap=True / gap=False populations still land within a
    fraction of a percentage point of each other on qualification truth).
    """
    gap_flags = pd.Series(False, index=df.index)
    gap_reasons = pd.Series("", index=df.index, dtype=object)

    for archetype_id, group in df.groupby("archetype", sort=True):
        n_gap = config.CAREER_GAP_COUNTS[archetype_id]
        rng = config.deterministic_rng("career_gap", archetype_id)
        chosen = rng.choice(group.index.to_numpy(), size=n_gap, replace=False) \
            if n_gap > 0 else np.array([], dtype=group.index.dtype)
        gap_flags.loc[chosen] = True
        reason_rng = config.deterministic_rng("career_gap_reason", archetype_id)
        for idx in chosen:
            gap_reasons.loc[idx] = reason_rng.choice(config.CAREER_GAP_REASONS)

    df = df.copy()
    df["career_gap"] = gap_flags
    df["career_gap_reason"] = gap_reasons
    return df


def assign_graduation_year(df: pd.DataFrame) -> pd.DataFrame:
    """Pick an exact graduation year within the candidate's assigned band."""
    years = pd.Series(index=df.index, dtype=int)
    for idx, row in df.iterrows():
        band = next(b for b in config.GRAD_YEAR_BANDS if b["id"] == row["grad_year_band"])
        rng = config.deterministic_rng("grad_year_exact", idx)
        lo, hi = band["range"]
        years.loc[idx] = int(rng.integers(lo, hi + 1))
    df = df.copy()
    df["graduation_year"] = years
    return df


def assign_names(df: pd.DataFrame) -> pd.DataFrame:
    """Full name from the name-origin x gender first-name pool and the
    name-origin surname pool. Names are drawn without replacement within
    each (name_origin, gender) cell until the pool is exhausted, then a
    fresh shuffled lap begins (pools have ~20 entries; cells can have more
    than 20 candidates), so repeats only occur once genuinely necessary.
    """
    first = pd.Series(index=df.index, dtype=object)
    last = pd.Series(index=df.index, dtype=object)

    for (origin, gender), group in df.groupby(["name_origin", "gender"], sort=True):
        pool = list(config.FIRST_NAMES[(origin, gender)])
        rng = config.deterministic_rng("first_name", origin, gender)
        laps = []
        while len(laps) < len(group):
            lap = list(pool)
            rng.shuffle(lap)
            laps += lap
        first.loc[group.index] = laps[:len(group)]

    for origin, group in df.groupby("name_origin", sort=True):
        pool = list(config.SURNAMES[origin])
        rng = config.deterministic_rng("surname", origin)
        laps = []
        while len(laps) < len(group):
            lap = list(pool)
            rng.shuffle(lap)
            laps += lap
        last.loc[group.index] = laps[:len(group)]

    df = df.copy()
    df["first_name"] = first
    df["last_name"] = last
    df["full_name"] = df["first_name"] + " " + df["last_name"]
    df = enforce_full_name_uniqueness(df)
    return df


def enforce_full_name_uniqueness(df: pd.DataFrame) -> pd.DataFrame:
    """First names and surnames are drawn from independent per-stratum
    pools (above), so the same first+surname combination can land on more
    than one candidate by coincidence -- corpus-wide full-name uniqueness
    is never guaranteed by construction otherwise. Walk candidates in
    candidate_id order; the first holder of a full name keeps it, every
    later duplicate gets a fresh surname (same name_origin pool, current
    surname excluded) redrawn from a dedicated, deterministic RNG stream
    until the resulting full name collides with nothing seen so far.

    (This exact mechanism resolved 7 real collisions found in the Phase 1
    corpus after the fact -- see fix_duplicate_names.py for that one-off
    repair. This function makes any
    FUTURE full regeneration safe from the same defect without needing a
    repeat one-off fix.)
    """
    df = df.copy()
    seen_full_names: set[str] = set()
    for idx in df.index:
        full_name = df.at[idx, "full_name"]
        if full_name not in seen_full_names:
            seen_full_names.add(full_name)
            continue

        origin = df.at[idx, "name_origin"]
        first_name = df.at[idx, "first_name"]
        current_surname = df.at[idx, "last_name"]
        candidate_id = df.at[idx, "candidate_id"]
        pool = [s for s in config.SURNAMES[origin] if s != current_surname]
        rng = config.deterministic_rng("dedup_surname", candidate_id)
        shuffled = list(pool)
        rng.shuffle(shuffled)

        resolved = False
        for new_surname in shuffled:
            candidate_full_name = f"{first_name} {new_surname}"
            if candidate_full_name not in seen_full_names:
                df.at[idx, "last_name"] = new_surname
                df.at[idx, "full_name"] = candidate_full_name
                seen_full_names.add(candidate_full_name)
                resolved = True
                break
        assert resolved, (
            f"{candidate_id}: exhausted the {origin} surname pool without "
            "finding a collision-free full name -- pool too small relative "
            "to how many candidates share this (name_origin, gender, "
            "first_name) combination")
    return df


def assign_university_and_employer(df: pd.DataFrame) -> pd.DataFrame:
    """One university (from the candidate's degree-country pool) and, for
    non-off-role candidates, one primary signal-processing-relevant employer
    for the most recent role (further employers are added ad hoc in the
    career skeleton builder). Off-role candidates draw from
    OFFROLE_PROFESSIONS instead.
    """
    university = pd.Series(index=df.index, dtype=object)
    for idx, row in df.iterrows():
        rng = config.deterministic_rng("university", idx)
        university.loc[idx] = rng.choice(config.UNIVERSITIES_BY_DEGREE_COUNTRY[row["degree_country"]])

    primary_employer = pd.Series(index=df.index, dtype=object)
    offrole_profession = pd.Series(index=df.index, dtype=object)
    for idx, row in df.iterrows():
        rng = config.deterministic_rng("employer", idx)
        if row["archetype"] == "OFFROLE":
            profession = rng.choice([p["field"] for p in config.OFFROLE_PROFESSIONS])
            offrole_profession.loc[idx] = profession
            primary_employer.loc[idx] = None
        else:
            primary_employer.loc[idx] = rng.choice(config.SIGNAL_PROCESSING_EMPLOYERS)
            offrole_profession.loc[idx] = None

    df = df.copy()
    df["university"] = university
    df["primary_employer"] = primary_employer
    df["offrole_profession"] = offrole_profession
    return df


def assign_style_seeds(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    style_seed = pd.Series(index=df.index, dtype=int)
    letter_words = pd.Series(index=df.index, dtype=int)
    for idx in df.index:
        rng = config.deterministic_rng("style_seed", idx)
        lo, hi = config.STYLE_SEED_RANGE
        style_seed.loc[idx] = int(rng.integers(lo, hi + 1))
        wlo, whi = config.COVER_LETTER_LENGTH_RANGE_WORDS
        letter_words.loc[idx] = int(rng.integers(wlo, whi + 1))
    df["style_seed"] = style_seed
    df["cover_letter_target_words"] = letter_words
    return df


def build_roster() -> pd.DataFrame:
    log("building candidate roster and archetype assignment")
    df = build_candidate_ids_and_archetypes()

    log("assigning demographic strata orthogonally to archetype")
    df["name_origin"] = assign_stratum_proportional(
        df, "name_origin", config.NAME_ORIGIN_TARGET_COUNTS, "name_origin")
    df["gender"] = assign_stratum_proportional(
        df, "gender", config.GENDER_TARGET_COUNTS, "gender")
    df["grad_year_band"] = assign_stratum_proportional(
        df, "grad_year_band", config.GRAD_YEAR_BAND_TARGET_COUNTS, "grad_year_band")
    df["degree_country"] = assign_stratum_proportional(
        df, "degree_country", config.DEGREE_COUNTRY_TARGET_COUNTS, "degree_country")

    df = assign_career_gap(df)
    df = assign_graduation_year(df)
    df = assign_names(df)
    df = assign_university_and_employer(df)
    df = assign_style_seeds(df)
    return df


# ---------------------------------------------------------------------------
# Step 3: per-requirement ground truth
# ---------------------------------------------------------------------------

def draw_profile_status(rng: np.random.Generator, profile: dict) -> str:
    levels = list(profile.keys())
    probs = list(profile.values())
    return str(rng.choice(levels, p=probs))


def choose_location(rng: np.random.Generator, profile: dict) -> str:
    levels = list(profile.keys())
    probs = list(profile.values())
    return str(rng.choice(levels, p=probs))


def determine_e_contradiction(candidate_id: str) -> tuple[str, str]:
    """Pick, once per E candidate, which of the two contradiction templates
    applies and which requirement it targets. Computed as its own function
    (rather than inline) so build_must_have_rows and
    build_desirable_constraint_rows always agree on the same draw for a
    given candidate -- the template's target can land on a must-have (R05)
    or a desirable (R08), and whichever builder owns that requirement id
    needs to apply the SAME contradiction, not redraw independently.
    """
    code_rng = config.deterministic_rng("credential_code", candidate_id)
    code = str(code_rng.choice(["degree_date", "title_inflation"]))
    return code, config.CONTRADICTION_BY_CODE[code]["requirement_id"]


def build_must_have_rows(candidate_id: str, archetype_id: str, rng_seed_key,
                          f_displacement: dict) -> list[dict]:
    """Ground truth for R01-R05 for one candidate, per the archetype's
    must_have_rule. Returns a list of dicts with keys: requirement_id,
    status, location, displaced(bool), displaced_phrase, contradiction_code,
    borderline_code, borderline_note.
    """
    rule = config.ARCHETYPE_BY_ID[archetype_id]["must_have_rule"]
    rows = []
    loc_rng = config.deterministic_rng("evidence_location", rng_seed_key)

    def evidenced_row(rid, location=None):
        loc = location or choose_location(loc_rng, config.BASELINE_EVIDENCE_LOCATION_PROFILE)
        return {"requirement_id": rid, "status": "evidenced", "location": loc,
                "displaced": False, "displaced_phrase": "",
                "contradiction_code": "", "borderline_code": "", "borderline_note": ""}

    def absent_row(rid):
        return {"requirement_id": rid, "status": "absent", "location": "",
                "displaced": False, "displaced_phrase": "",
                "contradiction_code": "", "borderline_code": "", "borderline_note": ""}

    def claimed_row(rid, location):
        return {"requirement_id": rid, "status": "claimed_only", "location": location,
                "displaced": False, "displaced_phrase": "",
                "contradiction_code": "", "borderline_code": "", "borderline_note": ""}

    if rule == "all_evidenced":
        for rid in config.MUST_HAVE_IDS:
            rows.append(evidenced_row(rid))

    elif rule == "clear_miss":
        # Fails >= 3 of the 5 must-haves, drawn per candidate; the failing
        # ones are ABSENT (a genuine, undisguised miss), the rest evidenced.
        pick_rng = config.deterministic_rng("clear_miss_pick", rng_seed_key)
        n_fail = int(pick_rng.integers(3, 6))  # 3, 4, or 5
        fail_ids = set(pick_rng.choice(config.MUST_HAVE_IDS, size=n_fail, replace=False))
        for rid in config.MUST_HAVE_IDS:
            rows.append(absent_row(rid) if rid in fail_ids else evidenced_row(rid))

    elif rule == "near_miss":
        pick_rng = config.deterministic_rng("near_miss_pick", rng_seed_key)
        missing_id = str(pick_rng.choice(config.MUST_HAVE_IDS))
        for rid in config.MUST_HAVE_IDS:
            rows.append(absent_row(rid) if rid == missing_id else evidenced_row(rid))

    elif rule == "all_claimed_only":
        claim_loc_rng = config.deterministic_rng("d_claim_location", rng_seed_key)
        for rid in config.MUST_HAVE_IDS:
            loc = choose_location(claim_loc_rng, config.D_CLAIM_LOCATION_PROFILE)
            rows.append(claimed_row(rid, loc))

    elif rule == "credential_inflation":
        template_code, contradicted_rid = determine_e_contradiction(candidate_id)
        for rid in config.MUST_HAVE_IDS:
            if rid == contradicted_rid:
                rows.append({"requirement_id": rid, "status": "contradicted",
                             "location": "work_history", "displaced": False,
                             "displaced_phrase": "", "contradiction_code": template_code,
                             "borderline_code": "", "borderline_note": ""})
            else:
                rows.append(evidenced_row(rid))
        # If the contradiction targets R08 (a desirable, from the
        # title_inflation template) it will not match any must-have id
        # above, so every must-have is evidenced normally here, and
        # build_desirable_constraint_rows applies the SAME contradiction
        # (via the identical determine_e_contradiction draw) to R08 instead.

    elif rule == "displaced":
        disp_rid, disp_loc = f_displacement
        phrase_rng = config.deterministic_rng("displacement_phrase", rng_seed_key)
        phrase = str(phrase_rng.choice(config.DISPLACEMENT_TABLE[disp_rid]))
        for rid in config.MUST_HAVE_IDS:
            if rid == disp_rid:
                rows.append({"requirement_id": rid, "status": "evidenced",
                             "location": disp_loc, "displaced": True,
                             "displaced_phrase": phrase, "contradiction_code": "",
                             "borderline_code": "", "borderline_note": ""})
            else:
                rows.append(evidenced_row(rid))

    elif rule == "borderline":
        code_rng = config.deterministic_rng("borderline_code", rng_seed_key)
        code = str(code_rng.choice(list(config.BORDERLINE_BY_CODE.keys())))
        template = config.BORDERLINE_BY_CODE[code]
        target_rid = template["requirement_id"]
        for rid in config.MUST_HAVE_IDS:
            if rid == target_rid:
                rows.append({"requirement_id": rid, "status": "evidenced",
                             "location": "project_description", "displaced": False,
                             "displaced_phrase": "", "contradiction_code": "",
                             "borderline_code": code, "borderline_note": template["borderline_note"]})
            else:
                rows.append(evidenced_row(rid))

    elif rule == "offrole":
        for rid in config.MUST_HAVE_IDS:
            rows.append(absent_row(rid))

    else:
        raise ValueError(f"unknown must_have_rule: {rule}")

    assert len(rows) == 5
    return rows


def build_desirable_constraint_rows(candidate_id: str, archetype_id: str,
                                     requirement_ids: list, profile: dict,
                                     rng_seed_key,
                                     e_contradiction: tuple | None = None) -> list[dict]:
    rows = []
    stat_rng = config.deterministic_rng("dc_status", rng_seed_key, "_".join(requirement_ids)[:8])
    loc_rng = config.deterministic_rng("dc_location", rng_seed_key)
    claim_loc_rng = config.deterministic_rng("dc_claim_location", rng_seed_key)

    contradicted_rid = e_contradiction[1] if e_contradiction else None
    for rid in requirement_ids:
        if rid == contradicted_rid:
            template_code = e_contradiction[0]
            rows.append({"requirement_id": rid, "status": "contradicted",
                         "location": "cover_letter", "displaced": False,
                         "displaced_phrase": "", "contradiction_code": template_code,
                         "borderline_code": "", "borderline_note": ""})
            continue
        status = draw_profile_status(stat_rng, profile)
        if status == "evidenced":
            location = choose_location(loc_rng, config.BASELINE_EVIDENCE_LOCATION_PROFILE)
        elif status == "claimed_only":
            # Desirables/constraints claimed-only live in the skills list or
            # (for D's stuffing) the cover letter -- reuse D's blend for any
            # archetype that draws a claimed_only desirable, since the
            # underlying phenomenon (an unsubstantiated claim) is the same.
            location = choose_location(claim_loc_rng, config.D_CLAIM_LOCATION_PROFILE)
        else:
            location = ""
        rows.append({"requirement_id": rid, "status": status, "location": location,
                     "displaced": False, "displaced_phrase": "",
                     "contradiction_code": "", "borderline_code": "", "borderline_note": ""})
    return rows


def build_answer_key(roster: pd.DataFrame) -> pd.DataFrame:
    log("building per-requirement ground truth")

    # Assign F's displacement plan (requirement + location) to the 18 F
    # candidates, shuffled deterministically so which specific candidate
    # gets which slot in F_DISPLACEMENT_PLAN isn't tied to candidate_id order.
    f_candidates = roster.loc[roster["archetype"] == "F", "candidate_id"].tolist()
    f_rng = config.deterministic_rng("f_displacement_assignment")
    f_plan = list(config.F_DISPLACEMENT_PLAN)
    f_rng.shuffle(f_plan)
    f_assignment = dict(zip(sorted(f_candidates), f_plan))
    # sorted() keeps this reproducible independent of DataFrame row order.

    key_rows = []
    for _, row in roster.iterrows():
        cid = row["candidate_id"]
        archetype_id = row["archetype"]
        archetype = config.ARCHETYPE_BY_ID[archetype_id]

        f_disp = f_assignment.get(cid)
        e_contradiction = determine_e_contradiction(cid) if archetype_id == "E" else None
        must_have_rows = build_must_have_rows(cid, archetype_id, cid, f_disp)
        desirable_rows = build_desirable_constraint_rows(
            cid, archetype_id, config.DESIRABLE_IDS, archetype["desirable_profile"], cid,
            e_contradiction=e_contradiction)
        constraint_rows = build_desirable_constraint_rows(
            cid, archetype_id, config.CONSTRAINT_IDS, archetype["constraint_profile"], cid,
            e_contradiction=e_contradiction)

        for r in must_have_rows + desirable_rows + constraint_rows:
            requirement = config.REQUIREMENT_BY_ID[r["requirement_id"]]
            key_rows.append({
                "candidate_id": cid,
                "archetype": archetype_id,
                "requirement_id": r["requirement_id"],
                "requirement_name": requirement["name"],
                "requirement_category": requirement["category"],
                "status": r["status"],
                "evidence_location": r["location"],
                "letter_only": bool(r["location"] == "cover_letter" and r["status"] == "evidenced"),
                "displaced": r["displaced"],
                "displaced_phrase": r["displaced_phrase"],
                "contradiction_code": r["contradiction_code"],
                "borderline_code": r["borderline_code"],
                "borderline_note": r["borderline_note"],
            })

    key = pd.DataFrame(key_rows)
    assert len(key) == config.N_CANDIDATES * len(config.REQUIREMENTS)
    return key


# ---------------------------------------------------------------------------
# Step 4: per-candidate summary key
# ---------------------------------------------------------------------------

def build_candidate_summary(roster: pd.DataFrame, key: pd.DataFrame) -> pd.DataFrame:
    log("building per-candidate summary key")
    must_have = key[key["requirement_category"] == "must_have"]
    pass_counts = must_have[must_have["status"] == "evidenced"].groupby("candidate_id").size()

    summary = roster.copy()
    summary["must_have_pass_count"] = summary["candidate_id"].map(pass_counts).fillna(0).astype(int)
    summary["fully_qualified"] = summary["archetype"].isin(config.FULLY_QUALIFIED_ARCHETYPES)
    summary["archetype_label"] = summary["archetype"].map(
        lambda a: config.ARCHETYPE_BY_ID[a]["label"])

    letter_only_counts = key[key["letter_only"]].groupby("candidate_id").size()
    summary["letter_only_evidence_count"] = summary["candidate_id"].map(letter_only_counts).fillna(0).astype(int)

    cols = ["candidate_id", "full_name", "archetype", "archetype_label",
            "name_origin", "gender", "graduation_year", "grad_year_band",
            "degree_country", "career_gap", "career_gap_reason",
            "university", "primary_employer", "offrole_profession",
            "must_have_pass_count", "fully_qualified", "letter_only_evidence_count",
            "style_seed", "cover_letter_target_words"]
    return summary[cols]


# ---------------------------------------------------------------------------
# Step 5: application briefs (one per candidate, for the prose step)
# ---------------------------------------------------------------------------

def build_career_skeleton(row: pd.Series, key_rows: pd.DataFrame) -> list[dict]:
    """A minimal, deterministic list of CV entries (education + jobs). The
    prose-writing agent turns this into prose; it does not invent entries.
    """
    skeleton = []
    grad_year = int(row["graduation_year"])
    skeleton.append({
        "type": "education", "institution": row["university"],
        "degree_field": "Electrical Engineering / Physics / Applied Mathematics"
                        if row["archetype"] != "OFFROLE" else "an unrelated field",
        "graduation_year": grad_year,
    })

    if row["archetype"] == "OFFROLE":
        profession = next(p for p in config.OFFROLE_PROFESSIONS
                           if p["field"] == row["offrole_profession"])
        rng = config.deterministic_rng("offrole_employer", row["candidate_id"])
        employer = rng.choice(profession["employer_pool"])
        skeleton.append({
            "type": "work_history", "employer": employer,
            "title": profession["title"],
            "start_year": grad_year, "end_year": "present",
            "notes": f"Career entirely in {profession['field'].replace('_', ' ')}, "
                     "unrelated to signal processing or remote sensing.",
        })
        return skeleton

    # Non-off-role: one or two work-history entries anchored on the
    # candidate's primary employer, plus a gap entry if flagged.
    assert grad_year + 1 <= config.CORPUS_NOW_YEAR, (
        f"primary role start_year (grad_year + 1 = {grad_year + 1}) falls "
        f"after CORPUS_NOW_YEAR ({config.CORPUS_NOW_YEAR}) -- a "
        "graduation-year band extends too close to/past 'now'"
    )
    skeleton.append({
        "type": "work_history", "employer": row["primary_employer"],
        "title": "Signal Processing Engineer",
        "start_year": grad_year + 1,
        "end_year": "present",
        "notes": "Primary role; most must-have evidence anchors here unless "
                 "the brief's evidence_to_write / cover_letter sections say "
                 "otherwise.",
    })

    if row["career_gap"]:
        # Default: gap starts 3 years after graduation, runs 1 year. For a
        # recent graduate this can overrun the corpus's "now"
        # (CORPUS_NOW_YEAR) -- e.g. grad_year=2024 + 3 = 2027. Clamp so the
        # gap always ends at or before CORPUS_NOW_YEAR, pulling it earlier
        # (never before grad_year + 1, when the first job starts) rather
        # than leaving it unclamped. For every candidate where the default
        # already fit (the overwhelming majority), this reproduces the
        # exact same start/end years as before -- only candidates who
        # graduated too recently for the default 3-year offset to fit are
        # affected.
        gap_end = min(grad_year + 4, config.CORPUS_NOW_YEAR)
        gap_start = max(gap_end - 1, grad_year + 1)
        assert grad_year + 1 <= gap_start < gap_end <= config.CORPUS_NOW_YEAR, (
            f"career-gap window did not fit for a candidate graduating "
            f"{grad_year}: start={gap_start}, end={gap_end}, "
            f"now={config.CORPUS_NOW_YEAR}"
        )
        skeleton.append({
            "type": "career_gap", "start_year": gap_start, "end_year": gap_end,
            "reason": row["career_gap_reason"],
            "notes": "A visible, plainly-stated gap -- not hidden or "
                     "explained away, just present in the timeline.",
        })

    return skeleton


def requirement_instruction(rid: str, r: pd.Series) -> dict:
    """Turn one answer-key row into a signal-placement instruction for the
    prose-writing agent -- never a literal status label from STATUSES.
    """
    requirement = config.REQUIREMENT_BY_ID[rid]
    base = {"requirement_id": rid, "canonical_name": requirement["name"]}
    if r["displaced"]:
        base["vocabulary_mode"] = "displaced"
        base["phrase_to_use"] = r["displaced_phrase"]
        base["instruction"] = (
            f"Describe real, substantive work matching this phrase: "
            f"\"{r['displaced_phrase']}\". Never use the canonical term "
            f"\"{requirement['name']}\" or close synonyms of it -- the "
            "point is that the underlying skill is genuinely there but "
            "named only in the displaced vocabulary."
        )
    elif r["borderline_code"]:
        template = config.BORDERLINE_BY_CODE[r["borderline_code"]]
        base["vocabulary_mode"] = "plain"
        base["instruction"] = template["instruction"]
    elif r["contradiction_code"]:
        template = config.CONTRADICTION_BY_CODE[r["contradiction_code"]]
        base["vocabulary_mode"] = "plain"
        base["instruction"] = template["instruction"]
    else:
        base["vocabulary_mode"] = "plain"
        base["instruction"] = (
            f"Give a concrete, specific example evidencing "
            f"\"{requirement['name']}\" -- a named project or role detail, "
            "not a bare keyword."
        )
    base["location"] = r["evidence_location"]
    return base


def claim_instruction(rid: str) -> dict:
    requirement = config.REQUIREMENT_BY_ID[rid]
    return {
        "requirement_id": rid, "canonical_name": requirement["name"],
        "instruction": (
            f"Assert \"{requirement['name']}\" as a skill/keyword only -- "
            "no project, no company, no concrete detail backing it up."
        ),
    }


def build_brief(row: pd.Series, key: pd.DataFrame) -> dict:
    cid = row["candidate_id"]
    crows = key[key["candidate_id"] == cid].set_index("requirement_id")

    evidence_to_write = []
    claims_only = []
    not_to_mention = []
    contradiction = None
    borderline = None
    letter_evidence = []
    letter_claims = []

    for rid, r in crows.iterrows():
        if r["status"] == "evidenced":
            instr = requirement_instruction(rid, r)
            if r["evidence_location"] == "cover_letter":
                letter_evidence.append(instr)
            else:
                evidence_to_write.append(instr)
            if r["contradiction_code"]:
                contradiction = {
                    "requirement_id": rid,
                    "code": r["contradiction_code"],
                    "instruction": config.CONTRADICTION_BY_CODE[r["contradiction_code"]]["instruction"],
                }
            if r["borderline_code"]:
                borderline = {
                    "requirement_id": rid,
                    "code": r["borderline_code"],
                    "instruction": config.BORDERLINE_BY_CODE[r["borderline_code"]]["instruction"],
                }
        elif r["status"] == "claimed_only":
            instr = claim_instruction(rid)
            if r["evidence_location"] == "cover_letter":
                letter_claims.append(instr)
            else:
                claims_only.append(instr)
        elif r["status"] == "contradicted":
            contradiction = {
                "requirement_id": rid,
                "code": r["contradiction_code"],
                "instruction": config.CONTRADICTION_BY_CODE[r["contradiction_code"]]["instruction"],
            }
        elif r["status"] in ("absent", "not_stated"):
            not_to_mention.append({
                "requirement_id": rid,
                "canonical_name": config.REQUIREMENT_BY_ID[rid]["name"],
                "note": "Do not write anything, in the CV or the letter, "
                        "that could read as evidence for this requirement "
                        "-- not even an oblique or partial mention.",
            })

    archetype = config.ARCHETYPE_BY_ID[row["archetype"]]
    motivation_rng = config.deterministic_rng("motivation_angle", cid)
    motivation_angles = [
        "genuine enthusiasm for spaceborne/airborne remote-sensing work, "
        "referencing the kind of mission-critical instrument work Kaikuvaara does",
        "a pragmatic, results-oriented pitch focused on concrete past deliverables",
        "an interest in Oulu specifically and the region's RF/photonics "
        "engineering community",
        "a career-narrative pitch explaining why this role is the next "
        "logical step",
    ]
    motivation_angle = str(motivation_rng.choice(motivation_angles))

    brief = {
        "candidate_id": cid,
        "archetype": row["archetype"],
        "archetype_label": archetype["label"],
        "archetype_hint": archetype["description"],
        "role": {"title": config.ROLE_TITLE, "company": config.COMPANY["name"],
                 "location": config.COMPANY["city"]},
        "demographics_surface": {
            "full_name": row["full_name"], "gender": row["gender"],
            "name_origin": row["name_origin"],
            "graduation_year": int(row["graduation_year"]),
            "degree_country": row["degree_country"],
            "career_gap": bool(row["career_gap"]),
            "career_gap_reason": row["career_gap_reason"] or None,
        },
        "career_skeleton": build_career_skeleton(row, key),
        "evidence_to_write": evidence_to_write,
        "claims_only": claims_only,
        "not_to_mention": not_to_mention,
        "contradiction": contradiction,
        "borderline": borderline,
        "cover_letter": {
            "motivation_angle": motivation_angle,
            "evidence_in_letter": letter_evidence,
            "claims_in_letter": letter_claims,
            "target_length_words": int(row["cover_letter_target_words"]),
            "style_seed": int(row["style_seed"]),
            "note": "Evidence and claims listed here must appear ONLY in "
                    "the cover letter -- do not also place them (or a "
                    "restatement of them) anywhere in the CV.",
        },
        "style_seed": int(row["style_seed"]),
        "writer_note": (
            "This brief lists exactly what to write and where. Never add a "
            "signal not listed here, never drop a listed signal, and never "
            "use a canonical requirement name as vocabulary where a "
            "displaced phrase is specified."
        ),
    }
    return brief


def write_briefs(roster: pd.DataFrame, key: pd.DataFrame) -> None:
    log(f"writing {len(roster)} application briefs to {config.BRIEFS_DIR}")
    config.BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    for _, row in roster.iterrows():
        brief = build_brief(row, key)
        num = int(row["candidate_id"][1:])
        out_path = config.BRIEFS_DIR / f"brief_{num:03d}.json"
        out_path.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 6: persona subset
# ---------------------------------------------------------------------------

def build_persona_subset(roster: pd.DataFrame) -> dict:
    log("sampling the 48-application persona-arm subset")
    chosen_ids = []
    for archetype_id, count in config.PERSONA_SUBSET_COUNTS_BY_ARCHETYPE.items():
        pool = roster.loc[roster["archetype"] == archetype_id, "candidate_id"].tolist()
        rng = config.deterministic_rng("persona_subset", archetype_id)
        picked = rng.choice(sorted(pool), size=count, replace=False)
        chosen_ids += sorted(picked.tolist())

    assert len(chosen_ids) == config.PERSONA_SUBSET_SIZE
    assert len(set(chosen_ids)) == config.PERSONA_SUBSET_SIZE

    return {
        "subset_size": config.PERSONA_SUBSET_SIZE,
        "candidate_ids": sorted(chosen_ids),
        "counts_by_archetype": config.PERSONA_SUBSET_COUNTS_BY_ARCHETYPE,
        "personas": config.PERSONAS,
        "note": "Both screening arms (unaided, then with the dossier) run "
                "over this same 48-application subset at a fixed time "
                "budget per design.md S3. Simulation itself is Phase 2/3 "
                "work, not built by this script.",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    roster = build_roster()
    key = build_answer_key(roster)
    summary = build_candidate_summary(roster, key)

    log(f"writing answer key ({len(key)} rows) to {config.ANSWER_KEY_PATH}")
    key.to_csv(config.ANSWER_KEY_PATH, index=False)

    log(f"writing candidate summary ({len(summary)} rows) to {config.ANSWER_KEY_CANDIDATES_PATH}")
    summary.to_csv(config.ANSWER_KEY_CANDIDATES_PATH, index=False)

    write_briefs(roster, key)

    persona_subset = build_persona_subset(roster)
    config.PERSONA_SUBSET_PATH.write_text(
        json.dumps(persona_subset, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote persona subset to {config.PERSONA_SUBSET_PATH}")

    log("done")


if __name__ == "__main__":
    main()
