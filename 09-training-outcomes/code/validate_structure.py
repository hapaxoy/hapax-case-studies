"""
Independent validator for the 09 Training Outcomes Phase 2 dataset.

Re-derives every coherence rule from the FILES ON DISK — never trusts
generate_structure.py's in-memory state (portfolio precedent: 07 Tenders,
08 Inbox). Exits 1 on any failure; a dataset that fails validation is a bug,
not a judgment call.

Checks:
    1. Name-collision check (re-run against config's exclusion lists).
    2. Archetype counts match config.ARCHETYPES exactly.
    3. Role split is even (10/10/10/10).
    4. Pre-form counterbalancing is even (20 A / 20 B).
    5. delta_post / confidence_delta_post correlation within the documented
       tolerance band (config.DELTA_CONFIDENCE_CORRELATION_TARGET).
    6. Form A/B difficulty balance within tolerance
       (config.FORM_DIFFICULTY_TOLERANCE).
    7. Response-brief completeness: exactly 240 files, one per
       (learner, form, occasion), each internally consistent with
       config.ability_to_band and the practice-effect rule.
    8. Answer-key completeness: 40 rows, every required field present, and
       learner_ids match the cohort exactly.
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

FAILURES = []


def check(condition, message):
    """Record a failure without stopping — collect everything wrong in one
    run, the same discipline as 07/08's validators."""
    if condition:
        print(f"  [OK] {message}")
    else:
        print(f"  [FAIL] {message}")
        FAILURES.append(message)


def load_learners_csv():
    path = config.COHORT_DIR / "learners.csv"
    if not path.exists():
        FAILURES.append(f"missing {path}")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_answer_key_csv():
    path = config.ANSWER_KEY_DIR / "answer_key.csv"
    if not path.exists():
        FAILURES.append(f"missing {path}")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_name_collisions_independent(learners):
    print("\n1. Name-collision check")
    try:
        config.check_name_collisions()
        collisions_in_config_lists = True
    except AssertionError as exc:
        collisions_in_config_lists = False
        print(f"  detail: {exc}")
    check(collisions_in_config_lists, "config-declared names carry no collisions")

    # Independent re-derivation: read the names actually written to disk
    # and check them again, rather than trusting the in-memory list used
    # to generate them.
    written_names = {row["name"] for row in learners}
    overlap_people = written_names & config.EXISTING_PORTFOLIO_PERSON_NAMES
    check(not overlap_people, f"written learner names collide with portfolio people: {overlap_people or 'none'}")
    overlap_firms = written_names & config.EXISTING_PORTFOLIO_FIRM_NAMES
    check(not overlap_firms, f"written learner names collide with portfolio firms: {overlap_firms or 'none'}")
    check(config.COMPANY["name"] not in config.EXISTING_PORTFOLIO_FIRM_NAMES,
          f"company name '{config.COMPANY['name']}' does not collide with an existing portfolio firm")
    check(len(written_names) == 40, f"40 unique learner names written on disk (found {len(written_names)})")


def check_archetype_counts(learners):
    print("\n2. Archetype counts")
    counts = {}
    for row in learners:
        counts[row["archetype"]] = counts.get(row["archetype"], 0) + 1
    for archetype_key, spec in config.ARCHETYPES.items():
        found = counts.get(archetype_key, 0)
        check(found == spec["n"], f"{archetype_key}: expected {spec['n']}, found {found}")
    check(sum(counts.values()) == 40, f"cohort totals 40 (found {sum(counts.values())})")


def check_role_split(learners):
    print("\n3. Role split")
    counts = {}
    for row in learners:
        counts[row["role"]] = counts.get(row["role"], 0) + 1
    for role in config.ROLES:
        found = counts.get(role, 0)
        check(found == config.ROLE_COUNT_PER_ROLE,
              f"role '{role}': expected {config.ROLE_COUNT_PER_ROLE}, found {found}")


def check_form_counterbalancing(learners):
    print("\n4. Pre-form counterbalancing")
    counts = {"A": 0, "B": 0}
    for row in learners:
        counts[row["pre_form"]] = counts.get(row["pre_form"], 0) + 1
    check(counts.get("A") == 20, f"20 learners pre-form A (found {counts.get('A')})")
    check(counts.get("B") == 20, f"20 learners pre-form B (found {counts.get('B')})")


