"""Phase 5 harness: run one request through one arm with the Anthropic Messages API and tool use.

What this module does
---------------------
run_one() takes a request, an arm (S, D, L or L-), a model ID and a model client, and runs one fresh session:

  S   schema only          the DDL with the warehouse's own column comments, and the run_sql tool
  D   shared prompt doc    S plus arms/prompt_doc.md, in the system prompt
  L   skills library       S plus the skill names and one-line descriptions in the system prompt, a load_skill tool
                           (SKILL.md first, then the skill's references and templates on request) and a run_script
                           tool for the library's scripts
  L-  library, no scripts  L without run_script and without the scripts folders (the ablation)

The loader is our own: no vendor skills runtime. The model gets the task wording from
config.TASK_INSTRUCTIONS and must reply with the JSON contract.

What the model can reach (isolation)
------------------------------------
Only the tools below, and each is fenced:
  run_sql      a read-only DuckDB connection with external access switched off and the configuration locked, so no
               file can be read, written or attached; one SELECT or EXPLAIN per call.
  load_skill   files inside the arm's own library folder (arms/library) and nowhere else.
  run_script   a script under <skill>/scripts/ in that library, run with the interpreter in isolated mode, in a scratch
               folder, with the API key and every other secret removed from its environment. The model supplies
               arguments only; the database path is supplied here. The script runs through script_runner.py, which
               gives every DuckDB connection the script opens the same lock as run_sql (query_check.py runs any SQL it
               is handed, so without the lock it would be a way to read files). A --file argument must name a file the
               model wrote through `files` into the scratch folder.
The prompt doc and the library are the only arm materials ever read; the builder's notes and tests are not in
either path and build_arm_materials() refuses a library folder that contains them.
The harness reads only the one request it is given. Nothing here opens data/key/ or the other test requests.

Budgets: config.MAX_QUERY_EXECUTIONS run_sql calls (every call counts, including ones that error) and
config.MAX_SKILL_LOADS distinct skills opened. A run_script call executes SQL, so it uses one query execution
(config.SCRIPT_CALLS_COUNT_AS_QUERIES). Reading more files of a skill already open is free, up to a safety cap.

Logging: one JSON-lines file per run under the output folder, flushed after every event, so a crash keeps the run up to
that point. Events: run_start, message, api_call, api_usage, tool_call, tool_result, run_end. Every run also appends one
summary line to runs_index.jsonl in the same folder.

Spending guard: before every API call the harness bounds the call's cost from above and does not make the call if
spend so far plus that bound would pass the ledger's cap (SpendLedger). A run stopped this way ends with status
cap_stop.

No network code lives here except AnthropicClient, which run_pilot.py builds only when a key is present.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

import duckdb

import config as cfg

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARM_FILENAME_LABEL = {"S": "S", "D": "D", "L": "L", "L-": "Lminus"}
# Names that must never appear anywhere under the library folder given to an arm (they name the incidents).
FORBIDDEN_ARM_NAMES = {"build_notes.md", "tests", "_scratch"}
PROVENANCE_MARKER_LINE = re.compile(r"^[ \t]*<!--\s*(?:facts|source)\s*:[^>]*?-->[ \t]*\r?\n?", re.MULTILINE)
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
SCRIPT_PATH_PATTERN = re.compile(r"^([a-z0-9][a-z0-9-]*)/scripts/([A-Za-z0-9_]+\.py)$")
SCRATCH_FILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
READABLE_SKILL_SUFFIXES = {".md", ".sql", ".csv", ".txt", ".json", ".py"}
SECRET_ENV_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "ANTHROPIC", "CREDENTIAL")
SCRIPT_RUNNER = Path(__file__).resolve().parent / "script_runner.py"   # runs a library script with locked DuckDB connections
FINAL_ANSWER_KEYS =("sql", "result", "definitions_applied", "assumptions", "caveats")


class ModelCallError(Exception):
    """A failed model call (network, status or request error). Carries the HTTP status when there is one."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

def normalise_usage(raw: Any) -> dict:
    """The four token counts the cost depends on, from an SDK usage object or a dict."""
    def pick(name: str) -> int:
        value = raw.get(name) if isinstance(raw, dict) else getattr(raw, name, None)
        return int(value or 0)
    return {
        "input_tokens": pick("input_tokens"),
        "cache_creation_input_tokens": pick("cache_creation_input_tokens"),
        "cache_read_input_tokens": pick("cache_read_input_tokens"),
        "output_tokens": pick("output_tokens"),
    }


def prices_for(model: str) -> dict:
    """Published prices for a model, with a clear error for a model that has none in config."""
    try:
        return cfg.MODEL_PRICES_USD_PER_MTOK[model]
    except KeyError:
        known = ", ".join(sorted(cfg.MODEL_PRICES_USD_PER_MTOK))
        raise SystemExit(f"No published price for model '{model}' in config.MODEL_PRICES_USD_PER_MTOK (known: {known}). "
                         "Add the price and the date it was read before running this model.")


