"""Shared parts of the two agent-run commands (hx_sql.py and hx_script.py): settings, the per-run query counter, output.

Self-contained on purpose (standard library plus duckdb in the commands). build_agent_packets.py copies this file, the two
commands and script_runner.py into data/agent_runs/stage/<arm>/tools/ and writes hx_settings.json beside them, so a run
needs nothing from code/ and code/ can be locked while runs go on.

Where the settings come from, in order:
  1. the file named by the environment variable HX_SETTINGS_FILE (used by the tests only), with absolute paths;
  2. hx_settings.json next to this file (a staged tools folder), with paths relative to the case folder;
  3. config.py, when this file sits in code/ (so the commands can be run from the source tree).

The counter. Every run has a file data/agent_runs/counters/<run_id>.json, created when the packet is built. Each call
that reaches the database (a SQL statement, a library script) takes one of the run's executions BEFORE it runs, whether
or not it then works, exactly as the API harness counted run_sql calls. A call made when the budget is used up is
refused and recorded. A run id with no counter file is refused, so a made-up id gives no fresh budget. Writes are atomic
and guarded by a lock file, because a model may issue two commands at once. The rename that makes a write atomic is retried for
about two seconds when Windows refuses it with PermissionError (a file-sync client or another program holding the file; the pilot 2 fault),
and a count that cannot be written down stops the call before it runs, so a count is never lost (see _write_counter).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$")
SETTINGS_FILE_ENV = "HX_SETTINGS_FILE"
SETTINGS_FILE_NAME = "hx_settings.json"
LOCK_WAIT_SECONDS = 15.0
LOCK_STALE_SECONDS = 60.0
REPLACE_RETRY_SECONDS = 2.0   # how long a refused os.replace of the counter file is retried (PermissionError under a file-sync client)
REPLACE_FIRST_DELAY_SECONDS = 0.02
REPLACE_MAX_DELAY_SECONDS = 0.25
PREVIEW_CHARS = 1500         # how much of each call's output the counter keeps for diagnosis
STATEMENT_CHARS = 6000        # how much of each statement the counter keeps


class HxError(Exception):
    """A problem the command should report in a sentence (not a traceback)."""


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    """The run settings with every path made absolute. See the module docstring for where they come from."""
    override = os.environ.get(SETTINGS_FILE_ENV)
    if override:
        raw = json.loads(Path(override).read_text(encoding="utf-8"))
        return dict(raw)
    here = Path(__file__).resolve().parent
    staged = here / SETTINGS_FILE_NAME
    if staged.is_file():
        raw = json.loads(staged.read_text(encoding="utf-8"))
        # tools -> <arm> -> stage -> agent_runs -> data -> case folder
        return _absolute(raw, here, here.parents[4])
    sys.path.insert(0, str(here))
    import config as cfg                           # only reached from the source tree
    return {
        "warehouse": str(cfg.WAREHOUSE_PATH), "counters_dir": str(cfg.AGENT_COUNTERS_DIR), "scratch_dir": str(cfg.AGENT_SCRATCH_DIR),
        "library_dir": str(cfg.AGENT_STAGE_DIR / "L" / "library"), "script_runner": str(here / "script_runner.py"),
        "max_queries": cfg.MAX_QUERY_EXECUTIONS, "row_cap": cfg.SQL_RESULT_ROW_LIMIT, "cell_char_limit": cfg.SQL_CELL_CHAR_LIMIT,
        "sql_timeout_s": cfg.SQL_TIMEOUT_SECONDS, "memory_limit": cfg.SQL_MEMORY_LIMIT,
        "script_timeout_s": cfg.SCRIPT_TIMEOUT_SECONDS, "script_output_char_limit": cfg.SCRIPT_OUTPUT_CHAR_LIMIT,
        "scripts_allowed": True,
    }


def _absolute(raw: dict, tools_dir: Path, case_root: Path) -> dict:
    """Path settings in a staged hx_settings.json are relative to the case folder, so a moved or synced folder still works."""
    settings = dict(raw)
    for key in ("warehouse", "counters_dir", "scratch_dir", "library_dir"):
        if settings.get(key):
            settings[key] = str(case_root / settings[key])
    settings["script_runner"] = str(tools_dir / "script_runner.py")
    return settings


# ---------------------------------------------------------------------------
# The counter
# ---------------------------------------------------------------------------

def check_run_id(run_id) -> str:
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.match(run_id):
        raise HxError("--run needs the run id from your brief (letters, digits, '_', '-', '.').")
    return run_id


def counter_path(settings: dict, run_id: str) -> Path:
    return Path(settings["counters_dir"]) / f"{check_run_id(run_id)}.json"


class _FileLock:
    """A lock file taken with O_EXCL, retried for a few seconds; a lock older than a minute is treated as stale."""

    def __init__(self, target: Path):
        self.path = target.with_suffix(target.suffix + ".lock")

    def __enter__(self):
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                handle = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(handle)
                return self
            except (FileExistsError, PermissionError):
                # PermissionError: on Windows a lock file that is being deleted (or held by a file-sync client) refuses a new one for a moment
                try:
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE_SECONDS:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise HxError("Could not take the run's counter lock; try the command again.")
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


def _read_counter(path: Path) -> dict:
    if not path.is_file():
        raise HxError("This run id is not registered, so no query can be run. Use the run id in your brief exactly as written.")
    # A read can meet the same short hold as a write (PermissionError), or a half-written file if the in-place fallback of
    # _write_counter was used by another process at that moment (JSON error): wait and read again for up to the same time.
    deadline = time.monotonic() + REPLACE_RETRY_SECONDS
    while True:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (PermissionError, json.JSONDecodeError):
            if time.monotonic() >= deadline:
                raise HxError("The run's counter file could not be read (another program is holding it). "
                              "Nothing was run or counted; try the command again in a moment.")
            time.sleep(REPLACE_FIRST_DELAY_SECONDS)


def _replace_with_retry(source: Path, target: Path) -> None:
    """os.replace, retried when Windows refuses it with PermissionError because another program (a file-sync client, a virus scanner,
    a parallel agent's read) holds the target for a moment. Waits 20 ms, doubling to at most 250 ms, for up to REPLACE_RETRY_SECONDS in
    all, then raises the last PermissionError."""
    deadline = time.monotonic() + REPLACE_RETRY_SECONDS
    delay = REPLACE_FIRST_DELAY_SECONDS
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, REPLACE_MAX_DELAY_SECONDS)


def _write_counter(path: Path, data: dict) -> None:
    """Write the counter file so that a count is never lost.
    1. The new content goes to a temporary file of its own (the process id in its name, so two processes never share one).
    2. The temporary file replaces the counter, retried for about two seconds if Windows says PermissionError (the 15 Oct 2026
       pilot 2 fault: a file-sync client held the file and 19 of 40 runs saw a traceback, some after their query had already been counted).
    3. If the rename still fails, the content is written into the counter file itself, also retried.
    4. If that fails too, HxError is raised with the temporary file removed. Callers treat that as 'not recorded': a call that could
       not reserve its execution does not run (so nothing is spent that was not written down), and the old file is untouched."""
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    text = json.dumps(data, ensure_ascii=False, indent=1)
    try:
        try:
            temporary.write_text(text, encoding="utf-8")
            _replace_with_retry(temporary, path)
            return
        except PermissionError:
            pass
        # The rename was refused for the whole wait. Writing into the file itself may still be allowed (sharing rules differ for it).
        deadline = time.monotonic() + REPLACE_RETRY_SECONDS
        while True:
            try:
                path.write_text(text, encoding="utf-8")
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise HxError("The run's counter file could not be written (another program is holding it). "
                                  "Nothing was run or counted; try the command again in a moment.")
                time.sleep(REPLACE_MAX_DELAY_SECONDS)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def reserve_execution(settings: dict, run_id: str, kind: str, statement: str) -> tuple:
    """Take one execution for this run before it runs. Returns (allowed, call_number, used, budget).
    A refused call (budget used up) is recorded and gives allowed=False."""
    path = counter_path(settings, run_id)
    _read_counter(path)      # an unregistered run id is refused before anything else happens
    with _FileLock(path):
        data = _read_counter(path)
        budget = int(data["budget"])
        entry = {"kind": kind, "at": datetime.now().isoformat(timespec="seconds"), "statement": statement[:STATEMENT_CHARS]}
        if data["used"] >= budget:
            data["refused"] = data.get("refused", 0) + 1
            data["calls"].append({**entry, "n": None, "refused": True})
            try:
                _write_counter(path, data)
            except HxError:
                pass         # the refusal stands whether or not it could be written down (used is already at the budget)
            return False, None, data["used"], budget
        data["used"] += 1
        number = data["used"]
        data["calls"].append({**entry, "n": number})
        _write_counter(path, data)
        return True, number, number, budget


def record_outcome(settings: dict, run_id: str, call_number: int, ok: bool, output_text: str, rows=None) -> None:
    """Add the outcome to the call recorded by reserve_execution (kept for diagnosis; never read by the commands)."""
    path = counter_path(settings, run_id)
    try:
        with _FileLock(path):
            data = _read_counter(path)
            for call in data["calls"]:
                if call.get("n") == call_number:
                    call["ok"] = ok
                    call["rows"] = rows
                    call["output_preview"] = output_text[:PREVIEW_CHARS]
                    break
            _write_counter(path, data)
    except HxError:
        pass                 # the count was written when the call was reserved; only this diagnostic note is lost, and the agent still gets its result


def new_counter(arm: str, model: str, request_id: str, budget: int, packet_sha256: str, task_version: str) -> dict:
    return {"run_id": None, "arm": arm, "model": model, "request_id": request_id, "budget": budget, "used": 0, "refused": 0,
            "packet_sha256": packet_sha256, "task_instructions_version": task_version, "calls": []}


BUDGET_USED_UP_TEXT = ("Query budget used up ({used} of {budget}). No further queries can be run. "
                       "Give your final answer now as the JSON object.")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def reconfigure_output() -> None:
    """UTF-8 on stdout whatever the console says (store names carry a, o with dots), and no failure on odd characters."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def read_stdin_text() -> str:
    """Standard input decoded as UTF-8 (the default on Windows would be the console code page)."""
    return sys.stdin.buffer.read().decode("utf-8", errors="replace")


def format_cell(value, cell_char_limit: int) -> str:
    """One DuckDB cell as compact text: NULL, ISO dates, plain numbers, long text cut."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "NULL" if value != value else repr(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()[:cell_char_limit]
    text = str(value).replace("\r", " ").replace("\n", " ")
    return text if len(text) <= cell_char_limit else text[:cell_char_limit] + "...[cut]"


def format_table(columns: list, rows: list, truncated: bool, row_cap: int, cell_char_limit: int) -> str:
    """A compact table: header, then one line per row, cells separated by ' | '. A cut result says so in capitals."""
    lines = [" | ".join(columns)]
    lines += [" | ".join(format_cell(cell, cell_char_limit) for cell in row) for row in rows]
    lines.append(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")
    if truncated:
        lines.append(f"[ROW CAP: the result has more than {row_cap} rows and only the first {row_cap} are shown. "
                     "Add a filter, an aggregate or a LIMIT to see the rest.]")
    return "\n".join(lines)
