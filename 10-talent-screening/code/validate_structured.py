"""Validation pass for Project 10 Phase 1 structured data.

Enforces every corpus coherence rule against the generated
answer_key.csv / answer_key_candidates.csv / briefs / persona_subset.json.
Exits 1 on any failure -- a dataset that fails this script is a bug, not a
judgment call, per the portfolio's standing rule.

Run: python validate_structured.py   (after generate_structured.py)
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
from scipy import stats

import config


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    """Record a failure without stopping the run -- every check should get
    a chance to report, so a single early failure doesn't hide the rest.
    """
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


def log(message: str) -> None:
    print(f"[validate_structured] {message}", flush=True)


def load() -> tuple[pd.DataFrame, pd.DataFrame, dict, list[dict]]:
    key = pd.read_csv(config.ANSWER_KEY_PATH, keep_default_na=False)
    summary = pd.read_csv(config.ANSWER_KEY_CANDIDATES_PATH, keep_default_na=False)
    persona_subset = json.loads(config.PERSONA_SUBSET_PATH.read_text(encoding="utf-8"))
    briefs = []
    for num in range(1, config.N_CANDIDATES + 1):
        path = config.BRIEFS_DIR / f"brief_{num:03d}.json"
        briefs.append(json.loads(path.read_text(encoding="utf-8")))
    return key, summary, persona_subset, briefs


# ---------------------------------------------------------------------------
# 1. Archetype counts exact; 240 total
# ---------------------------------------------------------------------------

def check_archetype_counts(summary: pd.DataFrame) -> None:
    log("=== archetype counts ===")
    check(len(summary) == config.N_CANDIDATES,
          f"total candidates == {config.N_CANDIDATES} (got {len(summary)})")
    counts = summary["archetype"].value_counts().to_dict()
    for archetype in config.ARCHETYPES:
        got = counts.get(archetype["id"], 0)
        check(got == archetype["n"],
              f"archetype {archetype['id']} ({archetype['label']}) count == "
              f"{archetype['n']} (got {got})")
    check(len(summary["candidate_id"].unique()) == config.N_CANDIDATES,
          "candidate_id is unique across all rows")


# ---------------------------------------------------------------------------
# 2. F candidates: displaced vocabulary always from config's table, never
#    the canonical term.
# ---------------------------------------------------------------------------

def check_displacement(key: pd.DataFrame) -> None:
    log("=== F displacement (hidden gem) ===")
    f_disp = key[key["displaced"] == True]  # noqa: E712 (explicit bool compare on CSV-loaded col)
    f_candidates = key.loc[key["archetype"] == "F", "candidate_id"].unique()
    check(len(f_disp) == len(f_candidates) == config.ARCHETYPE_BY_ID["F"]["n"],
          f"exactly one displaced requirement per F candidate "
          f"({config.ARCHETYPE_BY_ID['F']['n']} total)")

    only_f = set(f_disp["candidate_id"].unique()) <= set(f_candidates)
    check(only_f, "every displaced row belongs to an F candidate")
    check(set(f_disp["candidate_id"].unique()) == set(f_candidates),
          "every F candidate has exactly one displaced row")

    for _, row in f_disp.iterrows():
        rid = row["requirement_id"]
        phrase = row["displaced_phrase"]
        table = config.DISPLACEMENT_TABLE.get(rid, [])
        check(phrase in table,
              f"{row['candidate_id']}: displaced phrase for {rid} is drawn "
              f"from config.DISPLACEMENT_TABLE ({phrase!r})")
        canonical = config.REQUIREMENT_BY_ID[rid]["name"].lower()
        check(canonical not in phrase.lower(),
              f"{row['candidate_id']}: displaced phrase for {rid} does not "
              f"contain the canonical term {canonical!r}")
        check(row["status"] == "evidenced",
              f"{row['candidate_id']}: displaced requirement status is "
              f"'evidenced' (fully qualified, just relabelled)")

    n_letter_only = int(((f_disp["evidence_location"] == "cover_letter")).sum())
    log(f"F candidates with letter-only displaced evidence: {n_letter_only} of "
        f"{config.ARCHETYPE_BY_ID['F']['n']}")
    check(n_letter_only == 9,
          f"exactly 9 of 18 F candidates have their displaced skill "
          f"letter-only (got {n_letter_only})")

    # Self-defending: no non-F candidate may carry a displaced row at all.
    non_f_displaced = key[(key["displaced"] == True) & (key["archetype"] != "F")]  # noqa: E712
    check(len(non_f_displaced) == 0,
          "no non-F archetype carries a displaced-vocabulary row "
          "(self-defending: a config edit that leaks displacement to "
          "another archetype fails here)")


# ---------------------------------------------------------------------------
# 3. E candidates carry exactly the configured contradiction; self-defending
#    against any other archetype acquiring one.
# ---------------------------------------------------------------------------

def check_contradictions(key: pd.DataFrame) -> None:
    log("=== E credential inflation ===")
    contradicted = key[key["status"] == "contradicted"]
    e_candidates = key.loc[key["archetype"] == "E", "candidate_id"].unique()

    check(set(contradicted["candidate_id"].unique()) == set(e_candidates),
          "every E candidate has exactly one contradicted row, and only E "
          "candidates do (self-defending)")

    per_candidate_counts = contradicted.groupby("candidate_id").size()
    check((per_candidate_counts == 1).all(),
          "every contradicted candidate has EXACTLY one contradicted row")

    valid_targets = {c["requirement_id"] for c in config.CONTRADICTION_TEMPLATES}
    check(set(contradicted["requirement_id"].unique()) <= valid_targets,
          f"every contradiction targets a configured requirement {valid_targets}")

    codes = contradicted["contradiction_code"].value_counts().to_dict()
    log(f"contradiction template split: {codes}")
    check(set(codes.keys()) == {c["code"] for c in config.CONTRADICTION_TEMPLATES},
          "both contradiction templates are used at least once")
    check(sum(codes.values()) == config.ARCHETYPE_BY_ID["E"]["n"],
          f"contradiction template counts sum to {config.ARCHETYPE_BY_ID['E']['n']}")

    for _, row in contradicted.iterrows():
        template = config.CONTRADICTION_BY_CODE[row["contradiction_code"]]
        check(template["requirement_id"] == row["requirement_id"],
              f"{row['candidate_id']}: contradiction_code "
              f"{row['contradiction_code']!r} matches its requirement_id "
              f"{row['requirement_id']!r}")


# ---------------------------------------------------------------------------
# 4. H candidates: key records "defensible either way" on the designed
#    requirement; self-defending against other archetypes.
# ---------------------------------------------------------------------------

def check_borderline(key: pd.DataFrame) -> None:
    log("=== H genuine borderline ===")
    borderline_rows = key[key["borderline_code"] != ""]
    h_candidates = key.loc[key["archetype"] == "H", "candidate_id"].unique()

    check(set(borderline_rows["candidate_id"].unique()) == set(h_candidates),
          "every H candidate has exactly one borderline row, and only H "
          "candidates do (self-defending)")
    per_candidate_counts = borderline_rows.groupby("candidate_id").size()
    check((per_candidate_counts == 1).all(),
          "every borderline candidate has EXACTLY one borderline row")

    for _, row in borderline_rows.iterrows():
        template = config.BORDERLINE_BY_CODE[row["borderline_code"]]
        check(template["requirement_id"] == row["requirement_id"],
              f"{row['candidate_id']}: borderline_code matches its requirement_id")
        check(row["borderline_note"] == template["borderline_note"],
              f"{row['candidate_id']}: borderline_note matches the "
              "configured 'defensible either way' text")
        check(row["status"] == "evidenced",
              f"{row['candidate_id']}: borderline row status is 'evidenced' "
              "(the evidence is real; only its sufficiency is ambiguous)")

    codes = borderline_rows["borderline_code"].value_counts().to_dict()
    log(f"borderline template split: {codes}")
    check(set(codes.keys()) == {c["code"] for c in config.BORDERLINE_TEMPLATES},
          "both borderline templates are used at least once")


# ---------------------------------------------------------------------------
# 5. D (keyword stuffer): all five must-haves claimed-only, never evidenced,
#    self-defending against other archetypes reaching the same all-claimed
#    profile.
# ---------------------------------------------------------------------------

def check_stuffers(key: pd.DataFrame) -> None:
    log("=== D keyword stuffer ===")
    must_have = key[key["requirement_category"] == "must_have"]
    per_candidate_status = must_have.groupby("candidate_id")["status"].apply(set)

    d_candidates = set(key.loc[key["archetype"] == "D", "candidate_id"].unique())
    all_claimed_candidates = {cid for cid, statuses in per_candidate_status.items()
                               if statuses == {"claimed_only"}}
    check(all_claimed_candidates == d_candidates,
          "the set of candidates with ALL FIVE must-haves claimed-only is "
          "exactly D (self-defending: no other archetype's rules can "
          "produce this profile)")

    letter_bloom = must_have[(must_have["archetype"] == "D") &
                              (must_have["status"] == "claimed_only") &
                              (must_have["evidence_location"] == "cover_letter")]
    log(f"D must-have claims placed in the cover letter: {len(letter_bloom)} "
        f"of {len(must_have[must_have['archetype'] == 'D'])}")
    check(len(letter_bloom) > 0,
          "at least some D claims 'bloom' in the cover letter, by "
          "design")


# ---------------------------------------------------------------------------
# 6. Career-gap: G forced to 100%; parity of "fully qualified" rate between
#    gap=True and gap=False populations.
# ---------------------------------------------------------------------------

def check_career_gap(summary: pd.DataFrame) -> None:
    log("=== career gap ===")
    for archetype_id, expected in config.CAREER_GAP_COUNTS.items():
        got = int(summary.loc[summary["archetype"] == archetype_id, "career_gap"]
                  .astype(str).eq("True").sum())
        check(got == expected,
              f"archetype {archetype_id} career_gap count == {expected} (got {got})")

    gap_mask = summary["career_gap"].astype(str).eq("True")
    fq_mask = summary["fully_qualified"].astype(str).eq("True")
    rate_gap = fq_mask[gap_mask].mean()
    rate_nogap = fq_mask[~gap_mask].mean()
    diff_pp = abs(rate_gap - rate_nogap) * 100
    log(f"fully-qualified rate: gap=True {rate_gap:.4f}, gap=False {rate_nogap:.4f}, "
        f"diff {diff_pp:.2f}pp")
    check(diff_pp <= 2.0,
          f"fully-qualified rate differs by <= 2pp between career-gap "
          f"strata (got {diff_pp:.2f}pp)")


# ---------------------------------------------------------------------------
# 7. ORTHOGONALITY -- qualification truth independent of every demographic
#    stratum. Exact stratified balance where cell sizes allow (the
#    per-archetype proportional construction), confirmed by recomputing the
#    same apportionment; chi-square with a hard threshold as the statistical
#    backstop.
# ---------------------------------------------------------------------------

def check_orthogonality(summary: pd.DataFrame) -> None:
    log("=== orthogonality: qualification truth x demographic strata ===")
    summary = summary.copy()
    summary["fully_qualified_bool"] = summary["fully_qualified"].astype(str).eq("True")

    dimensions = [
        ("name_origin", config.NAME_ORIGIN_TARGET_COUNTS),
        ("gender", config.GENDER_TARGET_COUNTS),
        ("grad_year_band", config.GRAD_YEAR_BAND_TARGET_COUNTS),
        ("degree_country", config.DEGREE_COUNTRY_TARGET_COUNTS),
    ]

    for dim, target_counts in dimensions:
        log(f"--- {dim} ---")
        # (a) Exact-where-possible reconstruction check: recompute the same
        # per-archetype largest-remainder apportionment and confirm the
        # generated counts match it exactly. This is the self-defending
        # half of the rule -- an edit to the target proportions or the
        # archetype table is caught here, not just by a statistical test.
        total = len(summary)
        global_proportions = {k: v / total for k, v in target_counts.items()}
        mismatch = False
        for archetype_id, group in summary.groupby("archetype"):
            expected = config.largest_remainder_split(len(group), global_proportions)
            actual = group[dim].value_counts().to_dict()
            for level in target_counts:
                if actual.get(level, 0) != expected.get(level, 0):
                    mismatch = True
        check(not mismatch,
              f"{dim}: every archetype's level counts match the "
              "largest-remainder proportional target exactly")

        # (b) Qualification-truth table by stratum level, printed for
        # visibility, plus a chi-square independence test as the
        # statistical backstop.
        table = pd.crosstab(summary[dim], summary["fully_qualified_bool"])
        print(table)
        rates = summary.groupby(dim)["fully_qualified_bool"].mean()
        print((rates * 100).round(2).astype(str) + "%")
        max_diff_pp = (rates.max() - rates.min()) * 100
        chi2, p, _, _ = stats.chi2_contingency(table)
        log(f"{dim}: max pairwise fully-qualified-rate spread = "
            f"{max_diff_pp:.2f}pp, chi2 p-value = {p:.4f}")
        check(p >= 0.05 or max_diff_pp <= 2.0,
              f"{dim}: qualification truth independent of stratum "
              f"(chi2 p={p:.4f}, max spread {max_diff_pp:.2f}pp)")

    # Also print the full must-have pass-count table per dimension, for
    # visibility beyond the binary fully_qualified split.
    for dim, _ in dimensions:
        log(f"--- must_have_pass_count mean by {dim} ---")
        print(summary.groupby(dim)["must_have_pass_count"].mean().round(3))


# ---------------------------------------------------------------------------
# 8. Brief integrity: every planted evidence item in the key appears in
#    exactly one brief with a location; no brief mentions a raw truth status.
# ---------------------------------------------------------------------------

def check_brief_integrity(key: pd.DataFrame, briefs: list[dict]) -> None:
    log("=== brief integrity ===")
    briefs_by_id = {b["candidate_id"]: b for b in briefs}
    check(len(briefs) == config.N_CANDIDATES, "one brief file per candidate")
    check(set(briefs_by_id) == set(key["candidate_id"].unique()),
          "brief candidate_ids match the answer key exactly")

    evidenced = key[key["status"] == "evidenced"]
    location_mismatches = 0
    missing_from_brief = 0
    letter_only_mismatches = 0

    for _, row in evidenced.iterrows():
        brief = briefs_by_id[row["candidate_id"]]
        rid = row["requirement_id"]
        is_letter_only = bool(row["letter_only"])

        if is_letter_only:
            found = [it for it in brief["cover_letter"]["evidence_in_letter"]
                     if it["requirement_id"] == rid]
            also_in_cv = [it for it in brief["evidence_to_write"]
                          if it["requirement_id"] == rid]
            if also_in_cv:
                letter_only_mismatches += 1
        else:
            found = [it for it in brief["evidence_to_write"]
                     if it["requirement_id"] == rid]
            also_in_letter = [it for it in brief["cover_letter"]["evidence_in_letter"]
                               if it["requirement_id"] == rid]
            if also_in_letter:
                letter_only_mismatches += 1

        if len(found) != 1:
            missing_from_brief += 1
            continue
        if found[0].get("location", row["evidence_location"]) != row["evidence_location"]:
            location_mismatches += 1

    check(missing_from_brief == 0,
          f"every evidenced key row appears in exactly one place in its "
          f"candidate's brief (got {missing_from_brief} mismatches)")
    check(location_mismatches == 0,
          f"every evidenced item's brief location matches the key "
          f"(got {location_mismatches} mismatches)")
    check(letter_only_mismatches == 0,
          f"letter-only evidence items appear ONLY in the cover_letter "
          f"section of their brief, never duplicated in the CV section "
          f"(got {letter_only_mismatches} mismatches)")

    # No brief may contain a literal STATUSES vocabulary word as a
    # machine-readable field value (the writer places signals; it never
    # sees the truth matrix as such).
    banned_status_leak = 0
    for brief in briefs:
        flat = json.dumps(brief)
        for status_word in config.STATUSES:
            # "evidenced" alone is fine as English prose is not banned, but
            # a literal key like status: "evidenced" would be. We check for
            # the JSON key pattern specifically.
            if f'"status": "{status_word}"' in flat or f'"status":"{status_word}"' in flat:
                banned_status_leak += 1
    check(banned_status_leak == 0,
          "no brief embeds a literal answer-key status field "
          f"(got {banned_status_leak} leaks)")


# ---------------------------------------------------------------------------
# 9. Dates: nothing later than CORPUS_NOW_YEAR anywhere in briefs or the key,
# and every candidate's career events are monotonically ordered. Scoped
# strictly to KNOWN date fields (graduation_year, career_skeleton start/end
# years) rather than a blind numeric scan of the whole JSON -- style_seed
# and cover_letter target-word-count are plain integers that can coincide
# with a 4-digit "year-shaped" number (e.g. style_seed 2047) without being
# dates at all, and a blind scan would false-flag those.
# ---------------------------------------------------------------------------

def check_dates(summary: pd.DataFrame, briefs: list[dict]) -> None:
    log("=== dates: nothing after CORPUS_NOW_YEAR, timelines ordered ===")
    now = config.CORPUS_NOW_YEAR

    grad_years = summary["graduation_year"].astype(int)
    check(bool((grad_years <= now).all()),
          f"every candidate's graduation_year <= {now} "
          f"(max found: {grad_years.max()})")

    late_dates = 0
    ordering_violations = 0
    for brief in briefs:
        cid = brief["candidate_id"]
        entries = brief["career_skeleton"]

        # Collect (kind, start, end) for every entry with numeric years;
        # "present" is treated as "now" for ordering purposes only, not
        # compared against CORPUS_NOW_YEAR as if it were a stored date.
        numeric_years = []
        for e in entries:
            if e["type"] == "education":
                y = e["graduation_year"]
                numeric_years.append(("education_end", y))
                if y > now:
                    late_dates += 1
            else:
                start = e["start_year"]
                end = e["end_year"]
                numeric_years.append((f"{e['type']}_start", start))
                if start > now:
                    late_dates += 1
                if end != "present":
                    numeric_years.append((f"{e['type']}_end", end))
                    if end > now:
                        late_dates += 1

        # Monotonic ordering: walk the entries in their listed order and
        # confirm each entry's start is not before the previous entry's
        # start (education -> work_history -> career_gap is the only order
        # the generator ever writes), and every entry's own start <= end
        # (treating "present" as now).
        prev_start = None
        for e in entries:
            this_start = e["graduation_year"] if e["type"] == "education" else e["start_year"]
            this_end = now if e["type"] == "education" else (
                now if e["end_year"] == "present" else e["end_year"])
            if this_end < this_start:
                ordering_violations += 1
            if prev_start is not None and this_start < prev_start:
                ordering_violations += 1
            prev_start = this_start

    check(late_dates == 0,
          f"no career_skeleton date exceeds CORPUS_NOW_YEAR ({now}) in any "
          f"brief (got {late_dates} violations)")
    check(ordering_violations == 0,
          f"every candidate's career_skeleton entries are internally "
          f"ordered (start <= end; entries non-decreasing in start year) "
          f"(got {ordering_violations} violations)")


# ---------------------------------------------------------------------------
# 10. Name uniqueness: all 240 full names distinct. First names and surnames
# are drawn from independent per-stratum pools (config.py), so the same
# combination can coincide across candidates unless explicitly checked --
# this is exactly the defect fix_duplicate_names.py repaired (7 collisions
# found in the Phase 1 corpus after the fact).
# ---------------------------------------------------------------------------

def check_name_uniqueness(summary: pd.DataFrame) -> None:
    log("=== name uniqueness ===")
    counts = summary["full_name"].value_counts()
    duplicates = counts[counts > 1]
    check(len(duplicates) == 0,
          f"all {len(summary)} candidate full names are unique "
          f"(got {len(duplicates)} duplicated names: "
          f"{duplicates.to_dict() if len(duplicates) else '{}'})")


# ---------------------------------------------------------------------------
# 11. Persona subset: 12 personas, 48-application stratified subset.
# ---------------------------------------------------------------------------

def check_persona_subset(summary: pd.DataFrame, persona_subset: dict) -> None:
    log("=== persona subset ===")
    check(len(persona_subset["personas"]) == 12, "exactly 12 personas defined")
    check(persona_subset["subset_size"] == 48, "persona subset size == 48")
    ids = persona_subset["candidate_ids"]
    check(len(ids) == 48 and len(set(ids)) == 48,
          "48 distinct candidate ids in the persona subset")

    by_archetype = summary.set_index("candidate_id")["archetype"].to_dict()
    counts = {}
    for cid in ids:
        counts[by_archetype[cid]] = counts.get(by_archetype[cid], 0) + 1
    check(counts == config.PERSONA_SUBSET_COUNTS_BY_ARCHETYPE,
          f"persona subset archetype counts match config exactly (got {counts})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log("loading generated data")
    key, summary, persona_subset, briefs = load()

    check_archetype_counts(summary)
    check_displacement(key)
    check_contradictions(key)
    check_borderline(key)
    check_stuffers(key)
    check_career_gap(summary)
    check_orthogonality(summary)
    check_brief_integrity(key, briefs)
    check_dates(summary, briefs)
    check_name_uniqueness(summary)
    check_persona_subset(summary, persona_subset)

    print()
    if FAILURES:
        log(f"VALIDATION FAILED: {len(FAILURES)} failing checks")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        log("VALIDATION PASSED: all coherence rules satisfied")


if __name__ == "__main__":
    main()
