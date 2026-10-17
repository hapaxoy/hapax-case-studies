"""Stage the arms' files and build the run packets for agent runs (Claude Code subagents instead of the paid API).

    python code/build_agent_packets.py stage  [--arms S,D,L] [--refresh]
    python code/build_agent_packets.py packet --request REQ-D05 --arm S --model sonnet [--repeat 1] [--set NAME] [--new-attempt]
    python code/build_agent_packets.py pilot2 [--refresh] [--new-attempt]       # stage S, D, L; 40 packets; pilot2_plan.json
    python code/build_agent_packets.py pilot3 [--plan-only] [--refresh] [--new-attempt]
                                                                                # pilot3_plan.json; --plan-only builds no stage, packets or counters
    python code/build_agent_packets.py check  [--arms S,D,L]                     # verify the stage folders against their manifests
    python code/build_agent_packets.py check-plan --plan pilot3                  # verify a built plan: packets, hashes, counters

What a run is. The main session launches one subagent per run (model "sonnet" = Sonnet 5.5 or "haiku" = Haiku 4.5, fresh
context, one request, one arm). The subagent has Bash, Read and Glob. The PACKET is the agent's whole brief, a file the agent
reads itself: the Agent call's prompt is one short instruction that names the packet file (LAUNCH_PROMPT, the official delivery
from pilot 3; pilot 2 ran the same way). The packet holds the same arm material the API harness put in its system prompt (harness.build_arm_materials:
the schema, plus the prompt doc for D, plus the skill list for L), how to call the tools, and the shared task text
(config.TASK_INSTRUCTIONS, filled in for the request). Arm parity: S and D carry the harness's system text byte for byte; L
carries the same schema and the same skill names and descriptions, with the load_skill and run_script wording replaced by
the file and command wording below; the task text is identical for every arm; the budgets are the same numbers.

The STAGE (data/agent_runs/stage/<arm>/) holds only what the arm may read: its tools (hx_sql.py, hx_common.py and for L
hx_script.py and script_runner.py, with hx_settings.json) and for L the library, copied from arms/library with the provenance
markers stripped from the markdown (as the API harness did when it loaded a file) and without any builder notes, tests or
anything else outside skills. The prompt doc and the schema go inline in the packet, so S and D stage only tools.

A RUN is registered when its packet is built: data/agent_runs/counters/<run_id>.json holds its query budget (config.MAX_QUERY_EXECUTIONS: 12 for
the runs of rounds 1 to 38 of the full run, 30 for every run after the raise of 15 Oct 2026) and
an audit of every call the two commands make. The commands refuse a run id with no counter file.

Output goes only under data/agent_runs/. Nothing in world/, arms/, data/key/ or data/requests/ is written; the test
requests are read one at a time through harness.load_test_request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg                      # noqa: E402
import harness                            # noqa: E402
import hx_common                          # noqa: E402

CODE_DIR = Path(__file__).resolve().parent
STAGE_MARKER = ".hx_stage"
MANIFEST_NAME = "MANIFEST.json"
SETTINGS_NAME = "hx_settings.json"
AGENT_ARM_LABEL = harness.ARM_FILENAME_LABEL          # S, D, L, L- -> S, D, L, Lminus
TOOL_SOURCES = {"S": ["hx_common.py", "hx_sql.py"], "D": ["hx_common.py", "hx_sql.py"],
                "L": ["hx_common.py", "hx_sql.py", "hx_script.py", "script_runner.py"], "L-": ["hx_common.py", "hx_sql.py"]}


# ---------------------------------------------------------------------------
# Paths (a test points agent_dir at a temporary folder; everything else stays the real, read-only input)
# ---------------------------------------------------------------------------

@dataclass
class AgentPaths:
    agent_dir: Path
    world_dir: Path
    doc_path: Path
    library_dir: Path
    warehouse_path: Path

    @classmethod
    def default(cls) -> "AgentPaths":
        return cls(cfg.AGENT_RUNS_DIR, cfg.WORLD_DIR, cfg.ARMS_DOC_PATH, cfg.ARMS_LIBRARY_DIR, cfg.WAREHOUSE_PATH)

    @property
    def stage_dir(self) -> Path:
        return self.agent_dir / "stage"

    @property
    def packets_dir(self) -> Path:
        return self.agent_dir / "packets"

    @property
    def counters_dir(self) -> Path:
        return self.agent_dir / "counters"

    @property
    def scratch_dir(self) -> Path:
        return self.agent_dir / "scratch"

    @property
    def tools_root(self) -> Path:
        """The folder the staged tools compute paths from: three levels above the agent folder's stage (case/data/agent_runs)."""
        return self.agent_dir.parent.parent

    def arm_stage(self, arm: str) -> Path:
        return self.stage_dir / AGENT_ARM_LABEL[arm]


