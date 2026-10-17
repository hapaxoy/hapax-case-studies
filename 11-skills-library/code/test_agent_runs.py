"""Tests for the agent-run tooling: hx_sql, hx_script, staging and packets, the lock, collection, marking, the flag proposal.

    python code/test_agent_runs.py            (Python 3.10 with duckdb and pandas; no key, no network, no model)

Everything is written under a temporary folder. The real case folder is only read (the warehouse, world/, arms/, the key).
The staged tools are run for real as subprocesses from a staged copy, so the settings that resolve paths relative to the case
folder are tested the way a run uses them.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

CODE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE_DIR))

import build_agent_packets as bp          # noqa: E402
import collect_agent_answer as collect    # noqa: E402
import config as cfg                      # noqa: E402
import harness                            # noqa: E402
import hx_common                          # noqa: E402
import lock_answers as lock               # noqa: E402
import pilot_marking                      # noqa: E402
import propose_required_flags as proposal # noqa: E402

TEST_PASSWORD = "unit-test-password-123"
BUDGET = cfg.MAX_QUERY_EXECUTIONS      # 30 since the raise of 15 Oct 2026 (12 before); the tools take it from the counter
DEV = harness.load_dev_requests()
ORIGINAL_CONNECT = socket.socket.connect
TMP_ROOT = None            # a temporary "case folder": TMP_ROOT/data/agent_runs is the agent folder under test
PATHS = None
EXPECTED = {}


def setUpModule() -> None:
    global TMP_ROOT, PATHS
    socket.socket.connect = lambda self, *a, **k: (_ for _ in ()).throw(AssertionError("network access attempted during the tests"))
    TMP_ROOT = Path(tempfile.mkdtemp(prefix="hx_tests_"))
    agent_dir = TMP_ROOT / "data" / "agent_runs"
    PATHS = bp.AgentPaths(agent_dir, cfg.WORLD_DIR, cfg.ARMS_DOC_PATH, cfg.ARMS_LIBRARY_DIR, cfg.WAREHOUSE_PATH)
    for arm in ("S", "D", "L", "L-"):
        bp.stage_arm(arm, PATHS, quiet=True)


def tearDownModule() -> None:
    socket.socket.connect = ORIGINAL_CONNECT
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


def expected_for(request_id: str) -> dict:
    if request_id not in EXPECTED:
        EXPECTED[request_id] = pilot_marking.compute_expected_set(cfg.WAREHOUSE_PATH, request_id, DEV[request_id]["accepted_sql"])
    return EXPECTED[request_id]


def run_tool(arm: str, script: str, *args, stdin: str = None, env_extra: dict = None) -> subprocess.CompletedProcess:
    """Run a staged tool exactly as an agent would (the staged copy, no test settings)."""
    env = {key: value for key, value in os.environ.items() if key != hx_common.SETTINGS_FILE_ENV}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(PATHS.arm_stage(arm) / "tools" / script), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", env=env, timeout=300)


_RUN_COUNTER = [0]


def new_run(arm: str = "S", alias: str = "sonnet", request_id: str = "REQ-D20", set_name: str = "t") -> str:
    """Register a fresh run (a unique repeat number) and return its run id."""
    _RUN_COUNTER[0] += 1
    entry = bp.build_packet(request_id, arm, alias, _RUN_COUNTER[0], set_name, PATHS)
    return entry["run_id"]


def counter_of(run_id: str) -> dict:
    return json.loads((PATHS.counters_dir / f"{run_id}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The shared task text
# ---------------------------------------------------------------------------

class TestSharedTaskText(unittest.TestCase):
    RULES = ("Return exactly the columns the request asks for, plus label columns", "One row per natural grain of the question",
             "No total or subtotal rows unless the request asks for a total", "No padding rows", "Percentages are numbers in percent units",
             "Name things as well as giving their IDs")

    def test_all_six_rules_and_the_version(self):
        for rule in self.RULES:
            self.assertIn(rule, cfg.TASK_INSTRUCTIONS)
        self.assertEqual(cfg.TASK_INSTRUCTIONS_VERSION, "4")
        self.assertEqual(BUDGET, 30)

    def test_version_3_adds_the_two_pilot_2_rules_exactly(self):
        fiscal = ('Fiscal calendar labels go in separate columns: `fiscal_year` as the warehouse writes it (FY2025/26), and the quarter, '
                  'period or week as a plain whole number (3, 7, 22). Never join them into one label such as "FY2025/26 P07", '
                  '"FY2024/25 Q1" or "FY2025/26 W15".')
        read_through = ('Before you reply, read the table against the wording of the request. If the request asks for one figure, the table '
                        'is one row; if your query returned a total row, a breakdown or helper columns the request did not ask for, take them out.')
        for bullet in (fiscal, read_through):
            self.assertIn("  - " + bullet + "\n", cfg.TASK_INSTRUCTIONS)
        # both sit inside the "result" list: after the version 2 rules and before the next key
        text = cfg.TASK_INSTRUCTIONS
        self.assertLess(text.index("Name things as well as giving their IDs"), text.index(fiscal))
        self.assertLess(text.index(fiscal), text.index(read_through))
        self.assertLess(text.index(read_through), text.index('- "definitions_applied"'))
        # the budgets and the correction line did not move
        self.assertIn("You may run up to {max_queries} queries.", text)
        self.assertEqual((cfg.MAX_QUERY_EXECUTIONS, cfg.MAX_SKILL_LOADS), (30, 6))

    def test_every_packet_carries_the_version_3_rules(self):
        for arm in ("S", "D", "L"):
            run_id = new_run(arm)
            text = (PATHS.packets_dir / "t" / f"{run_id}.txt").read_text(encoding="utf-8")
            self.assertIn('Never join them into one label such as "FY2025/26 P07"', text)
            self.assertIn("read the table against the wording of the request", text)

    def test_still_formats_and_keeps_the_earlier_lines(self):
        text = harness.task_text(DEV["REQ-D20"]["request"])
        self.assertIn(f"up to {BUDGET} queries", text)
        self.assertIn("correct for it in your answer and list every correction in `caveats`", text)
        self.assertIn('{"columns": [...], "rows": [[...], ...]}', text)

    def test_names_no_incident(self):
        import validate_world
        lowered = cfg.TASK_INSTRUCTIONS.lower()
        self.assertEqual([t for t in validate_world.incident_tokens() if t in lowered], [])


# ---------------------------------------------------------------------------
# hx_sql
# ---------------------------------------------------------------------------

class TestHxSql(unittest.TestCase):
    def test_runs_a_select_and_counts_it(self):
        run_id = new_run()
        done = run_tool("S", "hx_sql.py", "--run", run_id, stdin="SELECT 1 AS one, 'a' AS letter, NULL AS nothing")
        self.assertEqual(done.returncode, 0, done.stdout)
        lines = done.stdout.strip().splitlines()
        self.assertEqual(lines[0], "one | letter | nothing")
        self.assertEqual(lines[1], "1 | a | NULL")
        self.assertIn("(1 row)", lines)
        self.assertEqual(lines[-1], f"[query 1 of {BUDGET} used]")
        self.assertEqual(counter_of(run_id)["used"], 1)

    def test_row_cap_is_visible(self):
        run_id = new_run()
        done = run_tool("S", "hx_sql.py", "--run", run_id, "--sql", "SELECT * FROM range(500)")
        self.assertEqual(done.returncode, 0)
        self.assertIn("[ROW CAP: the result has more than 200 rows and only the first 200 are shown.", done.stdout)
        self.assertIn("(200 rows)", done.stdout)
        done = run_tool("S", "hx_sql.py", "--run", run_id, "--sql", "SELECT * FROM range(200)")
        self.assertNotIn("ROW CAP", done.stdout)

    def test_non_ascii_goes_in_and_out_as_utf8(self):
        run_id = new_run()
        done = run_tool("S", "hx_sql.py", "--run", run_id, stdin="SELECT store_name FROM dim_store WHERE store_name LIKE '%Pitäjänmäki%' LIMIT 1")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("Helsinki Pitäjänmäki", done.stdout)

    def test_refusals_count_as_executions(self):
        run_id = new_run()
        refused = ["CREATE TABLE x AS SELECT 1", "SELECT 1; SELECT 2", "INSERT INTO dim_store SELECT * FROM dim_store", "SELECT FROM WHERE"]
        for sql in refused:
            done = run_tool("S", "hx_sql.py", "--run", run_id, "--sql", sql)
            self.assertEqual(done.returncode, 1, sql)
        self.assertEqual(counter_of(run_id)["used"], len(refused))

    def test_empty_statement_is_not_counted(self):
        run_id = new_run()
        done = run_tool("S", "hx_sql.py", "--run", run_id, "--sql", "   ")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(counter_of(run_id)["used"], 0)

    def test_file_access_is_locked(self):
        run_id = new_run()
        key_file = (cfg.KEY_DIR / "key.json").as_posix()
        statements = [f"SELECT * FROM read_text('{key_file}')", f"SELECT * FROM read_csv('{key_file}')", "SELECT * FROM glob('*')",
                      "COPY (SELECT 1) TO 'x.csv'", f"ATTACH '{cfg.WAREHOUSE_PATH.as_posix()}' AS other", "SET enable_external_access=true",
                      "INSTALL httpfs"]
        for sql in statements:
            done = run_tool("S", "hx_sql.py", "--run", run_id, "--sql", sql)
            self.assertEqual(done.returncode, 1, f"{sql} -> {done.stdout}")
        # the lock cannot be switched back, and the failed attempts did not leave a file behind
        self.assertFalse((Path.cwd() / "x.csv").exists())

    def test_budget_of_thirty_then_refused(self):
        run_id = new_run()
        for number in range(1, BUDGET + 1):
            done = run_tool("S", "hx_sql.py", "--run", run_id, "--sql", f"SELECT {number}")
            self.assertEqual(done.returncode, 0)
            self.assertTrue(done.stdout.strip().endswith(f"[query {number} of {BUDGET} used]"))
        done = run_tool("S", "hx_sql.py", "--run", run_id, "--sql", f"SELECT {BUDGET + 1}")
        self.assertEqual(done.returncode, 2)
        self.assertIn(f"Query budget used up ({BUDGET} of {BUDGET})", done.stdout)
        data = counter_of(run_id)
        self.assertEqual((data["used"], data["refused"]), (BUDGET, 1))
        self.assertTrue(data["calls"][-1]["refused"])

    def test_unregistered_run_id_gets_no_budget(self):
        done = run_tool("S", "hx_sql.py", "--run", "made-up-id", "--sql", "SELECT 1")
        self.assertEqual(done.returncode, 1)
        self.assertIn("not registered", done.stdout)
        self.assertFalse((PATHS.counters_dir / "made-up-id.json").exists())
        done = run_tool("S", "hx_sql.py", "--run", "../../escape", "--sql", "SELECT 1")
        self.assertEqual(done.returncode, 1)

    def test_parallel_calls_are_all_counted_once(self):
        run_id = new_run()
        results = []

        def call(number: int) -> None:
            results.append(run_tool("S", "hx_sql.py", "--run", run_id, "--sql", f"SELECT {number}"))
        threads = [threading.Thread(target=call, args=(n,)) for n in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertTrue(all(r.returncode == 0 for r in results), [r.stdout for r in results])
        data = counter_of(run_id)
        self.assertEqual(data["used"], 6)
        self.assertEqual(sorted(call["n"] for call in data["calls"]), [1, 2, 3, 4, 5, 6])

    def test_audit_keeps_the_sql_and_a_preview(self):
        run_id = new_run()
        run_tool("S", "hx_sql.py", "--run", run_id, "--sql", "SELECT 42 AS answer")
        call = counter_of(run_id)["calls"][0]
        self.assertEqual(call["statement"], "SELECT 42 AS answer")
        self.assertTrue(call["ok"])
        self.assertIn("42", call["output_preview"])

    def test_cell_formatting(self):
        from datetime import date
        from decimal import Decimal
        self.assertEqual(hx_common.format_cell(None, 200), "NULL")
        self.assertEqual(hx_common.format_cell(Decimal("12.50"), 200), "12.50")
        self.assertEqual(hx_common.format_cell(date(2026, 10, 5), 200), "2026-10-05")
        self.assertEqual(hx_common.format_cell(12.5, 200), "12.5")
        self.assertEqual(hx_common.format_cell("a\nb", 200), "a b")
        self.assertTrue(hx_common.format_cell("x" * 300, 200).endswith("...[cut]"))
        self.assertEqual(hx_common.format_table(["a"], [[1], [2]], False, 200, 200), "a\n1\n2\n(2 rows)")

    def test_runs_from_the_source_tree_too(self):
        """hx_sql.py in code/ falls back to config.py; the counter there is the real counters folder, so use a registered temp run
        through the settings override instead of touching real state."""
        run_id = new_run()
        settings = {"warehouse": str(cfg.WAREHOUSE_PATH), "counters_dir": str(PATHS.counters_dir), "scratch_dir": str(PATHS.scratch_dir),
                    "library_dir": None, "max_queries": BUDGET, "row_cap": 3, "cell_char_limit": 50, "sql_timeout_s": 60, "memory_limit": "1GB",
                    "script_timeout_s": 60, "script_output_char_limit": 1000, "scripts_allowed": False}
        settings_file = TMP_ROOT / "override.json"
        settings_file.write_text(json.dumps(settings), encoding="utf-8")
        done = subprocess.run([sys.executable, str(CODE_DIR / "hx_sql.py"), "--run", run_id, "--sql", "SELECT * FROM range(10)"],
                              capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, HX_SETTINGS_FILE=str(settings_file)))
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("more than 3 rows", done.stdout)


# ---------------------------------------------------------------------------
# hx_script
# ---------------------------------------------------------------------------

class ExclusiveHold:
    """Hold a file open with no sharing at all (Windows), as a file-sync client did for a moment in pilot 2: reading it, writing it,
    renaming over it and deleting it are all refused with PermissionError until release() is called."""

    def __init__(self, path: Path):
        import ctypes
        from ctypes import wintypes
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateFileW.restype = wintypes.HANDLE
        self.kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                              wintypes.DWORD, wintypes.HANDLE]
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        generic_read_write, no_sharing, open_existing, attribute_normal = 0x80000000 | 0x40000000, 0, 3, 0x80
        self.handle = self.kernel32.CreateFileW(str(path), generic_read_write, no_sharing, None, open_existing, attribute_normal, None)
        if self.handle is None or self.handle == ctypes.c_void_p(-1).value:
            raise OSError(f"could not hold {path}: error {ctypes.get_last_error()}")

    def release(self) -> None:
        if self.handle is not None:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


class TestCounterWriteRetry(unittest.TestCase):
    """The pilot 2 fault: os.replace of the counter file refused with PermissionError while a file-sync client held it. The write now retries,
    and a count that cannot be written stops the call before it runs, so a count is never lost."""

    def settings(self) -> dict:
        return {"counters_dir": str(PATHS.counters_dir)}

    def leftovers(self, run_id: str) -> list:
        return sorted(path.name for path in PATHS.counters_dir.glob(f"{run_id}.json*") if path.name != f"{run_id}.json")

    def test_replace_refused_a_few_times_then_allowed(self):
        run_id = new_run()
        real_replace, refusals = os.replace, [0]

        def flaky(source, target):
            if refusals[0] < 4:
                refusals[0] += 1
                raise PermissionError(5, "Access is denied")
            return real_replace(source, target)
        with mock.patch.object(hx_common.os, "replace", side_effect=flaky):
            allowed, number, used, budget = hx_common.reserve_execution(self.settings(), run_id, "sql", "SELECT 1")
            hx_common.record_outcome(self.settings(), run_id, number, True, "1", 1)
        self.assertGreaterEqual(refusals[0], 4)
        self.assertEqual((allowed, number, used, budget), (True, 1, 1, BUDGET))
        data = counter_of(run_id)
        self.assertEqual((data["used"], len(data["calls"]), data["calls"][0]["ok"]), (1, 1, True))
        self.assertEqual(self.leftovers(run_id), [])

    def test_rename_refused_for_the_whole_wait_falls_back_to_writing_in_place(self):
        run_id = new_run()
        with mock.patch.object(hx_common, "REPLACE_RETRY_SECONDS", 0.3), \
                mock.patch.object(hx_common.os, "replace", side_effect=PermissionError(5, "Access is denied")):
            allowed, number, used, _ = hx_common.reserve_execution(self.settings(), run_id, "sql", "SELECT 1")
        self.assertEqual((allowed, number, used), (True, 1, 1))
        self.assertEqual(counter_of(run_id)["used"], 1)
        self.assertEqual(self.leftovers(run_id), [])

    def test_a_count_that_cannot_be_written_stops_the_call_and_spends_nothing(self):
        run_id = new_run()
        counter_file = PATHS.counters_dir / f"{run_id}.json"
        real_write_text = Path.write_text

        def refuse_the_counter(self, *args, **kwargs):
            if self == counter_file:
                raise PermissionError(5, "Access is denied")
            return real_write_text(self, *args, **kwargs)
        with mock.patch.object(hx_common, "REPLACE_RETRY_SECONDS", 0.3), \
                mock.patch.object(hx_common.os, "replace", side_effect=PermissionError(5, "Access is denied")), \
                mock.patch.object(Path, "write_text", refuse_the_counter):
            with self.assertRaises(hx_common.HxError) as raised:
                hx_common.reserve_execution(self.settings(), run_id, "sql", "SELECT 1")
        self.assertIn("Nothing was run or counted", str(raised.exception))
        self.assertEqual(counter_of(run_id)["used"], 0)        # nothing was spent that was not written down
        self.assertEqual(self.leftovers(run_id), [])

    def test_a_lost_outcome_note_never_loses_the_count(self):
        run_id = new_run()
        allowed, number, used, _ = hx_common.reserve_execution(self.settings(), run_id, "sql", "SELECT 1")
        counter_file = PATHS.counters_dir / f"{run_id}.json"
        real_write_text = Path.write_text

        def refuse_the_counter(self, *args, **kwargs):
            if self == counter_file:
                raise PermissionError(5, "Access is denied")
            return real_write_text(self, *args, **kwargs)
        with mock.patch.object(hx_common, "REPLACE_RETRY_SECONDS", 0.3), \
                mock.patch.object(hx_common.os, "replace", side_effect=PermissionError(5, "Access is denied")), \
                mock.patch.object(Path, "write_text", refuse_the_counter):
            hx_common.record_outcome(self.settings(), run_id, number, True, "1", 1)       # must not raise
        data = counter_of(run_id)
        self.assertEqual((data["used"], len(data["calls"])), (1, 1))
        self.assertNotIn("ok", data["calls"][0])          # only the diagnostic note was lost

    @unittest.skipUnless(sys.platform == "win32", "needs Windows file sharing rules")
    def test_a_real_hold_on_the_file_for_half_a_second(self):
        """The counter is held with no sharing for 0.6 s. The call waits, then goes through, and every count is kept."""
        run_id = new_run()
        counter_file = PATHS.counters_dir / f"{run_id}.json"
        hold = ExclusiveHold(counter_file)
        timer = threading.Timer(0.6, hold.release)
        started = time.monotonic()
        timer.start()
        try:
            allowed, number, used, _ = hx_common.reserve_execution(self.settings(), run_id, "sql", "SELECT 1")
            waited = time.monotonic() - started
        finally:
            timer.join()
            hold.release()
        self.assertEqual((allowed, number, used), (True, 1, 1))
        self.assertGreaterEqual(waited, 0.5)
        self.assertEqual(counter_of(run_id)["used"], 1)
        self.assertEqual(self.leftovers(run_id), [])
        # a second call after the hold works as normal
        self.assertEqual(hx_common.reserve_execution(self.settings(), run_id, "sql", "SELECT 2")[2], 2)

    @unittest.skipUnless(sys.platform == "win32", "needs Windows file sharing rules")
    def test_a_real_hold_longer_than_the_wait_gives_a_sentence_and_spends_nothing(self):
        run_id = new_run()
        counter_file = PATHS.counters_dir / f"{run_id}.json"
        hold = ExclusiveHold(counter_file)
        try:
            with mock.patch.object(hx_common, "REPLACE_RETRY_SECONDS", 0.3):
                with self.assertRaises(hx_common.HxError):
                    hx_common.reserve_execution(self.settings(), run_id, "sql", "SELECT 1")
        finally:
            hold.release()
        self.assertEqual(counter_of(run_id)["used"], 0)
        self.assertEqual(self.leftovers(run_id), [])

    @unittest.skipUnless(sys.platform == "win32", "needs Windows file sharing rules")
    def test_the_staged_command_survives_a_hold_and_counts_once(self):
        """End to end, as an agent calls it: hx_sql.py while the counter is held for 0.6 s."""
        run_id = new_run()
        hold = ExclusiveHold(PATHS.counters_dir / f"{run_id}.json")
        timer = threading.Timer(0.6, hold.release)
        timer.start()
        try:
            done = run_tool("S", "hx_sql.py", "--run", run_id, "--sql", "SELECT 41 + 1 AS answer")
        finally:
            timer.join()
            hold.release()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("42", done.stdout)
        self.assertTrue(done.stdout.strip().endswith(f"[query 1 of {BUDGET} used]"))
        data = counter_of(run_id)
        self.assertEqual((data["used"], data["calls"][0].get("ok")), (1, True))
        self.assertNotIn("Traceback", done.stdout + done.stderr)


class TestHxScript(unittest.TestCase):
    def test_runs_a_script_and_shares_the_budget_with_sql(self):
        run_id = new_run("L")
        done = run_tool("L", "hx_script.py", "--run", run_id, "fiscal-calendar/scripts/fiscal.py", "last period")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("FY2026/27 P05", done.stdout)
        self.assertIn(f"[query 1 of {BUDGET} used]", done.stdout)
        done = run_tool("L", "hx_sql.py", "--run", run_id, "--sql", "SELECT 1")
        self.assertIn(f"[query 2 of {BUDGET} used]", done.stdout)
        data = counter_of(run_id)
        self.assertEqual([c["kind"] for c in data["calls"]], ["script", "sql"])

    def test_database_argument_is_supplied_not_taken(self):
        run_id = new_run("L")
        done = run_tool("L", "hx_script.py", "--run", run_id, "fiscal-calendar/scripts/fiscal.py", "PATH_TO/tuomimetsa.duckdb", "last period")
        self.assertEqual(done.returncode, 0, done.stdout)
        done = run_tool("L", "hx_script.py", "--run", run_id, "fiscal-calendar/scripts/fiscal.py", "last period", "other.duckdb")
        self.assertEqual(done.returncode, 1)
        self.assertIn("database path is supplied", done.stdout)

    def test_refuses_paths_outside_the_library_and_the_session(self):
        run_id = new_run("L")
        cases = [("../../hx_sql.py",), ("tools/hx_sql.py",), ("fiscal-calendar/scripts/../../../tools/hx_sql.py",), ("nope/scripts/x.py",),
                 ("fiscal-calendar/scripts/fiscal.py", "C:/Windows/win.ini"), ("fiscal-calendar/scripts/fiscal.py", "../x"),
                 ("query-check/scripts/query_check.py", "--file", "q.sql")]
        for case in cases:
            done = run_tool("L", "hx_script.py", "--run", run_id, *case)
            self.assertEqual(done.returncode, 1, f"{case} -> {done.stdout}")
        self.assertEqual(counter_of(run_id)["used"], 0)     # nothing reached the database

    def test_put_and_file_with_query_check(self):
        run_id = new_run("L")
        done = run_tool("L", "hx_script.py", "--run", run_id, "--put", "q.sql", "query-check/scripts/query_check.py", "--file", "q.sql",
                        "--grain", "store_id", stdin="SELECT store_id, store_name FROM dim_store WHERE is_current")
        self.assertEqual(done.returncode in (0, 1), True, done.stdout)
        self.assertIn(f"[query 1 of {BUDGET} used]", done.stdout)
        self.assertTrue((PATHS.scratch_dir / run_id / "q.sql").is_file())

    def test_a_script_cannot_read_files_through_sql(self):
        run_id = new_run("L")
        key_file = (cfg.KEY_DIR / "key.json").as_posix()
        done = run_tool("L", "hx_script.py", "--run", run_id, "query-check/scripts/query_check.py", "--sql", f"SELECT * FROM read_text('{key_file}')")
        self.assertNotIn("REQ-T01", done.stdout)
        self.assertRegex(done.stdout.lower(), r"permission|disabled|error")

    def test_budget_refuses_scripts_too(self):
        run_id = new_run("L")
        path = PATHS.counters_dir / f"{run_id}.json"
        data = counter_of(run_id)
        data["used"] = BUDGET
        path.write_text(json.dumps(data), encoding="utf-8")
        done = run_tool("L", "hx_script.py", "--run", run_id, "fiscal-calendar/scripts/fiscal.py", "last period")
        self.assertEqual(done.returncode, 2)
        self.assertIn("Query budget used up", done.stdout)

    def test_scripts_do_not_get_secrets(self):
        sys.path.insert(0, str(PATHS.arm_stage("L") / "tools"))
        sys.dont_write_bytecode = True
        try:
            import importlib
            module = importlib.import_module("hx_script")
            with mock.patch.dict(os.environ, {"HAPAX_LOCK_PASSWORD": "x" * 20, "ANTHROPIC_API_KEY": "k", "MY_TOKEN": "t", "PATH": os.environ["PATH"],
                                              "HX_SETTINGS_FILE": "s"}):
                environment = module.script_environment()
            for name in ("HAPAX_LOCK_PASSWORD", "ANTHROPIC_API_KEY", "MY_TOKEN", "HX_SETTINGS_FILE"):
                self.assertNotIn(name, environment)
            self.assertIn("PATH", environment)
        finally:
            sys.path.pop(0)
            sys.modules.pop("hx_script", None)

    def test_resolve_script_accepts_a_bare_name(self):
        library = (PATHS.arm_stage("L") / "library").resolve()
        sys.path.insert(0, str(PATHS.arm_stage("L") / "tools"))
        sys.dont_write_bytecode = True
        try:
            import importlib
            module = importlib.import_module("hx_script")
            self.assertEqual(module.resolve_script(library, "fiscal.py").name, "fiscal.py")
            self.assertEqual(module.resolve_script(library, "<library>/query-check/scripts/query_check.py").name, "query_check.py")
            self.assertIsNone(module.resolve_script(library, "../tools/hx_sql.py"))
        finally:
            sys.path.pop(0)
            sys.modules.pop("hx_script", None)


# ---------------------------------------------------------------------------
# Stage and packets
# ---------------------------------------------------------------------------

class TestStage(unittest.TestCase):
    def files(self, arm: str) -> set:
        target = PATHS.arm_stage(arm)
        return {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file() and p.name != bp.STAGE_MARKER}

    def test_each_arm_holds_only_its_own_files(self):
        s, d, l, lm = (self.files(arm) for arm in ("S", "D", "L", "L-"))
        base = {"tools/hx_common.py", "tools/hx_sql.py", "tools/hx_settings.json", "MANIFEST.json"}
        self.assertEqual(s, base)
        self.assertEqual(d, base)
        self.assertEqual(l - {f for f in l if f.startswith("library/")}, base | {"tools/hx_script.py", "tools/script_runner.py"})
        self.assertEqual(lm - {f for f in lm if f.startswith("library/")}, base)
        self.assertFalse([f for f in lm if "/scripts/" in f])
        self.assertTrue([f for f in l if "/scripts/" in f and f.startswith("library/")])

    def test_stage_is_clean_and_faithful(self):
        for arm in ("S", "D", "L", "L-"):
            self.assertEqual(bp.verify_stage(arm, PATHS), [], arm)
        library = cfg.ARMS_LIBRARY_DIR
        staged = PATHS.arm_stage("L") / "library"
        for original in library.rglob("*"):
            if not original.is_file() or "__pycache__" in original.parts or original.suffix not in harness.READABLE_SKILL_SUFFIXES:
                continue
            text = original.read_text(encoding="utf-8")
            expected = harness.strip_markers(text) if original.suffix == ".md" else text
            self.assertEqual((staged / original.relative_to(library)).read_text(encoding="utf-8"), expected, original.name)

    def test_nothing_held_out_is_staged(self):
        for arm in ("S", "D", "L", "L-"):
            for path in PATHS.arm_stage(arm).rglob("*"):
                self.assertFalse(set(path.parts) & {"build_notes.md", "tests", "_scratch", "key.json", "DECISIONS.md", "design.md", "test_requests.json"})
        key_hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for p in cfg.KEY_DIR.rglob("*") if p.is_file()} if cfg.KEY_DIR.exists() else set()
        for arm in ("S", "D", "L", "L-"):
            for path in PATHS.arm_stage(arm).rglob("*"):
                if path.is_file():
                    self.assertNotIn(hashlib.sha256(path.read_bytes()).hexdigest(), key_hashes)
                    if path.suffix == ".md":
                        self.assertNotIn("<!-- facts:", path.read_text(encoding="utf-8"))
                        self.assertNotIn("<!-- source:", path.read_text(encoding="utf-8"))

    def test_changed_stage_is_detected_and_refused(self):
        target = PATHS.arm_stage("S")
        extra = target / "tools" / "extra.txt"
        extra.write_text("x", encoding="utf-8")
        try:
            self.assertTrue([p for p in bp.verify_stage("S", PATHS) if "extra" in p])
            with self.assertRaises(SystemExit):
                bp.stage_arm("S", PATHS, quiet=True)
            bp.stage_arm("S", PATHS, refresh=True, quiet=True)
            self.assertFalse(extra.exists())
        finally:
            if extra.exists():
                extra.unlink()
        self.assertEqual(bp.verify_stage("S", PATHS), [])

    def test_staging_is_idempotent(self):
        before = {p: p.read_bytes() for p in PATHS.arm_stage("L").rglob("*") if p.is_file()}
        bp.stage_arm("L", PATHS, quiet=True)
        after = {p: p.read_bytes() for p in PATHS.arm_stage("L").rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_refuses_a_folder_it_did_not_make(self):
        stray = PATHS.stage_dir / "Lminus"
        marker = stray / bp.STAGE_MARKER
        marker.unlink()
        try:
            with self.assertRaises(SystemExit):
                bp.stage_arm("L-", PATHS, refresh=True, quiet=True)
        finally:
            marker.write_text("restored by the test\n", encoding="utf-8")

    def test_settings_point_at_the_case_through_relative_paths(self):
        settings = json.loads((PATHS.arm_stage("L") / "tools" / "hx_settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["max_queries"], BUDGET)
        self.assertEqual(settings["row_cap"], cfg.SQL_RESULT_ROW_LIMIT)
        self.assertEqual(settings["library_dir"], "data/agent_runs/stage/L/library")
        self.assertFalse(Path(settings["counters_dir"]).is_absolute())
        self.assertTrue(settings["scripts_allowed"])
        self.assertFalse(json.loads((PATHS.arm_stage("S") / "tools" / "hx_settings.json").read_text(encoding="utf-8"))["scripts_allowed"])


class TestPackets(unittest.TestCase):
    def packet(self, arm: str, request_id: str = "REQ-D20", alias: str = "sonnet") -> str:
        run_id = new_run(arm, alias, request_id)
        return (PATHS.packets_dir / "t" / f"{run_id}.txt").read_text(encoding="utf-8")

    def test_s_and_d_carry_the_api_system_text_verbatim(self):
        for arm in ("S", "D"):
            system = harness.build_arm_materials(arm).system_text
            self.assertIn(system, self.packet(arm), arm)

    def test_l_carries_the_same_schema_and_skill_list(self):
        api = harness.build_arm_materials("L")
        text = self.packet("L")
        schema_part = harness.build_arm_materials("S").system_text
        self.assertIn(schema_part, text)
        for line in api.system_text.splitlines():
            if line.startswith("- ") and ":" in line:
                self.assertIn(line, text)
        self.assertEqual(len(api.skill_names), 10)

    def test_task_text_is_identical_across_arms_and_models(self):
        tail = harness.task_text(DEV["REQ-D20"]["request"])
        for arm in ("S", "D", "L", "L-"):
            self.assertTrue(self.packet(arm).rstrip().endswith(tail.rstrip()), arm)
        self.assertTrue(self.packet("L", alias="haiku").rstrip().endswith(tail.rstrip()))

    def test_budgets_and_rules_are_in_every_packet(self):
        for arm in ("S", "D", "L", "L-"):
            text = self.packet(arm)
            self.assertIn(f"{BUDGET} query executions", text)
            self.assertIn("No padding rows", text)
            self.assertIn(f"up to {BUDGET} queries", text)
            self.assertIn("never 0.125", text)
        text = self.packet("L")
        self.assertIn("6 skill loads", text)
        self.assertIn("Read at most 30 library files", text)
        self.assertIn("hx_script.py", text)
        self.assertNotIn("hx_script.py", self.packet("S"))
        self.assertNotIn("hx_script.py", self.packet("L-"))
        self.assertIn("No script runner is available", self.packet("L-"))

    def test_only_the_arms_own_material(self):
        doc_marker = "Team prompt document"
        self.assertNotIn(doc_marker, self.packet("S"))
        self.assertIn(doc_marker, self.packet("D"))
        self.assertNotIn("## Skills library", self.packet("D"))
        self.assertNotIn(doc_marker, self.packet("L"))
        self.assertIn("## Skills library", self.packet("L"))

    def test_nothing_held_out_in_a_packet(self):
        for arm in ("S", "D", "L"):
            lowered = self.packet(arm).lower()
            for word in ("build_notes", "data/key", "reference_sql", "data/requests", "decisions.md", "<!-- facts"):
                self.assertNotIn(word, lowered)
        self.assertNotIn("REQ-D20", self.packet("S"))

    def test_paths_in_the_packet_point_at_this_arms_stage(self):
        text = self.packet("L")
        stage = PATHS.arm_stage("L").resolve().as_posix()
        self.assertIn(f"{stage}/tools/hx_sql.py", text)
        self.assertIn(f"{stage}/library", text)
        self.assertIn(Path(sys.executable).as_posix(), text)
        self.assertNotIn("/stage/D", text)

    def test_packets_are_deterministic(self):
        request = DEV["REQ-D20"]["request"]
        first = bp.build_packet_text(request, "L", "t-sonnet-L-d20-r9", PATHS)
        second = bp.build_packet_text(request, "L", "t-sonnet-L-d20-r9", PATHS)
        self.assertEqual(first, second)

    def test_a_test_request_is_read_one_at_a_time(self):
        if not (cfg.REQUESTS_DIR / "test_requests.json").exists():
            self.skipTest("data/requests is locked")
        entry = bp.build_packet("REQ-T05", "S", "haiku", 1, "t-main", PATHS)
        text = (PATHS.packets_dir / "t-main" / f"{entry['run_id']}.txt").read_text(encoding="utf-8")
        request = harness.load_test_request("REQ-T05")
        self.assertIn(request["request_text"], text)
        self.assertNotIn("REQ-T05", text)
        others = json.loads((cfg.REQUESTS_DIR / "test_requests.json").read_text(encoding="utf-8"))
        for other in others:
            if other["id"] != "REQ-T05" and other["request_text"] != request["request_text"]:
                self.assertNotIn(other["request_text"], text)

    def test_counter_registration(self):
        run_id = new_run()
        data = counter_of(run_id)
        self.assertEqual((data["used"], data["budget"], data["arm"], data["model"], data["request_id"]), (0, BUDGET, "S", "sonnet", "REQ-D20"))
        self.assertEqual(data["task_instructions_version"], cfg.TASK_INSTRUCTIONS_VERSION)
        # a used counter is not silently reset
        data["used"] = 3
        (PATHS.counters_dir / f"{run_id}.json").write_text(json.dumps(data), encoding="utf-8")
        repeat = int(run_id.rsplit("-r", 1)[1])
        with self.assertRaises(SystemExit):
            bp.build_packet("REQ-D20", "S", "sonnet", repeat, "t", PATHS)
        entry = bp.build_packet("REQ-D20", "S", "sonnet", repeat, "t", PATHS, new_attempt=True)
        self.assertEqual(counter_of(entry["run_id"])["used"], 0)
        self.assertEqual(json.loads((PATHS.counters_dir / f"{run_id}.attempt1.json").read_text(encoding="utf-8"))["used"], 3)

    def test_run_ids_do_not_name_the_request_file(self):
        run_id = bp.agent_run_id("p2", "sonnet", "S", "REQ-D05", 1)
        self.assertEqual(run_id, "p2-sonnet-S-d05-r1")
        self.assertNotIn("REQ", run_id)
        self.assertEqual(bp.agent_run_id("main", "haiku", "L-", "REQ-T13", 2), "main-haiku-Lminus-t13-r2")


class TestPilot2Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = bp.AgentPaths(TMP_ROOT / "plan_case" / "data" / "agent_runs", cfg.WORLD_DIR, cfg.ARMS_DOC_PATH, cfg.ARMS_LIBRARY_DIR, cfg.WAREHOUSE_PATH)
        cls.plan = bp.pilot2_plan(cls.paths, quiet=True)

    def test_forty_runs_in_the_four_cells(self):
        runs = self.plan["runs"]
        self.assertEqual(len(runs), 40)
        cells = {}
        for run in runs:
            cells.setdefault((run["agent_model"], run["arm"]), []).append(run["request_id"])
        self.assertEqual(sorted(cells), [("haiku", "L"), ("sonnet", "D"), ("sonnet", "L"), ("sonnet", "S")])
        for requests in cells.values():
            self.assertEqual(sorted(requests), sorted(cfg.PILOT2_REQUEST_IDS))
        self.assertEqual(len({run["run_id"] for run in runs}), 40)

    def test_each_entry_points_at_an_existing_packet_and_counter(self):
        root = self.paths.agent_dir.parent.parent
        for run in self.plan["runs"]:
            packet = root / run["packet_path"]
            self.assertTrue(packet.is_file(), run["packet_path"])
            self.assertEqual(hashlib.sha256(packet.read_bytes()).hexdigest(), run["packet_sha256"])
            self.assertTrue((root / run["counter_path"]).is_file())
            self.assertEqual(run["model_id"], cfg.AGENT_MODEL_IDS[run["agent_model"]])
        written = json.loads((self.paths.agent_dir / "pilot2_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(written["runs"], self.plan["runs"])

    def test_the_ten_requests_are_new_and_spread(self):
        import dev_requests
        patterns = {r["id"]: r["pattern"] for r in dev_requests.DEV_REQUESTS}
        chosen = list(cfg.PILOT2_REQUEST_IDS)
        self.assertEqual(len(set(chosen)), 10)
        self.assertFalse(set(chosen) & set(cfg.PILOT_REQUEST_IDS))
        self.assertFalse(set(chosen) & {"REQ-D01", "REQ-D07", "REQ-D25"})        # the three queries the prompt doc carries in full
        self.assertEqual(sorted(patterns[c] for c in chosen), sorted(cfg.DEV_PATTERNS_COVERED))
        for request_id in chosen:
            self.assertIn(request_id, pilot_marking.PILOT_ANSWER_SPECS)

    def test_batches_are_one_cell_each(self):
        batches = {}
        for run in self.plan["runs"]:
            batches.setdefault(run["batch"], []).append(run)
        self.assertEqual(sorted(batches), ["haiku-L", "sonnet-D", "sonnet-L", "sonnet-S"])
        self.assertTrue(all(len(items) == 10 for items in batches.values()))

    def test_s_packets_of_dev_requests_do_not_name_the_dev_file(self):
        root = self.paths.agent_dir.parent.parent
        for run in self.plan["runs"]:
            if run["arm"] == "S":
                text = (root / run["packet_path"]).read_text(encoding="utf-8")
                self.assertNotIn(run["request_id"], text, run["run_id"])


class TestLaunchProtocol(unittest.TestCase):
    """The official delivery (from pilot 3): the Agent call's prompt is one short instruction naming the packet file."""

    def test_the_packet_says_it_is_a_file_the_agent_reads(self):
        run_id = new_run("L")
        text = (PATHS.packets_dir / "t" / f"{run_id}.txt").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("This file is your whole brief."))
        self.assertNotIn("This message", text)
        self.assertIn("Apart from this brief, read only the files named in it.", text)

    def test_launch_prompt_is_one_short_line_naming_the_absolute_packet_path(self):
        entry = bp.build_packet("REQ-D20", "S", "sonnet", 77, "t", PATHS)
        prompt = bp.launch_prompt_for(entry, PATHS)
        packet = (PATHS.packets_dir / "t" / f"{entry['run_id']}.txt").resolve().as_posix()
        self.assertEqual(prompt, f"Your brief is the file `{packet}`. Read it with the Read tool, then do what it says.")
        self.assertNotIn("\n", prompt)
        self.assertLess(len(prompt), 400)
        # it carries nothing of the brief: no query text, no request wording, no budget
        for fragment in ("SELECT", "Web orders by hour", "12", "30", "hx_sql"):
            self.assertNotIn(fragment, prompt.replace(packet, ""))

    def test_the_prompt_template_and_notes_state_the_protocol(self):
        self.assertEqual(bp.LAUNCH_PROMPT.count("{packet_path}"), 1)
        notes = " ".join(bp.LAUNCH_NOTES)
        self.assertIn("launch_prompt", notes)
        self.assertIn("never pastes the packet text", notes)


