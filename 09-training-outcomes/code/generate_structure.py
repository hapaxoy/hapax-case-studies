"""
Phase 2 generator for the 09 Training Outcomes case study.

Builds, in order, from `config.py` alone:
    1. The task-set forms A and B (data/task_sets/) — the published
       instrument, plus a structured YAML version carrying the rubric.
    2. The 40-learner cohort (data/cohort/).
    3. The answer key (data/answer_key/) — complete before any response
       exists; it stays out of the modelling path entirely and is read only
       by code/mark.py.
    4. 240 response briefs (data/response_briefs/), one per learner x form x
       occasion, fixing a quality band per task from ability + a noise draw.
    5. The three instrument definitions (data/instruments/).

Deterministic Python controls every number in this file; no prose is
written here (that is Phase 3). Run this before
validate_structure.py.
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config


def clip(value, lower, upper):
    """Simple clip helper so every draw below reads the same way."""
    return max(lower, min(upper, value))


def draw(rng, mean_sd, lower, upper):
    """One normal draw from a (mean, sd) pair, clipped to [lower, upper]."""
    mean, sd = mean_sd
    return clip(float(rng.normal(mean, sd)), lower, upper)


# ---------------------------------------------------------------------------
# Step 1: task-set forms
# ---------------------------------------------------------------------------
def render_task_sets():
    """Write the published Markdown forms and the structured YAML versions
    (which additionally carry the rubric, for mark.py's future use)."""
    print("Step 1/5: rendering task-set Forms A and B...")
    config.TASK_SETS_DIR.mkdir(parents=True, exist_ok=True)

    for form_letter, prompt_key in (("A", "prompt_a"), ("B", "prompt_b")):
        md_lines = [
            f"# Kuusiharju Oy — AI-Augmented Workflows — Assessment Form {form_letter}",
            "",
            "This form is one half of a matched pair (Form A / Form B) used "
            "before and after the two-day AI-Augmented Workflows programme. "
            "Each learner sits one form before training and the other "
            "after, so that no one answers the identical questions twice. "
            "There are 10 tasks. Work through them in order; there is no "
            "trick in the ordering. Answer in your own words — there is no "
            "single required phrasing, only a fixed set of things a "
            "complete answer contains.",
            "",
            "---",
            "",
        ]
        yaml_tasks = []
        for pair in config.TASK_PAIRS:
            idx = pair["index"]
            category = pair["category"]
            prompt = pair[prompt_key]
            md_lines.append(f"## {form_letter}{idx}. ({category.replace('_', ' ')})")
            md_lines.append("")
            md_lines.append(prompt)
            md_lines.append("")
            yaml_tasks.append({
                "task_id": f"{form_letter}{idx}",
                "index": idx,
                "category": category,
                "prompt": prompt,
                "max_points": len(pair["rubric_items"]),
                "rubric_items": [
                    {
                        "item_id": f"{form_letter}{idx}.{item_num}",
                        "description": description,
                        "item_difficulty": difficulty,
                        "points": 1,
                    }
                    for item_num, (description, difficulty) in enumerate(
                        pair["rubric_items"], start=1
                    )
                ],
            })

        md_path = config.TASK_SETS_DIR / f"form_{form_letter.lower()}.md"
        md_path.write_text("\n".join(md_lines), encoding="utf-8")

        yaml_path = config.TASK_SETS_DIR / f"form_{form_letter.lower()}.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {"form": form_letter, "tasks": yaml_tasks},
                f, allow_unicode=True, sort_keys=False,
            )
        print(f"  wrote {md_path.name} and {yaml_path.name} ({len(yaml_tasks)} tasks)")


