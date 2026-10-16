"""Corpus step 1 — corpus preparation for Project 4 (Contract Clause
Extraction).

What this script does, in order:
  1. Verifies the CUAD zip archive against its recorded checksums.
  2. Builds an explicit filename map from every one of the 510 CSV rows to
     its plain-text contract file (three join methods, all recorded).
  3. Computes word counts and applies the eligibility rule (joinable,
     <= MAX_WORDS, not the spike contract).
  4. Draws a seeded, stratified 150-contract selection (50 stream + 100
     holdout) from the eligible pool.
  5. Copies the 150 texts and the clause-annotation CSV byte-verbatim into
     data/.
  6. Writes the licence/attribution file.
  7. Writes data/manifest.json (source checksums, per-file hashes, the full
     selection record).

Nothing here reads or writes clause spans or answers — this script only
ever touches master_clauses.csv's `Filename` column, for joining. That is a
deliberate scope boundary (rule 10, "answer-key
isolation"): the annotations themselves are handled exclusively by
derive_answer_key.py, downstream of this one. This file is on
validate_corpus.py's rule 10 whitelist, so it may name both plainly.

Run standalone: `python prepare_corpus.py`. Exits 0 on success, 1 on any
hard failure (never a silent skip).
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import random
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import config

CODE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CODE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
CONTRACTS_DIR = DATA_DIR / "contracts"

TXT_DIR = config.EXTRACTED / "full_contract_txt"


def fail(message: str) -> None:
    """Print an informative error and exit non-zero. Never a bare crash."""
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(1)


def announce(step: str) -> None:
    print(f"\n=== {step} ===")


# --------------------------------------------------------------------------
# Step 0/1 — cache presence and zip integrity
# --------------------------------------------------------------------------

def verify_cache_present() -> None:
    announce("Step 0: locating the CUAD cache")
    if not config.CACHE_DIR.exists():
        fail(
            f"CUAD cache not found at {config.CACHE_DIR}\n"
            f"This is a machine-local path (see config.py). Download from\n"
            f"  {config.ZIP_URL}\n"
            f"and extract it there, or recover the exact archive via the\n"
            f"checksums recorded in data/manifest.json from a prior run."
        )
    if not config.ZIP_PATH.exists():
        fail(f"CUAD zip not found at {config.ZIP_PATH}")
    if not config.EXTRACTED.exists():
        fail(f"Extracted CUAD folder not found at {config.EXTRACTED}")
    if not TXT_DIR.exists():
        fail(f"full_contract_txt folder not found under {config.EXTRACTED}")
    print(f"cache dir:  {config.CACHE_DIR}")
    print(f"extracted:  {config.EXTRACTED}")


def verify_zip_checksums() -> None:
    announce("Step 1: verifying the source zip against recorded checksums")
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with open(config.ZIP_PATH, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            md5.update(chunk)
            sha256.update(chunk)
    md5_hex, sha256_hex = md5.hexdigest(), sha256.hexdigest()
    if md5_hex != config.ZIP_MD5:
        fail(f"zip MD5 mismatch: computed {md5_hex}, expected {config.ZIP_MD5}")
    if sha256_hex != config.ZIP_SHA256:
        fail(f"zip SHA-256 mismatch: computed {sha256_hex}, expected {config.ZIP_SHA256}")
    print(f"MD5    OK  {md5_hex}")
    print(f"SHA-256 OK {sha256_hex}")


# --------------------------------------------------------------------------
# Step 2 — the filename map (CSV Filename column -> TXT file)
# --------------------------------------------------------------------------

_PDF_EXT_RE = re.compile(r"\.pdf['\"]?\s*$", re.IGNORECASE)


def _normalise_key(s: str) -> str:
    """Casefold, accent-stripped (NFKD, combining marks removed), then keep
    only alphanumerics. Unicode-form-agnostic: a filename typed with a
    precomposed accented letter and the same name spliced with a decomposed
    one normalise to the same key."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold()
    return re.sub(r"[^0-9a-z]+", "", s)


