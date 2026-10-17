"""hx_script: run one of the skills library's Python scripts against the warehouse, counted with hx_sql's queries.

    python hx_script.py --run <run_id> <skill>/scripts/<name>.py [arguments after the database path]

    python hx_script.py --run <run_id> --put query.sql query-check/scripts/query_check.py --file query.sql --grain a,b <<'SQL'
    SELECT ...
    SQL

The agent-run counterpart of the API harness's run_script tool (harness.ToolBox._run_script), with the same fences:
  - only <skill>/scripts/<name>.py inside the staged library (stage/L/library); a bare file name works if one script has it;
  - the script runs with the interpreter in isolated mode (-I) through script_runner.py, so every DuckDB connection the
    script opens is read-only-by-lock (external access off, configuration locked), in a scratch folder of its own, with the
    API key, the lock password and anything else named like a secret removed from its environment;
  - the database path is supplied here: you pass arguments only, and a database path of your own is refused;
  - an argument may not point outside the session (absolute path or '..'); --file must name a file written with --put
    (standard input, up to 20000 characters, a plain file name);
  - a script call executes SQL, so it uses one of the run's query executions, the same budget as hx_sql.
Exit code: 0 the script ran and exited 0 or 1, 1 refused, 2 the budget is used up or the script failed badly.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True      # a staged tools folder must stay exactly as staged
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hx_common as hx                    # noqa: E402

SCRIPT_PATH_PATTERN = re.compile(r"^([a-z0-9][a-z0-9-]*)/scripts/([A-Za-z0-9_]+\.py)$")
SCRATCH_FILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
SECRET_ENV_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "ANTHROPIC", "CREDENTIAL", "HAPAX_LOCK", "HX_")


def script_environment() -> dict:
    """The parent's environment minus the API key, the lock password and anything else that looks like a secret."""
    return {name: value for name, value in os.environ.items()
            if not any(word in name.upper() for word in SECRET_ENV_WORDS)} | {"PYTHONIOENCODING": "utf-8"}


def resolve_script(library_dir: Path, name) -> "Path | None":
    """Map the model's script name to a script file under <skill>/scripts/ in the staged library, or None."""
    if not isinstance(name, str):
        return None
    cleaned = name.strip().replace("\\", "/")
    for prefix in ("<library>/", "arms/library/", "library/", "./"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    if "/" not in cleaned:  # a bare file name such as fiscal.py, if exactly one script has it
        matches = [path for path in library_dir.glob(f"*/scripts/{cleaned}") if path.is_file()]
        return matches[0].resolve() if len(matches) == 1 else None
    if not SCRIPT_PATH_PATTERN.match(cleaned):
        return None
    path = (library_dir / cleaned).resolve()
    return path if path.is_file() and library_dir in path.parents else None


def clean_script_args(args: list, scratch_dir: Path) -> tuple:
    """Validate the argument list. Returns (clean_args, error_text)."""
    if len(args) > 40:
        return None, "At most 40 arguments."
    cleaned = list(args)
    if cleaned and cleaned[0].lower().endswith(".duckdb"):
        cleaned = cleaned[1:]  # the database is supplied here
    previous = ""
    for token in cleaned:
        if len(token) > 8000:
            return None, "An argument is too long."
        if previous != "--sql":
            if token.lower().endswith(".duckdb"):
                return None, "The database path is supplied for you; do not pass one."
            if re.match(r"^([A-Za-z]:|/|\\)", token) or re.search(r"(^|[\\/])\.\.([\\/]|$)", token):
                return None, f"Argument {token!r} points outside the session; only plain arguments and files from --put are allowed."
        if previous == "--file":
            resolved = (scratch_dir / token).resolve()
            if scratch_dir.resolve() not in resolved.parents or not resolved.is_file():
                return None, f"--file {token!r} is not a file you supplied with --put."
        previous = token
    return cleaned, None


def main(argv: list = None) -> int:
    hx.reconfigure_output()
    parser = argparse.ArgumentParser(description="Run a library script (counted with the run's queries).")
    parser.add_argument("--run", required=True, help="the run id from your brief")
    parser.add_argument("--put", metavar="NAME", help="write standard input to this plain file name in the run's scratch folder first")
    parser.add_argument("script", help="<skill>/scripts/<name>.py")
    parser.add_argument("script_args", nargs=argparse.REMAINDER, help="arguments that come after the database path")
    args = parser.parse_args(argv)
    try:
        settings = hx.load_settings()
        run_id = hx.check_run_id(args.run)
        if not settings.get("scripts_allowed") or not settings.get("library_dir"):
            print("No script runner is available in this session.")
            return 1
        library_dir = Path(settings["library_dir"]).resolve()
        script = resolve_script(library_dir, args.script)
        if script is None:
            print(f"No script {args.script!r} in the library. Give <skill>/scripts/<name>.py.")
            return 1
        scratch_dir = Path(settings["scratch_dir"]) / run_id
        scratch_dir.mkdir(parents=True, exist_ok=True)
        if args.put:
            if not SCRATCH_FILE_NAME_PATTERN.match(args.put):
                print(f"Bad scratch file name {args.put!r}: plain names only.")
                return 1
            content = hx.read_stdin_text()
            if len(content) > 20000:
                print("Scratch file too long (20000 characters at most).")
                return 1
            (scratch_dir / args.put).write_text(content, encoding="utf-8")
        script_args, problem = clean_script_args(args.script_args, scratch_dir)
        if problem:
            print(problem)
            return 1
        allowed, number, used, budget = hx.reserve_execution(settings, run_id, "script", f"{script.relative_to(library_dir).as_posix()} {' '.join(script_args)}")
        if not allowed:
            print(hx.BUDGET_USED_UP_TEXT.format(used=used, budget=budget))
            return 2
        command = [sys.executable, "-I", str(settings["script_runner"]), str(script), str(Path(settings["warehouse"]).resolve()), *script_args]
        try:
            done = subprocess.run(command, cwd=str(scratch_dir), env=script_environment(), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=float(settings["script_timeout_s"]))
        except subprocess.TimeoutExpired:
            text = f"Script timed out after {settings['script_timeout_s']} seconds."
            hx.record_outcome(settings, run_id, number, False, text)
            print(text)
            print(f"[query {number} of {budget} used]")
            return 2
        output = done.stdout + (("\n[stderr]\n" + done.stderr) if done.stderr.strip() else "")
        limit = int(settings["script_output_char_limit"])
        if len(output) > limit:
            output = output[:limit] + "\n...[output cut]"
        output += f"\n[exit code {done.returncode}]"
        hx.record_outcome(settings, run_id, number, done.returncode < 2, output)
        print(output)
        print(f"[query {number} of {budget} used]")
        return 2 if done.returncode >= 2 else 0
    except hx.HxError as error:
        print(str(error))
        return 1


if __name__ == "__main__":
    sys.exit(main())