class TestPilot3Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = TMP_ROOT / "plan3_case"
        cls.paths = bp.AgentPaths(cls.case / "data" / "agent_runs", cfg.WORLD_DIR, cfg.ARMS_DOC_PATH, cfg.ARMS_LIBRARY_DIR, cfg.WAREHOUSE_PATH)
        cls.plan = bp.pilot3_plan(cls.paths, build=False, quiet=True)
        cls.files_after_plan_only = sorted(p.relative_to(cls.case).as_posix() for p in cls.case.rglob("*") if p.is_file())

    def test_plan_only_writes_the_plan_and_nothing_else(self):
        self.assertEqual(self.files_after_plan_only, ["data/agent_runs/pilot3_plan.json"])
        self.assertTrue(all(not run["built"] and run["packet_sha256"] is None for run in self.plan["runs"]))
        self.assertIn("not built", self.plan["status"])

    def test_forty_runs_in_the_four_cells_and_run_ids_carry_pilot3(self):
        runs = self.plan["runs"]
        self.assertEqual(len(runs), 40)
        cells = {}
        for run in runs:
            cells.setdefault((run["agent_model"], run["arm"]), []).append(run["request_id"])
        self.assertEqual(sorted(cells), [("haiku", "L"), ("sonnet", "D"), ("sonnet", "L"), ("sonnet", "S")])
        for requests in cells.values():
            self.assertEqual(sorted(requests), sorted(cfg.PILOT3_REQUEST_IDS))
        self.assertEqual(len({run["run_id"] for run in runs}), 40)
        for run in runs:
            self.assertTrue(run["run_id"].startswith("pilot3-"), run["run_id"])
            self.assertIn("pilot3", run["packet_path"])
            self.assertNotIn("REQ", run["run_id"])
        self.assertEqual(self.plan["plan"], "pilot3")
        self.assertEqual(self.plan["task_instructions_version"], cfg.TASK_INSTRUCTIONS_VERSION)
        self.assertEqual(self.plan["marker_version"], pilot_marking.MARKER_VERSION)
        batches = {run["batch"] for run in runs}
        self.assertEqual(batches, {"sonnet-S", "sonnet-D", "sonnet-L", "haiku-L"})

    def test_the_ten_requests_are_new_spread_and_have_specs(self):
        import dev_requests
        patterns = {r["id"]: r["pattern"] for r in dev_requests.DEV_REQUESTS}
        chosen = list(cfg.PILOT3_REQUEST_IDS)
        self.assertEqual(len(set(chosen)), 10)
        self.assertFalse(set(chosen) & set(cfg.PILOT_REQUEST_IDS))
        self.assertFalse(set(chosen) & set(cfg.PILOT2_REQUEST_IDS))
        self.assertFalse(set(chosen) & {"REQ-D01", "REQ-D07", "REQ-D25"})
        self.assertEqual(sorted(patterns[c] for c in chosen), sorted(cfg.DEV_PATTERNS_COVERED))
        for request_id in chosen:
            self.assertIn(request_id, pilot_marking.PILOT_ANSWER_SPECS)
        # at least two requests exercise the weekly-series and "last year" fixes
        self.assertTrue({"REQ-D03", "REQ-D18"} <= set(chosen))
        self.assertTrue({"REQ-D08", "REQ-D29", "REQ-D35"} <= set(chosen))

    def test_every_entry_has_the_launch_prompt_for_its_packet(self):
        for run in self.plan["runs"]:
            self.assertEqual(run["launch_prompt"], bp.launch_prompt_for(run, self.paths))
            self.assertIn(run["run_id"] + ".txt", run["launch_prompt"])
        written = json.loads((self.paths.agent_dir / "pilot3_plan.json").read_text(encoding="utf-8"))
        # (the file may already be the built plan if another test ran first; the run ids and prompts are the same either way)
        self.assertEqual([(r["run_id"], r["launch_prompt"]) for r in written["runs"]], [(r["run_id"], r["launch_prompt"]) for r in self.plan["runs"]])
        self.assertEqual(written["launch_prompt_template"], bp.LAUNCH_PROMPT)

    def test_building_the_plan_makes_packets_counters_and_a_clean_check(self):
        built = bp.pilot3_plan(self.paths, build=True, quiet=True)
        self.assertEqual([r["run_id"] for r in built["runs"]], [r["run_id"] for r in self.plan["runs"]])
        self.assertTrue(all(r["built"] and r["packet_sha256"] for r in built["runs"]))
        self.assertEqual(bp.check_plan(self.paths.agent_dir / "pilot3_plan.json", self.paths), [])
        root = self.case
        sample = built["runs"][0]
        packet_file = root / sample["packet_path"]
        # the version 3 rules are in the packets of the plan
        self.assertIn("Never join them into one label", packet_file.read_text(encoding="utf-8"))
        # a changed packet, a used counter and a moved launch prompt are all caught
        original = packet_file.read_bytes()
        packet_file.write_bytes(original + b"x")
        self.assertTrue(any("packet changed" in p for p in bp.check_plan(self.paths.agent_dir / "pilot3_plan.json", self.paths)))
        packet_file.write_bytes(original)
        counter_file = root / sample["counter_path"]
        data = json.loads(counter_file.read_text(encoding="utf-8"))
        data["used"] = 2
        counter_file.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("counter already used" in p for p in bp.check_plan(self.paths.agent_dir / "pilot3_plan.json", self.paths)))
        data["used"] = 0
        counter_file.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(bp.check_plan(self.paths.agent_dir / "pilot3_plan.json", self.paths), [])
        # a plan with unbuilt entries does not pass
        unbuilt = bp.planned_entry("REQ-D03", "S", "sonnet", "pilot3", self.paths)
        plan = json.loads((self.paths.agent_dir / "pilot3_plan.json").read_text(encoding="utf-8"))
        plan["runs"][0] = dict(unbuilt, batch="sonnet-S", launch_prompt=bp.launch_prompt_for(unbuilt, self.paths))
        (self.paths.agent_dir / "unbuilt_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        self.assertTrue(any("not built" in p for p in bp.check_plan(self.paths.agent_dir / "unbuilt_plan.json", self.paths)))


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------

COPY_DIRS = ["design", "data/key", "data/requests", "arms", "world", "data/runs"]
COPY_FILES = ["README.md", "data/facts.yaml", "data/validation_report.json"]


def make_scratch_case(destination: Path) -> Path:
    """A small copy of the case folder: everything the lock touches, a stand-in for the 43 MB internal tables, and the code files."""
    case = cfg.CASE_ROOT
    for relative in COPY_DIRS:
        source = case / relative
        if source.exists():
            shutil.copytree(source, destination / relative, ignore=shutil.ignore_patterns("__pycache__", "_scratch"))
    for relative in COPY_FILES:
        if (case / relative).exists():
            (destination / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(case / relative, destination / relative)
    (destination / "data" / "internal").mkdir(parents=True, exist_ok=True)
    (destination / "data" / "internal" / "incident_manifest.json").write_text('{"stand-in": "internal"}\n', encoding="utf-8")
    (destination / "data" / "internal" / "table.parquet").write_bytes(os.urandom(4096))
    (destination / "code").mkdir(parents=True, exist_ok=True)
    for path in CODE_DIR.glob("*.py"):
        if not path.name.startswith("test_"):          # the test files hold the test password as a literal
            shutil.copy2(path, destination / "code" / path.name)
    (destination / "data" / "warehouse").mkdir(parents=True, exist_ok=True)
    (destination / "data" / "warehouse" / "stand_in.duckdb").write_bytes(os.urandom(2048))
    (destination / "data" / "agent_runs" / "packets").mkdir(parents=True, exist_ok=True)
    (destination / "data" / "agent_runs" / "packets" / "p.txt").write_text("a packet\n", encoding="utf-8")
    return destination


def snapshot(root: Path) -> dict:
    """{relative path: (sha256, mtime_ns)} for every file outside the vault."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_file() and not relative.startswith(lock.VAULT_RELATIVE) and "__pycache__" not in relative:
            result[relative] = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    return result


def quiet(*args, **kwargs) -> None:
    pass


class TestLock(unittest.TestCase):
    def setUp(self):
        self.root = make_scratch_case(Path(tempfile.mkdtemp(prefix="hx_lock_", dir=TMP_ROOT)))
        self.before = snapshot(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def lock(self, groups=("core",)):
        return lock.command_lock(self.root, list(groups), password=TEST_PASSWORD, say=quiet)

    def test_core_round_trip_is_byte_for_byte(self):
        self.lock()
        for relative in ("data/key", "design", "data/requests", "arms/build_notes.md", "arms/tests", "data/runs"):
            self.assertFalse((self.root / relative).exists(), relative)
        for relative in ("arms/prompt_doc.md", "arms/library", "world", "README.md", "code", "data/internal"):
            self.assertTrue((self.root / relative).exists(), relative)       # core does not touch these
        report = lock.status_report(self.root)
        self.assertTrue(report["clean"], report)
        written = lock.command_unlock(self.root, password=TEST_PASSWORD, say=quiet)
        self.assertGreater(len(written), 20)
        self.assertEqual(snapshot(self.root), self.before)                    # content and modification time of every file
        restored = list((self.root / lock.VAULT_RELATIVE).glob("locked_answers.restored-*.zip"))
        self.assertEqual(len(restored), 1)                                    # the archive is kept, not deleted

    def test_design_notes_and_readme_come_back_exactly(self):
        original = {name: (self.root / name).read_bytes() for name in ("design/DECISIONS.md", "design/design.md", "README.md")}
        self.lock()
        self.lock_status_says_gone("design/DECISIONS.md")
        lock.command_unlock(self.root, password=TEST_PASSWORD, say=quiet)
        for name, data in original.items():
            self.assertEqual((self.root / name).read_bytes(), data, name)

    def lock_status_says_gone(self, relative: str) -> None:
        self.assertFalse((self.root / relative).exists())

    def test_extended_and_code_round_trip(self):
        self.lock(("core", "extended", "code"))
        for relative in ("world", "arms/prompt_doc.md", "arms/library", "arms/tests", "data/internal", "data/facts.yaml", "data/validation_report.json"):
            self.assertFalse((self.root / relative).exists(), relative)
        self.assertEqual(list((self.root / "arms").iterdir()) if (self.root / "arms").exists() else [], [])
        remaining = sorted(p.relative_to(self.root).as_posix() for p in (self.root / "code").rglob("*") if p.is_file())
        self.assertEqual(remaining, ["code/lock_answers.py"])
        self.assertTrue((self.root / "README.md").exists())
        self.assertTrue(lock.status_report(self.root)["clean"])
        lock.command_unlock(self.root, password=TEST_PASSWORD, say=quiet)
        self.assertEqual(snapshot(self.root), self.before)

    def test_stage_copies_of_arm_material_are_allowed_but_other_copies_are_not(self):
        stage = self.root / "data" / "agent_runs" / "stage" / "L"
        (stage / "library").mkdir(parents=True)
        shutil.copy2(self.root / "arms" / "library" / "stock" / "templates" / "weeks_of_cover.sql", stage / "library" / "w.sql")
        self.lock(("core", "extended"))                                       # an arm's own copy in the stage is expected
        lock.command_unlock(self.root, password=TEST_PASSWORD, say=quiet)
        shutil.copy2(self.root / "arms" / "build_notes.md", stage / "library" / "notes.md")      # a copy of a held-out file is a leak
        before = snapshot(self.root)
        with self.assertRaises(lock.LockError) as caught:
            self.lock(("core", "extended"))
        self.assertIn("byte-identical", str(caught.exception))
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse((self.root / lock.VAULT_RELATIVE / lock.STATE_NAME).exists())

    def test_a_leaked_key_copy_outside_the_stage_refuses_the_lock(self):
        leak = self.root / "data" / "agent_runs" / "packets" / "oops.json"
        shutil.copy2(self.root / "data" / "key" / "key.json", leak)
        before = snapshot(self.root)
        with self.assertRaises(lock.LockError) as caught:
            self.lock()
        self.assertIn("oops.json", str(caught.exception))
        self.assertEqual(snapshot(self.root), before)                          # nothing moved
        self.assertFalse((self.root / lock.VAULT_RELATIVE / lock.ARCHIVE_NAME).exists())

    def test_status_notices_a_plain_file_or_a_copy_after_locking(self):
        self.lock()
        (self.root / "design").mkdir()
        (self.root / "design" / "new_notes.md").write_text("back again\n", encoding="utf-8")
        report = lock.status_report(self.root)
        self.assertFalse(report["clean"])
        self.assertTrue(any("plain file" in p for p in report["problems"]))
        (self.root / "design" / "new_notes.md").unlink()
        (self.root / "design").rmdir()
        self.assertTrue(lock.status_report(self.root)["clean"])

    def test_status_notices_a_copy_of_locked_content(self):
        archive_state = None
        self.lock()
        # recreate a locked file's content elsewhere: take it back out of the archive for a moment
        with lock.open_archive(self.root / lock.VAULT_RELATIVE / lock.ARCHIVE_NAME, "r", TEST_PASSWORD) as archive:
            manifest = lock.read_manifest(archive)
            entry = next(e for e in manifest["entries"] if e["path"].endswith("review_sheet.md"))
            (self.root / "somewhere.txt").write_bytes(archive.read(entry["id"]))
        report = lock.status_report(self.root)
        self.assertFalse(report["clean"])
        self.assertTrue(any("byte-identical" in p and "somewhere.txt" in p for p in report["problems"]), report["problems"])

    def test_wrong_password_changes_nothing(self):
        self.lock()
        with self.assertRaises(lock.LockError) as caught:
            lock.command_unlock(self.root, password="a-completely-wrong-password", say=quiet)
        self.assertIn("Wrong password", str(caught.exception))
        self.assertTrue(lock.status_report(self.root)["clean"])
        self.assertFalse((self.root / "design").exists())

    def test_unlock_refuses_when_a_plain_file_is_in_the_way(self):
        self.lock()
        (self.root / "design").mkdir()
        (self.root / "design" / "design.md").write_text("someone wrote this meanwhile\n", encoding="utf-8")
        with self.assertRaises(lock.LockError) as caught:
            lock.command_unlock(self.root, password=TEST_PASSWORD, say=quiet)
        self.assertIn("in the way", str(caught.exception))
        self.assertFalse((self.root / "data" / "key").exists())               # nothing was restored
        (self.root / "design" / "design.md").unlink()
        (self.root / "design").rmdir()
        lock.command_unlock(self.root, password=TEST_PASSWORD, say=quiet)
        self.assertEqual(snapshot(self.root), self.before)

    def test_a_failed_delete_puts_everything_back(self):
        calls = {"n": 0}

        def failing_delete(path):
            calls["n"] += 1
            if calls["n"] == 5:
                raise PermissionError("locked by another program")
            os.remove(path)
        with self.assertRaises(lock.LockError) as caught:
            lock.command_lock(self.root, ["core"], password=TEST_PASSWORD, say=quiet, delete_hook=failing_delete)
        self.assertIn("nothing is left half locked", str(caught.exception))
        self.assertEqual(snapshot(self.root), self.before)
        self.assertFalse((self.root / lock.VAULT_RELATIVE / lock.STATE_NAME).exists())
        self.assertFalse((self.root / lock.VAULT_RELATIVE / lock.ARCHIVE_NAME).exists())
        self.assertEqual(lock.status_report(self.root)["state"], "unlocked")

    def test_refuses_a_second_lock_and_a_missing_path(self):
        self.lock()
        with self.assertRaises(lock.LockError):
            self.lock()
        lock.command_unlock(self.root, password=TEST_PASSWORD, say=quiet)
        shutil.rmtree(self.root / "design")
        with self.assertRaises(lock.LockError) as caught:
            self.lock()
        self.assertIn("design", str(caught.exception))

    def test_password_rules(self):
        for bad in (None, "", "short-one"):
            with mock.patch.object(lock, "get_password", return_value=None):
                with self.assertRaises(lock.LockError):
                    lock.command_lock(self.root, ["core"], password=bad, say=quiet)
        self.assertEqual(snapshot(self.root), self.before)
        self.assertEqual(lock.PASSWORD_ENV, "HAPAX_LOCK_PASSWORD")
        self.assertEqual(lock.MIN_PASSWORD_LENGTH, 12)

    def test_password_comes_from_the_environment_then_the_registry(self):
        with mock.patch.dict(os.environ, {"HAPAX_LOCK_PASSWORD": "from-the-environment"}):
            with mock.patch.object(lock, "read_user_registry_variable", return_value="from-the-registry") as registry:
                self.assertEqual(lock.get_password(), "from-the-environment")
                registry.assert_not_called()
        environment = {k: v for k, v in os.environ.items() if k != "HAPAX_LOCK_PASSWORD"}
        with mock.patch.dict(os.environ, environment, clear=True):
            with mock.patch.object(lock, "read_user_registry_variable", return_value="from-the-registry") as registry:
                self.assertEqual(lock.get_password(), "from-the-registry")
                registry.assert_called_once_with("HAPAX_LOCK_PASSWORD")
            with mock.patch.object(lock, "read_user_registry_variable", return_value=None):
                self.assertIsNone(lock.get_password())

    def test_the_registry_reader_works_on_this_machine(self):
        value = lock.read_user_registry_variable("HAPAX_TEST_VARIABLE_THAT_DOES_NOT_EXIST")
        self.assertIsNone(value)                                              # absent: None, no exception

    def test_the_password_is_never_written_or_printed(self):
        env = {k: v for k, v in os.environ.items()}
        env["HAPAX_LOCK_PASSWORD"] = TEST_PASSWORD
        done = subprocess.run([sys.executable, str(CODE_DIR / "lock_answers.py"), "lock", "--root", str(self.root)], capture_output=True,
                              text=True, encoding="utf-8", env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn(TEST_PASSWORD, done.stdout + done.stderr)
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(TEST_PASSWORD.encode(), path.read_bytes(), path.name)
        done = subprocess.run([sys.executable, str(CODE_DIR / "lock_answers.py"), "unlock", "--root", str(self.root)], capture_output=True,
                              text=True, encoding="utf-8", env=dict(env, HAPAX_LOCK_PASSWORD="not the password at all"))
        self.assertEqual(done.returncode, 1)
        self.assertNotIn("not the password", done.stdout + done.stderr)

    def test_the_archive_is_encrypted_with_opaque_names(self):
        self.lock()
        archive_path = self.root / lock.VAULT_RELATIVE / lock.ARCHIVE_NAME
        raw = archive_path.read_bytes()
        self.assertNotIn(b"REQ-T01", raw)
        self.assertNotIn(b"reference_sql", raw)
        self.assertNotIn(b"key.json", raw)
        import pyzipper
        with pyzipper.AESZipFile(archive_path) as archive:
            names = archive.namelist()
            self.assertTrue(all(n == "manifest.json" or n.startswith("f0") for n in names))
            with self.assertRaises(RuntimeError):
                archive.read(names[0])                                         # no password
            archive.setpassword(b"wrong-wrong-wrong")
            with self.assertRaises(RuntimeError):
                archive.read(names[0])
        state = json.loads((self.root / lock.VAULT_RELATIVE / lock.STATE_NAME).read_text(encoding="utf-8"))
        self.assertNotIn("key.json", json.dumps(state))                       # the plain record names no file

    def test_cli_status_exit_codes(self):
        def cli(*args, password=TEST_PASSWORD):
            return subprocess.run([sys.executable, str(CODE_DIR / "lock_answers.py"), *args, "--root", str(self.root)], capture_output=True,
                                  text=True, encoding="utf-8", env={**os.environ, "HAPAX_LOCK_PASSWORD": password})
        self.assertEqual(cli("status").returncode, 0)
        self.assertEqual(cli("status", "--require-locked").returncode, 1)
        self.assertEqual(cli("lock").returncode, 0)
        done = cli("status", "--require-locked")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("LOCKED", done.stdout)
        self.assertEqual(cli("status", "--deep").returncode, 0)
        self.assertEqual(cli("unlock").returncode, 0)
        self.assertEqual(cli("status").returncode, 0)
        self.assertEqual(snapshot(self.root), self.before)

    def test_deep_status_catches_a_damaged_archive(self):
        self.lock()
        archive_path = self.root / lock.VAULT_RELATIVE / lock.ARCHIVE_NAME
        data = bytearray(archive_path.read_bytes())
        data[len(data) // 2] ^= 0xFF
        archive_path.write_bytes(bytes(data))
        report = lock.status_report(self.root, password=TEST_PASSWORD, deep=True)
        self.assertFalse(report["clean"])
        with self.assertRaises(lock.LockError):
            lock.command_unlock(self.root, password=TEST_PASSWORD, say=quiet)

    def test_delete_archive_flag(self):
        self.lock()
        lock.command_unlock(self.root, password=TEST_PASSWORD, delete_archive=True, say=quiet)
        self.assertEqual(list((self.root / lock.VAULT_RELATIVE).glob("*.zip")), [])
        self.assertEqual(snapshot(self.root), self.before)


class TestLockOnTheRealFolderIsNotTouched(unittest.TestCase):
    def test_the_real_case_folder_is_unlocked_and_complete(self):
        report = lock.status_report(cfg.CASE_ROOT)
        self.assertEqual(report["state"], "unlocked", report)


# ---------------------------------------------------------------------------
# Collecting and marking
# ---------------------------------------------------------------------------

def final_message_for(request_id: str, table: dict = None, sql: str = None, **overrides) -> str:
    table = table or expected_for(request_id)["table"]
    answer = {"sql": sql or DEV[request_id]["accepted_sql"], "result": {"columns": table["columns"], "rows": table["rows"]},
              "definitions_applied": ["net sales"], "assumptions": [], "caveats": []}
    answer.update(overrides)
    return json.dumps(answer, default=str)


def simulate_run(request_id: str, arm: str = "S", alias: str = "sonnet", queries: int = 2) -> str:
    """Register a run and make real counted calls through the staged tool, as an agent would."""
    run_id = new_run(arm, alias, request_id, set_name="sim")
    for number in range(queries):
        done = run_tool(arm, "hx_sql.py", "--run", run_id, "--sql", f"SELECT {number + 1}")
        assert done.returncode == 0, done.stdout
    return run_id


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.logs = TMP_ROOT / f"logs_{self._testMethodName}"

    def collect(self, run_id: str, text: str, **kwargs):
        defaults = dict(total_tokens=50000, tool_calls=9, duration_s=161.0, paths=PATHS, out_dir=self.logs)
        defaults.update(kwargs)
        return collect.collect(run_id, text, **defaults)

    def test_log_has_the_shape_of_the_api_logs(self):
        run_id = simulate_run("REQ-D20", queries=3)
        summary = self.collect(run_id, final_message_for("REQ-D20"))
        for key in ("run_id", "label", "arm", "model_requested", "model_returned", "request_id", "repeat", "status", "problem", "answer", "final_text",
                    "turns", "queries_used", "skills_opened", "files_read", "scripts_run", "refused_query_calls", "tokens", "cost_usd",
                    "cost_usd_warm_prefix", "elapsed_s", "stop_reasons", "client_kind", "log_file"):
            self.assertIn(key, summary)
        self.assertEqual((summary["status"], summary["arm"], summary["request_id"], summary["model_requested"]),
                         ("ok", "S", "REQ-D20", "claude-sonnet-5-5"))
        self.assertEqual(summary["queries_used"], 3)                          # from the counter
        self.assertEqual(summary["tokens"], {"total_tokens": 50000})
        self.assertEqual((summary["elapsed_s"], summary["tool_calls_reported"]), (161.0, 9))
        events = [json.loads(line) for line in (self.logs / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines()]
        kinds = [event["event"] for event in events]
        self.assertEqual(kinds[0], "run_start")
        self.assertEqual(kinds[-1], "run_end")
        self.assertEqual(kinds.count("tool_call"), 3)
        self.assertEqual(kinds.count("tool_result"), 3)
        self.assertEqual(events[-1]["answer"]["sql"], DEV["REQ-D20"]["accepted_sql"])
        self.assertTrue(events[0]["packet_matches_counter"])
        index = [json.loads(line) for line in (self.logs / "runs_index.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(index[-1]["run_id"], run_id)
        self.assertNotIn("answer", index[-1])

    def test_queries_come_from_the_counter_not_from_the_agent(self):
        run_id = simulate_run("REQ-D20", queries=4)
        summary = self.collect(run_id, final_message_for("REQ-D20", caveats=["I ran 1 query"]))
        self.assertEqual(summary["queries_used"], 4)

    def test_final_sql_was_run_flag(self):
        run_id = new_run(request_id="REQ-D20", set_name="sim")
        run_tool("S", "hx_sql.py", "--run", run_id, "--sql", "SELECT 7 AS seven")
        ran = self.collect(run_id, final_message_for("REQ-D20", sql="select 7 as seven ;"))
        self.assertTrue(ran["final_sql_was_run"])
        run_id = new_run(request_id="REQ-D20", set_name="sim")
        run_tool("S", "hx_sql.py", "--run", run_id, "--sql", "SELECT 7 AS seven")
        never = self.collect(run_id, final_message_for("REQ-D20", sql="SELECT 8 AS eight"))
        self.assertFalse(never["final_sql_was_run"])

    def test_statuses(self):
        run_id = simulate_run("REQ-D20", queries=1)
        self.assertEqual(self.collect(run_id, "Here is the answer: it is 42.")["status"], "malformed")
        run_id = simulate_run("REQ-D20", queries=1)
        self.assertEqual(self.collect(run_id, "   ")["status"], "no_answer")
        run_id = simulate_run("REQ-D20", queries=1)
        failed = self.collect(run_id, "", agent_failed="the agent stopped after 20 minutes")
        self.assertEqual((failed["status"], failed["problem"]), ("agent_error", "the agent stopped after 20 minutes"))
        run_id = simulate_run("REQ-D20", queries=1)
        fenced = self.collect(run_id, "```json\n" + final_message_for("REQ-D20") + "\n```")
        self.assertEqual(fenced["status"], "ok")

    def test_html_entities_are_unescaped_before_parsing(self):
        """Pilot 2: agents handed back the SQL and category names with &lt; &gt; &amp; in them."""
        import html
        sql = "SELECT a FROM t WHERE x <> 3 AND y < 5 AND z > 1 AND label = 'R&D' AND w = 'a < b'"
        raw = final_message_for("REQ-D20", sql=sql, caveats=["Sport & Outdoor <excluded>"])
        escaped = html.escape(raw, quote=False)                       # & < > only, as the agents' messages had them
        self.assertNotEqual(escaped, raw)
        self.assertIn("&lt;&gt;", escaped)
        run_id = simulate_run("REQ-D20", queries=1)
        summary = self.collect(run_id, escaped)
        self.assertEqual(summary["status"], "ok", summary["problem"])
        self.assertEqual(summary["answer"]["sql"], sql)
        self.assertEqual(summary["answer"]["caveats"], ["Sport & Outdoor <excluded>"])
        self.assertTrue(summary["entities_unescaped"])
        # the log keeps the message as the agent wrote it
        events = [json.loads(line) for line in (self.logs / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e for e in events if e["event"] == "message"][-1]["content"][0]["text"], escaped)
        # an unescaped message is untouched, and says so
        run_id = simulate_run("REQ-D20", queries=1)
        plain = self.collect(run_id, raw)
        self.assertEqual((plain["status"], plain["entities_unescaped"]), ("ok", False))
        # a numeric reference and a double-escaped ampersand are unescaped once, no more
        answer, problem, changed = collect.parse_agent_message(final_message_for("REQ-D20", sql="SELECT &#39;x&#39; AS a, 'R&amp;amp;D'"))
        self.assertIsNotNone(answer, problem)
        self.assertEqual(answer["sql"], "SELECT 'x' AS a, 'R&amp;D'")
        self.assertTrue(changed)

    def test_an_answer_in_a_code_fence_or_after_a_sentence_is_accepted(self):
        message = final_message_for("REQ-D20")
        expected_sql = DEV["REQ-D20"]["accepted_sql"]
        for label, text in [
            ("bare", message),
            ("json fence", "```json\n" + message + "\n```"),
            ("plain fence", "```\n" + message + "\n```"),
            ("sentence before", "Perfect! The query has been validated. Now I will give the final answer:\n\n" + message),
            ("sentence before a fence", "Here is the answer:\n```json\n" + message + "\n```"),
            ("sentence after", message + "\n\nI ran 3 queries {all fine}."),
            ("fence and sentence after with braces", "Result:\n```json\n" + message + "\n```\nNote: {see caveats}."),
            ("surrounding whitespace", "\n\n  " + message + "  \n"),
        ]:
            with self.subTest(label):
                answer, problem, _ = collect.parse_agent_message(text)
                self.assertIsNotNone(answer, f"{label}: {problem}")
                self.assertEqual(answer["sql"], expected_sql)
        # and through the whole collection, with entities and a fence together
        import html
        run_id = simulate_run("REQ-D20", queries=1)
        summary = self.collect(run_id, "Here it is:\n```json\n" + html.escape(message, quote=False) + "\n```")
        self.assertEqual(summary["status"], "ok", summary["problem"])
        self.assertEqual(summary["answer"]["sql"], expected_sql)

    def test_a_message_without_the_contract_is_still_malformed(self):
        for text in ["Here is the answer: it is 42.", '{"sql": "SELECT 1"}', "```json\n{not json}\n```",
                     '{"sql": "x", "result": {"columns": ["a"], "rows": "no"}, "definitions_applied": [], "assumptions": [], "caveats": []}']:
            with self.subTest(text[:30]):
                answer, problem, _ = collect.parse_agent_message(text)
                self.assertIsNone(answer)
                self.assertTrue(problem)

    def test_scripts_and_refusals_are_recorded(self):
        run_id = new_run("L", request_id="REQ-D20", set_name="sim")
        run_tool("L", "hx_script.py", "--run", run_id, "fiscal-calendar/scripts/fiscal.py", "last period")
        path = PATHS.counters_dir / f"{run_id}.json"
        data = counter_of(run_id)
        data["used"] = BUDGET
        path.write_text(json.dumps(data), encoding="utf-8")
        run_tool("L", "hx_sql.py", "--run", run_id, "--sql", "SELECT 1")
        summary = self.collect(run_id, final_message_for("REQ-D20"))
        self.assertEqual(summary["scripts_run"], ["fiscal-calendar/scripts/fiscal.py"])
        self.assertEqual(summary["refused_query_calls"], 1)

    def test_an_earlier_log_is_kept_as_an_attempt(self):
        run_id = simulate_run("REQ-D20", queries=1)
        self.collect(run_id, final_message_for("REQ-D20"))
        self.collect(run_id, "second try")
        self.assertTrue((self.logs / f"{run_id}.attempt1.jsonl").exists())
        self.assertEqual(json.loads((self.logs / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines()[-1])["status"], "malformed")

    def test_unregistered_runs_and_input_folders_are_refused(self):
        with self.assertRaises(SystemExit):
            self.collect("never-registered", "{}")
        run_id = simulate_run("REQ-D20", queries=1)
        with self.assertRaises(SystemExit):
            self.collect(run_id, "{}", out_dir=PATHS.packets_dir)
        with self.assertRaises(SystemExit):
            self.collect(run_id, "{}", out_dir=cfg.WORLD_DIR)

    def test_what_the_agent_tool_reports(self):
        self.assertEqual(collect.parse_tokens("48,210"), 48210)
        self.assertEqual(collect.parse_tokens("48.2k"), 48200)
        self.assertEqual(collect.parse_tokens("1.5m"), 1500000)
        self.assertEqual(collect.parse_duration_seconds("95"), 95)
        self.assertEqual(collect.parse_duration_seconds("2m 41s"), 161)
        self.assertEqual(collect.parse_duration_seconds("1:35"), 95)
        self.assertEqual(collect.parse_duration_seconds("1:02:03"), 3723)
        self.assertEqual(collect.parse_duration_seconds("161000ms"), 161)
        self.assertEqual(collect.parse_duration_seconds("2.5 min"), 150)
        with self.assertRaises(SystemExit):
            collect.parse_tokens("lots")
        with self.assertRaises(SystemExit):
            collect.parse_duration_seconds("a while")

    def test_command_line(self):
        run_id = simulate_run("REQ-D20", queries=1)
        message = TMP_ROOT / "final_cli.txt"
        message.write_text(final_message_for("REQ-D20"), encoding="utf-8")
        # the CLI uses the real agent folder; point it at the temporary one through a patched default
        with mock.patch.object(bp.AgentPaths, "default", classmethod(lambda cls: PATHS)):
            code = collect.main(["--run", run_id, "--final-message-file", str(message), "--tokens", "12.5k", "--tool-calls", "7",
                                 "--duration", "1m 5s", "--out-dir", str(self.logs)])
        self.assertEqual(code, 0)
        summary = json.loads((self.logs / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((summary["tokens"]["total_tokens"], summary["elapsed_s"], summary["tool_calls_reported"]), (12500, 65.0, 7))


class TestMarking(unittest.TestCase):
    def test_any_of_label_groups(self):
        table = {"columns": ["rank", "store_id", "store_name", "net_sales_per_trading_day"],
                 "rows": [[1, 115, "Tampere Hervanta", 2504.0], [2, 102, "Helsinki Pitäjänmäki", 2297.0]]}
        spec = {"dimensions": ["rank", "store_id", "store_name"], "required": [["store_name", "store_id"], "net_sales_per_trading_day"], "ordered": True}
        by_name = {"columns": ["store", "per_day"], "rows": [["Tampere Hervanta", 2504.3], ["Helsinki Pitäjänmäki", 2297.1]]}
        by_id = {"columns": ["id", "per_day"], "rows": [[115, 2504.0], [102, 2297.0]]}
        neither = {"columns": ["per_day"], "rows": [[2504.0], [2297.0]]}
        swapped = {"columns": ["store", "per_day"], "rows": [["Helsinki Pitäjänmäki", 2297.0], ["Tampere Hervanta", 2504.0]]}
        self.assertTrue(pilot_marking.compare_tables(table, by_name, True, spec)[0])
        self.assertTrue(pilot_marking.compare_tables(table, by_id, True, spec)[0])
        self.assertFalse(pilot_marking.compare_tables(table, neither, True, spec)[0])
        self.assertFalse(pilot_marking.compare_tables(table, swapped, True, spec)[0])           # a league table is ordered
        self.assertTrue(pilot_marking.compare_tables(table, swapped, False, spec)[0])
        self.assertEqual(pilot_marking.required_variants(["a", ["b", "c"], ["x", "c"]], ["a", "b", "c"]), [["a", "b", "c"]])
        self.assertEqual(pilot_marking.required_variants(["a", ["b", "c"]], ["a", "b", "c"]), [["a", "b"], ["a", "c"]])

    def test_the_spec_can_force_order(self):
        self.assertTrue(expected_for("REQ-D40")["ordered"])
        self.assertTrue(expected_for("REQ-D34")["ordered"])
        self.assertFalse(expected_for("REQ-D05")["ordered"])

    def test_every_pilot2_spec_names_real_columns_and_the_accepted_table_passes(self):
        for request_id in cfg.PILOT2_REQUEST_IDS:
            entry = expected_for(request_id)
            spec = pilot_marking.answer_spec(request_id)
            columns = entry["table"]["columns"]
            names = {n for item in spec["required"] for n in (item if isinstance(item, list) else [item])}
            self.assertTrue(names <= set(columns), (request_id, names - set(columns)))
            self.assertTrue(set(spec["dimensions"]) <= set(columns), request_id)
            ok, reason = pilot_marking.compare_tables(entry["table"], entry["table"], entry["ordered"], spec)
            self.assertTrue(ok, (request_id, reason))
            for alternative in entry["alternatives"]:
                self.assertTrue(pilot_marking.compare_tables(alternative["table"], alternative["table"], entry["ordered"],
                                                             alternative.get("wide_spec", spec))[0], (request_id, alternative["label"]))

    def test_every_pilot3_spec_names_real_columns_and_the_accepted_table_passes(self):
        for request_id in cfg.PILOT3_REQUEST_IDS:
            entry = expected_for(request_id)
            spec = pilot_marking.answer_spec(request_id)
            self.assertIsNotNone(spec, request_id)
            columns = entry["table"]["columns"]
            names = {n for item in spec["required"] for n in (item if isinstance(item, list) else [item])}
            self.assertTrue(names <= set(columns), (request_id, names - set(columns)))
            self.assertTrue(set(spec["dimensions"]) <= set(columns), request_id)
            ok, reason = pilot_marking.compare_tables(entry["table"], entry["table"], entry["ordered"], spec)
            self.assertTrue(ok, (request_id, reason))
        # order matters exactly where the request is a ranking
        ordered = {request_id: expected_for(request_id)["ordered"] for request_id in cfg.PILOT3_REQUEST_IDS}
        self.assertEqual({k for k, v in ordered.items() if v}, {"REQ-D12", "REQ-D35", "REQ-D39"})

    def test_pilot3_wrong_numbers_missing_columns_and_missing_rows_fail(self):
        for request_id in cfg.PILOT3_REQUEST_IDS:
            entry = expected_for(request_id)
            spec = pilot_marking.answer_spec(request_id)
            table = entry["table"]
            required = [n for item in spec["required"] for n in (item if isinstance(item, list) else [item])]
            numeric = [n for n in required if isinstance(table["rows"][0][table["columns"].index(n)], (int, float))
                       and n not in ("rank", "fiscal_week", "fiscal_quarter", "fiscal_period", "day_of_week", "store_id")]
            self.assertTrue(numeric, request_id)
            position = table["columns"].index(numeric[-1])
            bent = {"columns": table["columns"], "rows": [[v * 1.05 if i == position else v for i, v in enumerate(row)] for row in table["rows"]]}
            self.assertFalse(pilot_marking.compare_tables(table, bent, entry["ordered"], spec)[0], request_id)
            if len(table["rows"]) > 1:
                short = {"columns": table["columns"], "rows": table["rows"][:-1]}
                self.assertFalse(pilot_marking.compare_tables(table, short, entry["ordered"], spec)[0], request_id)

    def test_pilot3_shapes_that_must_pass_and_fail(self):
        # supporting columns may go (REQ-D08 growth only, REQ-D03 without growth), a total row above a breakdown may be added
        d08 = expected_for("REQ-D08")
        growth_only = {"columns": ["region", "lfl_growth_pct"], "rows": [[r[0], r[3]] for r in d08["table"]["rows"]]}
        self.assertTrue(pilot_marking.compare_tables(d08["table"], growth_only, False, pilot_marking.answer_spec("REQ-D08"))[0])
        with_total = {"columns": ["region", "lfl_growth_pct"], "rows": [[None, 2.0]] + growth_only["rows"]}
        self.assertTrue(pilot_marking.compare_tables(d08["table"], with_total, False, pilot_marking.answer_spec("REQ-D08"))[0])
        total_only = {"columns": ["lfl_growth_pct"], "rows": [[2.0]]}
        self.assertFalse(pilot_marking.compare_tables(d08["table"], total_only, False, pilot_marking.answer_spec("REQ-D08"))[0])
        d03 = expected_for("REQ-D03")["table"]
        no_growth = {"columns": ["fiscal_week", "this_year", "last_year"], "rows": [r[:3] for r in d03["rows"]]}
        self.assertTrue(pilot_marking.compare_tables(d03, no_growth, False, pilot_marking.answer_spec("REQ-D03"))[0])
        # a part week or a week from outside Q3 is an extra row with real figures: wrong (the whole-weeks rule)
        part_week = {"columns": no_growth["columns"], "rows": no_growth["rows"] + [[40, 120000.0, 110000.0]]}
        self.assertFalse(pilot_marking.compare_tables(d03, part_week, False, pilot_marking.answer_spec("REQ-D03"))[0])
        # weekday by number or by name; a league table in the wrong order fails
        d27 = expected_for("REQ-D27")["table"]
        by_name = {"columns": ["day_name", "atv"], "rows": [[r[1], r[3]] for r in d27["rows"]]}
        by_number = {"columns": ["weekday", "atv"], "rows": [[r[0], r[3]] for r in d27["rows"]]}
        for answer in (by_name, by_number):
            self.assertTrue(pilot_marking.compare_tables(d27, answer, False, pilot_marking.answer_spec("REQ-D27"))[0])
        d39 = expected_for("REQ-D39")
        position = d39["table"]["columns"].index("net_sales_per_trading_day")
        name = d39["table"]["columns"].index("store_name")
        league = {"columns": ["store", "per_day"], "rows": [[r[name], r[position]] for r in d39["table"]["rows"]]}
        self.assertTrue(pilot_marking.compare_tables(d39["table"], league, True, pilot_marking.answer_spec("REQ-D39"))[0])
        league["rows"][0], league["rows"][1] = league["rows"][1], league["rows"][0]
        self.assertFalse(pilot_marking.compare_tables(d39["table"], league, True, pilot_marking.answer_spec("REQ-D39"))[0])
        # one figure, with or without a label
        d29 = expected_for("REQ-D29")["table"]
        self.assertTrue(pilot_marking.compare_tables(d29, {"columns": ["n"], "rows": [[d29["rows"][0][0]]]}, False, pilot_marking.answer_spec("REQ-D29"))[0])
        self.assertFalse(pilot_marking.compare_tables(d29, {"columns": ["n"], "rows": [[d29["rows"][0][0] + 500]]}, False, pilot_marking.answer_spec("REQ-D29"))[0])

    def test_wrong_numbers_and_missing_required_columns_fail(self):
        for request_id in cfg.PILOT2_REQUEST_IDS:
            entry = expected_for(request_id)
            spec = pilot_marking.answer_spec(request_id)
            table = entry["table"]
            required = [n for item in spec["required"] for n in (item if isinstance(item, list) else [item])]
            numeric = [n for n in required if n in table["columns"] and isinstance(table["rows"][0][table["columns"].index(n)], (int, float))
                       and n not in ("rank", "fiscal_week", "fiscal_quarter", "fiscal_period")]
            self.assertTrue(numeric, request_id)
            position = table["columns"].index(numeric[-1])
            bent = {"columns": table["columns"], "rows": [[v * 1.05 if i == position else v for i, v in enumerate(row)] for row in table["rows"]]}
            self.assertFalse(pilot_marking.compare_tables(table, bent, entry["ordered"], spec)[0], request_id)
            short = {"columns": table["columns"], "rows": table["rows"][:-1]} if len(table["rows"]) > 1 else {"columns": table["columns"], "rows": []}
            self.assertFalse(pilot_marking.compare_tables(table, short, entry["ordered"], spec)[0], request_id)

    def test_supporting_columns_may_be_left_out_and_extras_are_fine(self):
        for request_id, keep in (("REQ-D10", ["category", "net_sales", "gross_margin_pct"]), ("REQ-D09", ["lfl_growth_pct"]),
                                 ("REQ-D34", ["brand", "gross_margin"]), ("REQ-D16", ["category", "channel_group", "return_rate_pct"])):
            entry = expected_for(request_id)
            table = entry["table"]
            positions = [table["columns"].index(name) for name in keep]
            trimmed = {"columns": keep, "rows": [[row[p] for p in positions] for row in table["rows"]]}
            self.assertTrue(pilot_marking.compare_tables(table, trimmed, entry["ordered"], pilot_marking.answer_spec(request_id))[0], request_id)
            padded = {"columns": table["columns"] + ["note"], "rows": [row + ["x"] for row in table["rows"]]}
            self.assertTrue(pilot_marking.compare_tables(table, padded, entry["ordered"], pilot_marking.answer_spec(request_id))[0], request_id)

    def test_d16_accepts_both_readings_of_last_year_and_d19_accepts_either_week_label(self):
        entry = expected_for("REQ-D16")
        # the previous fiscal year, the wide shape, and both together
        self.assertEqual(len(entry["alternatives"]), 3)
        self.assertEqual([bool(a.get("wide_spec")) for a in entry["alternatives"]], [False, True, True])
        alternative = entry["alternatives"][0]["table"]
        self.assertNotEqual(alternative["rows"], entry["table"]["rows"])
        result = pilot_marking.mark_run({"status": "ok", "answer": {"result": alternative}}, entry["table"], entry["ordered"],
                                        spec=pilot_marking.answer_spec("REQ-D16"), alternatives=entry["alternatives"])
        self.assertEqual(result["outcome"], "correct")
        self.assertIn("accepted alternative", result["reason"])
        d19 = expected_for("REQ-D19")["table"]
        for label in ("fiscal_week", "week_start"):
            position = d19["columns"].index(label)
            answer = {"columns": [label, "web_net_sales"], "rows": [[row[position], row[d19["columns"].index("web_net_sales")]] for row in d19["rows"]]}
            self.assertTrue(pilot_marking.compare_tables(d19, answer, False, pilot_marking.answer_spec("REQ-D19"))[0], label)

    def test_trap_readings_still_fail(self):
        """A table that looks right but carries a trap's number must stay wrong: here, REQ-D24 with the incomplete current quarter added."""
        entry = expected_for("REQ-D24")
        table = entry["table"]
        extra = {"columns": table["columns"], "rows": table["rows"] + [["FY2025/26", 4, 9000, 2100, 23.3]]}
        self.assertFalse(pilot_marking.compare_tables(table, extra, False, pilot_marking.answer_spec("REQ-D24"))[0])

    # ---- marker version 4 (pilot 2 diagnosis) ------------------------------------------------------------------------------

    def test_a_column_the_accepted_query_rounded_may_be_given_unrounded(self):
        """REQ-D40 rounds net sales per trading day to whole euros: 372.5 against 373 is more than 0.1% but less than half a euro."""
        entry = expected_for("REQ-D40")
        table, spec = entry["table"], pilot_marking.answer_spec("REQ-D40")
        position = table["columns"].index("net_sales_per_trading_day")
        self.assertEqual(pilot_marking.rounding_half_unit([row[position] for row in table["rows"]]), 0.5)

        def with_figures(shift: float) -> dict:
            rows = [list(row) for row in table["rows"]]
            for row in rows:
                row[position] = row[position] + shift
            return {"columns": table["columns"], "rows": rows}
        self.assertTrue(pilot_marking.compare_tables(table, with_figures(0.45), True, spec)[0])
        self.assertTrue(pilot_marking.compare_tables(table, with_figures(-0.45), True, spec)[0])
        self.assertFalse(pilot_marking.compare_tables(table, with_figures(0.6), True, spec)[0])
        # counts are never rounded figures, and a short column is not taken as rounded
        self.assertEqual(pilot_marking.rounding_half_unit([35, 35, 7, 35, 35]), 0.0)
        self.assertEqual(pilot_marking.rounding_half_unit([2.0, 3.0]), 0.0)
        self.assertEqual(pilot_marking.rounding_half_unit([4.61, 2.0, 5.43, 10.11, 23.24]), 0.0)
        self.assertEqual(pilot_marking.rounding_half_unit([4.6, 2.0, 5.4, 10.1, 23.2]), 0.05)

    def test_web_and_stores_side_by_side_carry_the_same_rates(self):
        entry = expected_for("REQ-D16")
        table, spec = entry["table"], pilot_marking.answer_spec("REQ-D16")
        category, channel, rate = (table["columns"].index(n) for n in ("category", "channel_group", "return_rate_pct"))
        by_category = {}
        for row in table["rows"]:
            by_category.setdefault(row[category], {})[row[channel]] = row[rate]
        wide = {"columns": ["category", "web_return_rate_pct", "stores_return_rate_pct"],
                "rows": [[name, rates["Web"], rates["Stores"]] for name, rates in by_category.items()]}
        summary = {"status": "ok", "answer": {"result": wide}}
        mark = pilot_marking.mark_run(summary, table, entry["ordered"], spec=spec, alternatives=entry["alternatives"])
        self.assertEqual(mark["outcome"], "correct", mark["reason"])
        self.assertIn("channel_group as columns", mark["reason"])
        # not without the alternative, and not with a wrong figure or a missing channel
        self.assertFalse(pilot_marking.compare_tables(table, wide, entry["ordered"], spec)[0])
        bent = {"columns": wide["columns"], "rows": [[r[0], r[1] * 1.2, r[2]] for r in wide["rows"]]}
        self.assertEqual(pilot_marking.mark_run({"status": "ok", "answer": {"result": bent}}, table, entry["ordered"], spec=spec,
                                                alternatives=entry["alternatives"])["outcome"], "wrong")
        web_only = {"columns": ["category", "web_rate"], "rows": [[r[0], r[1]] for r in wide["rows"]]}
        self.assertEqual(pilot_marking.mark_run({"status": "ok", "answer": {"result": web_only}}, table, entry["ordered"], spec=spec,
                                                alternatives=entry["alternatives"])["outcome"], "wrong")
        # the previous fiscal year, side by side, with the singular label in the long form
        previous = next(a for a in entry["alternatives"] if a["label"] == "'last year' = FY2024/25")["table"]
        category, channel, rate = (previous["columns"].index(n) for n in ("category", "channel_group", "return_rate_pct"))
        long_form = {"columns": ["category", "channel", "return_rate_pct"],
                     "rows": [[row[category], "Store" if row[channel] == "Stores" else row[channel], row[rate]] for row in previous["rows"]]}
        mark = pilot_marking.mark_run({"status": "ok", "answer": {"result": long_form}}, table, entry["ordered"], spec=spec, alternatives=entry["alternatives"])
        self.assertEqual(mark["outcome"], "correct", mark["reason"])

    def test_widen_table(self):
        long_table = {"columns": ["k", "ch", "m", "x"], "rows": [["a", "Stores", 1.0, 9], ["a", "Web", 2.0, 9], ["b", "Stores", 3.0, 9], ["b", "Web", 4.0, 9]]}
        wide = pilot_marking.widen_table(long_table, "ch", "m", ["k", "ch"])
        self.assertEqual(wide["table"], {"columns": ["k", "Stores_m", "Web_m"], "rows": [["a", 1.0, 2.0], ["b", 3.0, 4.0]]})
        self.assertEqual(wide["spec"], {"dimensions": ["k"], "required": ["k", "Stores_m", "Web_m"]})

    # ---- marker version 5 (after pilot 2): a fused fiscal label equals a separate year and number ----------------

    def test_marker_version_is_5(self):
        self.assertEqual(pilot_marking.MARKER_VERSION, "5")

    def test_split_fused_fiscal_columns(self):
        columns, rows, count = pilot_marking.split_fused_fiscal_columns(
            ["label", "x"], [["FY2025/26 P07", 1.5], ["fy2024/25 q1", 2.5], ["FY2025/26W15", 3.5], ["FY2025/26-P7", 4.5], ["FY2025/26 W 03", 5.5]])
        self.assertEqual(count, 1)
        self.assertEqual(columns, ["label", "x", "label (fiscal year)", "label (number)"])
        self.assertEqual([row[2:] for row in rows], [["FY2025/26", 7], ["FY2024/25", 1], ["FY2025/26", 15], ["FY2025/26", 7], ["FY2025/26", 3]])
        # the fused column stays, the other columns are untouched
        self.assertEqual([row[:2] for row in rows][0], ["FY2025/26 P07", 1.5])
        # a column where only some cells are fused, a plain number, a label without a year, a period of another form: not split
        for cells in (["FY2025/26 P07", "P08"], [7, 8], ["P07", "P08"], ["FY2025/26", "FY2025/26"], ["FY2025/26 P07", None], ["Total", "FY2025/26 P07"],
                      ["FY2025/26 P07 and more", "FY2025/26 P08"], ["FY25/26 P07", "FY25/26 P08"]):
            unchanged = pilot_marking.split_fused_fiscal_columns(["c"], [[cell] for cell in cells])
            self.assertEqual(unchanged[2], 0, cells)
        self.assertEqual(pilot_marking.split_fused_fiscal_columns(["c"], [])[2], 0)

    def test_periods_fused_with_their_year_equal_the_separate_columns(self):
        """'FY2025/26 P07', 'FY2024/25 Q1' and 'FY2025/26 W15' are the same answer as a fiscal_year column and a plain number."""
        d28 = expected_for("REQ-D28")["table"]
        spec28 = pilot_marking.answer_spec("REQ-D28")
        fused = {"columns": ["period", "pori_atv", "chain_atv"], "rows": [[f"FY2025/26 P{row[0]:02d}", row[1], row[2]] for row in d28["rows"]]}
        ok, reason = pilot_marking.compare_tables(d28, fused, False, spec28)
        self.assertTrue(ok, reason)
        self.assertIn("fused fiscal label", reason)
        plain = {"columns": ["fiscal_year", "fiscal_period", "pori_atv", "chain_atv"], "rows": [["FY2025/26"] + list(row) for row in d28["rows"]]}
        ok, reason = pilot_marking.compare_tables(d28, plain, False, spec28)
        self.assertTrue(ok)
        self.assertNotIn("fused", reason)
        d24 = expected_for("REQ-D24")["table"]
        spec24 = pilot_marking.answer_spec("REQ-D24")
        fused = {"columns": ["quarter", "share"], "rows": [[f"{row[0]} Q{row[1]}", row[4]] for row in d24["rows"]]}
        self.assertTrue(pilot_marking.compare_tables(d24, fused, False, spec24)[0])
        d19 = expected_for("REQ-D19")["table"]
        year, week, sales = (d19["columns"].index(n) for n in ("fiscal_year", "fiscal_week", "web_net_sales"))
        fused = {"columns": ["week", "web_sales"], "rows": [[f"{row[year]} W{row[week]:02d}", row[sales]] for row in d19["rows"]]}
        self.assertTrue(pilot_marking.compare_tables(d19, fused, False, pilot_marking.answer_spec("REQ-D19"))[0])
        # and through mark_run, as the collector's marking does it
        summary = {"status": "ok", "answer": {"result": fused}}
        mark = pilot_marking.mark_run(summary, d19, False, spec=pilot_marking.answer_spec("REQ-D19"))
        self.assertEqual(mark["outcome"], "correct", mark["reason"])

    def test_fused_labels_are_still_held_to_the_right_year_and_number_and_figures(self):
        d24 = expected_for("REQ-D24")["table"]
        spec24 = pilot_marking.answer_spec("REQ-D24")
        label = lambda row, year=None, shift=0: f"{year or row[0]} Q{row[1] + shift}"
        good = {"columns": ["quarter", "share"], "rows": [[label(row), row[4]] for row in d24["rows"]]}
        self.assertTrue(pilot_marking.compare_tables(d24, good, False, spec24)[0])
        wrong_year = {"columns": ["quarter", "share"], "rows": [[label(row, "FY2019/20"), row[4]] for row in d24["rows"]]}
        self.assertFalse(pilot_marking.compare_tables(d24, wrong_year, False, spec24)[0])
        wrong_number = {"columns": ["quarter", "share"], "rows": [[label(row, shift=1), row[4]] for row in d24["rows"]]}
        self.assertFalse(pilot_marking.compare_tables(d24, wrong_number, False, spec24)[0])
        wrong_figure = {"columns": ["quarter", "share"], "rows": [[label(row), row[4] * 1.05] for row in d24["rows"]]}
        self.assertFalse(pilot_marking.compare_tables(d24, wrong_figure, False, spec24)[0])
        # a trap reading stays wrong with a fused label: an incomplete quarter added
        extra = {"columns": ["quarter", "share"], "rows": [[label(row), row[4]] for row in d24["rows"]] + [["FY2026/27 Q1", 23.3]]}
        self.assertFalse(pilot_marking.compare_tables(d24, extra, False, spec24)[0])
        # a label with some cells fused and some plain is not read as fiscal
        half = {"columns": ["quarter", "share"], "rows": [[label(row), row[4]] for row in d24["rows"]]}
        half["rows"][0][0] = str(d24["rows"][0][1])
        self.assertFalse(pilot_marking.compare_tables(d24, half, False, spec24)[0])

    def test_marking_agent_runs_end_to_end(self):
        logs = TMP_ROOT / "marking_logs"
        out = TMP_ROOT / "marking_out"
        wrong_table = {"columns": expected_for("REQ-D30")["table"]["columns"], "rows": [["Basic", 1], ["Gold", 1], ["Silver", 1]]}
        runs = [("REQ-D30", "S", "sonnet", final_message_for("REQ-D30")), ("REQ-D30", "D", "sonnet", final_message_for("REQ-D30", table=wrong_table)),
                ("REQ-D28", "L", "haiku", "no json here"), ("REQ-D10", "L", "haiku", final_message_for("REQ-D10"))]
        for request_id, arm, alias, text in runs:
            run_id = simulate_run(request_id, arm, alias, queries=1)
            collect.collect(run_id, text, total_tokens=1000, tool_calls=4, duration_s=30.0, paths=PATHS, out_dir=logs)
        summary = pilot_marking.mark_agent_runs(logs, out, quiet=True)
        results = [json.loads(line) for line in (out / "agent_results.jsonl").read_text(encoding="utf-8").splitlines()]
        outcomes = {(r["request_id"], r["arm"]): r["outcome"] for r in results}
        self.assertEqual(outcomes, {("REQ-D30", "S"): "correct", ("REQ-D30", "D"): "wrong", ("REQ-D28", "L"): "no_answer", ("REQ-D10", "L"): "correct"})
        self.assertEqual(summary["correct_total"], 2)
        self.assertEqual(summary["by_cell"]["sonnet/S"]["correct"], 1)
        text = (out / "agent_summary.txt").read_text(encoding="utf-8")
        self.assertIn("2 correct of 4", text)
        self.assertIn("Runs not marked correct", text)
        self.assertTrue((out / "expected_results.json").exists())
        with self.assertRaises(SystemExit):
            pilot_marking.mark_agent_runs(logs, logs, quiet=True)

    def test_marking_one_set_leaves_the_other_sets_logs_alone(self):
        """Pilot 2's and pilot 3's logs share a folder; marking pilot3 must not touch pilot 2's, and the CLI defaults follow the set."""
        logs, out = TMP_ROOT / "marking_logs_sets", TMP_ROOT / "marking_out_sets"
        for set_name in ("setA", "setB"):
            run_id = new_run("S", "sonnet", "REQ-D30", set_name=set_name)
            done = run_tool("S", "hx_sql.py", "--run", run_id, "--sql", "SELECT 1")
            self.assertEqual(done.returncode, 0)
            collect.collect(run_id, final_message_for("REQ-D30"), total_tokens=1, tool_calls=1, duration_s=1.0, paths=PATHS, out_dir=logs)
        summary = pilot_marking.mark_agent_runs(logs, out, quiet=True, run_prefix="setB-")
        self.assertEqual(summary["runs_marked"], 1)
        results = [json.loads(line) for line in (out / "agent_results.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all(r["run_id"].startswith("setB-") for r in results))
        # without a prefix both are marked (the library call keeps its old behaviour)
        both = pilot_marking.mark_agent_runs(logs, TMP_ROOT / "marking_out_sets_all", quiet=True)
        self.assertEqual(both["runs_marked"], 2)

    def test_test_requests_wait_for_the_phase_6_marker(self):
        if not (cfg.REQUESTS_DIR / "test_requests.json").exists():
            self.skipTest("data/requests is locked")
        logs = TMP_ROOT / "marking_logs_t"
        run_id = new_run("S", "sonnet", "REQ-T05", set_name="simt")
        collect.collect(run_id, "{}", total_tokens=1, tool_calls=1, duration_s=1.0, paths=PATHS, out_dir=logs)
        summary = pilot_marking.mark_agent_runs(logs, TMP_ROOT / "marking_out_t", quiet=True)
        self.assertEqual(summary["runs_marked"], 0)
        self.assertTrue(any("Phase 6" in note for note in summary["skipped"]))


# ---------------------------------------------------------------------------
# The required-flag proposal
# ---------------------------------------------------------------------------

class TestRequiredFlagProposal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key_path = cfg.KEY_DIR / "key.json"
        if not key_path.exists():
            raise unittest.SkipTest("the key is locked")
        cls.key_bytes = key_path.read_bytes()
        cls.proposal = proposal.build_proposal(json.loads(cls.key_bytes.decode("utf-8")))
        cls.by_id = {entry["request_id"]: entry for entry in cls.proposal["entries"]}

    def flags(self, request_id: str) -> dict:
        return {m["name"]: m["required"] for m in self.by_id[request_id]["measures"]}

    def test_counts_match_the_diagnosis(self):
        self.assertEqual(self.proposal["entries_total"], 60)
        self.assertEqual(self.proposal["entries_with_more_than_one_measure"], 19)
        self.assertEqual(sorted(e["request_id"] for e in self.proposal["entries"] if e["supporting"]),
                         ["REQ-T01", "REQ-T06", "REQ-T08", "REQ-T17", "REQ-T23", "REQ-T26", "REQ-T34", "REQ-T42", "REQ-T53", "REQ-T58"])

    def test_decisions(self):
        self.assertEqual(self.flags("REQ-T01"), {"net_sales_ty": False, "net_sales_ly": False, "lfl_growth_pct": True})
        self.assertEqual(self.flags("REQ-T05"), {"net_sales_ty": True, "net_sales_ly": True, "growth_pct": True})
        self.assertEqual(self.flags("REQ-T06"), {"sold_net": False, "returned_net": False, "return_rate_pct": True})
        self.assertEqual(self.flags("REQ-T26"), {"trading_days": False, "net_sales": False, "net_sales_per_trading_day": True})
        self.assertTrue(all(self.flags("REQ-T04").values()))
        self.assertTrue(all(self.flags("REQ-T51").values()))
        self.assertTrue(all(self.flags("REQ-T22").values()))
        self.assertTrue(all(self.flags("REQ-T44").values()))
        self.assertTrue(all(self.flags("REQ-T11").values()))

    def test_every_single_measure_entry_is_required_and_ids_are_flagged(self):
        for entry in self.proposal["entries"]:
            self.assertTrue(entry["measures"], entry["request_id"])
            if not entry["multi_measure"]:
                self.assertTrue(entry["measures"][0]["required"])
        self.assertIn("store_id", self.by_id["REQ-T26"]["accept_name_or_id"])

    def test_the_key_is_not_touched(self):
        self.assertEqual((cfg.KEY_DIR / "key.json").read_bytes(), self.key_bytes)
        self.assertIn("Proposed `required` flags", proposal.build_markdown(self.proposal))


if __name__ == "__main__":
    unittest.main(verbosity=1)