def posix(path: Path) -> str:
    """A path as forward slashes, which Git Bash and Windows Python both accept."""
    return Path(path).resolve().as_posix()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_inside_agent_dir(path: Path, paths: AgentPaths) -> None:
    resolved, root = Path(path).resolve(), paths.agent_dir.resolve()
    if resolved != root and root not in resolved.parents:
        raise SystemExit(f"Refusing to write {resolved}: output goes only under {root}.")


# ---------------------------------------------------------------------------
# Stage: what each arm may read
# ---------------------------------------------------------------------------

def library_files(arm: str, paths: AgentPaths) -> dict:
    """{relative posix path: text} for the library as the arm may read it: the harness's readable suffixes, provenance markers
    stripped from markdown, no scripts folder in L-. Refuses a library folder that holds build notes or tests."""
    library = Path(paths.library_dir)
    harness.check_library_is_clean(library)
    files = {}
    for skill_dir in harness.list_skill_dirs(library):
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.name != "SKILL.md" and path.suffix not in harness.READABLE_SKILL_SUFFIXES:
                continue
            relative = path.relative_to(library).as_posix()
            if arm == "L-" and relative.split("/")[1] == "scripts":
                continue
            text = path.read_text(encoding="utf-8")
            files[relative] = harness.strip_markers(text) if path.suffix == ".md" else text
    return files


def settings_for_arm(arm: str, paths: AgentPaths) -> dict:
    """Contents of hx_settings.json: paths relative to the case folder, the limits as the API harness had them."""
    import os

    def relative(path: Path) -> str:
        return Path(os.path.relpath(Path(path).resolve(), paths.tools_root.resolve())).as_posix()
    return {
        "warehouse": relative(paths.warehouse_path), "counters_dir": relative(paths.counters_dir), "scratch_dir": relative(paths.scratch_dir),
        "library_dir": relative(paths.arm_stage(arm) / "library") if arm in ("L", "L-") else None,
        "max_queries": cfg.MAX_QUERY_EXECUTIONS, "row_cap": cfg.SQL_RESULT_ROW_LIMIT, "cell_char_limit": cfg.SQL_CELL_CHAR_LIMIT,
        "sql_timeout_s": cfg.SQL_TIMEOUT_SECONDS, "memory_limit": cfg.SQL_MEMORY_LIMIT,
        "script_timeout_s": cfg.SCRIPT_TIMEOUT_SECONDS, "script_output_char_limit": cfg.SCRIPT_OUTPUT_CHAR_LIMIT,
        "scripts_allowed": arm == "L",
    }


def stage_contents(arm: str, paths: AgentPaths) -> dict:
    """{relative path inside the arm's stage folder: bytes} for everything the arm may read, plus its manifest."""
    if arm not in AGENT_ARM_LABEL:
        raise SystemExit(f"Unknown arm {arm!r}; arms are {cfg.ARM_LABELS}.")
    contents = {}
    for name in TOOL_SOURCES[arm]:
        contents[f"tools/{name}"] = (CODE_DIR / name).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    contents[f"tools/{SETTINGS_NAME}"] = (json.dumps(settings_for_arm(arm, paths), indent=1) + "\n").encode("utf-8")
    if arm in ("L", "L-"):
        for relative, text in library_files(arm, paths).items():
            contents[f"library/{relative}"] = text.encode("utf-8")
    manifest = {"arm": arm, "files": [{"path": name, "sha256": sha256_bytes(data), "bytes": len(data)} for name, data in sorted(contents.items())]}
    contents[MANIFEST_NAME] = (json.dumps(manifest, indent=1) + "\n").encode("utf-8")
    return contents