def check_delta_confidence_independence(learners):
    print("\n5. delta_post / confidence_delta_post independence")
    deltas = np.array([float(row["delta_post"]) for row in learners])
    conf_deltas = np.array([float(row["confidence_delta_post"]) for row in learners])
    r = float(np.corrcoef(deltas, conf_deltas)[0, 1])
    lo, hi = config.DELTA_CONFIDENCE_CORRELATION_TARGET
    check(lo <= r <= hi, f"correlation r = {r:.3f} within target band [{lo}, {hi}]")

    # The within-archetype independence claim: no archetype should show a
    # strong internal correlation between the two (each is an independent
    # draw per learner within its archetype's distributions).
    by_archetype = {}
    for row in learners:
        by_archetype.setdefault(row["archetype"], []).append(row)
    for archetype_key, rows in by_archetype.items():
        if len(rows) < 4:
            continue  # too few points (n=3 archetypes) for a meaningful r
        d = np.array([float(r_["delta_post"]) for r_ in rows])
        c = np.array([float(r_["confidence_delta_post"]) for r_ in rows])
        if d.std() < 1e-9 or c.std() < 1e-9:
            continue
        r_within = float(np.corrcoef(d, c)[0, 1])
        check(abs(r_within) <= 0.75,
              f"within-archetype '{archetype_key}' independence plausible (r_within = {r_within:.3f})")


def check_form_difficulty_balance():
    print("\n6. Form A/B difficulty balance")
    path_a = config.TASK_SETS_DIR / "form_a.yaml"
    path_b = config.TASK_SETS_DIR / "form_b.yaml"
    if not path_a.exists() or not path_b.exists():
        FAILURES.append("form_a.yaml or form_b.yaml missing")
        return
    with open(path_a, encoding="utf-8") as f:
        form_a = yaml.safe_load(f)
    with open(path_b, encoding="utf-8") as f:
        form_b = yaml.safe_load(f)

    check(len(form_a["tasks"]) == 10, f"Form A has 10 tasks (found {len(form_a['tasks'])})")
    check(len(form_b["tasks"]) == 10, f"Form B has 10 tasks (found {len(form_b['tasks'])})")

    def mean_difficulty(form):
        difficulties = [
            item["item_difficulty"]
            for task in form["tasks"]
            for item in task["rubric_items"]
        ]
        return sum(difficulties) / len(difficulties)

    mean_a = mean_difficulty(form_a)
    mean_b = mean_difficulty(form_b)
    gap = abs(mean_a - mean_b)
    check(gap <= config.FORM_DIFFICULTY_TOLERANCE,
          f"mean item difficulty A={mean_a:.4f} vs B={mean_b:.4f}, gap {gap:.4f} <= tolerance {config.FORM_DIFFICULTY_TOLERANCE}")

    # Pairwise match by task index (A{i} vs B{i} share the same rubric
    # difficulty spread by construction — check it wasn't broken by hand-edits).
    tasks_a = {t["index"]: t for t in form_a["tasks"]}
    tasks_b = {t["index"]: t for t in form_b["tasks"]}
    all_pairs_matched = True
    for idx in tasks_a:
        diffs_a = sorted(item["item_difficulty"] for item in tasks_a[idx]["rubric_items"])
        diffs_b = sorted(item["item_difficulty"] for item in tasks_b[idx]["rubric_items"])
        if diffs_a != diffs_b:
            all_pairs_matched = False
    check(all_pairs_matched, "every A{i}/B{i} task pair shares an identical rubric-difficulty spread")


