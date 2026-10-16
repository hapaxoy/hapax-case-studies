"""Shared helpers for the pipeline tooling (Project 4, Contract
Clause Extraction).

Answer-key isolation (validate_corpus.py rule
10): this file is a pipeline-facing helper module and is NOT on the rule 10
whitelist. It must never reference the derived key or its CSV source by
name — every path here is contracts, runs, matchers, or the manifest.

All state-carrying functions take an explicit `paths` argument (a `Paths`
instance) rather than reading module-level globals, so tests can point the
whole pipeline at a temporary directory without touching the real project
tree. CLI scripts call `default_paths()` once and thread it through.
"""

from __future__ import annotations

import importlib.util
import json
import random
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import config
import schemas

# cp1252 console guard, applied once for every pipeline entry script that
# imports this module: corpus filenames contain combining marks (LECLANCHÉ,
# selected in the corpus) and Windows consoles may be cp1252 — a bare print
# of a filename must degrade, never crash a batch mid-run. errors="replace"
# affects console rendering only, never file contents.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass  # closed/odd stream (e.g. under some test runners)

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Paths:
    project_dir: Path
    code_dir: Path
    data_dir: Path
    contracts_dir: Path
    manifest_path: Path
    runs_dir: Path
    batches_dir: Path
    llm_extractions_dir: Path
    matcher_outputs_dir: Path
    matcher_outputs_holdout_dir: Path
    commissions_dir: Path
    gate_results_dir: Path
    matchers_generated_dir: Path
    matcher_state_path: Path
    shadow_answers_path: Path
    stream_events_path: Path
    evaluation_path: Path
    evaluation_worksheet_path: Path
    extract_agent_log_path: Path
    holdout_coverage_path: Path


def build_paths(project_dir: Path) -> Paths:
    """Construct a full `Paths` instance from a project root. Real runs pass
    the actual project directory (via `default_paths()`); tests pass a
    temporary directory so nothing under real `data/` is ever touched."""
    project_dir = project_dir.resolve()
    code_dir = project_dir / "code"
    data_dir = project_dir / "data"
    runs_dir = data_dir / "runs"
    return Paths(
        project_dir=project_dir,
        code_dir=code_dir,
        data_dir=data_dir,
        contracts_dir=data_dir / "contracts",
        manifest_path=data_dir / "manifest.json",
        runs_dir=runs_dir,
        batches_dir=runs_dir / "batches",
        llm_extractions_dir=runs_dir / "llm_extractions",
        matcher_outputs_dir=runs_dir / "matcher_outputs",
        matcher_outputs_holdout_dir=runs_dir / "matcher_outputs_holdout",
        commissions_dir=runs_dir / "commissions",
        gate_results_dir=runs_dir / "gate_results",
        matchers_generated_dir=code_dir / "matchers_generated",
        matcher_state_path=runs_dir / "matcher_state.json",
        shadow_answers_path=runs_dir / "shadow_answers.json",
        stream_events_path=runs_dir / "stream_events.json",
        evaluation_path=runs_dir / "evaluation.json",
        evaluation_worksheet_path=runs_dir / "evaluation_worksheet.md",
        extract_agent_log_path=runs_dir / "extract_agent_log.json",
        holdout_coverage_path=runs_dir / "holdout_coverage.json",
    )


def default_paths() -> Paths:
    """The real project tree, resolved relative to this file (house rule:
    scripts use pathlib paths relative to their own location, never
    hardcoded absolutes)."""
    code_dir = Path(__file__).resolve().parent
    return build_paths(code_dir.parent)


def assert_safe_output_paths(paths: Paths) -> None:
    """House rule: never write where inputs are read from. Every script
    that writes under `runs_dir` calls this once at the top of main()."""
    assert paths.runs_dir.resolve() != paths.contracts_dir.resolve()
    assert paths.runs_dir.resolve() != paths.data_dir.resolve()
    assert paths.matchers_generated_dir.resolve() != paths.contracts_dir.resolve()


