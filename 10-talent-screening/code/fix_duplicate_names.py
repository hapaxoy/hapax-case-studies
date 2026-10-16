"""One-off repair script: 7 duplicate full names across the 240-candidate
corpus (`assign_names()` in generate_structured.py drew first names and
surnames independently and never checked the resulting FULL NAME for
corpus-wide uniqueness, so seven first+surname combinations collided).

This is a SURGICAL fix, not a regeneration: batches 03, 06, 08's prose
timeline fix already showed the pattern, but here the added constraint is
that some batches (notably batch_13, containing C104) have already had
prose written against them by the prose-writing agent, so a full
re-run of generate_structured.py (which would re-shuffle every name pool
and rename candidates wholesale) is out of the question. Instead: rename
exactly one member of each duplicate pair -- always the one whose batch has
NOT been written yet, except the Emma Petrov pair (C015 / C104), where both
batches are written, so C104 (the more recently touched one) is renamed and
its already-written prose is patched in place (see patch_c104_prose()).

Read-only inputs: data/answer_key_candidates.csv (for the corpus-wide
full-name collision check).
Writes: the 7 affected data/briefs/brief_NNN.json files, their embedded
copies in data/brief_batches/batch_NN.json, the 7 corresponding rows in
data/answer_key_candidates.csv, and (C104 only) a text patch to
data/applications_raw/batch_13.json.

Run once: python fix_duplicate_names.py
Then:     python validate_structured.py   (now includes a full-name
                                            uniqueness check)
"""
from __future__ import annotations

import json
import re

import pandas as pd

import config


def log(message: str) -> None:
    print(f"[fix_duplicate_names] {message}", flush=True)


# candidate_id -> True means "rename this one" (the unwritten-batch member
# of each pair, except C104 which is the exception documented above).
RENAME_TARGETS = ["C104", "C161", "C188", "C190", "C192", "C219", "C232"]

BRIEFS_DIR = config.BRIEFS_DIR
BATCHES_DIR = config.BATCHES_DIR
APPLICATIONS_RAW_DIR = config.DATA_DIR / "applications_raw"


def candidate_num(cid: str) -> int:
    return int(cid[1:])


def batch_num_for(cid: str) -> int:
    return ((candidate_num(cid) - 1) // config.BRIEF_BATCH_SIZE) + 1


def choose_new_surnames(summary: pd.DataFrame) -> dict:
    """Deterministically pick one new surname per rename target, drawn from
    the candidate's own name_origin pool, excluding their current surname,
    and rejecting any candidate full name (first_name + new surname) that
    collides with any of the 240 existing full names OR with a full name
    just assigned earlier in this same pass (so the 7 renames can't collide
    with each other either).
    """
    existing_full_names = set(summary["full_name"])
    by_id = summary.set_index("candidate_id")

    new_surnames = {}
    for cid in RENAME_TARGETS:
        row = by_id.loc[cid]
        first_name = row["full_name"].split(" ", 1)[0]
        current_surname = row["full_name"].split(" ", 1)[1]
        origin = row["name_origin"]
        pool = [s for s in config.SURNAMES[origin] if s != current_surname]

        rng = config.deterministic_rng("manual_rename_fix_v1", cid)
        shuffled = list(pool)
        rng.shuffle(shuffled)

        chosen = None
        for candidate_surname in shuffled:
            candidate_full_name = f"{first_name} {candidate_surname}"
            if candidate_full_name not in existing_full_names:
                chosen = candidate_surname
                break
        assert chosen is not None, f"no collision-free surname found for {cid}"

        new_full_name = f"{first_name} {chosen}"
        existing_full_names.add(new_full_name)  # so later picks avoid it too
        new_surnames[cid] = {
            "first_name": first_name,
            "old_surname": current_surname,
            "new_surname": chosen,
            "old_full_name": row["full_name"],
            "new_full_name": new_full_name,
            "name_origin": origin,
        }
    return new_surnames


def patch_brief_file(cid: str, rename: dict) -> None:
    num = candidate_num(cid)
    path = BRIEFS_DIR / f"brief_{num:03d}.json"
    brief = json.loads(path.read_text(encoding="utf-8"))
    assert brief["demographics_surface"]["full_name"] == rename["old_full_name"]
    brief["demographics_surface"]["full_name"] = rename["new_full_name"]
    path.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"{cid}: rewrote {path.name} full_name -> {rename['new_full_name']!r}")


def patch_batch_file(cid: str, rename: dict) -> None:
    bnum = batch_num_for(cid)
    path = BATCHES_DIR / f"batch_{bnum:02d}.json"
    batch = json.loads(path.read_text(encoding="utf-8"))
    touched = 0
    for brief in batch["briefs"]:
        if brief["candidate_id"] == cid:
            assert brief["demographics_surface"]["full_name"] == rename["old_full_name"]
            brief["demographics_surface"]["full_name"] = rename["new_full_name"]
            touched += 1
    assert touched == 1, f"expected exactly one brief for {cid} in {path.name}, found {touched}"
    path.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"{cid}: patched embedded copy in {path.name}")