def stage_arm(arm: str, paths: Optional[AgentPaths] = None, refresh: bool = False, quiet: bool = False) -> Path:
    """Write the arm's stage folder. An existing folder that already matches is left alone; one that differs is refused
    unless refresh is set, which replaces it (only ever a folder this function made: it carries a marker file)."""
    paths = paths or AgentPaths.default()
    say = (lambda *a, **k: None) if quiet else print
    target = paths.arm_stage(arm)
    assert_inside_agent_dir(target, paths)
    contents = stage_contents(arm, paths)
    if target.exists():
        if not (target / STAGE_MARKER).is_file():
            raise SystemExit(f"{target} exists but was not made by this script (no {STAGE_MARKER}); not touching it.")
        if stage_matches(target, contents):
            say(f"  stage/{AGENT_ARM_LABEL[arm]}: already up to date ({len(contents)} files)")
            return target
        if not refresh:
            raise SystemExit(f"{target} differs from what the arm's material now gives. Run again with --refresh to replace it.")
        shutil.rmtree(target)
    target.mkdir(parents=True)
    (target / STAGE_MARKER).write_text("Made by build_agent_packets.py; safe to replace with --refresh.\n", encoding="utf-8")
    for relative, data in contents.items():
        file_path = target / relative
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)
    say(f"  stage/{AGENT_ARM_LABEL[arm]}: {len(contents)} files written")
    return target


def stage_matches(target: Path, contents: dict) -> bool:
    on_disk = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file() and path.name != STAGE_MARKER}
    if on_disk != set(contents):
        return False
    return all((target / relative).read_bytes() == data for relative, data in contents.items())


def verify_stage(arm: str, paths: Optional[AgentPaths] = None) -> list:
    """Problems with an arm's stage folder: files missing, extra or changed against the manifest, and anything that must
    never be there (build notes, tests, the key, design documents, request files). Returns a list of sentences; empty is clean."""
    paths = paths or AgentPaths.default()
    target = paths.arm_stage(arm)
    problems = []
    if not (target / MANIFEST_NAME).is_file():
        return [f"stage/{AGENT_ARM_LABEL[arm]} has no {MANIFEST_NAME} (not staged)"]
    manifest = json.loads((target / MANIFEST_NAME).read_text(encoding="utf-8"))
    listed = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    present = {path.relative_to(target).as_posix(): path for path in target.rglob("*")
               if path.is_file() and path.name not in (STAGE_MARKER, MANIFEST_NAME)}
    for relative in sorted(set(present) - set(listed)):
        problems.append(f"extra file not in the manifest: {relative}")
    for relative in sorted(set(listed) - set(present)):
        problems.append(f"file in the manifest is missing: {relative}")
    for relative, path in present.items():
        if relative in listed and sha256_bytes(path.read_bytes()) != listed[relative]:
            problems.append(f"file changed since staging: {relative}")
    forbidden = set(harness.FORBIDDEN_ARM_NAMES) | {"key.json", "review_sheet.md", "DECISIONS.md", "design.md", "test_requests.json", "briefs.json", "facts.yaml"}
    for relative in present:
        if set(Path(relative).parts) & forbidden:
            problems.append(f"forbidden file in the stage: {relative}")
    if arm in ("S", "D") and any(relative.startswith("library/") for relative in present):
        problems.append("an arm without the library has library files")
    if arm == "L-" and any("/scripts/" in relative for relative in present):
        problems.append("L- stage holds script files")
    for relative, path in present.items():
        if path.suffix in (".md",) and "<!-- facts:" in path.read_text(encoding="utf-8"):
            problems.append(f"provenance marker left in {relative}")
    return problems


# ---------------------------------------------------------------------------
# Packet text
# ---------------------------------------------------------------------------

HEADER_TEXT = """This file is your whole brief. Your run id is `{run_id}`. You have the Bash, Read and Glob tools.

How to work in this session:
- Apart from this brief, read only the files named in it. They are all under `{stage_dir}`. Do not list, search or open any other folder.
- Do not open the warehouse file yourself with Python or any other program. All SQL goes through the command under "Running SQL", which is read-only and counts your queries.
- Do not create, change or delete any file.
- Your final message is collected exactly as you write it. It must be the JSON object described in the request, and nothing else."""

SQL_TEXT = """## Running SQL

Run SQL with this command. The statement goes on standard input; the quoted `'SQL'` marker lets you write quotes and apostrophes freely.

```bash
"{python}" "{hx_sql}" --run {run_id} <<'SQL'
SELECT ...
SQL
```

It runs exactly one statement, a SELECT (including WITH) or an EXPLAIN, on the Tuomimetsä warehouse (DuckDB dialect) and prints the result as a table: a header line, then one line per row with the cells separated by " | ". A result longer than {row_cap} rows is cut and a line in capitals says so. Every call uses one of your {max_queries} query executions, including calls that fail or are refused; the output ends with "[query n of {max_queries} used]". When they are used up, give your final answer."""

SKILLS_INTRO = ("## Skills library\n\nThe team keeps a library of skills: instructions, reference files and validated SQL templates for recurring "
                "request types. Only the names and descriptions are shown here. Read a skill in full when a request needs it (see \"Reading skills\").")