def build_filename_map(csv_rows: list[dict], txt_files: list[str]) -> dict[str, dict]:
    """Resolve every row's Filename (a PDF name) to exactly one TXT filename.
    Three methods, tried in order, every use recorded:
      (a) exact stem match after a plain .pdf/.PDF -> .txt swap
      (b) case-insensitive stem match
      (c) normalised match (accent/case/punctuation-insensitive), with a
          tolerant extension strip (a couple of CUAD's Filename values carry
          a stray trailing quote after ".PDF" — a CSV data wart, not a
          naming convention)
    Returns {csv_filename: {"txt_name": ..., "method": ...}}.
    Exits 1, listing every offender, if any row resolves to zero or more
    than one TXT file.
    """
    txt_exact = set(txt_files)
    casefold_map: dict[str, list[str]] = defaultdict(list)
    norm_map: dict[str, list[str]] = defaultdict(list)
    for t in txt_files:
        stem = t[:-4]  # strip ".txt"
        casefold_map[stem.casefold()].append(t)
        norm_map[_normalise_key(stem)].append(t)

    resolved: dict[str, dict] = {}
    failures: list[str] = []
    for row in csv_rows:
        fn = row["Filename"]
        stem = fn[:-4] if fn.lower().endswith(".pdf") else fn
        exact_candidate = stem + ".txt"
        if exact_candidate in txt_exact:
            resolved[fn] = {"txt_name": exact_candidate, "method": "exact"}
            continue

        ci_matches = casefold_map.get(stem.casefold(), [])
        if len(ci_matches) == 1:
            resolved[fn] = {"txt_name": ci_matches[0], "method": "case_insensitive"}
            continue
        if len(ci_matches) > 1:
            failures.append(f"AMBIGUOUS (case-insensitive): {fn!r} -> {ci_matches}")
            continue

        normalised_stem = _PDF_EXT_RE.sub("", fn)
        key = _normalise_key(normalised_stem)
        norm_matches = norm_map.get(key, [])
        if len(norm_matches) == 1:
            resolved[fn] = {"txt_name": norm_matches[0], "method": "normalised"}
            continue
        if len(norm_matches) > 1:
            failures.append(f"AMBIGUOUS (normalised): {fn!r} -> {norm_matches}")
            continue

        failures.append(f"UNMATCHED: {fn!r}")

    if failures:
        fail("filename join failed for the following rows:\n  " + "\n  ".join(failures))

    if len(set(e["txt_name"] for e in resolved.values())) != len(resolved):
        fail("filename join is not one-to-one: two or more CSV rows resolved to the same TXT file")

    return resolved


# --------------------------------------------------------------------------
# Step 3 — word counts, type inference, length bands, eligibility
# --------------------------------------------------------------------------

def infer_type(txt_filename: str) -> str:
    upper = txt_filename.upper()
    for pattern, label in config.TYPE_PATTERNS:
        if pattern in upper:
            return label
    return config.TYPE_FALLBACK


def length_band(word_count: int) -> tuple[int, int]:
    for lo, hi in config.LENGTH_BANDS:
        if lo <= word_count < hi:
            return (lo, hi)
    raise ValueError(f"word count {word_count} falls outside every configured length band")


def word_count_of(txt_name: str) -> int:
    path = TXT_DIR / txt_name
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        fail(f"could not decode {txt_name} as UTF-8: {exc}")
    except OSError as exc:
        fail(f"could not read {txt_name}: {exc}")
    return len(text.split())


# --------------------------------------------------------------------------
# Step 4 — stratified seeded draw
# --------------------------------------------------------------------------

def largest_remainder_quotas(strata: dict, total_quota: int, total_eligible: int) -> dict:
    """Per-stratum quotas proportional to stratum size, largest-remainder
    rounding, ties broken by ascending sorted stratum key."""
    raw, floor_q, remainder = {}, {}, {}
    for key, members in strata.items():
        r = total_quota * len(members) / total_eligible
        raw[key] = r
        floor_q[key] = int(r)
        remainder[key] = r - floor_q[key]

    assigned = sum(floor_q.values())
    still_needed = total_quota - assigned
    priority_order = sorted(strata.keys(), key=lambda k: (-remainder[k], k))

    quota = dict(floor_q)
    for key in priority_order[:still_needed]:
        quota[key] += 1

    assert sum(quota.values()) == total_quota, "largest-remainder rounding did not reach the total"
    return quota, raw