def patch_answer_key_candidates(renames: dict, summary_path) -> None:
    summary = pd.read_csv(summary_path, keep_default_na=False)
    before_snapshot = summary.copy()
    for cid, rename in renames.items():
        mask = summary["candidate_id"] == cid
        assert mask.sum() == 1
        assert summary.loc[mask, "full_name"].iloc[0] == rename["old_full_name"]
        summary.loc[mask, "full_name"] = rename["new_full_name"]

    # Confirm every other row (and every other column of the touched rows)
    # is untouched before writing.
    diff_mask = (summary != before_snapshot).any(axis=1)
    changed_ids = set(summary.loc[diff_mask, "candidate_id"])
    assert changed_ids == set(renames.keys()), (
        f"expected only {set(renames.keys())} to change, got {changed_ids}")
    for cid in renames:
        row_before = before_snapshot.loc[before_snapshot["candidate_id"] == cid].iloc[0]
        row_after = summary.loc[summary["candidate_id"] == cid].iloc[0]
        non_name_cols = [c for c in summary.columns if c != "full_name"]
        assert (row_before[non_name_cols] == row_after[non_name_cols]).all(), (
            f"{cid}: a non-name column changed unexpectedly")

    summary.to_csv(summary_path, index=False)
    log(f"patched {len(renames)} rows in {summary_path.name}; "
        f"confirmed no other row/column changed")


def patch_c104_prose(rename: dict) -> None:
    """Surgical text patch of the already-written C104 prose in
    data/applications_raw/batch_13.json: replace the old full name, the
    bare surname, and the surname as it appears (lowercased) inside the
    invented email address, with the new name. Every other entry in the
    batch file is verified byte-identical before and after.
    """
    path = APPLICATIONS_RAW_DIR / "batch_13.json"
    if not path.exists():
        log(f"WARNING: {path} does not exist -- C104 prose was not yet "
            "written, nothing to patch")
        return

    raw_text_before = path.read_text(encoding="utf-8")
    batch = json.loads(raw_text_before)

    old_full = rename["old_full_name"]
    new_full = rename["new_full_name"]
    first_name = rename["first_name"]
    old_surname = rename["old_surname"]
    new_surname = rename["new_surname"]
    old_email_token = f"{first_name.lower()}.{old_surname.lower()}"
    new_email_token = f"{first_name.lower()}.{new_surname.lower()}"

    others_before = {item["candidate_id"]: json.dumps(item, sort_keys=True)
                      for item in batch if item["candidate_id"] != "C104"}

    patched_entry = None
    for item in batch:
        if item["candidate_id"] != "C104":
            continue
        patched_entry = item
        for field in ("cv_markdown", "cover_letter_markdown"):
            text = item[field]
            occurrences_before = len(re.findall(re.escape(old_surname), text, flags=re.IGNORECASE))
            # Order matters, to keep casing correct:
            #   1. exact "Emma Petrov" -> "Emma <NewSurname>" (CV header,
            #      letter signature)
            #   2. the lowercase "emma.petrov" email token specifically ->
            #      "emma.<newsurname>" (kept lowercase, since it's an email)
            #   3. any remaining title-case "Petrov" -> "<NewSurname>"
            #   4. any remaining lowercase "petrov" -> "<newsurname>"
            text = text.replace(old_full, new_full)
            text = text.replace(old_email_token, new_email_token)
            text = text.replace(old_surname, new_surname)
            text = text.replace(old_surname.lower(), new_surname.lower())
            item[field] = text
            occurrences_after = len(re.findall(re.escape(old_surname), text, flags=re.IGNORECASE))
            log(f"C104 {field}: replaced {occurrences_before} occurrence(s) "
                f"of {old_surname!r} (any case); {occurrences_after} remaining (expect 0)")

    assert patched_entry is not None, "C104 not found in batch_13.json"

    others_after = {item["candidate_id"]: json.dumps(item, sort_keys=True)
                     for item in batch if item["candidate_id"] != "C104"}
    assert others_before == others_after, (
        "a non-C104 entry in batch_13.json changed -- aborting write")
    assert len(others_before) == 7, f"expected 7 other entries, found {len(others_before)}"

    path.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"patched {path.name}: C104 prose updated, other 7 entries confirmed byte-identical")


def main() -> None:
    log("loading answer_key_candidates.csv")
    summary = pd.read_csv(config.ANSWER_KEY_CANDIDATES_PATH, keep_default_na=False)

    dup_counts = summary["full_name"].value_counts()
    duplicates = dup_counts[dup_counts > 1]
    log(f"duplicate full names found before fix: {len(duplicates)}")
    for name, n in duplicates.items():
        print(f"  {name}: {n}")

    renames = choose_new_surnames(summary)
    log("chosen renames:")
    for cid, r in renames.items():
        print(f"  {cid}: {r['old_full_name']!r} -> {r['new_full_name']!r}")

    for cid, rename in renames.items():
        patch_brief_file(cid, rename)
        patch_batch_file(cid, rename)

    patch_answer_key_candidates(renames, config.ANSWER_KEY_CANDIDATES_PATH)
    patch_c104_prose(renames["C104"])

    # Final corpus-wide uniqueness re-check.
    summary_after = pd.read_csv(config.ANSWER_KEY_CANDIDATES_PATH, keep_default_na=False)
    n_unique = summary_after["full_name"].nunique()
    log(f"full names after fix: {n_unique} unique of {len(summary_after)} "
        f"(expect {len(summary_after)})")
    assert n_unique == len(summary_after)

    log("done")


if __name__ == "__main__":
    main()