def check_response_briefs(learners):
    print("\n7. Response-brief completeness")
    files = sorted(config.RESPONSE_BRIEFS_DIR.glob("L*_form*.json"))
    check(len(files) == 240, f"240 response-brief files present (found {len(files)})")

    expected_keys = {
        (row["learner_id"], form, occasion)
        for row in learners
        for form in ("A", "B")
        for occasion in config.COMPANY["occasions"]
    }
    found_keys = set()
    bad_practice_flags = 0
    bad_task_counts = 0
    bad_bands = 0

    for path in files:
        try:
            brief = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            FAILURES.append(f"{path.name} is not valid JSON: {exc}")
            continue
        key = (brief["learner_id"], brief["form"], brief["occasion"])
        found_keys.add(key)

        expected_bonus = config.PRACTICE_EFFECT_BONUS if brief["is_repeat_form"] else 0.0
        if abs(brief["practice_bonus_applied"] - expected_bonus) > 1e-9:
            bad_practice_flags += 1

        if len(brief["tasks"]) != 10:
            bad_task_counts += 1

        for task in brief["tasks"]:
            expected_band = config.ability_to_band(task["effective_ability"])
            if task["band"] != expected_band:
                bad_bands += 1

    check(found_keys == expected_keys,
          f"every (learner, form, occasion) combination present exactly once "
          f"(missing {len(expected_keys - found_keys)}, unexpected {len(found_keys - expected_keys)})")
    check(bad_practice_flags == 0, f"practice-effect bonus matches the is_repeat_form rule in every brief (found {bad_practice_flags} mismatches)")
    check(bad_task_counts == 0, f"every brief carries exactly 10 tasks (found {bad_task_counts} briefs that don't)")
    check(bad_bands == 0, f"every task's recorded band matches config.ability_to_band(effective_ability) (found {bad_bands} mismatches)")

    manifest_path = config.RESPONSE_BRIEFS_DIR / "manifest.csv"
    check(manifest_path.exists(), f"{manifest_path.name} present")


def check_answer_key(learners, answer_key_rows):
    print("\n8. Answer-key completeness")
    check(len(answer_key_rows) == 40, f"answer key has 40 rows (found {len(answer_key_rows)})")

    required_fields = [
        "learner_id", "archetype", "delta_post", "retention_factor",
        "confidence_pre", "confidence_post", "confidence_8wk", "volunteer",
    ]
    missing_field_rows = 0
    for row in answer_key_rows:
        for field in required_fields:
            if row.get(field, "") == "":
                missing_field_rows += 1
                break
    check(missing_field_rows == 0, f"every required field populated in every row (found {missing_field_rows} incomplete rows)")

    key_ids = {row["learner_id"] for row in answer_key_rows}
    cohort_ids = {row["learner_id"] for row in learners}
    check(key_ids == cohort_ids, "answer-key learner_ids match the cohort exactly")

    json_path = config.ANSWER_KEY_DIR / "answer_key.json"
    check(json_path.exists(), f"{json_path.name} present")


def check_instruments():
    print("\n9. Instrument definitions")
    for key in config.INSTRUMENT_DEFINITIONS:
        path = config.INSTRUMENTS_DIR / f"{key}.yaml"
        check(path.exists(), f"{path.name} present")
        if path.exists():
            with open(path, encoding="utf-8") as f:
                payload = yaml.safe_load(f)
            check("population" in payload, f"{path.name} declares a population rule")
    naive_path = config.INSTRUMENTS_DIR / "naive.yaml"
    if naive_path.exists():
        with open(naive_path, encoding="utf-8") as f:
            naive = yaml.safe_load(f)
        check("volunteer_learner_ids" in naive and len(naive["volunteer_learner_ids"]) > 0,
              f"naive instrument records a non-empty volunteer roster ({len(naive.get('volunteer_learner_ids', []))} learners)")


def main():
    print(f"09 Training Outcomes - Phase 2 structure validation (seed={config.RANDOM_SEED})")

    learners = load_learners_csv()
    answer_key_rows = load_answer_key_csv()

    if not learners:
        print("FATAL: no cohort data found — run generate_structure.py first.", file=sys.stderr)
        sys.exit(1)

    check_name_collisions_independent(learners)
    check_archetype_counts(learners)
    check_role_split(learners)
    check_form_counterbalancing(learners)
    check_delta_confidence_independence(learners)
    check_form_difficulty_balance()
    check_response_briefs(learners)
    check_answer_key(learners, answer_key_rows)
    check_instruments()

    print()
    if FAILURES:
        print(f"VALIDATION FAILED — {len(FAILURES)} check(s) failed:")
        for message in FAILURES:
            print(f"  - {message}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
