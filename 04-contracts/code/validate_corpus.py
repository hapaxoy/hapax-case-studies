"""Corpus step 3 — corpus/key validation for Project 4 (Contract Clause
Extraction): the ten coherence rules. Every rule is a hard requirement:
a dataset that fails validation is a bug, not a judgment call.

Each `check_rule_N_<slug>()` function prints PASS/FAIL plus detail and
returns a bool. `main()` runs all ten and exits 1 if any fail.

Run standalone: `python validate_corpus.py` (needs prepare_corpus.py and
derive_answer_key.py already run).
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import config
import schemas
import derive_answer_key

CODE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CODE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
CONTRACTS_DIR = DATA_DIR / "contracts"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"
MANIFEST_PATH = DATA_DIR / "manifest.json"
LICENCE_PATH = DATA_DIR / "CUAD_LICENCE_ATTRIBUTION.md"
# Rule 9's re-derivation scratch lives in the SYSTEM temp dir, never inside
# the project tree: file locks can defeat cleanup and leave stray
# artefacts in data/ (observed 3 Jul 2026 — one leftover file survived an
# ignore_errors rmtree).


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def load_answer_key_records() -> dict[str, dict]:
    """contract txt filename -> derived record, read back from disk."""
    records = {}
    for path in sorted(ANSWER_KEY_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        records[rec["contract"]] = rec
    return records


def report(rule_label: str, ok: bool, detail_lines: list[str]) -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {rule_label}")
    for line in detail_lines:
        print(f"    {line}")
    return ok


# --------------------------------------------------------------------------
# Rule 1 — manifest integrity
# --------------------------------------------------------------------------

def check_rule_1_manifest_integrity() -> bool:
    detail = []
    ok = True

    if not MANIFEST_PATH.exists():
        return report("rule_1_manifest_integrity", False, [f"{MANIFEST_PATH} missing"])
    manifest = load_manifest()

    if manifest["source"]["zip_md5"] != config.ZIP_MD5:
        ok = False
        detail.append(f"manifest zip_md5 {manifest['source']['zip_md5']} != config {config.ZIP_MD5}")
    if manifest["source"]["zip_sha256"] != config.ZIP_SHA256:
        ok = False
        detail.append(f"manifest zip_sha256 mismatch against config")

    recorded = manifest["file_sha256"]
    checked = 0
    for rel_path, expected_hash in recorded.items():
        actual_path = DATA_DIR / rel_path
        if not actual_path.exists():
            ok = False
            detail.append(f"missing file recorded in manifest: {rel_path}")
            continue
        actual_hash = sha256_of(actual_path)
        if actual_hash != expected_hash:
            ok = False
            detail.append(f"hash mismatch: {rel_path} manifest={expected_hash} actual={actual_hash}")
        checked += 1
    detail.append(f"checked {checked}/{len(recorded)} recorded files")

    # every contract file on disk must also be recorded (no untracked extras)
    on_disk = {f"contracts/{p.name}" for p in CONTRACTS_DIR.glob("*.txt")}
    untracked = on_disk - set(recorded.keys())
    if untracked:
        ok = False
        detail.append(f"{len(untracked)} contract file(s) on disk but not in manifest: {sorted(untracked)[:5]}")

    # no stray files/dirs anywhere under data/ (added 3 Jul 2026 after a
    # file-locked temp dir survived cleanup). Atomic-write artefacts
    # (*.tmp.NNNN.xxxx) are transient sync debris, not content — reported
    # for awareness but not failed.
    # data/runs/ is the pipeline's run-artefact tree (session data, free-form
    # contents documented in the README's regenerate-vs-artefact split) —
    # exempt from the strays check, like the two content dirs.
    expected_dirs = {"contracts", "answer_key", "runs"}
    expected_root_files = {"manifest.json", "master_clauses.csv",
                           "CUAD_LICENCE_ATTRIBUTION.md"}
    sync_tmp = re.compile(r"\.tmp\.\d+\.[0-9a-f]+$", re.IGNORECASE)
    strays, sync_debris = [], []
    for p in DATA_DIR.rglob("*"):
        rel = p.relative_to(DATA_DIR)
        top = rel.parts[0]
        if sync_tmp.search(p.name):
            sync_debris.append(str(rel))
            continue
        if top == "runs":
            continue  # free-form session-artefact tree, exempt
        if p.is_dir():
            if top not in expected_dirs:
                strays.append(str(rel) + "/")
        elif top in expected_dirs:
            if len(rel.parts) != 2 or p.suffix not in (".txt", ".json"):
                strays.append(str(rel))
        elif str(rel) not in expected_root_files:
            strays.append(str(rel))
    if strays:
        ok = False
        detail.append(f"stray entries under data/: {sorted(strays)[:10]}")
    if sync_debris:
        detail.append(f"(transient sync artefacts, ignored: {len(sync_debris)})")

    return report("rule_1_manifest_integrity", ok, detail)


# --------------------------------------------------------------------------
# Rule 2 — join completeness
# --------------------------------------------------------------------------

def check_rule_2_join_completeness() -> bool:
    detail = []
    ok = True
    manifest = load_manifest()
    selection = manifest["selection"]
    all_entries = selection["stream"] + selection["holdout"]

    source_rows_seen = set()
    contracts_seen = set()
    for entry in all_entries:
        contract = entry.get("contract")
        source_row = entry.get("source_row")
        method = entry.get("join_method")
        if not contract or not source_row or not method:
            ok = False
            detail.append(f"incomplete map entry: {entry}")
            continue
        if method not in ("exact", "case_insensitive", "normalised"):
            ok = False
            detail.append(f"unrecognised join method {method!r} for {contract}")
        if contract in contracts_seen:
            ok = False
            detail.append(f"duplicate contract in selection: {contract}")
        contracts_seen.add(contract)
        if source_row in source_rows_seen:
            ok = False
            detail.append(f"duplicate source_row (ambiguous join) in selection: {source_row}")
        source_rows_seen.add(source_row)

    detail.append(f"{len(all_entries)} selected map entries; "
                   f"{len(contracts_seen)} unique contracts; {len(source_rows_seen)} unique source rows")
    non_exact = [e for e in all_entries if e.get("join_method") != "exact"]
    detail.append(f"non-exact joins in selection: {len(non_exact)}")

    return report("rule_2_join_completeness", ok, detail)


# --------------------------------------------------------------------------
# Rule 3 — key parseability
# --------------------------------------------------------------------------

def check_rule_3_key_parseability() -> bool:
    detail = []
    ok = True
    manifest = load_manifest()
    csv_filename = manifest["selection"]["csv_filename"]
    csv_path = DATA_DIR / csv_filename
    with open(csv_path, encoding="utf-8", newline="") as fh:
        rows_by_filename = {row["Filename"]: row for row in csv.DictReader(fh)}

    all_entries = manifest["selection"]["stream"] + manifest["selection"]["holdout"]
    parse_failures = 0
    bad_yesno = 0
    checked_columns = 0
    for entry in all_entries:
        source_row = entry["source_row"]
        row = rows_by_filename.get(source_row)
        if row is None:
            ok = False
            detail.append(f"selected source_row not found in CSV: {source_row}")
            continue
        for cat in schemas.CATEGORIES:
            csv_col = cat["csv"]
            answer_col = f"{csv_col}-Answer"
            checked_columns += 2
            raw_spans = row.get(csv_col, "")
            if raw_spans.strip():
                try:
                    value = ast.literal_eval(raw_spans)
                    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                        raise ValueError("not a list of strings")
                except (ValueError, SyntaxError) as exc:
                    ok = False
                    parse_failures += 1
                    detail.append(f"unparseable clause column: {source_row} / {csv_col}: {exc}")
            if cat["kind"] == "yesno":
                ans = (row.get(answer_col, "") or "").strip().casefold()
                if ans not in ("yes", "no", ""):
                    ok = False
                    bad_yesno += 1
                    detail.append(f"yes/no answer not in {{Yes,No,''}}: {source_row} / {answer_col} = {row.get(answer_col)!r}")

    detail.append(f"checked {checked_columns} column-instances across {len(all_entries)} rows "
                  f"(24 columns x 150 rows expected = {24 * 150})")
    detail.append(f"parse failures: {parse_failures}   bad yes/no values: {bad_yesno}")
    return report("rule_3_key_parseability", ok, detail)


# --------------------------------------------------------------------------
# Rule 4 — answer well-formedness
# --------------------------------------------------------------------------

DATE_CATEGORIES = ("Agreement Date", "Expiration Date")
EXTRACTION_CATEGORIES = [c["name"] for c in schemas.CATEGORIES if c["kind"] == "extraction"]


def check_rule_4_answer_wellformedness() -> bool:
    detail = []
    ok = True
    records = load_answer_key_records()

    kind_counts: dict[str, dict[str, int]] = {name: defaultdict(int) for name in DATE_CATEGORIES}
    blank_present_counts: dict[str, int] = defaultdict(int)
    redacted_count = 0
    structural_failures = 0

    for contract, rec in records.items():
        for name in EXTRACTION_CATEGORIES:
            entry = rec["categories"][name]
            if not entry["present"]:
                continue  # absent categories carry no requirement
            answer = entry["answer"]
            # Hard structural requirement: a present extraction category
            # must carry a string answer (never None) — this would be a
            # derivation bug, not a CUAD data quirk.
            if not isinstance(answer, str):
                ok = False
                structural_failures += 1
                detail.append(f"{contract} / {name}: present but answer is not a string ({answer!r})")
                continue
            if name in DATE_CATEGORIES:
                kind, _ = schemas.parse_date_answer(answer)
                kind_counts[name][kind] += 1
                if kind == "redacted":
                    redacted_count += 1
                if kind == "empty":
                    # Present via a non-empty span but a blank normalised
                    # answer — a real, expected CUAD data pattern
                    # (documented for Expiration Date in particular: the
                    # pre-registered "answer computed" trap category — the
                    # annotators sometimes recorded the descriptive span
                    # without computing the resulting calendar date).
                    # Counted, not failed.
                    blank_present_counts[name] += 1
            else:
                if not answer.strip():
                    blank_present_counts[name] += 1

    detail.append(f"structural failures (present with non-string answer): {structural_failures}")
    detail.append(f"redacted date answers: {redacted_count}")
    for name in DATE_CATEGORIES:
        counts = dict(kind_counts[name])
        detail.append(f"{name} date-kind counts: {counts}")
    if blank_present_counts:
        detail.append("present-but-blank-answer counts (informational, not a failure — see comment): "
                      + ", ".join(f"{k}={v}" for k, v in sorted(blank_present_counts.items())))
    else:
        detail.append("present-but-blank-answer counts: none")

    return report("rule_4_answer_wellformedness", ok, detail)


# --------------------------------------------------------------------------
# Rule 5 — span presence
# --------------------------------------------------------------------------

def check_rule_5_span_presence() -> bool:
    detail = []
    ok = True
    records = load_answer_key_records()

    total_segments = 0
    total_unfound = 0
    per_contract_fraction: dict[str, float] = {}

    for contract, rec in records.items():
        contract_path = CONTRACTS_DIR / contract
        if not contract_path.exists():
            ok = False
            detail.append(f"missing contract text for span check: {contract}")
            continue
        text_norm = schemas.norm_ws(contract_path.read_text(encoding="utf-8"))

        contract_segments = 0
        contract_unfound = 0
        for cat in schemas.CATEGORIES:
            entry = rec["categories"][cat["name"]]
            for span in entry["spans"]:
                for segment in schemas.span_segments(span):
                    contract_segments += 1
                    if not schemas.segment_in_text(segment, text_norm):
                        contract_unfound += 1

        total_segments += contract_segments
        total_unfound += contract_unfound
        per_contract_fraction[contract] = (contract_unfound / contract_segments) if contract_segments else 0.0

    over_threshold = {c: f for c, f in per_contract_fraction.items() if f > 0.10}
    if over_threshold:
        ok = False

    worst = sorted(per_contract_fraction.items(), key=lambda kv: -kv[1])[:10]
    detail.append(f"total segments: {total_segments}   unfound: {total_unfound}   "
                  f"overall unfound rate: {(total_unfound / total_segments if total_segments else 0):.4f}")
    detail.append(f"contracts over the 10% unfound threshold: {len(over_threshold)}")
    detail.append("worst offenders (contract: unfound fraction):")
    for contract, frac in worst:
        if frac > 0:
            detail.append(f"  {frac:.3f}  {contract}")

    return report("rule_5_span_presence", ok, detail)


# --------------------------------------------------------------------------
# Rule 6 — split discipline
# --------------------------------------------------------------------------

def check_rule_6_split_discipline() -> bool:
    detail = []
    ok = True
    manifest = load_manifest()
    selection = manifest["selection"]
    stream = selection["stream"]
    holdout = selection["holdout"]

    stream_names = [e["contract"] for e in stream]
    holdout_names = [e["contract"] for e in holdout]

    if len(stream_names) != config.STREAM_SIZE:
        ok = False
        detail.append(f"stream size {len(stream_names)} != {config.STREAM_SIZE}")
    if len(holdout_names) != config.HOLDOUT_SIZE:
        ok = False
        detail.append(f"holdout size {len(holdout_names)} != {config.HOLDOUT_SIZE}")
    if len(set(stream_names)) != len(stream_names):
        ok = False
        detail.append("stream contains duplicate contracts")
    if len(set(holdout_names)) != len(holdout_names):
        ok = False
        detail.append("holdout contains duplicate contracts")

    overlap = set(stream_names) & set(holdout_names)
    if overlap:
        ok = False
        detail.append(f"stream/holdout overlap: {sorted(overlap)}")

    for entry in stream + holdout:
        if entry["word_count"] > config.MAX_WORDS:
            ok = False
            detail.append(f"{entry['contract']} exceeds MAX_WORDS ({entry['word_count']} > {config.MAX_WORDS})")
        if entry["contract"] == config.SPIKE_CONTRACT:
            ok = False
            detail.append(f"spike contract present in selection: {entry['contract']}")

    if not stream_names:
        ok = False
        detail.append("stream order is empty")

    detail.append(f"stream={len(stream_names)} holdout={len(holdout_names)} "
                  f"overlap={len(overlap)} spike_excluded={config.SPIKE_CONTRACT not in stream_names + holdout_names}")

    return report("rule_6_split_discipline", ok, detail)


# --------------------------------------------------------------------------
# Rule 7 — prevalence sanity
# --------------------------------------------------------------------------

def _full_corpus_presence_rate(csv_path: Path) -> dict[str, float]:
    """p_full per category, computed over ALL rows of the clause-annotation
    CSV using the exact same present-derivation rules as
    derive_answer_key.py (reused directly, not re-implemented), so this is
    an apples-to-apples comparison against the 150-selection presence
    counts — not against the corpus design's descriptive prevalence figures, which
    counts extraction-category presence by non-blank answer only. Here,
    presence also counts a category with a non-empty
    span but a blank normalised answer (real for Expiration Date
    especially) — so p_full is measurably higher than that table for
    the date categories. That is expected, not a bug; see rule 4.
    """
    with open(csv_path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    presence_count = defaultdict(int)
    for row in rows:
        for cat in schemas.CATEGORIES:
            name = cat["name"]
            csv_col = cat["csv"]
            answer_col = f"{csv_col}-Answer"
            spans = derive_answer_key.parse_span_list(row.get(csv_col, ""), source_row=row["Filename"], column=csv_col)
            answer_raw = row.get(answer_col, "")
            if cat["kind"] == "yesno":
                entry = derive_answer_key.derive_yesno_entry(spans, answer_raw)
            else:
                entry = derive_answer_key.derive_extraction_entry(spans, answer_raw)
            if entry["present"]:
                presence_count[name] += 1
    return {cat["name"]: presence_count[cat["name"]] / len(rows) for cat in schemas.CATEGORIES}


def check_rule_7_prevalence_sanity() -> bool:
    detail = []
    ok = True
    manifest = load_manifest()
    csv_filename = manifest["selection"]["csv_filename"]
    p_full = _full_corpus_presence_rate(DATA_DIR / csv_filename)

    records = load_answer_key_records()
    n_selected = len(records)
    k_observed = defaultdict(int)
    for rec in records.values():
        for name, entry in rec["categories"].items():
            if entry["present"]:
                k_observed[name] += 1

    for cat in schemas.CATEGORIES:
        name = cat["name"]
        p = p_full[name]
        k = k_observed[name]
        expected = n_selected * p
        bound = 2.576 * math.sqrt(n_selected * p * (1 - p)) + 1  # +1 slack
        within = abs(k - expected) <= bound
        if not within:
            ok = False
        detail.append(f"{name:28s} p_full={p:.4f} expected={expected:6.2f} observed={k:4d} "
                      f"bound=+/-{bound:5.2f} {'OK' if within else 'OUT OF BOUNDS'}")

    return report("rule_7_prevalence_sanity", ok, detail)


# --------------------------------------------------------------------------
# Rule 8 — licence presence
# --------------------------------------------------------------------------

def check_rule_8_licence_presence() -> bool:
    detail = []
    ok = True
    if not LICENCE_PATH.exists():
        return report("rule_8_licence_presence", False, [f"{LICENCE_PATH} missing"])
    text = LICENCE_PATH.read_text(encoding="utf-8")
    for required in ("CC BY 4.0", "Atticus", "2103.06268"):
        if required not in text:
            ok = False
            detail.append(f"required string not found: {required!r}")
    detail.append(f"licence file: {LICENCE_PATH}")
    return report("rule_8_licence_presence", ok, detail)


# --------------------------------------------------------------------------
# Rule 9 — derivation determinism
# --------------------------------------------------------------------------

def check_rule_9_derivation_determinism() -> bool:
    detail = []
    ok = True
    tmp_dir = Path(tempfile.mkdtemp(prefix="hapax04_validate_"))
    try:
        manifest = derive_answer_key.load_manifest()
        csv_filename = manifest["selection"]["csv_filename"]
        csv_rows = derive_answer_key.load_master_clauses_rows(DATA_DIR / csv_filename)
        derive_answer_key.derive_all(tmp_dir, manifest=manifest, csv_rows_by_filename=csv_rows)

        live_files = sorted(p.name for p in ANSWER_KEY_DIR.glob("*.json"))
        tmp_files = sorted(p.name for p in tmp_dir.glob("*.json"))
        if live_files != tmp_files:
            ok = False
            detail.append(f"file set differs: live has {len(live_files)}, re-run has {len(tmp_files)}")

        diffs = 0
        for name in live_files:
            live_bytes = (ANSWER_KEY_DIR / name).read_bytes()
            tmp_bytes = (tmp_dir / name).read_bytes()
            if live_bytes != tmp_bytes:
                diffs += 1
                ok = False
                detail.append(f"byte diff: {name}")
        detail.append(f"compared {len(live_files)} records; byte-identical diffs: {diffs}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return report("rule_9_derivation_determinism", ok, detail)


# --------------------------------------------------------------------------
# Rule 10 — answer-key isolation
# --------------------------------------------------------------------------

# Explicit whitelist, hardcoded (never globbed/derived): the first six scripts
# are the only places the annotations legitimately exist. Everything else
# under code/ — present or future (code/matchers_generated/**, router.py,
# regression_gate.py, any batch tooling) — is pipeline-facing and must stay
# clean; that split is the rule's real target: pipeline-facing code never
# touches the key. verify_interactive.py is a scanner, not a
# reader — like this file, it names the forbidden strings only to police
# the interactive page for them; it opens neither the key nor the CSV.
EXEMPT_FILES = (
    "prepare_corpus.py",
    "derive_answer_key.py",
    "validate_corpus.py",
    "evaluate.py",
    "schemas.py",
    "test_schemas.py",
    "verify_interactive.py",
)
FORBIDDEN_STRINGS = ["answer_key", "master_clauses"]


def check_rule_10_answer_key_isolation() -> bool:
    detail = []
    ok = True

    # Guard the whitelist itself: it must be exactly the seven named files,
    # not a count that silently drifted (e.g. a future edit deleting one).
    # (Six originally; widened to seven for verify_interactive.py, the
    # second scanner.)
    if len(EXEMPT_FILES) != 7 or len(set(EXEMPT_FILES)) != 7:
        ok = False
        detail.append(f"whitelist must hardcode exactly seven distinct filenames, found: {EXEMPT_FILES!r}")

    violations = []
    for py_file in sorted(CODE_DIR.rglob("*.py")):
        if py_file.name in EXEMPT_FILES:
            continue
        text = py_file.read_text(encoding="utf-8", errors="replace")
        for term in FORBIDDEN_STRINGS:
            if term in text:
                violations.append((py_file.relative_to(CODE_DIR), term))

    if violations:
        ok = False
        for f, term in violations:
            detail.append(f"{f} contains forbidden string {term!r}")

    present_on_disk = [f for f in EXEMPT_FILES if (CODE_DIR / f).exists()]
    scanned = [str(p.relative_to(CODE_DIR)) for p in CODE_DIR.rglob("*.py") if p.name not in EXEMPT_FILES]
    detail.append(f"whitelist (hardcoded, {len(EXEMPT_FILES)} names): {list(EXEMPT_FILES)}")
    detail.append(f"whitelisted files present on disk now: {present_on_disk} "
                  f"({len(EXEMPT_FILES) - len(present_on_disk)} not yet written, e.g. evaluate.py before Phase 3)")
    detail.append(f"scanned {len(scanned)} non-whitelisted .py file(s): {scanned}")

    return report("rule_10_answer_key_isolation", ok, detail)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    checks = [
        check_rule_1_manifest_integrity,
        check_rule_2_join_completeness,
        check_rule_3_key_parseability,
        check_rule_4_answer_wellformedness,
        check_rule_5_span_presence,
        check_rule_6_split_discipline,
        check_rule_7_prevalence_sanity,
        check_rule_8_licence_presence,
        check_rule_9_derivation_determinism,
        check_rule_10_answer_key_isolation,
    ]

    print("=== validate_corpus.py: running all 10 coherence rules ===\n")
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as exc:  # a check itself must never crash silently
            print(f"FAIL  {check.__name__} raised an exception: {exc}")
            results.append(False)
        print()

    passed = sum(results)
    print(f"=== Summary: {passed}/{len(results)} rules passed ===")
    if not all(results):
        print("VALIDATION FAILED", file=sys.stderr)
        sys.exit(1)
    print("All rules passed.")


if __name__ == "__main__":
    # cp1252 console guard (corpus filenames contain combining marks)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