def stratified_draw(eligible: list[dict]) -> tuple[list[dict], list[dict], dict, dict]:
    """Deterministic procedure (step 4).
    Returns (stream, holdout, quota_by_stratum, raw_quota_by_stratum)."""
    eligible_sorted = sorted(eligible, key=lambda c: c["txt_name"])

    strata: dict[tuple, list[dict]] = defaultdict(list)
    for c in eligible_sorted:
        key = (c["type"], f"{c['band'][0]}-{c['band'][1]}")
        strata[key].append(c)

    total_quota = config.STREAM_SIZE + config.HOLDOUT_SIZE
    quota, raw_quota = largest_remainder_quotas(strata, total_quota, len(eligible_sorted))

    rng = random.Random(config.RANDOM_SEED)
    selected_pool: list[dict] = []
    for key in sorted(strata.keys()):
        members = strata[key]  # already sorted by txt_name
        q = quota[key]
        selected_pool.extend(rng.sample(members, q))

    pool_sorted = sorted(selected_pool, key=lambda c: c["txt_name"])
    shuffled = pool_sorted[:]
    rng.shuffle(shuffled)

    stream = shuffled[: config.STREAM_SIZE]
    holdout_unsorted = shuffled[config.STREAM_SIZE :]
    holdout = sorted(holdout_unsorted, key=lambda c: c["txt_name"])

    return stream, holdout, quota, raw_quota


# --------------------------------------------------------------------------
# Step 5/6/7 — write outputs
# --------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_selected_contracts(selected: list[dict]) -> dict[str, str]:
    """Byte-verbatim copy of every selected TXT into data/contracts/.
    Returns {relative_path: sha256}."""
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for c in sorted(selected, key=lambda x: x["txt_name"]):
        src = TXT_DIR / c["txt_name"]
        dst = CONTRACTS_DIR / c["txt_name"]
        shutil.copyfile(src, dst)  # byte-for-byte, no text re-encoding
        hashes[f"contracts/{c['txt_name']}"] = sha256_of(dst)
    return hashes


def copy_csv(csv_source: Path) -> tuple[Path, str]:
    dest = DATA_DIR / csv_source.name
    shutil.copyfile(csv_source, dest)
    return dest, sha256_of(dest)


def write_licence_file() -> Path:
    """Writes the CC BY 4.0 attribution file. This script is on
    validate_corpus.py's rule 10 whitelist, so the derived-file paths below
    are named plainly."""
    licence_path = DATA_DIR / "CUAD_LICENCE_ATTRIBUTION.md"
    text = """# Licence and attribution — CUAD v1

This project's contract corpus, and the clause annotations it is derived
from, come from the **Contract Understanding Atticus Dataset (CUAD) v1**,
© The Atticus Project, Inc.

## Licence

Quoted verbatim from the in-archive `CUAD_v1_README.txt`:

> CUAD is licensed under the Creative Commons Attribution 4.0 (CC BY 4.0)
> license and free to the public for commercial and non-commercial use.

Licence deed: <https://creativecommons.org/licenses/by/4.0/>

## Required citation

Hendrycks, D., Burns, C., Chen, A., & Ball, S. (2021). CUAD: An
Expert-Annotated NLP Dataset for Legal Contract Review. *NeurIPS 2021
Datasets and Benchmarks Track*. arXiv:2103.06268.

## Derived files in this project

This project's derived files (`data/answer_key/`, `data/manifest.json`)
are adaptations of CUAD's `master_clauses.csv` under the same licence.

## Scope note

CUAD's own README states plainly: "We make no representations or
warranties regarding the license status of the underlying contracts, which
are publicly available and downloadable from EDGAR." Nothing in this
project is legal advice.
"""
    licence_path.write_text(text, encoding="utf-8")
    return licence_path