def usage_cost_usd(usage: dict, model: str) -> float:
    """USD cost of one API call from its usage block at the published prices in config."""
    price = prices_for(model)
    return (usage["input_tokens"] * price["input"]
            + usage["cache_creation_input_tokens"] * price["cache_write_5m"]
            + usage["cache_read_input_tokens"] * price["cache_read"]
            + usage["output_tokens"] * price["output"]) / 1_000_000


def call_cost_upper_bound_usd(request_chars: int, model: str) -> float:
    """A bound the real cost of the next call cannot exceed: every input token as a cache write at a pessimistic
    characters-per-token figure, plus a full max_tokens of output."""
    price = prices_for(model)
    input_tokens = request_chars / cfg.PESSIMISTIC_CHARS_PER_TOKEN
    return (input_tokens * max(price["cache_write_5m"], price["input"])
            + cfg.MAX_OUTPUT_TOKENS * price["output"]) / 1_000_000


class SpendLedger:
    """Running total of money spent against a hard cap (USD). allows(x) asks whether x more may be spent."""

    def __init__(self, cap_usd: float, already_spent_usd: float = 0.0):
        self.cap_usd = float(cap_usd)
        self.spent_usd = float(already_spent_usd)

    def allows(self, additional_usd: float) -> bool:
        return self.spent_usd + additional_usd <= self.cap_usd

    def add(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd

    @property
    def remaining_usd(self) -> float:
        return self.cap_usd - self.spent_usd


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

def load_dev_requests(world_dir: Path = cfg.WORLD_DIR) -> dict:
    """Parse world/request_history/REQ-D*.md into {id: {"request": {...}, "accepted_sql": str, "note": str}}.
    The request dict has the keys the harness needs: id, received, requester, department, request_text."""
    history_dir = Path(world_dir) / "request_history"
    parsed = {}
    for path in sorted(history_dir.glob("REQ-D*.md")):
        text = path.read_text(encoding="utf-8")
        received = re.search(r"^- Received:\s*(\S+)", text, re.MULTILINE)
        sender = re.search(r"^- From:\s*(.+)$", text, re.MULTILINE)
        request_text = re.search(r"^## Request\s*\n+((?:>.*\n?)+)", text, re.MULTILINE)
        accepted = re.search(r"## Accepted query\s*\n+```sql\n(.*?)```", text, re.DOTALL)
        note = re.search(r"^## Note\s*\n+(.+?)\s*\Z", text, re.MULTILINE | re.DOTALL)
        if not (received and sender and request_text and accepted):
            raise ValueError(f"{path.name}: could not parse the request history entry")
        requester, department = [part.strip() for part in sender.group(1).split(",", 1)]
        body = " ".join(line.lstrip("> ").strip() for line in request_text.group(1).splitlines()).strip()
        parsed[path.stem] = {
            "request": {"id": path.stem, "received": received.group(1), "requester": requester,
                        "department": department, "request_text": body},
            "accepted_sql": accepted.group(1).strip(),
            "note": note.group(1).strip() if note else "",
        }
    return parsed


def load_test_request(request_id: str, requests_path: Path = cfg.REQUESTS_DIR / "test_requests.json") -> dict:
    """The one test request asked for, and nothing else from the file."""
    for entry in json.loads(Path(requests_path).read_text(encoding="utf-8")):
        if entry["id"] == request_id:
            return {key: entry[key] for key in ("id", "received", "requester", "department", "request_text")}
    raise KeyError(f"No test request with id {request_id}")


def task_text(request: dict) -> str:
    """The shared task wording (config.TASK_INSTRUCTIONS) filled in for one request. Identical for every arm."""
    return cfg.TASK_INSTRUCTIONS.format(
        max_queries=cfg.MAX_QUERY_EXECUTIONS, received_date=request["received"], requester=request["requester"],
        department=request["department"], request_text=request["request_text"])


# ---------------------------------------------------------------------------
# Arm materials: the static system prompt and the tool list for each arm
# ---------------------------------------------------------------------------

def strip_markers(text: str) -> str:
    """Drop the <!-- facts: --> and <!-- source: --> provenance lines. Applied alike to the doc and the library."""
    return PROVENANCE_MARKER_LINE.sub("", text) if cfg.STRIP_PROVENANCE_MARKERS else text


def parse_skill_header(skill_md: str) -> dict:
    """name and description from a SKILL.md front matter block."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", skill_md, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md has no front matter")
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    if "name" not in fields or "description" not in fields:
        raise ValueError("SKILL.md front matter needs name and description")
    return fields


TOOL_RUN_SQL = {
    "name": "run_sql",
    "description": ("Run one read-only SQL statement (DuckDB dialect) on the Tuomimetsä warehouse. Only SELECT (including WITH) "
                    f"and EXPLAIN are allowed. Returns JSON with the columns and rows (at most {cfg.SQL_RESULT_ROW_LIMIT} rows; "
                    "longer results are cut and say so). Every call uses one of your query executions."),
    "input_schema": {"type": "object", "properties": {"sql": {"type": "string", "description": "One SQL statement."}},
                     "required": ["sql"]},
}
TOOL_LOAD_SKILL = {
    "name": "load_skill",
    "description": ("Read a skill from the team's skills library. With only `skill`, returns the skill's SKILL.md and a list of the "
                    "other files bundled with it (references, SQL templates). With `path` as well, returns one of those files. "
                    f"Opening a skill for the first time uses one of your {cfg.MAX_SKILL_LOADS} skill loads; reading further files "
                    "of a skill you have already opened does not."),
    "input_schema": {"type": "object",
                     "properties": {"skill": {"type": "string", "description": "Skill name, as listed."},
                                    "path": {"type": "string", "description": "Optional file inside the skill, as listed, for example references/x.md or templates/y.sql."}},
                     "required": ["skill"]},
}
TOOL_RUN_SCRIPT = {
    "name": "run_script",
    "description": ("Run one of the library's Python scripts (read-only against the warehouse). The skills show command lines of the form "
                    "`python <library>/<skill>/scripts/<script>.py PATH_TO/tuomimetsa.duckdb ...`. Here, give `script` as "
                    "<skill>/scripts/<script>.py and `args` as the arguments that come after the database path; the database is supplied for "
                    "you. `files` may hold small text files to place beside the script run (for example a .sql file named in --file). "
                    "Returns the script's output. A script call executes SQL, so it uses one of your query executions."),
    "input_schema": {"type": "object",
                     "properties": {"script": {"type": "string", "description": "For example fiscal-calendar/scripts/fiscal.py"},
                                    "args": {"type": "array", "items": {"type": "string"}, "description": "Arguments after the database path."},
                                    "files": {"type": "object", "additionalProperties": {"type": "string"},
                                              "description": "Optional {file name: text} to write into the run's scratch folder."}},
                     "required": ["script"]},
}

PREAMBLE = ("You answer data requests for the Data & Analytics team by querying the company's DuckDB warehouse through the tools provided.\n"
            "The warehouse schema follows: the object definitions with the column comments the warehouse carries.")


@dataclass
class ArmMaterials:
    """What an arm sends on every call: the static system text, the tool definitions, and the library location."""
    arm: str
    system_text: str
    tools: list
    library_dir: Optional[Path]
    skill_names: list = field(default_factory=list)

    @property
    def sha256(self) -> str:
        blob = json.dumps({"system": self.system_text, "tools": self.tools}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def tool_names(self) -> list:
        return [tool["name"] for tool in self.tools]


def list_skill_dirs(library_dir: Path) -> list:
    """Skill folders (those with a SKILL.md), sorted by name."""
    return sorted(path for path in Path(library_dir).iterdir() if path.is_dir() and (path / "SKILL.md").is_file())


def check_library_is_clean(library_dir: Path) -> None:
    """Refuse a library folder that holds anything the arms must never see."""
    for path in Path(library_dir).rglob("*"):
        if path.name in FORBIDDEN_ARM_NAMES:
            raise RuntimeError(f"{path} must not be inside an arm's library folder (it is not arm material).")


def build_arm_materials(arm: str, world_dir: Path = cfg.WORLD_DIR, doc_path: Path = cfg.ARMS_DOC_PATH,
                        library_dir: Path = cfg.ARMS_LIBRARY_DIR) -> ArmMaterials:
    """Assemble the static system prompt and tools for one arm. Everything here is identical from run to run, so it
    caches (caching for the static parts, as a real deployment would)."""
    if arm not in cfg.ARM_LABELS:
        raise ValueError(f"Unknown arm '{arm}'. Arms are {cfg.ARM_LABELS}.")
    ddl = (Path(world_dir) / "schema_ddl.sql").read_text(encoding="utf-8")
    sections = [PREAMBLE, "## Warehouse schema\n\n" + ddl.strip()]
    tools = [TOOL_RUN_SQL]
    skill_names = []
    library = None
    if arm == "D":
        sections.append("## Team prompt document\n\nThe team's shared prompt document, which the whole team pastes into its assistant, follows.\n\n"
                        + strip_markers(Path(doc_path).read_text(encoding="utf-8")).strip())
    if arm in ("L", "L-"):
        library = Path(library_dir)
        check_library_is_clean(library)
        lines = []
        for skill_dir in list_skill_dirs(library):
            header = parse_skill_header((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
            skill_names.append(header["name"])
            lines.append(f"- {header['name']}: {header['description']}")
        intro = ("## Skills library\n\nThe team keeps a library of skills: instructions, reference files and validated SQL templates for recurring "
                 "request types. Only the names and descriptions are shown here. Use the load_skill tool to read a skill in full when a request needs it.")
        if arm == "L":
            tools += [TOOL_LOAD_SKILL, TOOL_RUN_SCRIPT]
            intro += " The library's check scripts can be run with the run_script tool."
        else:
            tools += [TOOL_LOAD_SKILL]
            intro += " No script runner is available in this session; where a skill mentions running a script, skip that step."
        sections.append(intro + "\n\n" + "\n".join(lines))
    return ArmMaterials(arm=arm, system_text="\n\n".join(sections), tools=tools, library_dir=library, skill_names=skill_names)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def json_safe(value: Any) -> Any:
    """Make one DuckDB cell JSON-serialisable (dates to ISO, decimals to floats, long text cut)."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return None if value != value else value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()[:cfg.SQL_CELL_CHAR_LIMIT]
    text = str(value)
    return text if len(text) <= cfg.SQL_CELL_CHAR_LIMIT else text[:cfg.SQL_CELL_CHAR_LIMIT] + "...[cut]"


def script_environment() -> dict:
    """Environment for a library script: the parent's, minus the API key and anything that looks like a secret."""
    return {name: value for name, value in os.environ.items()
            if not any(word in name.upper() for word in SECRET_ENV_WORDS)} | {"PYTHONIOENCODING": "utf-8"}


class ToolBox:
    """The tools of one run, with its budgets, scratch folder and counters."""

    def __init__(self, materials: ArmMaterials, warehouse_path: Path, scratch_dir: Path):
        self.materials = materials
        self.warehouse_path = Path(warehouse_path).resolve()
        self.scratch_dir = Path(scratch_dir)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir = materials.library_dir.resolve() if materials.library_dir else None
        self.scripts_allowed = materials.arm == "L"
        self.queries_used = 0
        self.skills_opened: list = []
        self.files_read = 0
        self.scripts_run: list = []
        self.refused_query_calls = 0
        self.connection = duckdb.connect(str(self.warehouse_path), read_only=True)
        # Lock the connection down: no file can be read, written or attached, and the setting cannot be flipped back.
        self.connection.execute("SET enable_external_access=false")
        self.connection.execute(f"SET memory_limit='{cfg.SQL_MEMORY_LIMIT}'")
        self.connection.execute("SET lock_configuration=true")

    def close(self) -> None:
        try:
            self.connection.close()
        finally:
            shutil.rmtree(self.scratch_dir, ignore_errors=True)

    # -- dispatch ----------------------------------------------------------

    @property
    def query_budget_left(self) -> int:
        return cfg.MAX_QUERY_EXECUTIONS - self.queries_used

    def execute(self, name: str, tool_input: Any) -> tuple:
        """Run one tool call. Returns (is_error, text). Never raises for a model mistake."""
        if name not in self.materials.tool_names:
            return True, f"Unknown tool '{name}'. Available tools: {', '.join(self.materials.tool_names)}."
        if not isinstance(tool_input, dict):
            return True, "Tool input must be a JSON object."
        try:
            if name == "run_sql":
                return self._run_sql(tool_input)
            if name == "load_skill":
                return self._load_skill(tool_input)
            return self._run_script(tool_input)
        except Exception as error:  # a harness fault must not end the run silently; report it to the model and the log
            return True, f"Tool error: {type(error).__name__}: {error}"

    def _refuse_query(self) -> tuple:
        self.refused_query_calls += 1
        return True, (f"Query budget used up ({cfg.MAX_QUERY_EXECUTIONS} of {cfg.MAX_QUERY_EXECUTIONS}). "
                      "No further queries can be run. Give your final answer now as the JSON object.")

    # -- run_sql -----------------------------------------------------------

    def _run_sql(self, tool_input: dict) -> tuple:
        sql = tool_input.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            return True, "run_sql needs a non-empty `sql` string."
        if self.queries_used >= cfg.MAX_QUERY_EXECUTIONS:
            return self._refuse_query()
        self.queries_used += 1
        try:
            statements = self.connection.extract_statements(sql)
        except Exception as error:
            return True, f"SQL error: {error}"
        if len(statements) != 1:
            return True, "Run exactly one statement per call."
        if statements[0].type.name not in ("SELECT", "EXPLAIN"):
            return True, "Only SELECT (including WITH) and EXPLAIN statements are allowed; the warehouse is read-only."
        timer = threading.Timer(cfg.SQL_TIMEOUT_SECONDS, self.connection.interrupt)
        timer.start()
        try:
            cursor = self.connection.execute(sql)
            columns = [item[0] for item in cursor.description]
            fetched = cursor.fetchmany(cfg.SQL_RESULT_ROW_LIMIT + 1)
        except Exception as error:
            return True, f"SQL error: {error}"
        finally:
            timer.cancel()
        truncated = len(fetched) > cfg.SQL_RESULT_ROW_LIMIT
        rows = [[json_safe(cell) for cell in row] for row in fetched[:cfg.SQL_RESULT_ROW_LIMIT]]
        payload = {"columns": columns, "rows": rows, "row_count": len(rows)}
        if truncated:
            payload["truncated"] = f"more than {cfg.SQL_RESULT_ROW_LIMIT} rows; only the first {cfg.SQL_RESULT_ROW_LIMIT} are shown"
        return False, json.dumps(payload, ensure_ascii=False)

    # -- load_skill --------------------------------------------------------

    def _skill_dir(self, name: Any) -> Optional[Path]:
        if not isinstance(name, str) or not SKILL_NAME_PATTERN.match(name) or self.library_dir is None:
            return None
        candidate = (self.library_dir / name).resolve()
        if candidate.parent != self.library_dir or not (candidate / "SKILL.md").is_file():
            return None
        return candidate

    def _visible_files(self, skill_dir: Path) -> list:
        """Files of a skill the model may read, as posix paths relative to the skill. In L- the scripts folder is absent."""
        files = []
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file() or path.name == "SKILL.md" or path.suffix not in READABLE_SKILL_SUFFIXES:
                continue
            relative = path.relative_to(skill_dir).as_posix()
            if relative.split("/")[0] == "scripts" and self.materials.arm != "L":
                continue
            files.append(relative)
        return files

    def _load_skill(self, tool_input: dict) -> tuple:
        skill_name = tool_input.get("skill")
        skill_dir = self._skill_dir(skill_name)
        if skill_dir is None:
            names = ", ".join(self.materials.skill_names)
            return True, f"No skill named {skill_name!r}. Skills: {names}."
        already_open = skill_name in self.skills_opened
        if not already_open and len(self.skills_opened) >= cfg.MAX_SKILL_LOADS:
            return True, f"Skill load budget used up ({cfg.MAX_SKILL_LOADS} skills opened). Work from what you have."
        relative = tool_input.get("path")
        if relative in (None, ""):
            target = skill_dir / "SKILL.md"
            visible = self._visible_files(skill_dir)
        else:
            if not isinstance(relative, str) or "\\" in relative or relative.startswith("/") or re.match(r"^[A-Za-z]:", relative):
                return True, "path must be a relative path inside the skill, with forward slashes."
            target = (skill_dir / relative).resolve()
            if skill_dir not in target.parents or relative not in self._visible_files(skill_dir) + ["SKILL.md"]:
                return True, f"No file {relative!r} in skill {skill_name}."
            visible = None
        if self.files_read >= cfg.MAX_SKILL_FILE_READS:
            return True, "File read limit for this session reached."
        if target.stat().st_size > cfg.SKILL_FILE_CHAR_LIMIT:
            return True, "File too large to return."
        text = target.read_text(encoding="utf-8")
        text = strip_markers(text) if target.suffix == ".md" else text
        if not already_open:
            self.skills_opened.append(skill_name)
        self.files_read += 1
        if visible is not None:
            listing = "\n".join(f"- {item}" for item in visible) or "(none)"
            text = text.rstrip() + f"\n\n---\nOther files in this skill (read with load_skill, passing path):\n{listing}\n"
        return False, text

    # -- run_script --------------------------------------------------------

    def resolve_script(self, name: Any) -> Optional[Path]:
        """Map the model's script name to a script file under <skill>/scripts/ in the library, or None."""
        if not self.scripts_allowed or self.library_dir is None or not isinstance(name, str):
            return None
        cleaned = name.strip().replace("\\", "/")
        for prefix in ("<library>/", "arms/library/", "library/", "./"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        if "/" not in cleaned:  # a bare file name such as fiscal.py, if exactly one script has it
            matches = [p for p in self.library_dir.glob(f"*/scripts/{cleaned}") if p.is_file()]
            return matches[0].resolve() if len(matches) == 1 else None
        if not SCRIPT_PATH_PATTERN.match(cleaned):
            return None
        path = (self.library_dir / cleaned).resolve()
        return path if path.is_file() and self.library_dir in path.parents else None

    def _clean_script_args(self, args: Any) -> tuple:
        """Validate the argument list. Returns (clean_args, error_text)."""
        if args is None:
            return [], None
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args) or len(args) > 40:
            return None, "args must be a list of at most 40 strings."
        cleaned = list(args)
        if cleaned and cleaned[0].lower().endswith(".duckdb"):
            cleaned = cleaned[1:]  # the database is supplied by the harness
        previous = ""
        for token in cleaned:
            if len(token) > 8000:
                return None, "An argument is too long."
            if previous != "--sql":
                if token.lower().endswith(".duckdb"):
                    return None, "The database path is supplied for you; do not pass one."
                if re.match(r"^([A-Za-z]:|/|\\)", token) or re.search(r"(^|[\\/])\.\.([\\/]|$)", token):
                    return None, f"Argument {token!r} points outside the session; only plain arguments and files from `files` are allowed."
            if previous == "--file":
                resolved = (self.scratch_dir / token).resolve()
                if self.scratch_dir.resolve() not in resolved.parents or not resolved.is_file():
                    return None, f"--file {token!r} is not a file you supplied through `files`."
            previous = token
        return cleaned, None

    def _run_script(self, tool_input: dict) -> tuple:
        if not self.scripts_allowed:
            return True, "No script runner is available in this session."
        script = self.resolve_script(tool_input.get("script"))
        if script is None:
            return True, f"No script {tool_input.get('script')!r} in the library. Give <skill>/scripts/<name>.py."
        files = tool_input.get("files") or {}
        if not isinstance(files, dict) or len(files) > 5:
            return True, "files must be an object with at most 5 entries."
        for file_name, content in files.items():
            if not isinstance(content, str) or len(content) > 20000 or not SCRATCH_FILE_NAME_PATTERN.match(file_name):
                return True, f"Bad scratch file {file_name!r}: plain names only, text up to 20000 characters."
        # Files are validated, then written, then the arguments are checked (a --file argument must name one of them).
        for file_name, content in files.items():
            (self.scratch_dir / file_name).write_text(content, encoding="utf-8")
        args, problem = self._clean_script_args(tool_input.get("args"))
        if problem:
            return True, problem
        if cfg.SCRIPT_CALLS_COUNT_AS_QUERIES:
            if self.queries_used >= cfg.MAX_QUERY_EXECUTIONS:
                return self._refuse_query()
            self.queries_used += 1
        command = [sys.executable, "-I", str(SCRIPT_RUNNER), str(script), str(self.warehouse_path), *args]
        self.scripts_run.append(script.relative_to(self.library_dir).as_posix())
        try:
            done = subprocess.run(command, cwd=str(self.scratch_dir), env=script_environment(), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=cfg.SCRIPT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return True, f"Script timed out after {cfg.SCRIPT_TIMEOUT_SECONDS} seconds."
        output = done.stdout + (("\n[stderr]\n" + done.stderr) if done.stderr.strip() else "")
        if len(output) > cfg.SCRIPT_OUTPUT_CHAR_LIMIT:
            output = output[:cfg.SCRIPT_OUTPUT_CHAR_LIMIT] + "\n...[output cut]"
        output += f"\n[exit code {done.returncode}]"
        return done.returncode >= 2, output


# ---------------------------------------------------------------------------
# Final answer
# ---------------------------------------------------------------------------

def parse_final_answer(text: str) -> tuple:
    """Parse the model's final message into the JSON contract. Returns (answer_or_None, problem_text)."""
    if not text or not text.strip():
        return None, "empty final message"
    candidate = text.strip()
    attempts = [candidate]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.DOTALL)
    if fenced:
        attempts.append(fenced.group(1))
    first, last = candidate.find("{"), candidate.rfind("}")
    if first != -1 and last > first:
        attempts.append(candidate[first:last + 1])
    parsed = None
    for attempt in attempts:
        try:
            parsed = json.loads(attempt)
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(parsed, dict):
        return None, "final message is not a JSON object"
    missing = [key for key in FINAL_ANSWER_KEYS if key not in parsed]
    if missing:
        return None, f"missing keys: {', '.join(missing)}"
    result = parsed["result"]
    if not (isinstance(result, dict) and isinstance(result.get("columns"), list) and isinstance(result.get("rows"), list)
            and all(isinstance(row, list) for row in result["rows"])):
        return None, "result is not {columns: [...], rows: [[...]]}"
    return parsed, ""


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class RunLog:
    """JSON-lines log of one run, flushed after every event."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.handle = open(self.path, "w", encoding="utf-8")

    def event(self, kind: str, **fields: Any) -> None:
        record = {"event": kind, "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                  "t_s": round(time.monotonic() - self.started, 3), **fields}
        self.handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()


def block_to_param(block: dict) -> dict:
    """An assistant content block as the API wants it back in the next request (thinking blocks unchanged)."""
    kind = block.get("type")
    if kind == "text":
        return {"type": "text", "text": block.get("text", "")}
    if kind == "tool_use":
        return {"type": "tool_use", "id": block["id"], "name": block["name"], "input": block.get("input", {})}
    if kind == "thinking":
        return {"type": "thinking", "thinking": block.get("thinking", ""), "signature": block.get("signature", "")}
    if kind == "redacted_thinking":
        return {"type": "redacted_thinking", "data": block.get("data", "")}
    return dict(block)


def with_cache_marker(messages: list) -> list:
    """A copy of the messages with the moving cache breakpoint on the last content block, from the second call on."""
    if len(messages) < 2:
        return messages
    marked = copy.deepcopy(messages)
    last_block = marked[-1]["content"][-1]
    last_block["cache_control"] = {"type": "ephemeral"}
    return marked


def warehouse_fingerprint() -> dict:
    try:
        manifest = json.loads(cfg.MANIFEST_PATH.read_text(encoding="utf-8"))
        return {"content_hash": manifest.get("content_hash"), "duckdb_version": manifest.get("duckdb_version")}
    except (OSError, json.JSONDecodeError):
        return {"content_hash": None, "duckdb_version": None}


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def make_run_id(model: str, arm: str, request_id: str, repeat: int) -> str:
    return f"{model}__{ARM_FILENAME_LABEL[arm]}__{request_id}__r{repeat}"


def run_one(*, request: dict, arm: str, model: str, repeat: int = 1, client: Any, out_dir: Path,
            warehouse_path: Path = cfg.WAREHOUSE_PATH, materials: Optional[ArmMaterials] = None,
            ledger: Optional[SpendLedger] = None, run_id: Optional[str] = None, log_label: str = "") -> dict:
    """Run one request through one arm in a fresh session. Returns the run summary (also the last line of its log
    and a line in runs_index.jsonl). Never raises for a model, tool or API failure; those end the run with a status."""
    out_dir = Path(out_dir)
    prices_for(model)  # fail early on a model with no published price
    materials = materials or build_arm_materials(arm)
    run_id = run_id or make_run_id(model, arm, request["id"], repeat)
    log_path = out_dir / f"{run_id}.jsonl"
    if log_path.exists():  # keep an earlier attempt of the same run (for example one stopped by the cap)
        attempt = 1
        while (out_dir / f"{run_id}.attempt{attempt}.jsonl").exists():
            attempt += 1
        log_path.rename(out_dir / f"{run_id}.attempt{attempt}.jsonl")
    log = RunLog(log_path)
    prompt_dir = out_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / f"{ARM_FILENAME_LABEL[arm]}__{materials.sha256[:12]}.txt"
    if not prompt_file.exists():
        prompt_file.write_text(materials.system_text + "\n\n[tools]\n" + json.dumps(materials.tools, indent=1, ensure_ascii=False),
                               encoding="utf-8")
    scratch = out_dir / "_scratch" / run_id
    toolbox = ToolBox(materials, warehouse_path, scratch)
    started = time.monotonic()
    extras = dict(cfg.MODEL_REQUEST_EXTRAS.get(model, {}))
    system_blocks = [{"type": "text", "text": materials.system_text, "cache_control": {"type": "ephemeral"}}]
    user_text = task_text(request)
    messages: list = [{"role": "user", "content": [{"type": "text", "text": user_text}]}]
    totals = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0}
    run_cost = 0.0
    api_seconds = 0.0
    turns = 0
    status = "no_answer_turns"
    problem = ""
    final_text = ""
    answer = None
    model_returned = None
    first_turn_usage = None
    stop_reasons = []
    log.event("run_start", run_id=run_id, label=log_label, arm=arm, model_requested=model, repeat=repeat,
              request=request, tools=materials.tool_names, system_sha256=materials.sha256, prompt_file=prompt_file.name,
              system_chars=len(materials.system_text), client_kind=getattr(client, "kind", "unknown"),
              budgets={"max_queries": cfg.MAX_QUERY_EXECUTIONS, "max_skill_loads": cfg.MAX_SKILL_LOADS,
                       "max_turns": cfg.MAX_TURNS, "max_output_tokens": cfg.MAX_OUTPUT_TOKENS},
              request_extras=extras, harness_version=cfg.HARNESS_VERSION, warehouse=warehouse_fingerprint(),
              prices_usd_per_mtok=prices_for(model), prices_read_on=cfg.PRICES_READ_ON)
    log.event("message", role="user", content=messages[0]["content"])
    try:
        for turn in range(1, cfg.MAX_TURNS + 1):
            request_messages = with_cache_marker(messages)
            request_chars = len(json.dumps(system_blocks, ensure_ascii=False)) + len(json.dumps(materials.tools, ensure_ascii=False)) \
                + len(json.dumps(request_messages, ensure_ascii=False))
            bound = call_cost_upper_bound_usd(request_chars, model)
            if ledger is not None and not ledger.allows(bound):
                status = "cap_stop"
                problem = f"spending cap: next call could cost up to ${bound:.4f}, remaining ${ledger.remaining_usd:.4f}"
                break
            log.event("api_call", turn=turn, messages=len(request_messages), request_chars=request_chars, cost_bound_usd=round(bound, 5))
            call_started = time.monotonic()
            try:
                response = client.create(model=model, max_tokens=cfg.MAX_OUTPUT_TOKENS, system=system_blocks,
                                         tools=materials.tools, messages=request_messages, **extras)
            except ModelCallError as error:
                api_seconds += time.monotonic() - call_started
                status = "api_error"
                problem = f"{error} (status {error.status})"
                log.event("api_error", turn=turn, error=str(error), http_status=error.status)
                break
            latency = time.monotonic() - call_started
            api_seconds += latency
            turns += 1
            usage = normalise_usage(response.get("usage", {}))
            call_cost = usage_cost_usd(usage, model)
            run_cost += call_cost
            if ledger is not None:
                ledger.add(call_cost)
            for key in totals:
                totals[key] += usage[key]
            if first_turn_usage is None:
                first_turn_usage = dict(usage)
            model_returned = response.get("model") or model_returned
            stop_reasons.append(response.get("stop_reason"))
            log.event("api_usage", turn=turn, usage=usage, cost_usd=round(call_cost, 6), model_returned=response.get("model"),
                      stop_reason=response.get("stop_reason"), latency_s=round(latency, 3), response_id=response.get("id"))
            content = [block_to_param(block) for block in response.get("content", [])]
            messages.append({"role": "assistant", "content": content})
            log.event("message", role="assistant", content=content)
            tool_uses = [block for block in content if block["type"] == "tool_use"]
            if not tool_uses:
                final_text = "".join(block["text"] for block in content if block["type"] == "text")
                if response.get("stop_reason") == "refusal":
                    status, problem = "refusal", "model refused"
                elif response.get("stop_reason") == "max_tokens":
                    status, problem = "malformed", "output cut at max_tokens"
                else:
                    answer, problem = parse_final_answer(final_text)
                    status = "ok" if answer is not None else "malformed"
                break
            result_blocks = []
            for tool_use in tool_uses:
                log.event("tool_call", turn=turn, tool_use_id=tool_use["id"], name=tool_use["name"], input=tool_use["input"])
                tool_started = time.monotonic()
                is_error, text = toolbox.execute(tool_use["name"], tool_use["input"])
                log.event("tool_result", turn=turn, tool_use_id=tool_use["id"], name=tool_use["name"], is_error=is_error,
                          content=text, elapsed_ms=round((time.monotonic() - tool_started) * 1000),
                          queries_used=toolbox.queries_used, skills_opened=len(toolbox.skills_opened))
                block = {"type": "tool_result", "tool_use_id": tool_use["id"], "content": text}
                if is_error:
                    block["is_error"] = True
                result_blocks.append(block)
            messages.append({"role": "user", "content": result_blocks})
            log.event("message", role="user", content=result_blocks)
            if toolbox.refused_query_calls >= cfg.MAX_REFUSED_CALLS_AFTER_BUDGET:
                status, problem = "no_answer_budget", "kept calling tools after the query budget was used up"
                break
        else:
            status, problem = "no_answer_turns", f"no final answer within {cfg.MAX_TURNS} calls"
    finally:
        elapsed = time.monotonic() - started
        creation_first = first_turn_usage["cache_creation_input_tokens"] if first_turn_usage else 0
        read_first = first_turn_usage["cache_read_input_tokens"] if first_turn_usage else 0
        price = prices_for(model)
        # What the run would have cost with the static prefix already cached (a cold first call is a pilot artefact).
        steady_cost = run_cost - creation_first * (price["cache_write_5m"] - price["cache_read"]) / 1_000_000
        summary = {
            "run_id": run_id, "label": log_label, "arm": arm, "model_requested": model, "model_returned": model_returned,
            "request_id": request["id"], "repeat": repeat, "status": status, "problem": problem,
            "answer": answer, "final_text": final_text if status != "ok" else None,
            "turns": turns, "queries_used": toolbox.queries_used, "skills_opened": list(toolbox.skills_opened),
            "files_read": toolbox.files_read, "scripts_run": list(toolbox.scripts_run),
            "refused_query_calls": toolbox.refused_query_calls,
            "tokens": dict(totals), "first_turn_prefix_tokens": creation_first + read_first,
            "first_turn_cache_creation_tokens": creation_first,
            "cost_usd": round(run_cost, 6), "cost_usd_warm_prefix": round(steady_cost, 6),
            "elapsed_s": round(elapsed, 2), "api_seconds": round(api_seconds, 2),
            "stop_reasons": stop_reasons, "client_kind": getattr(client, "kind", "unknown"),
            "log_file": log_path.name,
        }
        log.event("run_end", **summary)
        log.close()
        toolbox.close()
        with open(out_dir / "runs_index.jsonl", "a", encoding="utf-8") as index_file:
            index_file.write(json.dumps({key: value for key, value in summary.items() if key != "answer"} | {"answer_present": answer is not None},
                                        ensure_ascii=False, default=str) + "\n")
    return summary


# ---------------------------------------------------------------------------
# The real client (the only code that touches the network)
# ---------------------------------------------------------------------------

class AnthropicClient:
    """Thin wrapper over anthropic.Anthropic().messages.create that returns plain dicts. Built by run_pilot.py only
    when ANTHROPIC_API_KEY is present."""

    kind = "anthropic-api"

    def __init__(self, api_key: str, http_client: Any = None, max_retries: Optional[int] = None):
        import anthropic  # imported here so the dry run and the tests never need a key or a network
        self._anthropic = anthropic
        retries = cfg.API_MAX_RETRIES if max_retries is None else max_retries
        extra = {"http_client": http_client} if http_client is not None else {}   # tests pass a mock transport here
        self._client = anthropic.Anthropic(api_key=api_key, timeout=cfg.API_TIMEOUT_SECONDS, max_retries=retries, **extra)

    def create(self, **request: Any) -> dict:
        try:
            response = self._client.messages.create(**request)
        except self._anthropic.APIError as error:
            raise ModelCallError(f"{type(error).__name__}: {error}", status=getattr(error, "status_code", None)) from error
        blocks = []
        for block in response.content:
            if block.type == "text":
                blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                blocks.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
            elif block.type == "thinking":
                blocks.append({"type": "thinking", "thinking": block.thinking, "signature": block.signature})
            elif block.type == "redacted_thinking":
                blocks.append({"type": "redacted_thinking", "data": block.data})
            else:
                blocks.append(block.model_dump(exclude_none=True))
        return {"id": response.id, "model": response.model, "stop_reason": response.stop_reason,
                "content": blocks, "usage": normalise_usage(response.usage)}