SKILLS_WITH_SCRIPTS = " The library's check scripts can be run with the script command (see \"Running library scripts\")."
SKILLS_WITHOUT_SCRIPTS = " No script runner is available in this session; where a skill mentions running a script, skip that step."

READING_TEXT = """## Reading skills

The library is the folder `{library_dir}`. Each skill is a folder there with a SKILL.md and, in some, reference files (`references/`), SQL templates (`templates/`){scripts_clause}. Read a skill with the Read tool, SKILL.md first, and see what else it holds with Glob. Opening a skill (reading any file of it for the first time) uses one of your {max_skill_loads} skill loads; reading further files of a skill you have already opened does not. Read at most {max_file_reads} library files in all."""

SCRIPTS_TEXT = """## Running library scripts

Run a library script with this command, in place of the `conda run ... python <library>/<skill>/scripts/<script>.py PATH_TO/tuomimetsa.duckdb ...` command lines the skills show. Give the script as `<skill>/scripts/<name>.py`, then the arguments that come after the database path. The database is supplied for you; do not pass one.

```bash
"{python}" "{hx_script}" --run {run_id} fiscal-calendar/scripts/fiscal.py "last period"
```

A script that takes a SQL file gets it with `--put`: standard input is written to a scratch file of that name, which you then name with `--file`.

```bash
"{python}" "{hx_script}" --run {run_id} --put q.sql query-check/scripts/query_check.py --file q.sql <<'SQL'
SELECT ...
SQL
```

Scripts are read-only against the warehouse. A script call executes SQL, so it uses one of your {max_queries} query executions, the same count as the SQL command."""


