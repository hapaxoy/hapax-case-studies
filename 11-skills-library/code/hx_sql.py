"""hx_sql: run one read-only SELECT on the Tuomimetsa warehouse and print the result as a compact table.

    python hx_sql.py --run <run_id> <<'SQL'
    SELECT ...
    SQL

    python hx_sql.py --run <run_id> --sql "SELECT ..."

This is the agent-run counterpart of the API harness's run_sql tool (harness.ToolBox._run_sql) and keeps its rules:
  - the connection is read-only with external access switched off and the configuration locked, so no file can be read,
    written or attached and the setting cannot be switched back (the same lock as script_runner.py);
  - one statement per call, and only SELECT (including WITH) or EXPLAIN;
  - every call that reaches the database uses one of the run's executions (12) whether it works or not; parse errors and
    refused statements count, an empty statement does not; when the budget is used up the call is refused;
  - the result is cut at the row cap and says so in capitals under the table.
Exit code: 0 ran, 1 refused or an error in the statement, 2 the run's query budget is used up.
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

sys.dont_write_bytecode = True      # a staged tools folder must stay exactly as staged
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hx_common as hx                    # noqa: E402


def run_statement(settings: dict, sql: str) -> tuple:
    """Run one statement on a locked read-only connection. Returns (ok, text, row_count)."""
    try:
        import duckdb
    except ImportError:
        return False, "duckdb is not available in this Python. Use the python named in your brief.", None
    connection = duckdb.connect(str(settings["warehouse"]), read_only=True)
    try:
        # Lock the connection down: no file can be read, written or attached, and the setting cannot be flipped back.
        connection.execute("SET enable_external_access=false")
        connection.execute(f"SET memory_limit='{settings['memory_limit']}'")
        connection.execute("SET lock_configuration=true")
        try:
            statements = connection.extract_statements(sql)
        except Exception as error:
            return False, f"SQL error: {error}", None
        if len(statements) != 1:
            return False, "Run exactly one statement per call.", None
        if statements[0].type.name not in ("SELECT", "EXPLAIN"):
            return False, "Only SELECT (including WITH) and EXPLAIN statements are allowed; the warehouse is read-only.", None
        timer = threading.Timer(float(settings["sql_timeout_s"]), connection.interrupt)
        timer.start()
        try:
            cursor = connection.execute(sql)
            columns = [item[0] for item in cursor.description]
            fetched = cursor.fetchmany(int(settings["row_cap"]) + 1)
        except Exception as error:
            return False, f"SQL error: {error}", None
        finally:
            timer.cancel()
        row_cap = int(settings["row_cap"])
        truncated = len(fetched) > row_cap
        rows = fetched[:row_cap]
        return True, hx.format_table(columns, rows, truncated, row_cap, int(settings["cell_char_limit"])), len(rows)
    finally:
        connection.close()


def main(argv: list = None) -> int:
    hx.reconfigure_output()
    parser = argparse.ArgumentParser(description="Run one read-only SELECT on the warehouse (counted against the run's queries).")
    parser.add_argument("--run", required=True, help="the run id from your brief")
    parser.add_argument("--sql", help="the statement; if absent it is read from standard input")
    args = parser.parse_args(argv)
    try:
        settings = hx.load_settings()
        hx.check_run_id(args.run)
        sql = args.sql if args.sql is not None else (hx.read_stdin_text() if not sys.stdin.isatty() else "")
        if not sql.strip():
            print("No SQL given. Pass it on standard input (a here-document) or with --sql. Nothing was counted.")
            return 1
        allowed, number, used, budget = hx.reserve_execution(settings, args.run, "sql", sql)
        if not allowed:
            print(hx.BUDGET_USED_UP_TEXT.format(used=used, budget=budget))
            return 2
        ok, text, rows = run_statement(settings, sql)
        hx.record_outcome(settings, args.run, number, ok, text, rows)
        print(text)
        print(f"[query {number} of {budget} used]")
        return 0 if ok else 1
    except hx.HxError as error:
        print(str(error))
        return 1


if __name__ == "__main__":
    sys.exit(main())