# ---------------------------------------------------------------------------
# Step 2: the cohort
# ---------------------------------------------------------------------------
def build_cohort(rng):
    """Assign archetype, role, pre-training form and every per-learner
    parameter, then compute the derived per-occasion ability and confidence
    trajectories. Returns a list of 40 learner dicts, in learner_id order."""
    print("Step 2/5: building the 40-learner cohort...")

    # Archetype assignment: one slot per learner, in archetype-table order,
    # then shuffled so archetype does not correlate with name-list position.
    archetype_slots = []
    for archetype_key, spec in config.ARCHETYPES.items():
        archetype_slots.extend([archetype_key] * spec["n"])
    assert len(archetype_slots) == config.COHORT_SIZE
    archetype_order = rng.permutation(len(archetype_slots))
    archetype_assignment = [archetype_slots[i] for i in archetype_order]

    # Roles: evenly split, shuffled independently of archetype.
    role_slots = list(config.ROLES) * config.ROLE_COUNT_PER_ROLE
    assert len(role_slots) == config.COHORT_SIZE
    role_order = rng.permutation(len(role_slots))
    role_assignment = [role_slots[i] for i in role_order]

    # Pre-training form: 20 A / 20 B, shuffled — this is the honest
    # instrument's counterbalancing and also fixes the naive arm's
    # "same form pre and post" form choice.
    form_slots = ["A"] * (config.COHORT_SIZE // 2) + ["B"] * (config.COHORT_SIZE // 2)
    form_order = rng.permutation(len(form_slots))
    form_assignment = [form_slots[i] for i in form_order]

    learners = []
    for i, name in enumerate(config.LEARNER_NAMES):
        learner_id = f"L{i + 1:02d}"
        archetype_key = archetype_assignment[i]
        spec = config.ARCHETYPES[archetype_key]

        baseline_ability = draw(rng, spec["baseline_ability"], 0.05, 0.97)
        delta_post = draw(rng, spec["delta_post"], -0.10, 0.60)
        retention_factor = draw(rng, spec["retention_factor"], 0.0, 1.05)
        confidence_baseline = draw(rng, spec["confidence_baseline"], 1.0, 7.0)
        confidence_delta_post = draw(rng, spec["confidence_delta_post"], -1.0, 3.0)
        confidence_retention = draw(rng, spec["confidence_retention"], 0.0, 1.05)
        assessment_noise = draw(rng, spec["assessment_noise"], 0.02, 0.20)
        volunteering_propensity = draw(rng, spec["volunteering_propensity"], 0.0, 1.0)

        # Derived per-occasion true ability (the planted signal mark.py
        # will one day try to recover).
        ability_pre = baseline_ability
        ability_post = clip(baseline_ability + delta_post, 0.0, 1.0)
        ability_8wk = clip(baseline_ability + delta_post * retention_factor, 0.0, 1.0)

        # Derived per-occasion self-reported confidence, drawn from its own
        # trajectory parameters — never a function of delta_post.
        confidence_pre = clip(confidence_baseline, 1.0, 7.0)
        confidence_post = clip(confidence_baseline + confidence_delta_post, 1.0, 7.0)
        confidence_8wk = clip(
            confidence_baseline + confidence_delta_post * confidence_retention,
            1.0, 7.0,
        )
        # Satisfaction tracks confidence with its own noise draw (feedback
        # sheet content); asked post-training only in practice, but
        # computed at every occasion for completeness.
        satisfaction_post = clip(confidence_post + rng.normal(0, 0.3), 1.0, 7.0)

        volunteer = bool(rng.random() < volunteering_propensity)

        learners.append({
            "learner_id": learner_id,
            "name": name,
            "role": role_assignment[i],
            "archetype": archetype_key,
            "archetype_label": spec["label"],
            "pre_form": form_assignment[i],
            "post_form": "B" if form_assignment[i] == "A" else "A",
            "baseline_ability": round(baseline_ability, 4),
            "delta_post": round(delta_post, 4),
            "retention_factor": round(retention_factor, 4),
            "ability_pre": round(ability_pre, 4),
            "ability_post": round(ability_post, 4),
            "ability_8wk": round(ability_8wk, 4),
            "confidence_baseline": round(confidence_baseline, 4),
            "confidence_delta_post": round(confidence_delta_post, 4),
            "confidence_retention": round(confidence_retention, 4),
            "confidence_pre": round(confidence_pre, 4),
            "confidence_post": round(confidence_post, 4),
            "confidence_8wk": round(confidence_8wk, 4),
            "satisfaction_post": round(satisfaction_post, 4),
            "assessment_noise": round(assessment_noise, 4),
            "volunteering_propensity": round(volunteering_propensity, 4),
            "volunteer": volunteer,
        })

    print(f"  assigned {len(learners)} learners across "
          f"{len(config.ARCHETYPES)} archetypes and {len(config.ROLES)} roles")
    return learners


def write_cohort(learners):
    config.COHORT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(learners[0].keys())

    csv_path = config.COHORT_DIR / "learners.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(learners)
    print(f"  wrote {csv_path.name} ({len(learners)} rows)")

    for learner in learners:
        json_path = config.COHORT_DIR / f"{learner['learner_id']}.json"
        json_path.write_text(
            json.dumps(learner, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(f"  wrote {len(learners)} per-learner JSON profiles")


# ---------------------------------------------------------------------------
# Step 3: answer key
# ---------------------------------------------------------------------------
def write_answer_key(learners):
    """The complete answer key — planted truth, nothing derived from any
    response. Written before any response brief exists in this run's
    output, and must stay complete before Phase 3 generates any prose."""
    print("Step 3/5: writing the answer key...")
    config.ANSWER_KEY_DIR.mkdir(parents=True, exist_ok=True)

    key_fields = [
        "learner_id", "name", "role", "archetype", "archetype_label",
        "pre_form", "post_form",
        "delta_post", "retention_factor",
        "ability_pre", "ability_post", "ability_8wk",
        "confidence_pre", "confidence_post", "confidence_8wk",
        "confidence_delta_post",
        "volunteer", "volunteering_propensity",
    ]
    key_rows = [{field: learner[field] for field in key_fields} for learner in learners]

    csv_path = config.ANSWER_KEY_DIR / "answer_key.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=key_fields)
        writer.writeheader()
        writer.writerows(key_rows)

    json_path = config.ANSWER_KEY_DIR / "answer_key.json"
    json_path.write_text(json.dumps(key_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  wrote {csv_path.name} and {json_path.name} ({len(key_rows)} learners)")


# ---------------------------------------------------------------------------
# Step 4: response briefs
# ---------------------------------------------------------------------------
def build_response_briefs(learners, rng):
    """One brief per (learner, form, occasion) = 40 x 2 x 3 = 240. Each
    brief fixes, per task, an effective-ability draw, the rubric band it
    maps to (config.ability_to_band), which rubric items are hit, and a
    characteristic mistake drawn from that band's mistake bank. A
    (learner, occasion) self-report block is duplicated across both forms'
    briefs for that occasion, since self-report is not form-specific."""
    print("Step 4/5: building 240 response briefs (40 learners x 2 forms x 3 occasions)...")
    config.RESPONSE_BRIEFS_DIR.mkdir(parents=True, exist_ok=True)

    occasions = config.COMPANY["occasions"]  # pre, post, follow_up_8wk
    ability_field = {"pre": "ability_pre", "post": "ability_post", "follow_up_8wk": "ability_8wk"}
    confidence_field = {"pre": "confidence_pre", "post": "confidence_post", "follow_up_8wk": "confidence_8wk"}

    manifest_rows = []
    brief_count = 0

    for learner in learners:
        for form_letter in ("A", "B"):
            is_learner_pre_form = (form_letter == learner["pre_form"])
            for occasion in occasions:
                occasion_ability = learner[ability_field[occasion]]

                # Practice effect: this form/occasion is a REPEAT
                # administration only if it is the learner's pre-training
                # form being seen again at a later occasion
                # (config.PRACTICE_EFFECT_BONUS).
                is_repeat = is_learner_pre_form and occasion != "pre"
                practice_bonus = config.PRACTICE_EFFECT_BONUS if is_repeat else 0.0

                task_entries = []
                for pair in config.TASK_PAIRS:
                    noise = float(rng.normal(0, learner["assessment_noise"]))
                    effective_ability = clip(occasion_ability + practice_bonus + noise, 0.0, 1.0)
                    band_id = config.ability_to_band(effective_ability)
                    band_label, mistakes = next(
                        (label, m) for bid, label, _lo, _hi, m in config.RUBRIC_BANDS if bid == band_id
                    )
                    rubric_items = pair["rubric_items"]
                    hit_indices = [
                        idx for idx, (_desc, difficulty) in enumerate(rubric_items, start=1)
                        if difficulty <= effective_ability
                    ]
                    # Deterministic pick of one characteristic mistake for
                    # this task from its band's bank, varied by task index
                    # so the same learner doesn't repeat the same line ten
                    # times in one brief.
                    mistake = mistakes[(pair["index"] - 1) % len(mistakes)] if band_id != "excellent" or mistakes else None

                    task_entries.append({
                        "task_id": f"{form_letter}{pair['index']}",
                        "category": pair["category"],
                        "effective_ability": round(effective_ability, 4),
                        "band": band_id,
                        "band_label": band_label,
                        "points_earned": len(hit_indices),
                        "max_points": len(rubric_items),
                        "rubric_items_hit": hit_indices,
                        "characteristic_mistake": mistake,
                    })

                brief = {
                    "learner_id": learner["learner_id"],
                    "name": learner["name"],
                    "role": learner["role"],
                    "form": form_letter,
                    "occasion": occasion,
                    "is_repeat_form": is_repeat,
                    "practice_bonus_applied": practice_bonus,
                    "self_report": {
                        "confidence": round(learner[confidence_field[occasion]], 4),
                        "satisfaction": round(learner["satisfaction_post"], 4) if occasion == "post" else None,
                    },
                    "tasks": task_entries,
                }

                filename = f"{learner['learner_id']}_form{form_letter}_{occasion}.json"
                path = config.RESPONSE_BRIEFS_DIR / filename
                path.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
                brief_count += 1

                manifest_rows.append({
                    "learner_id": learner["learner_id"],
                    "form": form_letter,
                    "occasion": occasion,
                    "filename": filename,
                    "is_repeat_form": is_repeat,
                    "mean_points_fraction": round(
                        sum(t["points_earned"] / t["max_points"] for t in task_entries) / len(task_entries), 4
                    ),
                })

    manifest_path = config.RESPONSE_BRIEFS_DIR / "manifest.csv"
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"  wrote {brief_count} response-brief files and {manifest_path.name}")
    return manifest_rows


# ---------------------------------------------------------------------------
# Step 5: instrument definitions
# ---------------------------------------------------------------------------
def write_instruments(learners):
    """Render the three instrument configs a future mark.py applies
    mechanically. The naive instrument's volunteer roster is fixed here
    (from the answer key's volunteer flag) so the selection bias is
    reproducible and inspectable ahead of any scoring run."""
    print("Step 5/5: writing the three instrument definitions...")
    config.INSTRUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    volunteer_ids = [l["learner_id"] for l in learners if l["volunteer"]]

    for key, definition in config.INSTRUMENT_DEFINITIONS.items():
        payload = dict(definition)
        if key == "naive":
            payload["volunteer_learner_ids"] = volunteer_ids
            payload["volunteer_count"] = len(volunteer_ids)
        path = config.INSTRUMENTS_DIR / f"{key}.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
        print(f"  wrote {path.name}")

    n_volunteers = len(volunteer_ids)
    print(f"  naive arm volunteer subset: {n_volunteers}/{len(learners)} learners "
          f"({n_volunteers / len(learners):.0%})")


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------
def print_diagnostics(learners):
    """Quick sanity read against the pre-registered expectations,
    for visibility only — validate_structure.py is the authority."""
    print("\nDiagnostics:")
    deltas = np.array([l["delta_post"] for l in learners])
    conf_deltas = np.array([l["confidence_delta_post"] for l in learners])
    r = np.corrcoef(deltas, conf_deltas)[0, 1]
    lo, hi = config.DELTA_CONFIDENCE_CORRELATION_TARGET
    flag = "OK" if lo <= r <= hi else "OUT OF BAND"
    print(f"  delta_post vs confidence_delta_post correlation: r = {r:.3f} "
          f"(target band {lo}-{hi}) [{flag}]")

    cohort_mean_delta = deltas.mean()
    print(f"  cohort mean planted delta_post: {cohort_mean_delta:.3f}")

    confident_non_learners = [l for l in learners if l["archetype"] == "confident_non_learner"]
    print(f"  confident non-learners: {len(confident_non_learners)} "
          f"(mean delta {np.mean([l['delta_post'] for l in confident_non_learners]):.3f}, "
          f"mean confidence gain {np.mean([l['confidence_delta_post'] for l in confident_non_learners]):.3f})")

    fast_forgetters = [l for l in learners if l["archetype"] == "fast_forgetter"]
    for l in fast_forgetters:
        print(f"  fast forgetter {l['learner_id']} ({l['name']}): "
              f"ability_post={l['ability_post']:.3f} -> ability_8wk={l['ability_8wk']:.3f}")


def main():
    print(f"09 Training Outcomes - Phase 2 structure generation (seed={config.RANDOM_SEED})")
    try:
        config.check_name_collisions()
        print("Name collision check: no collisions against the existing portfolio.")
    except AssertionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    rng = np.random.default_rng(config.RANDOM_SEED)

    try:
        render_task_sets()
        learners = build_cohort(rng)
        write_cohort(learners)
        write_answer_key(learners)
        build_response_briefs(learners, rng)
        write_instruments(learners)
        print_diagnostics(learners)
    except Exception as exc:  # graceful, informative failure per house rules
        print(f"ERROR during generation: {exc}", file=sys.stderr)
        raise

    print("\nDone. Run code/validate_structure.py next.")


if __name__ == "__main__":
    main()