def skill_list_section(arm: str, paths: AgentPaths) -> str:
    """The skill names and one-line descriptions, built from the same SKILL.md headers as the API harness's system prompt."""
    lines = []
    for skill_dir in harness.list_skill_dirs(Path(paths.library_dir)):
        header = harness.parse_skill_header((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
        lines.append(f"- {header['name']}: {header['description']}")
    intro = SKILLS_INTRO + (SKILLS_WITH_SCRIPTS if arm == "L" else SKILLS_WITHOUT_SCRIPTS)
    return intro + "\n\n" + "\n".join(lines)


def build_packet_text(request: dict, arm: str, run_id: str, paths: Optional[AgentPaths] = None) -> str:
    """The exact prompt text for one run. Deterministic: the same request, arm and run id give the same text."""
    paths = paths or AgentPaths.default()
    if arm not in AGENT_ARM_LABEL:
        raise SystemExit(f"Unknown arm {arm!r}; arms are {cfg.ARM_LABELS}.")
    stage = paths.arm_stage(arm)
    values = {
        "run_id": run_id, "stage_dir": posix(stage), "python": Path(sys.executable).as_posix(), "hx_sql": posix(stage / "tools" / "hx_sql.py"),
        "hx_script": posix(stage / "tools" / "hx_script.py"), "row_cap": cfg.SQL_RESULT_ROW_LIMIT, "max_queries": cfg.MAX_QUERY_EXECUTIONS,
        "max_skill_loads": cfg.MAX_SKILL_LOADS, "max_file_reads": cfg.MAX_SKILL_FILE_READS, "library_dir": posix(stage / "library"),
        "scripts_clause": " and scripts (`scripts/`)" if arm == "L" else "",
    }
    if arm in ("S", "D"):
        # The API harness's system text, verbatim: preamble, schema and (for D) the team prompt document.
        material = harness.build_arm_materials(arm, world_dir=paths.world_dir, doc_path=paths.doc_path, library_dir=paths.library_dir).system_text
    else:
        base = harness.build_arm_materials("S", world_dir=paths.world_dir).system_text
        material = base + "\n\n" + skill_list_section(arm, paths)
    sections = [HEADER_TEXT.format(**values), material, SQL_TEXT.format(**values)]
    if arm in ("L", "L-"):
        sections.append(READING_TEXT.format(**values))
    if arm == "L":
        sections.append(SCRIPTS_TEXT.format(**values))
    sections.append("## The request\n\n" + harness.task_text(request))
    return "\n\n".join(sections) + "\n"


def check_packet_text(text: str, request: dict, arm: str = "S") -> list:
    """Things a packet must not contain: paths or names of held-out material, incident wording, a test request ID."""
    problems = []
    lowered = text.lower()
    for word in ("build_notes", "data/key", "data\\key", "reference_sql", "answer key", "review_sheet", "data/requests", "data/internal",
                 "test_requests", "design/", "decisions.md", "tests/test_library"):
        if word in lowered:
            problems.append(f"packet mentions {word!r}")
    try:
        import validate_world
        for token in validate_world.incident_tokens():
            if token in lowered:
                problems.append(f"packet holds incident token {token!r}")
    except Exception as error:   # the world modules are needed for this check; say so rather than skip silently
        problems.append(f"incident-token check could not run: {type(error).__name__}: {error}")
    if arm == "S" and request["id"] in text:
        # D and L legitimately carry the dev IDs (the doc's digest, the library's history digest); S carries nothing but the schema.
        problems.append("the packet carries the request's full ID (it would name a file in world/request_history/ for a dev request)")
    return problems


# ---------------------------------------------------------------------------
# Runs: ids, counters, packets
# ---------------------------------------------------------------------------

def agent_run_id(set_name: str, alias: str, arm: str, request_id: str, repeat: int = 1) -> str:
    """The run id the agent sees and types: set, model, arm, and a short request code (d05, t13), never the full request ID,
    so a brief does not hand an S-arm agent the name of a file in world/request_history/. The plan maps it back."""
    if alias not in cfg.AGENT_MODEL_IDS:
        raise SystemExit(f"Unknown agent model {alias!r}; models are {', '.join(cfg.AGENT_MODEL_IDS)}.")
    kind = "t" if request_id.startswith("REQ-T") else "d"
    number = "".join(ch for ch in request_id if ch.isdigit())
    return f"{set_name}-{alias}-{AGENT_ARM_LABEL[arm]}-{kind}{number}-r{repeat}"


def load_request(request_id: str) -> dict:
    """The one request, from the dev history (REQ-D..) or the test set (REQ-T..)."""
    if request_id.startswith("REQ-D"):
        return harness.load_dev_requests()[request_id]["request"]
    return harness.load_test_request(request_id)


def register_run(run_id: str, arm: str, alias: str, request_id: str, packet_sha256: str, paths: AgentPaths, new_attempt: bool = False) -> Path:
    """Create the run's counter file. A counter that has been used is kept as .attemptN when --new-attempt is given, else refused."""
    path = paths.counters_dir / f"{run_id}.json"
    assert_inside_agent_dir(path, paths)
    paths.counters_dir.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("used", 0) or existing.get("refused", 0):
            if not new_attempt:
                raise SystemExit(f"Run {run_id} has already used {existing.get('used', 0)} queries. Use --new-attempt to keep that record "
                                 "as an earlier attempt and register a fresh run.")
            number = 1
            while (paths.counters_dir / f"{run_id}.attempt{number}.json").exists():
                number += 1
            path.rename(paths.counters_dir / f"{run_id}.attempt{number}.json")
    counter = hx_common.new_counter(arm, alias, request_id, cfg.MAX_QUERY_EXECUTIONS, packet_sha256, cfg.TASK_INSTRUCTIONS_VERSION)
    counter["run_id"] = run_id
    path.write_text(json.dumps(counter, indent=1), encoding="utf-8")
    return path


def build_packet(request_id: str, arm: str, alias: str, repeat: int = 1, set_name: str = "adhoc", paths: Optional[AgentPaths] = None,
                 new_attempt: bool = False, request: Optional[dict] = None) -> dict:
    """Build one run's packet file and register its counter. Returns the plan entry."""
    paths = paths or AgentPaths.default()
    request = request or load_request(request_id)
    run_id = agent_run_id(set_name, alias, arm, request_id, repeat)
    text = build_packet_text(request, arm, run_id, paths)
    problems = check_packet_text(text, request, arm)
    if problems:
        raise SystemExit(f"Packet for {run_id} failed its checks: {'; '.join(problems)}")
    packet_path = paths.packets_dir / set_name / f"{run_id}.txt"
    assert_inside_agent_dir(packet_path, paths)
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    packet_path.write_bytes(data)
    digest = sha256_bytes(data)
    counter = register_run(run_id, arm, alias, request_id, digest, paths, new_attempt=new_attempt)
    return {"run_id": run_id, "agent_model": alias, "model_id": cfg.AGENT_MODEL_IDS[alias], "arm": arm, "request_id": request_id,
            "repeat": repeat, "packet_path": packet_path.relative_to(paths.agent_dir.parent.parent).as_posix() if _under(packet_path, paths.agent_dir.parent.parent) else str(packet_path),
            "packet_sha256": digest, "counter_path": counter.relative_to(paths.agent_dir.parent.parent).as_posix() if _under(counter, paths.agent_dir.parent.parent) else str(counter),
            "packet_chars": len(text)}


def _under(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Pilot 2 plan
# ---------------------------------------------------------------------------

# The official delivery of a packet (from pilot 3; pilot 2 ran the same way although its plan said otherwise). The Agent call's prompt
# is this one short instruction with the packet's absolute path filled in. The agent reads the packet itself with the Read tool, so the
# packet file on disk is the brief and its hash in the plan is the hash of what the agent read. The runner adds nothing else.
LAUNCH_PROMPT = "Your brief is the file `{packet_path}`. Read it with the Read tool, then do what it says."

LAUNCH_NOTES = [
    "Delivery (the official protocol from pilot 3). For each run launch one Agent call with subagent_type general-purpose (it has Bash, "
    "Read and Glob), model = agent_model ('sonnet' or 'haiku'), no isolation, and as its prompt the run's `launch_prompt` exactly: one short "
    "instruction naming the packet file. The agent reads the packet itself; the runner never pastes the packet text into the prompt and "
    "adds no other instruction.",
    "Before the first batch: stage and packets built on this machine ('python code/build_agent_packets.py pilot3'), "
    "'python code/build_agent_packets.py check-plan --plan pilot3' clean, then 'python code/lock_answers.py lock --extended --with-code', "
    "then 'status --require-locked'.",
    "Launch one batch at a time (the runs of a batch may go in parallel).",
    "When an agent finishes, write its final message to a file and run code/collect_agent_answer.py with the run id, the "
    "tokens, tool calls and duration the Agent tool reports. Unlock only after the last batch, then mark with 'python code/pilot_marking.py'.",
    "A run that fails before answering is re-registered with 'build_agent_packets.py packet ... --new-attempt', never edited in place.",
]


def planned_entry(request_id: str, arm: str, alias: str, set_name: str, paths: AgentPaths, repeat: int = 1) -> dict:
    """A plan entry for a run whose packet is not built yet: the run id and where its packet and counter will be, no hash."""
    root = paths.agent_dir.parent.parent
    run_id = agent_run_id(set_name, alias, arm, request_id, repeat)
    packet_path = paths.packets_dir / set_name / f"{run_id}.txt"
    counter_path = paths.counters_dir / f"{run_id}.json"
    return {"run_id": run_id, "agent_model": alias, "model_id": cfg.AGENT_MODEL_IDS[alias], "arm": arm, "request_id": request_id,
            "repeat": repeat, "built": False,
            "packet_path": packet_path.relative_to(root).as_posix() if _under(packet_path, root) else str(packet_path),
            "packet_sha256": None,
            "counter_path": counter_path.relative_to(root).as_posix() if _under(counter_path, root) else str(counter_path),
            "packet_chars": None}


def launch_prompt_for(entry: dict, paths: AgentPaths) -> str:
    """The Agent call's prompt for a run: LAUNCH_PROMPT with the packet's absolute path (forward slashes, which Windows accepts)."""
    packet = paths.agent_dir.parent.parent / entry["packet_path"]
    return LAUNCH_PROMPT.format(packet_path=posix(packet))


def make_plan(set_name: str, request_ids: list, cells: tuple, paths: Optional[AgentPaths] = None, build: bool = True,
              refresh: bool = False, new_attempt: bool = False, quiet: bool = False) -> dict:
    """The plan for a set of runs (every request in every cell). With build=True: stage the arms, build every packet, register
    every counter. With build=False: names only, so nothing is staged, no packet or counter is written, and the entries say
    `built: false` with no hash. The plan is written to <agent folder>/<set_name>_plan.json either way. Returns the plan."""
    paths = paths or AgentPaths.default()
    say = (lambda *a, **k: None) if quiet else print
    request_ids = list(request_ids)
    if build:
        arms_needed = sorted({arm for _, arm in cells}, key=cfg.ARM_LABELS.index)
        say(f"{set_name}: staging arms {', '.join(arms_needed)} ...")
        for arm in arms_needed:
            stage_arm(arm, paths, refresh=refresh, quiet=quiet)
    runs = []
    for alias, arm in cells:
        batch = f"{alias}-{AGENT_ARM_LABEL[arm]}"
        for request_id in request_ids:
            if build:
                entry = build_packet(request_id, arm, alias, 1, set_name, paths, new_attempt=new_attempt)
                entry["built"] = True
            else:
                entry = planned_entry(request_id, arm, alias, set_name, paths)
            entry["batch"] = batch
            entry["launch_prompt"] = launch_prompt_for(entry, paths)
            runs.append(entry)
        say(f"  batch {batch}: {len(request_ids)} {'packets' if build else 'runs planned (packets not built)'}")
    plan = {
        "plan": set_name, "status": "built" if build else "planned: stage, packets and counters not built yet",
        "runs_total": len(runs), "task_instructions_version": cfg.TASK_INSTRUCTIONS_VERSION,
        "marker_version": pilot_marking_version(),
        "budgets": {"max_queries": cfg.MAX_QUERY_EXECUTIONS, "max_skill_loads": cfg.MAX_SKILL_LOADS, "max_skill_file_reads": cfg.MAX_SKILL_FILE_READS},
        "agent_models": cfg.AGENT_MODEL_IDS, "request_ids": request_ids, "cells": [list(cell) for cell in cells],
        "python": Path(sys.executable).as_posix(), "launch_prompt_template": LAUNCH_PROMPT, "launch_notes": LAUNCH_NOTES, "runs": runs,
    }
    plan_path = paths.agent_dir / f"{set_name}_plan.json"
    assert_inside_agent_dir(plan_path, paths)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    say(f"Plan with {len(runs)} runs written to {plan_path}")
    return plan


def pilot_marking_version() -> str:
    import pilot_marking
    return pilot_marking.MARKER_VERSION


def pilot2_plan(paths: Optional[AgentPaths] = None, refresh: bool = False, new_attempt: bool = False, quiet: bool = False) -> dict:
    """Stage S, D and L, build the 40 packets and register their counters, write pilot2_plan.json. Returns the plan."""
    return make_plan(cfg.PILOT2_NAME, cfg.PILOT2_REQUEST_IDS, cfg.PILOT2_CELLS, paths, True, refresh, new_attempt, quiet)


def pilot3_plan(paths: Optional[AgentPaths] = None, build: bool = True, refresh: bool = False, new_attempt: bool = False,
                quiet: bool = False) -> dict:
    """Pilot 3: with build=False only pilot3_plan.json is written (run ids, models, arms, requests, planned packet paths); with
    build=True the arms are staged, the 40 packets built and the counters registered, and the plan is rewritten with their hashes."""
    return make_plan(cfg.PILOT3_NAME, cfg.PILOT3_REQUEST_IDS, cfg.PILOT3_CELLS, paths, build, refresh, new_attempt, quiet)


def check_plan(plan_path: Path, paths: Optional[AgentPaths] = None, started_run_ids: Optional[set] = None) -> list:
    """Problems with a built plan, as sentences (empty is clean): every packet exists and still has the hash in the plan, every counter
    exists and is unused, every launch prompt is the template filled in for that packet, and the stage folders are clean.

    started_run_ids (the full run, mid-way): run ids whose counters are expected to have been used, because the run has a final message.
    Their counters may be used, but never past their own budget; every other run's counter must still be unused. A plan entry may carry
    `query_budget` and `task_instructions_version` (the full run has two budgets: 12 before the raise of 15 Oct 2026, 30 after);
    where it does not, the code's current values apply. The counter must agree with its entry."""
    paths = paths or AgentPaths.default()
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    root = paths.agent_dir.parent.parent
    started_run_ids = started_run_ids or set()
    problems = []
    if plan.get("task_instructions_version") != cfg.TASK_INSTRUCTIONS_VERSION:
        problems.append(f"plan was made with task text version {plan.get('task_instructions_version')}, the code has {cfg.TASK_INSTRUCTIONS_VERSION}")
    for run in plan["runs"]:
        if not run.get("built"):
            problems.append(f"{run['run_id']}: packet not built")
            continue
        packet = root / run["packet_path"]
        if not packet.is_file():
            problems.append(f"{run['run_id']}: packet file missing")
        elif sha256_bytes(packet.read_bytes()) != run["packet_sha256"]:
            problems.append(f"{run['run_id']}: packet changed since the plan was made")
        counter = root / run["counter_path"]
        if not counter.is_file():
            problems.append(f"{run['run_id']}: counter missing")
        else:
            data = json.loads(counter.read_text(encoding="utf-8"))
            expected_budget = run.get("query_budget", cfg.MAX_QUERY_EXECUTIONS)
            expected_version = run.get("task_instructions_version", cfg.TASK_INSTRUCTIONS_VERSION)
            if run["run_id"] in started_run_ids:
                if data.get("used", 0) > data.get("budget", 0):
                    problems.append(f"{run['run_id']}: counter shows {data.get('used')} queries used, over its budget of {data.get('budget')}")
            elif data.get("used") or data.get("refused"):
                problems.append(f"{run['run_id']}: counter already used ({data.get('used')} used, {data.get('refused', 0)} refused)")
            if data.get("budget") != expected_budget:
                problems.append(f"{run['run_id']}: counter budget is {data.get('budget')}, the plan says {expected_budget}")
            if data.get("task_instructions_version") != expected_version:
                problems.append(f"{run['run_id']}: counter task text version is {data.get('task_instructions_version')}, the plan says {expected_version}")
            if data.get("packet_sha256") != run["packet_sha256"]:
                problems.append(f"{run['run_id']}: counter holds another packet hash")
        if run.get("launch_prompt") != launch_prompt_for(run, paths):
            problems.append(f"{run['run_id']}: launch prompt is not the template filled in for this packet (moved folder?)")
    for arm in sorted({run["arm"] for run in plan["runs"]}, key=cfg.ARM_LABELS.index):
        problems += [f"stage/{AGENT_ARM_LABEL[arm]}: {problem}" for problem in verify_stage(arm, paths)]
    return problems


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv: list = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Stage the arms' files and build run packets for agent runs.")
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage", help="write the stage folders")
    stage.add_argument("--arms", default="S,D,L")
    stage.add_argument("--refresh", action="store_true")
    packet = commands.add_parser("packet", help="build one packet and register its run")
    packet.add_argument("--request", required=True)
    packet.add_argument("--arm", required=True, choices=cfg.ARM_LABELS)
    packet.add_argument("--model", required=True, choices=sorted(cfg.AGENT_MODEL_IDS))
    packet.add_argument("--repeat", type=int, default=1)
    packet.add_argument("--set", dest="set_name", default="adhoc")
    packet.add_argument("--new-attempt", action="store_true")
    pilot = commands.add_parser("pilot2", help="stage, build the 40 packets and write pilot2_plan.json")
    pilot.add_argument("--refresh", action="store_true")
    pilot.add_argument("--new-attempt", action="store_true")
    pilot3 = commands.add_parser("pilot3", help="write pilot3_plan.json; unless --plan-only, also stage, build the 40 packets and register the counters")
    pilot3.add_argument("--plan-only", action="store_true", help="names only: no stage, packets or counters")
    pilot3.add_argument("--refresh", action="store_true")
    pilot3.add_argument("--new-attempt", action="store_true")
    check = commands.add_parser("check", help="verify the stage folders")
    check.add_argument("--arms", default="S,D,L")
    check_plan_parser = commands.add_parser("check-plan", help="verify a built plan: packets, hashes, counters, launch prompts, stage folders")
    check_plan_parser.add_argument("--plan", required=True, help="plan name, for example pilot3 (the file data/agent_runs/<name>_plan.json)")
    args = parser.parse_args(argv)
    paths = AgentPaths.default()
    if args.command == "stage":
        for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
            stage_arm(arm, paths, refresh=args.refresh)
    elif args.command == "packet":
        entry = build_packet(args.request, args.arm, args.model, args.repeat, args.set_name, paths, new_attempt=args.new_attempt)
        print(json.dumps(entry, indent=1))
    elif args.command == "pilot2":
        pilot2_plan(paths, refresh=args.refresh, new_attempt=args.new_attempt)
    elif args.command == "pilot3":
        pilot3_plan(paths, build=not args.plan_only, refresh=args.refresh, new_attempt=args.new_attempt)
    elif args.command == "check-plan":
        plan_path = paths.agent_dir / f"{args.plan}_plan.json"
        if not plan_path.is_file():
            print(f"No plan file at {plan_path}.")
            return 1
        if args.plan == "full":
            # The full run has its own, wider check (frozen state, counts, order, rounds, every packet's contents).
            import build_full_plan
            problems = build_full_plan.check_full_plan(plan_path, paths)
        else:
            problems = check_plan(plan_path, paths)
        print(f"{plan_path.name}: " + ("clean" if not problems else f"{len(problems)} PROBLEMS"))
        for problem in problems[:60]:
            print("   " + problem)
        return 1 if problems else 0
    else:
        failed = False
        for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
            problems = verify_stage(arm, paths)
            print(f"stage/{AGENT_ARM_LABEL[arm]}: " + ("clean" if not problems else "PROBLEMS"))
            for problem in problems:
                print("   " + problem)
            failed = failed or bool(problems)
        return 1 if failed else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