# --------------------------------------------------------------------------
# Console conventions (matches prepare_corpus.py / validate_corpus.py)
# --------------------------------------------------------------------------

def fail(message: str) -> None:
    """Print an informative error and exit non-zero. Never a bare crash."""
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(1)


def announce(step: str) -> None:
    print(f"\n=== {step} ===")


# --------------------------------------------------------------------------
# JSON read/write (deterministic: sorted keys, no timestamps)
# --------------------------------------------------------------------------

def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict:
    if not path.exists():
        fail(f"expected file not found: {path}")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        fail(f"could not parse {path} as JSON: {exc}")


def read_json_soft(path: Path) -> dict:
    """Like read_json, but raises instead of exiting the process — for
    callers (accept_batch.py) that need a bad file to become a reportable
    per-file rejection rather than a hard process failure."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# Manifest / stream / batch membership
# --------------------------------------------------------------------------

# Pinned batching: the 50 stream contracts in
# recorded order, batched 6,6,6,6,6,6,7,7 (8 batches).
BATCH_SIZES = [6, 6, 6, 6, 6, 6, 7, 7]
assert len(BATCH_SIZES) == 8 and sum(BATCH_SIZES) == 50, "batch sizes must be 8 batches totalling 50"


def load_manifest(paths: Paths) -> dict:
    if not paths.manifest_path.exists():
        fail(f"{paths.manifest_path} not found — run prepare_corpus.py first.")
    return read_json(paths.manifest_path)


def stream_contracts(manifest: dict) -> list[str]:
    """The 50 stream contract filenames, in the manifest's recorded seeded
    order (never re-sorted — order is the learning-year timeline)."""
    return [entry["contract"] for entry in manifest["selection"]["stream"]]


def holdout_contracts(manifest: dict) -> list[str]:
    return [entry["contract"] for entry in manifest["selection"]["holdout"]]


def batch_boundaries() -> list[tuple[int, int]]:
    """Cumulative (start, end) index ranges into the 50-contract stream for
    each of the 8 batches, per BATCH_SIZES."""
    bounds = []
    start = 0
    for size in BATCH_SIZES:
        bounds.append((start, start + size))
        start += size
    return bounds


def batch_contracts(manifest: dict, batch_number: int) -> list[str]:
    """1-indexed batch number -> the stream contract filenames in that
    batch, in stream order."""
    if not (1 <= batch_number <= len(BATCH_SIZES)):
        fail(f"batch_number must be between 1 and {len(BATCH_SIZES)}, got {batch_number}")
    stream = stream_contracts(manifest)
    lo, hi = batch_boundaries()[batch_number - 1]
    return stream[lo:hi]


def contract_batch_map(manifest: dict) -> dict[str, int]:
    """contract filename -> 1-indexed batch number, for every stream
    contract."""
    mapping = {}
    for batch_number in range(1, len(BATCH_SIZES) + 1):
        for contract in batch_contracts(manifest, batch_number):
            mapping[contract] = batch_number
    return mapping


def read_contract_text(paths: Paths, contract: str) -> str:
    """Stream and holdout contracts both live in the same directory (see
    prepare_corpus.py's copy step) — one read helper covers both splits."""
    path = paths.contracts_dir / contract
    if not path.exists():
        fail(f"contract text not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"could not read {path}: {exc}")


# --------------------------------------------------------------------------
# Matcher lifecycle state (data/runs/matcher_state.json)
# --------------------------------------------------------------------------
#
# Lifecycle per category: none -> commissioned -> active | failed -> demoted?
# "none" categories have no matcher yet; "commissioned" categories have an
# induction folder built and are awaiting the overseer + gate; "active"
# categories route their category on the stream/holdout from
# active_from_batch onward; "failed" categories never passed the gate;
# "demoted" categories passed once but were later demoted (permanent for
# the run). failed/demoted are both terminal and frozen.

def fresh_matcher_state() -> dict:
    return {
        "last_accepted_batch": 0,
        "read_count": 0,
        "read_log": [],
        "categories": {
            name: {
                "status": "none",
                "trust": None,
                "matcher_id": None,
                "matcher_path": None,
                "commissioned_at_batch": None,
                "active_from_batch": None,
                "failed_at_batch": None,
                "demoted_at_batch": None,
                "demotion_reason": None,
                "history": [],
            }
            for name in schemas.CATEGORY_NAMES
        },
    }


def load_matcher_state(paths: Paths) -> dict:
    """Fresh state if no run has started yet (batch 1's dry run has no
    matchers active and no prior batches accepted); otherwise load from
    disk."""
    if not paths.matcher_state_path.exists():
        return fresh_matcher_state()
    return read_json(paths.matcher_state_path)


def save_matcher_state(paths: Paths, state: dict) -> None:
    write_json(paths.matcher_state_path, state)


def record_history(state: dict, category: str, batch_number: int | None, event: str, detail: str) -> None:
    state["categories"][category]["history"].append(
        {"batch": batch_number, "event": event, "detail": detail}
    )


def demote_category(state: dict, category: str, batch_number: int, reason: str) -> None:
    """Demotion is permanent for the run: the
    matcher_path/matcher_id are left in place (frozen and reported), only
    status and the demotion bookkeeping change."""
    info = state["categories"][category]
    info["status"] = "demoted"
    info["demoted_at_batch"] = batch_number
    info["demotion_reason"] = reason
    record_history(state, category, batch_number, "demoted", reason)


# --------------------------------------------------------------------------
# Read accounting (config.READ_CAP = 60; a read = one contract processed by
# an extraction agent; a retry of the same contract is +1 read)
# --------------------------------------------------------------------------

def record_reads(state: dict, batch_number: int, reads: int, retries: int = 0) -> None:
    state["read_count"] += reads + retries
    state["read_log"].append({"batch": batch_number, "reads": reads, "retries": retries})


def read_cap_exceeded(state: dict, additional: int) -> bool:
    return (state["read_count"] + additional) > config.READ_CAP


# --------------------------------------------------------------------------
# Matcher module loading and calling
# --------------------------------------------------------------------------

def load_matcher_module(matcher_path: Path):
    """Import a generated matcher file by path (importlib), giving every
    load a unique module name so repeated loads (e.g. across gate replay
    and later run_matchers.py calls, or across test fixtures reusing a
    filename) never collide via sys.modules caching."""
    if not matcher_path.exists():
        fail(f"matcher file not found: {matcher_path}")
    unique_name = f"_generated_matcher_{matcher_path.stem}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(unique_name, matcher_path)
    if spec is None or spec.loader is None:
        fail(f"could not build an import spec for {matcher_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # a broken matcher file must fail loud, named
        fail(f"matcher module {matcher_path} raised on import: {exc}")
    if not hasattr(module, "match") or not hasattr(module, "NoMatch"):
        fail(f"matcher module {matcher_path} does not define both match() and NoMatch")
    return module


def call_matcher(module, text: str) -> tuple[bool, dict | None]:
    """Call module.match(text). Returns (True, result) on a match, or
    (False, None) on that module's own NoMatch. Any other exception is a
    matcher bug and is left to propagate — fail loud, never swallow it as
    if it were a considered non-answer."""
    try:
        result = module.match(text)
        return True, result
    except module.NoMatch:
        return False, None


def validate_matcher_output(category: str, result: dict, contract_text: str, trust: str) -> list[str]:
    """Batch-prep / gate / holdout validation of one matcher answer:
    schema shape (via schemas.validate_record), every span verbatim in the
    contract text (after schemas.norm_ws), and the one-sided discipline
    (a one-sided matcher may never return present: False)."""
    errors = list(schemas.validate_record({"contract": "_", "categories": {category: result}}, [category]))
    text_norm = schemas.norm_ws(contract_text)
    for span in result.get("spans", []) or []:
        if not isinstance(span, str):
            continue  # already flagged by validate_record's type check
        if schemas.norm_ws(span) not in text_norm:
            errors.append(f"{category}: span not verbatim in contract text: {span!r}")
    if trust == "one-sided" and result.get("present") is False:
        errors.append(f"{category}: one-sided matcher returned present: False (not permitted)")
    return errors


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------

def slugify(category: str) -> str:
    """Category name -> filesystem/id-safe slug, e.g. 'Cap on Liability' ->
    'cap-on-liability', 'IP Ownership Assignment' -> 'ip-ownership-assignment'."""
    return re.sub(r"[^a-z0-9]+", "-", category.casefold()).strip("-")


def matcher_path_for(paths: Paths, category: str) -> Path:
    return paths.matchers_generated_dir / f"matcher_{slugify(category)}.py"


def next_commission_id(paths: Paths, category: str) -> str:
    """c<NN>-<slug>, NN = count of existing commission folders + 1 (there
    are only 12 categories, so two digits never overflow)."""
    slug = slugify(category)
    existing = 0
    if paths.commissions_dir.exists():
        existing = sum(1 for p in paths.commissions_dir.iterdir() if p.is_dir())
    return f"c{existing + 1:02d}-{slug}"


# --------------------------------------------------------------------------
# Accepted-extraction store (data/runs/llm_extractions/<stem>.json) — the
# model path's accepted, non-shadow answers, one file per contract,
# accumulated across categories.
# --------------------------------------------------------------------------

def _stem(contract: str) -> str:
    return contract[:-4] if contract.lower().endswith(".txt") else contract


def llm_extraction_path(paths: Paths, contract: str) -> Path:
    return paths.llm_extractions_dir / f"{_stem(contract)}.json"


def load_llm_extraction(paths: Paths, contract: str) -> dict | None:
    path = llm_extraction_path(paths, contract)
    return read_json(path) if path.exists() else None


def merge_llm_extraction(paths: Paths, contract: str, categories_subset: dict) -> Path:
    path = llm_extraction_path(paths, contract)
    record = read_json(path) if path.exists() else {"contract": contract, "categories": {}}
    record.setdefault("categories", {}).update(categories_subset)
    write_json(path, record)
    return path


def load_all_llm_extractions(paths: Paths) -> dict[str, dict]:
    records = {}
    if not paths.llm_extractions_dir.exists():
        return records
    for path in sorted(paths.llm_extractions_dir.glob("*.json")):
        rec = read_json(path)
        records[rec["contract"]] = rec
    return records


def category_accept_counts(paths: Paths, category: str) -> tuple[int, int]:
    """(accepted positives, accepted negatives) for a category, counted
    over every accepted (non-shadow) extraction recorded so far."""
    positives = negatives = 0
    for record in load_all_llm_extractions(paths).values():
        entry = record.get("categories", {}).get(category)
        if entry is None:
            continue
        if entry.get("present"):
            positives += 1
        else:
            negatives += 1
    return positives, negatives


# --------------------------------------------------------------------------
# Matcher-output store (data/runs/matcher_outputs/<stem>.json, and the
# holdout twin) — accumulated per category, one file per contract.
# --------------------------------------------------------------------------

def matcher_output_path(paths: Paths, contract: str, holdout: bool = False) -> Path:
    base = paths.matcher_outputs_holdout_dir if holdout else paths.matcher_outputs_dir
    return base / f"{_stem(contract)}.json"


def merge_matcher_output(paths: Paths, contract: str, category: str, entry: dict, holdout: bool = False) -> Path:
    path = matcher_output_path(paths, contract, holdout=holdout)
    record = read_json(path) if path.exists() else {"contract": contract, "categories": {}}
    record.setdefault("categories", {})[category] = entry
    write_json(path, record)
    return path


def load_matcher_output(paths: Paths, contract: str, holdout: bool = False) -> dict | None:
    path = matcher_output_path(paths, contract, holdout=holdout)
    return read_json(path) if path.exists() else None


# --------------------------------------------------------------------------
# Trust grading at commissioning (pinned):
# yes/no categories are ALWAYS one-sided (a pattern cannot prove absence of
# a clause); extraction categories get two-sided only with >= 3 accepted
# negatives, else one-sided.
# --------------------------------------------------------------------------

def trust_grade_for_commissioning(kind: str, negative_count: int) -> str:
    if kind == "yesno":
        return "one-sided"
    return "two-sided" if negative_count >= 3 else "one-sided"


# --------------------------------------------------------------------------
# Shadow regression assignment (pinned rule,
# corrected 3 Jul 2026 after a batch-2 preparation gap): in every batch, each
# active category is added to the question list of exactly one contract
# the LLM is reading anyway, chosen by seeded rotation, so its answer can
# be compared against the matcher's. That comparison is only meaningful on
# a (contract, category) pair where the active matcher actually produced
# an answer this batch (not NoMatch) — a NoMatch pair has nothing to
# regress against, since the category is already a plain question there
# with no matcher answer to disagree with. Eligibility per category is
# therefore: contracts with a non-empty question list (the LLM is reading
# them anyway) AND a recorded matcher answer for THAT category this batch.
# Max 2 shadow categories per contract; excess (or no eligible contract at
# all) dropped by seeded priority.
# --------------------------------------------------------------------------

def assign_shadow_categories(
    active_categories: list[str],
    llm_read_contracts: list[str],
    category_answered_contracts: dict[str, list[str]],
    batch_number: int,
) -> tuple[dict[str, list[str]], list[str]]:
    """Returns (shadow_map, dropped). shadow_map: contract -> list of
    categories shadow-assigned to it (max 2). dropped: categories that
    could not be assigned — either no eligible contract exists this batch
    (its matcher NoMatched every LLM-read contract) or every eligible
    contract was already at its 2-shadow cap — in priority order.

    `category_answered_contracts`: category -> contracts in this batch
    where that category's active matcher recorded a real answer this batch
    (built by prepare_batch.py from its matcher-run loop). Only categories
    present here (with a non-empty, LLM-read-intersecting list) can receive
    a shadow slot at all.

    Deterministic given the inputs and batch_number: a single
    `random.Random(RANDOM_SEED + batch_number)` fixes both the priority
    order categories are assigned in (so the same categories are dropped
    first whenever capacity runs out) and a rotation order over the
    batch's LLM-read contracts, which each category's eligible pool is
    then filtered from (preserving that shared seeded order).
    """
    shadow_map: dict[str, list[str]] = {}
    dropped: list[str] = []
    if not active_categories or not llm_read_contracts:
        return shadow_map, sorted(active_categories)

    rng = random.Random(config.RANDOM_SEED + batch_number)
    priority = sorted(active_categories)
    rng.shuffle(priority)
    llm_read_set = set(llm_read_contracts)
    contracts_pool = sorted(llm_read_contracts)
    rng.shuffle(contracts_pool)

    idx = 0
    for category in priority:
        answered_set = set(category_answered_contracts.get(category, []))
        eligible = [c for c in contracts_pool if c in llm_read_set and c in answered_set]
        if not eligible:
            dropped.append(category)
            continue
        assigned = False
        for _ in range(len(eligible)):
            contract = eligible[idx % len(eligible)]
            idx += 1
            slot = shadow_map.setdefault(contract, [])
            if len(slot) < 2:
                slot.append(category)
                assigned = True
                break
        if not assigned:
            dropped.append(category)

    # Drop empty entries (contracts that ended up with no shadow) for a
    # clean map, and sort each contract's list for determinism.
    shadow_map = {c: sorted(cats) for c, cats in shadow_map.items() if cats}
    return shadow_map, sorted(dropped)
