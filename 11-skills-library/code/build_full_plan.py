"""The full test-set run: plan, stage, packets and counters for 1,800 agent runs.

    python code/build_full_plan.py build [--plan-only] [--refresh] [--new-attempt]
    python code/build_full_plan.py check                 # the same as: build_agent_packets.py check-plan --plan full
    python code/build_full_plan.py frozen                # only verify the frozen state (arms/ and config.py against the manifest)

What it builds (15 Oct 2026; nothing here calls a model or an API):
  * the 60 test requests (data/requests/test_requests.json), 5 repeats each (r1 to r5);
  * Sonnet 5.5 on S, D, L and L- (1,200 runs) and Haiku 4.5 on S and L (600 runs): 1,800 runs;
  * the order shuffled with a seed derived from config.RANDOM_SEED, so arms, models and repeats are interleaved, and cut into
    rounds of 30 (60 rounds); every plan entry carries its round, its place in the round and its launch prompt (as in pilot 3);
  * the stage folders for S, D, L and L- (L- = L without the scripts folder, the script runner and its tool, plus the one added
    sentence "No script runner is available ...", exactly as the API harness's L- arm), 1,800 packets under
    data/agent_runs/packets/full/ and 1,800 counters at zero under data/agent_runs/counters/.

Before anything is built the frozen state is verified: every file of arms/ against the freeze manifest, no file
in arms/ that the manifest does not list, and code/config.py against the manifest's SHA-256. A difference stops the build.

Order of work: this script reads data/requests/ and arms/, so it runs BEFORE the lock.

After round 38 the query budget was raised from 12 to 30 and the runs that had used all 12 were queued to run again in rounds 61 and 62
(a one-off amendment script, run once). `build` makes a plan at the current budget
and must not be run over the amended plan: it would rebuild the packets and counters of runs already done.

Output goes only under data/agent_runs/ (the same guard as build_agent_packets.py). Nothing in arms/, world/, data/key/ or
data/requests/ is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_agent_packets as bp          # noqa: E402
import config as cfg                      # noqa: E402

# ---------------------------------------------------------------------------
# Config block. config.py is frozen (its hash is in the manifest), so the settings of the full run live here.
# ---------------------------------------------------------------------------

FULL_NAME = "full"                                    # set name: run ids start "full-", packets in packets/full/, plan full_plan.json
FULL_REPEATS = 5                                      # r1 to r5 (cfg.FULL_PLAN_RUNS_PER_REQUEST)
FULL_CELLS = (("sonnet", "S"), ("sonnet", "D"), ("sonnet", "L"), ("sonnet", "L-"),     # (agent model, arm)
              ("haiku", "S"), ("haiku", "L"))                                           # Sonnet 4 x 300 + Haiku 2 x 300 = 1,800
ROUND_SIZE = 30                                       # runs per round; the runner launches one round, then checks it
ORDER_SEED_SALT = 11                                  # order seed = [cfg.RANDOM_SEED, ORDER_SEED_SALT]
FROZEN_MANIFEST_PATH = cfg.CASE_ROOT / "design" / "arms-frozen-2026-10-15.renamed-2026-10-16.json"
FINALS_SUBDIR = "full"                                # scratch/full/: final-<run_id>.txt and usage-round-NN.jsonl
EXPECTED_RUNS = 1800
EXPECTED_ROUNDS = 60                                  # the first-pass rounds; re-run rounds come after them (see below)

# The query budget was raised from 12 to 30 after round 38 (15 Oct 2026). Runs that finished within 12 queries stand. Runs that used all 12 were set aside and are re-run under 30 in
# new rounds after the first-pass rounds, 30 to a round, in an order shuffled with this seed.
RERUN_SEED_SALT = 12                                  # re-run order seed = [cfg.RANDOM_SEED, RERUN_SEED_SALT]
SUPERSEDED_SUBDIR = "superseded_cap12"                # under data/agent_runs/: finals/, counters/, packets/, usage-lines.jsonl, INDEX.json


# ---------------------------------------------------------------------------
# Frozen state
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_frozen_state(case_root: Path = cfg.CASE_ROOT, manifest_path: Path = FROZEN_MANIFEST_PATH) -> list:
    """Problems (sentences) with the frozen material: a file of arms/ missing, changed or extra against the manifest's SHA-256,
    config.py changed, or the task text version different. Empty list means the frozen state holds."""
    problems = []
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    listed = manifest["files"]
    for relative, expected in listed.items():
        path = case_root / relative
        if not path.is_file():
            problems.append(f"frozen file is missing: {relative}")
        elif sha256_file(path) != expected:
            problems.append(f"frozen file has changed: {relative}")
    arms_dir = case_root / "arms"
    on_disk = {path.relative_to(case_root).as_posix() for path in arms_dir.rglob("*")
               if path.is_file() and "__pycache__" not in path.parts}
    for relative in sorted(on_disk - set(listed)):
        problems.append(f"file in arms/ that the manifest does not list: {relative}")
    config_path = case_root / "code" / "config.py"
    if not config_path.is_file():
        problems.append("code/config.py is missing")
    elif sha256_file(config_path) != manifest["config_py_sha256"]:
        problems.append("code/config.py has changed since the freeze")
    if str(cfg.TASK_INSTRUCTIONS_VERSION) != str(manifest["task_instructions_version"]):
        problems.append(f"task text version is {cfg.TASK_INSTRUCTIONS_VERSION}, the manifest froze {manifest['task_instructions_version']}")
    return problems


# ---------------------------------------------------------------------------
# The order of runs
# ---------------------------------------------------------------------------

def test_request_ids(requests_path: Path = cfg.REQUESTS_DIR / "test_requests.json") -> list:
    """The 60 ids, in file order (ids only: the request texts are read one at a time when a packet is built)."""
    return [entry["id"] for entry in json.loads(Path(requests_path).read_text(encoding="utf-8"))]


def canonical_specs(request_ids: list, cells: tuple = FULL_CELLS, repeats: int = FULL_REPEATS) -> list:
    """Every run as (agent model, arm, request id, repeat), in a fixed canonical order (before the shuffle)."""
    return [(alias, arm, request_id, repeat) for alias, arm in cells for request_id in request_ids for repeat in range(1, repeats + 1)]


def shuffled_specs(specs: list, seed: int = cfg.RANDOM_SEED, salt: int = ORDER_SEED_SALT) -> list:
    """The runs in launch order: a seeded permutation of the canonical list (numpy default_rng, same seed gives the same order)."""
    permutation = np.random.default_rng([seed, salt]).permutation(len(specs))
    return [specs[index] for index in permutation]


def round_of(position: int, round_size: int = ROUND_SIZE) -> int:
    """Round number (1, 2, ...) of the run at 0-based position in the shuffled list."""
    return position // round_size + 1


def rerun_schedule(rerun_orders: list, first_pass_rounds: int, round_size: int = ROUND_SIZE, seed: int = cfg.RANDOM_SEED,
                   salt: int = RERUN_SEED_SALT) -> dict:
    """Where each re-run goes: {the run's first-pass `order`: (round, slot)}. The runs are taken in the order of their first-pass
    position, shuffled with numpy's default_rng([seed, salt]) and cut into rounds of round_size, numbered after the first-pass rounds."""
    ordered = sorted(rerun_orders)
    permutation = np.random.default_rng([seed, salt]).permutation(len(ordered))
    shuffled = [ordered[index] for index in permutation]
    return {order: (first_pass_rounds + position // round_size + 1, position % round_size + 1) for position, order in enumerate(shuffled)}


def has_final_message(paths: bp.AgentPaths, run_id: str) -> bool:
    """True when the run's final message file exists and holds more than white space (the run has been done)."""
    path = paths.scratch_dir / FINALS_SUBDIR / f"final-{run_id}.txt"
    try:
        return path.is_file() and bool(path.read_text(encoding="utf-8", errors="replace").strip())
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

LAUNCH_NOTES_FULL = [
    "Delivery is the pilot 3 protocol. For each run launch one Agent call with subagent_type general-purpose, model = agent_model "
    "('sonnet' or 'haiku'), no isolation, and as its prompt the run's `launch_prompt` exactly. The agent reads its packet itself; "
    "the runner pastes nothing else into the prompt.",
    "Order: 'runs' is already in launch order (shuffled with a fixed seed, so models, arms and repeats are interleaved). Take the "
    "runs with round = 1, then round = 2, and so on; 30 runs per round, 60 rounds. The runs of a round may go in parallel (mind the "
    "concurrency limit: a launch the limit refuses is relaunched, with the same packet, because the counter is still at zero).",
    "Before the first round: 'python code/build_full_plan.py frozen' and 'python code/build_agent_packets.py check-plan --plan full' "
    "clean, then 'python code/lock_answers.py lock --extended --with-code' (the lock procedure of the pilots), then "
    "'status --require-locked'. data/requests/ is locked during the runs although every packet carries "
    "the text of its own request; each agent is told to read only its packet and its stage folder, and the transcript lane check "
    "afterwards verifies that it did.",
    "Each run's final message is saved, exactly as received, to data/agent_runs/scratch/full/"
    "final-<run_id>.txt, and one line {\"run_id\", \"tokens\", \"tool_calls\", \"duration_s\"} is appended to "
    "data/agent_runs/scratch/full/usage-round-NN.jsonl (NN = the round, two digits).",
    "A run that fails before answering is not edited in place: its counter is kept as an earlier attempt and a fresh one registered "
    "with 'build_agent_packets.py packet --request REQ-Txx --arm A --model M --repeat N --set full --new-attempt' (this needs the "
    "code and the request folder, so it can only be done after the unlock, or with the run left for a later round).",
    "Unlock only after the last round, then collect each run with code/collect_agent_answer.py, lane-check the transcripts and mark.",
]


def plan_entry(spec: tuple, paths: bp.AgentPaths, build: bool, new_attempt: bool) -> dict:
    """One plan entry (a built packet and counter, or names only), with its batch label."""
    alias, arm, request_id, repeat = spec
    if build:
        entry = bp.build_packet(request_id, arm, alias, repeat, FULL_NAME, paths, new_attempt=new_attempt)
        entry["built"] = True
    else:
        entry = bp.planned_entry(request_id, arm, alias, FULL_NAME, paths, repeat)
    entry["batch"] = f"{alias}-{bp.AGENT_ARM_LABEL[arm]}"
    entry["query_budget"] = cfg.MAX_QUERY_EXECUTIONS                       # what this run's counter holds
    entry["task_instructions_version"] = cfg.TASK_INSTRUCTIONS_VERSION     # the task text its packet carries
    entry["launch_prompt"] = bp.launch_prompt_for(entry, paths)
    return entry


def make_full_plan(paths: Optional[bp.AgentPaths] = None, build: bool = True, refresh: bool = False, new_attempt: bool = False,
                   quiet: bool = False, request_ids: Optional[list] = None, cells: tuple = FULL_CELLS, repeats: int = FULL_REPEATS,
                   round_size: int = ROUND_SIZE, check_frozen: bool = True) -> dict:
    """Verify the frozen state, stage the arms (build=True), build every packet and counter, write <agent folder>/full_plan.json.
    The keyword arguments beyond paths/build exist so the tests can build a small plan in a temporary folder."""
    paths = paths or bp.AgentPaths.default()
    say = (lambda *a, **k: None) if quiet else print
    if check_frozen:
        say("Verifying the frozen state against the manifest ...")
        frozen_problems = verify_frozen_state()
        if frozen_problems:
            raise SystemExit("The frozen state does not hold; nothing was built:\n  " + "\n  ".join(frozen_problems))
        say(f"  arms/ and code/config.py match {FROZEN_MANIFEST_PATH.name}")
    request_ids = request_ids if request_ids is not None else test_request_ids()
    specs = shuffled_specs(canonical_specs(request_ids, cells, repeats))
    if build:
        arms_needed = sorted({arm for _, arm in cells}, key=cfg.ARM_LABELS.index)
        say(f"Staging arms {', '.join(arms_needed)} ...")
        for arm in arms_needed:
            bp.stage_arm(arm, paths, refresh=refresh, quiet=quiet)
        (paths.scratch_dir / FINALS_SUBDIR).mkdir(parents=True, exist_ok=True)
    runs = []
    for position, spec in enumerate(specs):
        entry = plan_entry(spec, paths, build, new_attempt)
        entry = {"order": position + 1, "round": round_of(position, round_size), "slot": position % round_size + 1, **entry}
        runs.append(entry)
        if not quiet and (position + 1) % 150 == 0:
            say(f"  {position + 1} of {len(specs)} {'packets built' if build else 'runs planned'}")
    plan = {
        "plan": FULL_NAME, "status": "built" if build else "planned: stage, packets and counters not built yet",
        "runs_total": len(runs), "rounds_total": max(run["round"] for run in runs) if runs else 0, "round_size": round_size,
        "first_pass_rounds": max(run["round"] for run in runs) if runs else 0,
        "repeats": repeats, "task_instructions_version": cfg.TASK_INSTRUCTIONS_VERSION, "marker_version": bp.pilot_marking_version(),
        "frozen_manifest": FROZEN_MANIFEST_PATH.name, "frozen_manifest_sha256": sha256_file(FROZEN_MANIFEST_PATH),
        "order_seed": [cfg.RANDOM_SEED, ORDER_SEED_SALT],
        "budgets": {"max_queries": cfg.MAX_QUERY_EXECUTIONS, "max_skill_loads": cfg.MAX_SKILL_LOADS, "max_skill_file_reads": cfg.MAX_SKILL_FILE_READS},
        "agent_models": cfg.AGENT_MODEL_IDS, "request_ids": request_ids, "cells": [list(cell) for cell in cells],
        "finals_dir": f"data/agent_runs/scratch/{FINALS_SUBDIR}", "python": Path(sys.executable).as_posix(),
        "launch_prompt_template": bp.LAUNCH_PROMPT, "launch_notes": LAUNCH_NOTES_FULL, "runs": runs,
    }
    plan_path = paths.agent_dir / f"{FULL_NAME}_plan.json"
    bp.assert_inside_agent_dir(plan_path, paths)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    say(f"Plan with {len(runs)} runs in {plan['rounds_total']} rounds of {round_size} written to {plan_path}")
    return plan


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def material_of(text: str, run_id: str) -> str:
    """A packet without its run id and its request section: what must be identical for every packet of one arm."""
    return text.split("## The request", 1)[0].replace(run_id, "<RUN>")


def check_full_plan(plan_path: Path, paths: Optional[bp.AgentPaths] = None, check_frozen: bool = True,
                    expected_runs: Optional[int] = EXPECTED_RUNS, expected_rounds: Optional[int] = EXPECTED_ROUNDS) -> list:
    """Problems (sentences; empty is clean) with a built full plan: everything check_plan checks (packet hashes, counters at zero for
    the runs not yet done, launch prompts, clean stage folders) plus the frozen state, the shape of the plan (counts, repeats, run ids,
    the reproducible order, the rounds), the stage folders against what the frozen arms give, and, packet by packet, that the run's own
    request is in it, its own arm's stage and no other, no test request id, its own query budget, and the same arm material as every
    other packet of that arm and budget.

    A run is done when it has a final message in scratch/full/. A done run's counter may be used (never past its budget); a run not yet
    done has an unused counter. After the query budget was raised (plan key `query_budget_raise`, see code/raise_query_budget.py) the
    plan holds runs at two budgets: the done runs that never reached 12 queries keep 12; every run not yet done is at 30; and the runs
    that did reach 12 (re-runs) are scheduled again in rounds after the first-pass rounds, their old final message, counter and packet
    kept in data/agent_runs/superseded_cap12/."""
    paths = paths or bp.AgentPaths.default()
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    root = paths.agent_dir.parent.parent
    runs = plan["runs"]
    problems = []
    if check_frozen:
        problems += [f"frozen state: {problem}" for problem in verify_frozen_state()]
    done_ids = {run["run_id"] for run in runs if has_final_message(paths, run["run_id"])}
    problems += bp.check_plan(plan_path, paths, started_run_ids=done_ids)
    raise_info = plan.get("query_budget_raise")
    rerun_runs = [run for run in runs if run.get("rerun_of_cap")]
    old_budget = raise_info["from"] if raise_info else None

    # Shape: counts, run ids, repeats, order, rounds.
    if expected_runs is not None and len(runs) != expected_runs:
        problems.append(f"the plan has {len(runs)} runs, expected {expected_runs}")
    if plan.get("runs_total") != len(runs):
        problems.append("runs_total does not match the number of runs")
    run_ids = [run["run_id"] for run in runs]
    if len(set(run_ids)) != len(run_ids):
        problems.append("run ids are not unique")
    cells = [tuple(cell) for cell in plan["cells"]]
    request_ids = plan["request_ids"]
    expected = canonical_specs(request_ids, tuple(cells), plan["repeats"])
    got = [(run["agent_model"], run["arm"], run["request_id"], run["repeat"]) for run in runs]
    if sorted(got) != sorted(expected):
        problems.append("the runs are not exactly every request x every cell x every repeat")
    if got != shuffled_specs(expected, *plan["order_seed"]):
        problems.append("the order of runs is not the seeded shuffle of the canonical list (seed in the plan)")
    for run in runs:
        wanted = bp.agent_run_id(FULL_NAME, run["agent_model"], run["arm"], run["request_id"], run["repeat"])
        if run["run_id"] != wanted:
            problems.append(f"{run['run_id']}: run id should be {wanted}")
    if expected_runs is not None:
        per_cell = {}
        for run in runs:
            per_cell[(run["agent_model"], run["arm"])] = per_cell.get((run["agent_model"], run["arm"]), 0) + 1
        want = len(request_ids) * plan["repeats"]
        for cell in cells:
            if per_cell.get(cell) != want:
                problems.append(f"cell {cell} has {per_cell.get(cell)} runs, expected {want}")
        if sorted({request_id for request_id in request_ids}) != sorted(test_request_ids()):
            problems.append("the plan's requests are not the 60 test requests")
    size = plan["round_size"]
    first_pass_rounds = plan.get("first_pass_rounds", plan["rounds_total"])
    if rerun_runs and not raise_info:
        problems.append("the plan has re-runs but no query_budget_raise record")
    schedule = {}
    if rerun_runs:
        schedule = rerun_schedule([run["order"] for run in rerun_runs], first_pass_rounds, size, *raise_info["rerun_seed"])
    for position, run in enumerate(runs):
        first = (position + 1, round_of(position, size), position % size + 1)
        if run.get("rerun_of_cap"):
            # a re-run keeps its first-pass order, round and slot (as first_round, first_slot) and has a new round and slot
            if (run["order"], run.get("first_round"), run.get("first_slot")) != first or (run["round"], run["slot"]) != schedule[run["order"]]:
                problems.append(f"{run['run_id']}: order, round or slot is wrong (re-run)")
                break
        elif (run["order"], run["round"], run["slot"]) != first:
            problems.append(f"{run['run_id']}: order, round or slot is wrong")
            break
    if expected_rounds is not None and first_pass_rounds != expected_rounds:
        problems.append(f"the plan has {first_pass_rounds} first-pass rounds, expected {expected_rounds}")
    rerun_rounds = -(-len(rerun_runs) // size)
    if plan["rounds_total"] != first_pass_rounds + rerun_rounds:
        problems.append(f"rounds_total is {plan['rounds_total']}, expected {first_pass_rounds} first-pass rounds plus {rerun_rounds} re-run rounds")

    # The query budget: what each entry and its counter say, and the record kept of every run set aside.
    superseded_dir = paths.agent_dir / SUPERSEDED_SUBDIR
    for run in runs:
        counter_path = root / run["counter_path"]
        if not counter_path.is_file():
            continue                                          # check_plan has reported it
        counter = json.loads(counter_path.read_text(encoding="utf-8"))
        budget = run.get("query_budget", cfg.MAX_QUERY_EXECUTIONS)
        if run["run_id"] not in done_ids and budget != cfg.MAX_QUERY_EXECUTIONS:
            problems.append(f"{run['run_id']}: not yet run but its budget is {budget}, not {cfg.MAX_QUERY_EXECUTIONS}")
        if budget not in (cfg.MAX_QUERY_EXECUTIONS, old_budget):
            problems.append(f"{run['run_id']}: budget {budget} is neither {cfg.MAX_QUERY_EXECUTIONS} nor the earlier one")
        if budget == old_budget and old_budget != cfg.MAX_QUERY_EXECUTIONS:
            if run.get("rerun_of_cap"):
                problems.append(f"{run['run_id']}: a re-run still has the earlier budget of {budget}")
            elif counter.get("used", 0) >= budget:
                problems.append(f"{run['run_id']}: finished at the earlier budget with {counter.get('used')} of {budget} queries used "
                                "and was not set aside to run again")
    for run in rerun_runs:
        proof = run.get("superseded") or {}
        label = run["run_id"]
        if run.get("query_budget") != cfg.MAX_QUERY_EXECUTIONS:
            problems.append(f"{label}: a re-run must have the new budget")
        for key, folder, name in (("final_sha256", "finals", f"final-{label}.txt"), ("counter_sha256", "counters", f"{label}.json"),
                                  ("packet_sha256", "packets", f"{label}.txt")):
            kept = superseded_dir / folder / name
            if not kept.is_file():
                problems.append(f"{label}: the set-aside file is missing: {SUPERSEDED_SUBDIR}/{folder}/{name}")
            elif bp.sha256_bytes(kept.read_bytes()) != proof.get(key):
                problems.append(f"{label}: the set-aside file changed since it was kept: {SUPERSEDED_SUBDIR}/{folder}/{name}")
        kept_counter = superseded_dir / "counters" / f"{label}.json"
        if kept_counter.is_file():
            old = json.loads(kept_counter.read_text(encoding="utf-8"))
            if old.get("budget") != old_budget or old.get("used", 0) < old_budget:
                problems.append(f"{label}: the set-aside counter does not show the earlier budget used up")

    # Stage folders: each equals what the frozen arms and tools give now (check_plan only compares a stage with its own manifest).
    for arm in sorted({run["arm"] for run in runs}, key=cfg.ARM_LABELS.index):
        target = paths.arm_stage(arm)
        if target.is_dir() and not bp.stage_matches(target, bp.stage_contents(arm, paths)):
            problems.append(f"stage/{bp.AGENT_ARM_LABEL[arm]}: differs from what the frozen arms and tools give")

    # Packets, one by one.
    stage_posix = {arm: bp.posix(paths.arm_stage(arm)) + "/" for arm in bp.AGENT_ARM_LABEL}
    reference = {}
    for run in runs:
        packet = root / run["packet_path"]
        if not packet.is_file():
            continue                                          # check_plan has reported it
        text = packet.read_text(encoding="utf-8")
        request = bp.load_request(run["request_id"])
        label = f"{run['run_id']}"
        if request["request_text"] not in text or request["received"] not in text:
            problems.append(f"{label}: the packet lacks its own request's text or received date")
        if "REQ-T" in text or ("REQ-D" in text and run["arm"] == "S"):
            problems.append(f"{label}: the packet names a request id")
        if stage_posix[run["arm"]] not in text:
            problems.append(f"{label}: the packet does not point at its own arm's stage folder")
        for other, folder in stage_posix.items():
            if other != run["arm"] and folder in text:
                problems.append(f"{label}: the packet points at the {other} stage folder")
        if run["arm"] == "L-" and ("Running library scripts" in text or "hx_script" in text):
            problems.append(f"{label}: an L- packet offers the script runner")
        if run["arm"] == "L" and "Running library scripts" not in text:
            problems.append(f"{label}: an L packet does not offer the script runner")
        budget = run.get("query_budget", cfg.MAX_QUERY_EXECUTIONS)
        for wording in (f"Every call uses one of your {budget} query executions", f"up to {budget} queries"):
            if wording not in text:
                problems.append(f"{label}: the packet does not say '{wording}'")
        material = material_of(text, run["run_id"])
        key = (run["arm"], budget)
        if key not in reference:
            reference[key] = (run["run_id"], material)
        elif material != reference[key][1]:
            problems.append(f"{label}: the arm material differs from {reference[key][0]}'s")
    return problems


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv: list = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Plan, stage, packets and counters for the full test-set run.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="verify the frozen state, stage S, D, L and L-, build 1,800 packets and counters, write full_plan.json")
    build.add_argument("--plan-only", action="store_true", help="names only: no stage, packets or counters")
    build.add_argument("--refresh", action="store_true", help="replace a stage folder that differs (pilot stages are replaced only with this)")
    build.add_argument("--new-attempt", action="store_true", help="keep a used counter as an earlier attempt and register a fresh run")
    commands.add_parser("check", help="verify the built plan")
    commands.add_parser("frozen", help="verify the frozen state only")
    args = parser.parse_args(argv)
    if args.command == "frozen":
        problems = verify_frozen_state()
        print("frozen state: " + ("clean" if not problems else f"{len(problems)} PROBLEMS"))
        for problem in problems:
            print("   " + problem)
        return 1 if problems else 0
    if args.command == "build":
        make_full_plan(build=not args.plan_only, refresh=args.refresh, new_attempt=args.new_attempt)
        return 0
    paths = bp.AgentPaths.default()
    plan_path = paths.agent_dir / f"{FULL_NAME}_plan.json"
    if not plan_path.is_file():
        print(f"No plan file at {plan_path}.")
        return 1
    problems = check_full_plan(plan_path, paths)
    print(f"{plan_path.name}: " + ("clean" if not problems else f"{len(problems)} PROBLEMS"))
    for problem in problems[:60]:
        print("   " + problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