def write_manifest(*, eligible_count: int, total_corpus: int, strata_table: list[dict],
                    stream: list[dict], holdout: list[dict], file_hashes: dict[str, str],
                    csv_relative_name: str) -> Path:
    manifest = {
        "source": {
            "zip_url": config.ZIP_URL,
            "zip_md5": config.ZIP_MD5,
            "zip_sha256": config.ZIP_SHA256,
        },
        "file_sha256": dict(sorted(file_hashes.items())),
        "selection": {
            "total_corpus": total_corpus,
            "eligible_count": eligible_count,
            "max_words": config.MAX_WORDS,
            "spike_contract": config.SPIKE_CONTRACT,
            "stream_size": config.STREAM_SIZE,
            "holdout_size": config.HOLDOUT_SIZE,
            "random_seed": config.RANDOM_SEED,
            "csv_filename": csv_relative_name,
            "strata": strata_table,
            "stream": stream,
            "holdout": holdout,
        },
        "versions": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "generated_utc": None,
    }
    manifest_path = DATA_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    # House rule: never write where we read from.
    assert DATA_DIR.resolve() != config.CACHE_DIR.resolve()
    assert DATA_DIR.resolve() != config.EXTRACTED.resolve()

    verify_cache_present()
    verify_zip_checksums()

    announce("Step 2: building the filename map (510 CSV rows -> TXT files)")
    csv_source = config.EXTRACTED / "master_clauses.csv"
    if not csv_source.exists():
        fail(f"master_clauses.csv not found at {csv_source}")

    with open(csv_source, encoding="utf-8", newline="") as fh:
        csv_rows = list(csv.DictReader(fh))
    total_corpus = len(csv_rows)
    print(f"CSV rows: {total_corpus}")

    txt_files = sorted(p.name for p in TXT_DIR.glob("*.txt"))
    print(f"TXT files available: {len(txt_files)}")

    filename_map = build_filename_map(csv_rows, txt_files)
    non_exact = sorted(
        (fn, info["method"], info["txt_name"])
        for fn, info in filename_map.items()
        if info["method"] != "exact"
    )
    print(f"All {total_corpus} rows joined cleanly (0 ambiguous, 0 unmatched).")
    print(f"Rows needing a non-exact join method: {len(non_exact)}")
    for fn, method, txt_name in non_exact:
        print(f"  [{method}] {fn!r} -> {txt_name!r}")

    announce("Step 3: word counts and eligibility")
    contracts_by_row: list[dict] = []
    for row in csv_rows:
        fn = row["Filename"]
        txt_name = filename_map[fn]["txt_name"]
        wc = word_count_of(txt_name)
        contracts_by_row.append({
            "pdf_filename": fn,
            "txt_name": txt_name,
            "word_count": wc,
            "join_method": filename_map[fn]["method"],
        })

    eligible = []
    for c in contracts_by_row:
        is_spike = c["txt_name"] == config.SPIKE_CONTRACT
        if c["word_count"] <= config.MAX_WORDS and not is_spike:
            band = length_band(c["word_count"])
            eligible.append({**c, "type": infer_type(c["txt_name"]), "band": band})

    print(f"Eligible (<= {config.MAX_WORDS} words, joined, non-spike): {len(eligible)} / {total_corpus}")

    announce("Step 4: stratified seeded draw (150 = 50 stream + 100 holdout)")
    stream, holdout, quota, raw_quota = stratified_draw(eligible)
    print(f"Strata observed: {len(quota)}")
    print(f"Stream: {len(stream)}   Holdout: {len(holdout)}   "
          f"Disjoint: {not (set(c['txt_name'] for c in stream) & set(c['txt_name'] for c in holdout))}")

    strata_table = []
    for key in sorted(quota.keys()):
        type_label, band_label = key
        lo, hi = (int(x) for x in band_label.split("-"))
        size = sum(1 for c in eligible if c["type"] == type_label and c["band"] == (lo, hi))
        strata_table.append({
            "type": type_label,
            "band": [lo, hi],
            "size": size,
            "raw_quota": round(raw_quota[key], 6),
            "quota": quota[key],
        })

    def record(c: dict) -> dict:
        return {
            "contract": c["txt_name"],
            "source_row": c["pdf_filename"],
            "word_count": c["word_count"],
            "type": c["type"],
            "band": list(c["band"]),
            "join_method": c["join_method"],
        }

    stream_records = [record(c) for c in stream]
    holdout_records = [record(c) for c in holdout]

    announce("Step 5: copying selected files verbatim into data/")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_hashes = copy_selected_contracts(stream + holdout)
    csv_dest, csv_hash = copy_csv(csv_source)
    file_hashes[csv_dest.name] = csv_hash
    print(f"Copied {len(stream) + len(holdout)} contract texts to {CONTRACTS_DIR}")
    print(f"Copied {csv_source.name} to {csv_dest}")

    announce("Step 6: writing the licence/attribution file")
    licence_path = write_licence_file()
    print(f"Wrote {licence_path}")

    announce("Step 7: writing the manifest")
    manifest_path = write_manifest(
        eligible_count=len(eligible),
        total_corpus=total_corpus,
        strata_table=strata_table,
        stream=stream_records,
        holdout=holdout_records,
        file_hashes=file_hashes,
        csv_relative_name=csv_dest.name,
    )
    print(f"Wrote {manifest_path}")

    announce("Summary")
    print(f"Total corpus rows:     {total_corpus}")
    print(f"Eligible:              {len(eligible)}")
    print(f"Non-exact joins:       {len(non_exact)}")
    print(f"Stream / Holdout:      {len(stream)} / {len(holdout)}")
    print(f"Strata:                {len(quota)}")
    print("prepare_corpus.py completed successfully.")


if __name__ == "__main__":
    # Windows consoles may be cp1252; corpus filenames contain combining
    # marks (LECLANCHÉ). Keep reporting robust without changing file writes.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
