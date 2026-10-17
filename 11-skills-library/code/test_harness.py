"""Tests for the Phase 5 harness, the scripted client, the pilot marker and the pilot runner. No key, no network.

    python code/test_harness.py            (from anywhere; Python 3.10 with duckdb and pandas)

A socket guard makes any network connection fail the test run, and a final test checks that the anthropic SDK was never
even imported, so passing here shows the dry run needs no key and touches no network.

Everything is written under a temporary folder; nothing in the case folder is created or changed.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE_DIR))

import config as cfg                      # noqa: E402
import harness                            # noqa: E402
import pilot_marking                      # noqa: E402
import run_pilot                          # noqa: E402
from fake_client import ScriptedClient, POLICIES   # noqa: E402

DEV = harness.load_dev_requests()
SMALL_REQUEST = "REQ-D20"                 # web orders by hour on Black Friday: a 24-row accepted result
EXPECTED_SMALL = None
ORIGINAL_CONNECT = socket.socket.connect


def block_network() -> None:
    def refuse(self, *args, **kwargs):
        raise AssertionError("network access attempted during the tests")
    socket.socket.connect = refuse


def setUpModule() -> None:
    block_network()
    global EXPECTED_SMALL
    EXPECTED_SMALL = pilot_marking.compute_expected(cfg.WAREHOUSE_PATH, DEV[SMALL_REQUEST]["accepted_sql"])


def tearDownModule() -> None:
    socket.socket.connect = ORIGINAL_CONNECT


def make_client(policy: str = "correct") -> ScriptedClient:
    return ScriptedClient({entry["request"]["request_text"]: entry["accepted_sql"] for entry in DEV.values()}, policy=policy)


def read_log(path: Path) -> list:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skills_harness_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)


# ---------------------------------------------------------------------------

class TestCostAndTask(unittest.TestCase):
    def test_cost_formula_matches_published_prices(self):
        usage = {"input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000,
                 "cache_read_input_tokens": 1_000_000, "output_tokens": 1_000_000}
        self.assertAlmostEqual(harness.usage_cost_usd(usage, "claude-sonnet-5-5"), 2.0 + 2.5 + 0.1 + 10.0)
        self.assertAlmostEqual(harness.usage_cost_usd(usage, "claude-haiku-4-5-20251001"), 1.0 + 1.25 + 0.1 + 5.0)

    def test_unknown_model_has_no_price(self):
        with self.assertRaises(SystemExit):
            harness.prices_for("claude-nonesuch")

    def test_upper_bound_exceeds_a_realistic_call(self):
        realistic = harness.usage_cost_usd({"input_tokens": 500, "cache_creation_input_tokens": 3000,
                                            "cache_read_input_tokens": 50000, "output_tokens": 3000}, "claude-sonnet-5-5")
        self.assertGreater(harness.call_cost_upper_bound_usd(200_000, "claude-sonnet-5-5"), realistic)

    def test_task_text_fills_every_placeholder(self):
        text = harness.task_text(DEV[SMALL_REQUEST]["request"])
        self.assertIn(DEV[SMALL_REQUEST]["request"]["request_text"], text)
        self.assertIn(f"up to {cfg.MAX_QUERY_EXECUTIONS} queries", text)
        self.assertNotIn("{", text.replace('{"columns"', ""))

    def test_dev_requests_parse(self):
        self.assertEqual(len(DEV), 40)
        for entry in DEV.values():
            self.assertTrue(entry["accepted_sql"].strip())
            self.assertTrue(entry["request"]["request_text"])

    def test_pilot_requests_are_dev_requests_and_not_the_docs_full_queries(self):
        for request_id in cfg.PILOT_REQUEST_IDS:
            self.assertIn(request_id, DEV)
        self.assertFalse({"REQ-D01", "REQ-D07", "REQ-D25"} & set(cfg.PILOT_REQUEST_IDS))

    def test_parse_final_answer_variants(self):
        good = {"sql": "select 1", "result": {"columns": ["a"], "rows": [[1]]}, "definitions_applied": [], "assumptions": [], "caveats": []}
        self.assertEqual(harness.parse_final_answer(json.dumps(good))[0], good)
        self.assertEqual(harness.parse_final_answer("Sure.\n```json\n" + json.dumps(good) + "\n```")[0], good)
        self.assertIsNone(harness.parse_final_answer("not json")[0])
        self.assertIsNone(harness.parse_final_answer(json.dumps({"sql": "x"}))[0])
        bad_result = dict(good, result={"columns": ["a"], "rows": [1]})
        self.assertIsNone(harness.parse_final_answer(json.dumps(bad_result))[0])
        self.assertIsNone(harness.parse_final_answer("")[0])


class TestArmMaterials(TempDirCase):
    def test_arms_differ_only_as_designed(self):
        materials = {arm: harness.build_arm_materials(arm) for arm in cfg.ARM_LABELS}
        self.assertEqual(materials["S"].tool_names, ["run_sql"])
        self.assertEqual(materials["D"].tool_names, ["run_sql"])
        self.assertEqual(materials["L"].tool_names, ["run_sql", "load_skill", "run_script"])
        self.assertEqual(materials["L-"].tool_names, ["run_sql", "load_skill"])
        doc_first_line = cfg.ARMS_DOC_PATH.read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("Team prompt document", materials["D"].system_text)
        self.assertNotIn("Team prompt document", materials["S"].system_text)
        self.assertEqual(len(materials["L"].skill_names), 10)
        for name in materials["L"].skill_names:
            self.assertIn(f"- {name}:", materials["L"].system_text)
            self.assertIn(f"- {name}:", materials["L-"].system_text)
        self.assertIn("No script runner", materials["L-"].system_text)
        self.assertNotIn("No script runner", materials["L"].system_text)
        schema_part = materials["S"].system_text
        for arm in ("D", "L", "L-"):
            self.assertTrue(materials[arm].system_text.startswith(schema_part))
        self.assertTrue(doc_first_line)

    def test_provenance_markers_stripped_and_nothing_forbidden_present(self):
        for arm in cfg.ARM_LABELS:
            text = harness.build_arm_materials(arm).system_text
            self.assertNotIn("<!-- facts", text)
            self.assertNotIn("<!-- source", text)
            for forbidden in ("build_notes", "INC-1", "INC-2", "INC-3", "INC-4", "REQ-T", "key.json"):
                self.assertNotIn(forbidden, text)

    def test_static_prompt_is_deterministic(self):
        self.assertEqual(harness.build_arm_materials("D").sha256, harness.build_arm_materials("D").sha256)

    def test_library_with_builder_notes_or_tests_is_refused(self):
        copy = self.tmp / "library"
        shutil.copytree(cfg.ARMS_LIBRARY_DIR, copy)
        (copy / "tests").mkdir()
        with self.assertRaises(RuntimeError):
            harness.build_arm_materials("L", library_dir=copy)


class ToolBoxCase(TempDirCase):
    arm = "L"

    def setUp(self) -> None:
        super().setUp()
        self.materials = harness.build_arm_materials(self.arm)
        self.box = harness.ToolBox(self.materials, cfg.WAREHOUSE_PATH, self.tmp / "scratch")
        self.addCleanup(self.box.close)

    def assertRefused(self, name: str, tool_input: dict, fragment: str = "") -> str:
        is_error, text = self.box.execute(name, tool_input)
        self.assertTrue(is_error, f"{name} {tool_input} should have been refused, got: {text[:200]}")
        self.assertIn(fragment, text)
        return text


class TestSqlTool(ToolBoxCase):
    def test_select_works_and_returns_json(self):
        is_error, text = self.box.execute("run_sql", {"sql": "SELECT COUNT(*) AS n FROM dim_date"})
        self.assertFalse(is_error)
        self.assertEqual(json.loads(text)["rows"], [[889]])

    def test_files_cannot_be_read_written_or_attached(self):
        for sql in ("SELECT * FROM read_csv('world/schema_comments.csv')",
                    "SELECT * FROM read_text('C:/Users/someone/notes.md')",
                    "COPY (SELECT 1) TO 'x.csv'",
                    "ATTACH 'other.duckdb' AS other",
                    "SELECT * FROM glob('*')",
                    "INSTALL httpfs"):
            self.assertRefused("run_sql", {"sql": sql})
        self.assertFalse(Path("x.csv").exists())
        self.assertFalse(Path("other.duckdb").exists())

    def test_configuration_cannot_be_unlocked_and_writes_fail(self):
        self.assertRefused("run_sql", {"sql": "SET enable_external_access=true"})
        self.assertRefused("run_sql", {"sql": "SET lock_configuration=false"})
        self.assertRefused("run_sql", {"sql": "DROP TABLE dim_date"})
        self.assertRefused("run_sql", {"sql": "INSERT INTO dim_date SELECT * FROM dim_date"})
        self.assertRefused("run_sql", {"sql": "CREATE TABLE t AS SELECT 1"})
        # and the key query still cannot read after all those attempts
        self.assertRefused("run_sql", {"sql": "SELECT * FROM read_csv('data/key/key.json')"})

    def test_one_statement_only_and_bad_input(self):
        self.assertRefused("run_sql", {"sql": "SELECT 1; SELECT 2"}, "exactly one")
        self.assertRefused("run_sql", {"sql": ""})
        self.assertRefused("run_sql", {"sql": 5})
        self.assertRefused("run_sql", {})
        self.assertRefused("run_sql", {"sql": "SELEC broken"}, "SQL error")

    def test_long_results_are_cut_and_say_so(self):
        is_error, text = self.box.execute("run_sql", {"sql": "SELECT * FROM range(500)"})
        payload = json.loads(text)
        self.assertFalse(is_error)
        self.assertEqual(len(payload["rows"]), cfg.SQL_RESULT_ROW_LIMIT)
        self.assertIn("truncated", payload)

    def test_dates_and_decimals_become_json(self):
        is_error, text = self.box.execute("run_sql", {"sql": "SELECT DATE '2026-10-04' AS d, 1.50::DECIMAL(5,2) AS x, NULL AS n"})
        self.assertEqual(json.loads(text)["rows"], [["2026-10-04", 1.5, None]])

    def test_unknown_tool_and_non_object_input(self):
        self.assertRefused("delete_everything", {}, "Unknown tool")
        self.assertRefused("run_sql", "SELECT 1")


class TestSkillLoader(ToolBoxCase):
    def test_skill_md_and_file_index(self):
        is_error, text = self.box.execute("load_skill", {"skill": "warehouse-map"})
        self.assertFalse(is_error)
        self.assertIn("# Warehouse map", text)
        self.assertIn("references/tables.md", text)
        self.assertNotIn("<!-- facts", text)
        is_error, reference = self.box.execute("load_skill", {"skill": "warehouse-map", "path": "references/tables.md"})
        self.assertFalse(is_error)
        self.assertEqual(self.box.skills_opened, ["warehouse-map"])

    def test_scripts_are_readable_in_L(self):
        is_error, text = self.box.execute("load_skill", {"skill": "fiscal-calendar"})
        self.assertIn("scripts/fiscal.py", text)

    def test_nothing_outside_the_library_is_reachable(self):
        for path in ("../../../data/key/key.json", "../../build_notes.md", "../../../../CLAUDE.md", "C:/Users/someone/notes.md",
                     "/etc/passwd", "..\\..\\build_notes.md", "references/../../../prompt_doc.md", "./../metric-dictionary/SKILL.md",
                     "references/does_not_exist.md", ""):
            if path == "":
                continue
            self.assertRefused("load_skill", {"skill": "warehouse-map", "path": path})
        for skill in ("../../data/key", "..", ".", "warehouse-map/../metric-dictionary", "WAREHOUSE-MAP", "C:/x", "build_notes", "tests", ""):
            self.assertRefused("load_skill", {"skill": skill}, "No skill")
        self.assertEqual(self.box.skills_opened, [])

    def test_skill_budget_counts_distinct_skills_and_rereads_are_free(self):
        names = self.materials.skill_names[:cfg.MAX_SKILL_LOADS]
        for name in names:
            self.assertFalse(self.box.execute("load_skill", {"skill": name})[0])
        self.assertEqual(len(self.box.skills_opened), cfg.MAX_SKILL_LOADS)
        self.assertRefused("load_skill", {"skill": self.materials.skill_names[cfg.MAX_SKILL_LOADS]}, "budget")
        self.assertFalse(self.box.execute("load_skill", {"skill": names[0]})[0])                 # a skill already open is free
        first_extra_file = self.box._visible_files(self.box._skill_dir(names[0]))[0]
        self.assertFalse(self.box.execute("load_skill", {"skill": names[0], "path": first_extra_file})[0])


class TestLibraryWithoutScripts(ToolBoxCase):
    arm = "L-"

    def test_no_script_tool_and_scripts_hidden(self):
        self.assertRefused("run_script", {"script": "fiscal-calendar/scripts/fiscal.py"}, "Unknown tool")
        is_error, text = self.box.execute("load_skill", {"skill": "fiscal-calendar"})
        self.assertFalse(is_error)
        self.assertNotIn("scripts/fiscal.py", text.split("Other files in this skill")[1])
        self.assertRefused("load_skill", {"skill": "fiscal-calendar", "path": "scripts/fiscal.py"})


class TestScriptTool(ToolBoxCase):
    def test_fiscal_script_runs_with_the_database_supplied(self):
        is_error, text = self.box.execute("run_script", {"script": "fiscal-calendar/scripts/fiscal.py",
                                                         "args": ["last period", "--as-of", "2026-10-05"]})
        self.assertFalse(is_error, text)
        self.assertIn("[exit code 0]", text)
        self.assertIn("P05", text)
        self.assertEqual(self.box.queries_used, 1)

    def test_model_supplied_database_path_is_dropped_and_names_are_forgiving(self):
        is_error, text = self.box.execute("run_script", {"script": "<library>/fiscal-calendar/scripts/fiscal.py",
                                                         "args": ["PATH_TO/tuomimetsa.duckdb", "last period", "--as-of", "2026-10-05"]})
        self.assertFalse(is_error, text)
        is_error, text = self.box.execute("run_script", {"script": "fiscal.py", "args": ["P5", "--as-of", "2026-10-05"]})
        self.assertFalse(is_error, text)

    def test_files_parameter_and_file_argument(self):
        is_error, text = self.box.execute("run_script", {"script": "query-check/scripts/query_check.py",
                                                         "args": ["--file", "q.sql", "--grain", "n"], "files": {"q.sql": "SELECT 1 AS n"}})
        self.assertFalse(is_error, text)
        self.assertIn("[exit code 0]", text)

    def test_only_library_scripts_with_safe_arguments(self):
        for script in ("../../code/config.py", "fiscal-calendar/scripts/../../../code/config.py", "C:/Windows/System32/notepad.exe",
                       "fiscal-calendar/SKILL.md", "fiscal-calendar/scripts/missing.py", "scripts/fiscal.py", "", "build_notes.md",
                       "/bin/sh", "query-check/scripts/query_check.py; echo hi"):
            self.assertRefused("run_script", {"script": script})
        for args in (["--file", "../../../data/key/key.json"], ["--file", "C:/Users/someone/notes.md"], ["--file", "missing.sql"],
                     ["last period", "other.duckdb"], ["../../data/key/key.json"], "last period", [1, 2], ["x"] * 41):
            self.assertRefused("run_script", {"script": "query-check/scripts/query_check.py", "args": args})
        self.assertRefused("run_script", {"script": "query-check/scripts/query_check.py", "args": ["--file", "../x.sql"], "files": {"../x.sql": "SELECT 1"}})
        self.assertRefused("run_script", {"script": "query-check/scripts/query_check.py", "files": {"a b.sql": "x"}})
        self.assertRefused("run_script", {"script": "query-check/scripts/query_check.py", "files": ["q.sql"]})
        self.assertEqual(self.box.queries_used, 0)
        self.assertFalse((self.tmp / "x.sql").exists())

    def test_a_script_cannot_be_used_to_read_or_write_files(self):
        """query_check.py runs whatever SQL it is given; the wrapper must lock its connection like run_sql's."""
        key_text = (cfg.KEY_DIR / "key.json").read_text(encoding="utf-8")
        key_path = (cfg.KEY_DIR / "key.json").as_posix()
        attempts = [
            {"args": ["--sql", f"SELECT * FROM read_text('{key_path}')"]},
            {"args": ["--sql", f"SELECT * FROM read_csv('{key_path}')"]},
            {"args": ["--sql", f"SELECT * FROM '{key_path}'"]},
            {"args": ["--sql", "COPY (SELECT 1) TO 'z.csv'"]},
            {"args": ["--sql", "ATTACH 'o.duckdb' AS o"]},
            {"args": ["--file", "q.sql"], "files": {"q.sql": f"SELECT * FROM read_text('{key_path}')"}},
        ]
        for attempt in attempts:
            is_error, text = self.box.execute("run_script", dict(attempt, script="query-check/scripts/query_check.py"))
            self.assertNotIn(key_text[:80], text)
            self.assertIn("disabled by configuration", text, text[:300])
        self.assertFalse((self.tmp / "scratch" / "z.csv").exists())
        self.assertFalse((self.tmp / "scratch" / "o.duckdb").exists())

    def test_script_environment_has_no_secrets(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-not-real"
        os.environ["MY_SECRET_TOKEN"] = "abc"
        try:
            environment = harness.script_environment()
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
            del os.environ["MY_SECRET_TOKEN"]
        self.assertNotIn("ANTHROPIC_API_KEY", environment)
        self.assertNotIn("MY_SECRET_TOKEN", environment)

    def test_script_calls_use_the_query_budget(self):
        for _ in range(cfg.MAX_QUERY_EXECUTIONS - 1):
            self.assertFalse(self.box.execute("run_sql", {"sql": "SELECT 1"})[0])
        self.assertFalse(self.box.execute("run_script", {"script": "fiscal.py", "args": ["P5"]})[0])
        self.assertRefused("run_sql", {"sql": "SELECT 1"}, "Query budget used up")
        self.assertRefused("run_script", {"script": "fiscal.py", "args": ["P5"]}, "Query budget used up")
        self.assertEqual(self.box.queries_used, cfg.MAX_QUERY_EXECUTIONS)

    def test_query_budget_counts_failed_queries_too(self):
        for _ in range(cfg.MAX_QUERY_EXECUTIONS):
            self.box.execute("run_sql", {"sql": "SELEC broken"})
        self.assertRefused("run_sql", {"sql": "SELECT 1"}, "Query budget used up")


# ---------------------------------------------------------------------------

class TestRunOne(TempDirCase):
    def run_policy(self, policy: str, arm: str = "L", model: str = "claude-sonnet-5-5", ledger=None, client=None):
        client = client or make_client(policy)
        summary = harness.run_one(request=DEV[SMALL_REQUEST]["request"], arm=arm, model=model, client=client, out_dir=self.tmp,
                                  ledger=ledger)
        return summary, client

    def test_correct_run_on_every_arm_is_logged_and_marked_correct(self):
        for arm in cfg.ARM_LABELS:
            summary, _ = self.run_policy("correct", arm=arm)
            self.assertEqual(summary["status"], "ok", summary["problem"])
            mark = pilot_marking.mark_run(summary, EXPECTED_SMALL, False)
            self.assertEqual(mark["outcome"], "correct", mark["reason"])
            events = read_log(self.tmp / summary["log_file"])
            kinds = [e["event"] for e in events]
            self.assertEqual(kinds[0], "run_start")
            self.assertEqual(kinds[-1], "run_end")
            for needed in ("message", "api_call", "api_usage", "tool_call", "tool_result"):
                self.assertIn(needed, kinds)
            start = events[0]
            self.assertEqual(start["arm"], arm)
            self.assertEqual(start["client_kind"], "scripted-fake")
            self.assertEqual(events[-1]["model_returned"], "claude-sonnet-5-5")
            usages = [e for e in events if e["event"] == "api_usage"]
            self.assertTrue(all({"input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"} <= set(u["usage"]) for u in usages))
            self.assertAlmostEqual(sum(u["cost_usd"] for u in usages), summary["cost_usd"], places=4)
        index = [json.loads(line) for line in (self.tmp / "runs_index.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(index), 4)
        self.assertTrue((self.tmp / "prompts").is_dir())
        self.assertFalse((self.tmp / "_scratch" / index[0]["run_id"]).exists())   # scratch folders are removed

    def test_second_run_reads_the_cached_prefix(self):
        client = make_client("correct")
        first, _ = self.run_policy("correct", arm="D", client=client)
        second, _ = self.run_policy("correct", arm="D", client=client)
        self.assertGreater(first["first_turn_cache_creation_tokens"], 0)
        self.assertEqual(second["first_turn_cache_creation_tokens"], 0)
        self.assertGreater(second["tokens"]["cache_read_input_tokens"], 0)
        self.assertLess(second["cost_usd"], first["cost_usd"])
        self.assertAlmostEqual(second["cost_usd"], second["cost_usd_warm_prefix"], places=6)
        self.assertLess(first["cost_usd_warm_prefix"], first["cost_usd"])

    def test_rerunning_a_run_id_keeps_the_earlier_log(self):
        self.run_policy("correct", arm="S")
        self.run_policy("correct", arm="S")
        self.assertEqual(len(list(self.tmp.glob("*.attempt1.jsonl"))), 1)

    def test_thinking_blocks_are_passed_back_unchanged(self):
        seen = {}

        class Capturing(ScriptedClient):
            def create(self, **request):
                seen["messages"] = request["messages"]
                return super().create(**request)
        client = Capturing({e["request"]["request_text"]: e["accepted_sql"] for e in DEV.values()}, policy="thinking")
        summary, _ = self.run_policy("thinking", arm="S", client=client)
        self.assertEqual(summary["status"], "ok")
        assistant_turns = [m for m in seen["messages"] if m["role"] == "assistant"]
        self.assertTrue(assistant_turns)
        for turn in assistant_turns:
            self.assertEqual(turn["content"][0], {"type": "thinking", "thinking": "", "signature": "scripted-signature"})

    def test_parallel_tool_calls_get_all_results_in_one_message(self):
        seen = {}

        class Capturing(ScriptedClient):
            def create(self, **request):
                seen["messages"] = request["messages"]
                return super().create(**request)
        client = Capturing({e["request"]["request_text"]: e["accepted_sql"] for e in DEV.values()}, policy="parallel")
        summary, _ = self.run_policy("parallel", arm="S", client=client)
        self.assertEqual(summary["status"], "ok")
        first_results = seen["messages"][2]["content"]
        self.assertEqual(len(first_results), 2)
        self.assertTrue(all(block["type"] == "tool_result" for block in first_results))

    def test_cache_marker_only_on_the_last_block_from_the_second_call(self):
        seen = []

        class Capturing(ScriptedClient):
            def create(self, **request):
                seen.append(request)
                return super().create(**request)
        client = Capturing({e["request"]["request_text"]: e["accepted_sql"] for e in DEV.values()}, policy="correct")
        self.run_policy("correct", arm="S", client=client)
        self.assertNotIn("cache_control", json.dumps(seen[0]["messages"]))
        self.assertIn("cache_control", seen[0]["system"][0])
        for request in seen[1:]:
            self.assertEqual(json.dumps(request["messages"]).count("cache_control"), 1)
            self.assertIn("cache_control", request["messages"][-1]["content"][-1])

    def test_malformed_and_fenced_answers(self):
        summary, _ = self.run_policy("malformed", arm="S")
        self.assertEqual(summary["status"], "malformed")
        self.assertEqual(pilot_marking.mark_run(summary, EXPECTED_SMALL, False)["outcome"], "no_answer")
        summary, _ = self.run_policy("fenced", arm="S")
        self.assertEqual(summary["status"], "ok")

    def test_wrong_answer_is_marked_wrong(self):
        summary, _ = self.run_policy("wrong", arm="S")
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(pilot_marking.mark_run(summary, EXPECTED_SMALL, False)["outcome"], "wrong")

    def test_query_budget_ends_a_run_that_never_answers(self):
        summary, _ = self.run_policy("budget_hog", arm="S")
        self.assertEqual(summary["status"], "no_answer_budget")
        self.assertEqual(summary["queries_used"], cfg.MAX_QUERY_EXECUTIONS)
        self.assertEqual(summary["refused_query_calls"], cfg.MAX_REFUSED_CALLS_AFTER_BUDGET)
        events = read_log(self.tmp / summary["log_file"])
        refused = [e for e in events if e["event"] == "tool_result" and "Query budget used up" in e["content"]]
        self.assertEqual(len(refused), cfg.MAX_REFUSED_CALLS_AFTER_BUDGET)

    def test_seventh_skill_is_refused_and_the_run_carries_on(self):
        summary, _ = self.run_policy("skill_hog", arm="L")
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(len(summary["skills_opened"]), cfg.MAX_SKILL_LOADS)
        events = read_log(self.tmp / summary["log_file"])
        self.assertTrue(any(e["event"] == "tool_result" and e["is_error"] and "Skill load budget" in e["content"] for e in events))

    def test_escape_attempts_all_fail_and_leave_no_trace(self):
        for arm in cfg.ARM_LABELS:
            summary, _ = self.run_policy("escape", arm=arm)
            self.assertEqual(summary["status"], "ok", f"{arm}: {summary['problem']}")
            events = read_log(self.tmp / summary["log_file"])
            calls = {e["tool_use_id"]: e for e in events if e["event"] == "tool_call"}
            results = {e["tool_use_id"]: e for e in events if e["event"] == "tool_result"}
            refused = [tool_id for tool_id in results if results[tool_id]["is_error"]]
            self.assertGreaterEqual(len(refused), 7, arm)
            log_text = (self.tmp / summary["log_file"]).read_text(encoding="utf-8")
            for forbidden in ("REQ-T0", "reference_sql", "naive", "accepted_interpretations"):
                self.assertNotIn(forbidden, log_text, f"{arm}: {forbidden} leaked into the log")
        self.assertFalse((self.tmp / "escaped.csv").exists())
        self.assertFalse(Path("escaped.csv").exists())
        self.assertFalse(Path("other.duckdb").exists())

    def test_api_error_ends_the_run_cleanly(self):
        summary, _ = self.run_policy("api_error", arm="S")
        self.assertEqual(summary["status"], "api_error")
        self.assertIn("scripted API failure", summary["problem"])
        self.assertEqual(read_log(self.tmp / summary["log_file"])[-1]["event"], "run_end")

    def test_spending_cap_stops_before_the_call(self):
        client = make_client("correct")
        ledger = harness.SpendLedger(cap_usd=0.0001)
        summary, _ = self.run_policy("correct", arm="D", ledger=ledger, client=client)
        self.assertEqual(summary["status"], "cap_stop")
        self.assertEqual(client.calls, 0)
        self.assertEqual(ledger.spent_usd, 0.0)

    def test_ledger_is_charged_for_every_call(self):
        ledger = harness.SpendLedger(cap_usd=100.0, already_spent_usd=1.0)
        summary, _ = self.run_policy("correct", arm="S", ledger=ledger)
        # the summary's cost is rounded to six decimals, so the ledger may differ by up to half a micro-dollar (found 15 Oct 2026 when the
        # task text grew to version 3 and the fake client's token counts landed on the rounding edge)
        self.assertAlmostEqual(ledger.spent_usd, 1.0 + summary["cost_usd"], delta=1e-6)

    def test_missing_price_fails_before_any_work(self):
        with self.assertRaises(SystemExit):
            harness.run_one(request=DEV[SMALL_REQUEST]["request"], arm="S", model="claude-unpriced", client=make_client(), out_dir=self.tmp)

    def test_every_policy_is_exercised_somewhere(self):
        self.assertEqual(set(POLICIES), {"correct", "wrong", "malformed", "fenced", "thinking", "parallel", "budget_hog", "skill_hog", "escape", "api_error"})


# ---------------------------------------------------------------------------

class TestMarking(unittest.TestCase):
    EXPECTED = {"columns": ["store", "sales", "growth_pct"], "rows": [[101, 1000.0, 5.0], [102, 2000.0, -3.2], [103, 500.0, 0.0]]}

    def check(self, got, ordered=False):
        return pilot_marking.compare_tables(self.EXPECTED, got, ordered)[0]

    def test_exact_and_reordered_rows_and_renamed_columns(self):
        self.assertTrue(self.check({"columns": ["a", "b", "c"], "rows": [[103, 500, 0], [101, 1000, 5], [102, 2000, -3.2]]}))

    def test_column_order_does_not_matter(self):
        self.assertTrue(self.check({"columns": ["g", "s", "n"], "rows": [[5.0, 1000, 101], [-3.2, 2000, 102], [0, 500, 103]]}))

    def test_tolerances(self):
        self.assertTrue(self.check({"columns": ["a", "b", "c"], "rows": [[101, 1000.9, 5.05], [102, 2001.5, -3.25], [103, 500.004, 0.05]]}))
        self.assertFalse(self.check({"columns": ["a", "b", "c"], "rows": [[101, 1002, 5.0], [102, 2000, -3.2], [103, 500, 0]]}))   # 0.2% off
        self.assertFalse(self.check({"columns": ["a", "b", "c"], "rows": [[101, 1000, 5.3], [102, 2000, -3.2], [103, 500, 0]]}))   # 0.3 pp off

    def test_failures(self):
        self.assertFalse(self.check({"columns": ["a", "b", "c"], "rows": [[101, 1000, 5], [102, 2000, -3.2]]}))                    # row missing
        self.assertFalse(self.check({"columns": ["a", "b"], "rows": [[101, 1000], [102, 2000], [103, 500]]}))                       # column missing
        self.assertFalse(self.check({"columns": ["a", "b", "c"], "rows": [[101, 2000, 5], [102, 1000, -3.2], [103, 500, 0]]}))     # values on wrong rows
        self.assertFalse(self.check("a table"))

    def test_extra_columns_are_tolerated(self):
        ok, reason = pilot_marking.compare_tables(self.EXPECTED, {"columns": ["a", "b", "c", "d"], "rows": [[101, 1000, 5, "x"], [102, 2000, -3.2, "y"], [103, 500, 0, "z"]]}, False)
        self.assertTrue(ok)
        self.assertIn("extra", reason)

    def test_order_matters_only_when_asked(self):
        shuffled = {"columns": ["a", "b", "c"], "rows": [[102, 2000, -3.2], [101, 1000, 5], [103, 500, 0]]}
        self.assertTrue(self.check(shuffled, ordered=False))
        self.assertFalse(self.check(shuffled, ordered=True))

    def test_dates_strings_and_numeric_strings(self):
        expected = {"columns": ["day", "region", "n"], "rows": [["2025-11-28", "North", 12.0]]}
        self.assertTrue(pilot_marking.compare_tables(expected, {"columns": ["d", "r", "n"], "rows": [["2025-11-28 00:00:00", "north", "12"]]}, False)[0])

    def test_limit_means_ordered(self):
        self.assertTrue(pilot_marking.is_ordered("select * from t order by x limit 10"))
        self.assertFalse(pilot_marking.is_ordered("select * from t order by x"))

    def test_accepted_result_of_a_dev_request_marks_itself_correct(self):
        self.assertTrue(pilot_marking.compare_tables(EXPECTED_SMALL, json.loads(json.dumps(EXPECTED_SMALL)), False)[0])


# ---------------------------------------------------------------------------
# The marker fixes from the pilot diagnosis (15 Oct 2026). One class per fix.

REGION_EXPECTED = {"columns": ["region", "net_sales", "member_share_pct"],
                   "rows": [["East", 1000.0, 58.4], ["North", 2000.0, 55.4], ["Online", 500.0, 69.9]]}
REGION_SPEC = {"dimensions": ["region"], "required": ["region", "member_share_pct"], "alternatives": []}
SINGLE_EXPECTED = {"columns": ["this_year", "last_year", "lfl_growth_pct"], "rows": [[3422400.96, 3327897.39, 2.84]]}
SINGLE_SPEC = {"dimensions": [], "required": ["lfl_growth_pct"], "alternatives": []}
HOURS_EXPECTED = {"columns": ["hour_helsinki", "web_orders"], "rows": [[0, 43.0], [1, 3.0], [2, 1.0], [4, 1.0]]}
HOURS_SPEC = {"dimensions": ["hour_helsinki"], "required": ["hour_helsinki", "web_orders"], "alternatives": []}


def answer_summary(result: dict) -> dict:
    """A minimal finished run summary carrying one answer table, for mark_run."""
    return {"status": "ok", "problem": "", "answer": {"sql": "select 1", "result": result, "definitions_applied": [],
                                                       "assumptions": [], "caveats": []}}


class TestMarkingTotalRows(unittest.TestCase):
    """Fix 1: a labelled total row is not an extra answer row; a one-figure answer may sit on a total row."""

    def test_labelled_total_rows_are_ignored(self):
        for label in ("Total", "Total company", "All regions", "Company total", None):
            got = {"columns": ["r", "n", "m", "s"],
                   "rows": [["East", 1000, 584, 58.4], ["North", 2000, 1108, 55.4], ["Online", 500, 350, 69.9], [label, 3500, 2042, 58.3]]}
            ok, reason = pilot_marking.compare_tables(REGION_EXPECTED, got, False, REGION_SPEC)
            self.assertTrue(ok, f"{label}: {reason}")
            self.assertIn("total row ignored", reason)

    def test_total_rows_are_ignored_without_a_spec_too(self):
        got = {"columns": ["r", "n", "s"], "rows": [["East", 1000, 58.4], ["North", 2000, 55.4], ["Online", 500, 69.9], ["Total", 3500, 58.3]]}
        self.assertTrue(pilot_marking.compare_tables(REGION_EXPECTED, got, False)[0])

    def test_a_category_that_merely_contains_all_is_not_a_total(self):
        got = {"columns": ["r", "s"], "rows": [["East", 58.4], ["North", 55.4], ["Online", 69.9], ["Allotment", 1.0]]}
        self.assertFalse(pilot_marking.compare_tables(REGION_EXPECTED, got, False, REGION_SPEC)[0])

    def test_one_figure_on_a_total_row_with_a_breakdown_is_accepted(self):
        for label in ("Total", None):
            got = {"columns": ["region", "store_weeks", "ty", "ly", "g"],
                   "rows": [[label, 478, 3422400.96, 3327897.39, 2.84], ["East", 104, 675230.07, 648710.54, 4.09],
                            ["West", 117, 1009573.23, 979158.15, 3.11]]}
            ok, reason = pilot_marking.compare_tables(SINGLE_EXPECTED, got, False, SINGLE_SPEC)
            self.assertTrue(ok, reason)
            self.assertIn("figure taken from the total row", reason)

    def test_one_figure_with_unlabelled_extra_rows_still_fails(self):
        got = {"columns": ["region", "g"], "rows": [["East", 2.84], ["West", 3.11]]}
        self.assertFalse(pilot_marking.compare_tables(SINGLE_EXPECTED, got, False, SINGLE_SPEC)[0])

    def test_a_wrong_figure_on_the_total_row_fails(self):
        got = {"columns": ["region", "g"], "rows": [["Total", 3.5], ["East", 2.84]]}
        self.assertFalse(pilot_marking.compare_tables(SINGLE_EXPECTED, got, False, SINGLE_SPEC)[0])


class TestMarkingZeroRows(unittest.TestCase):
    """Fix 2: an extra row whose required measures are zero (an empty hour) says the same as an absent row."""

    def test_zero_filled_rows_are_ignored(self):
        got = {"columns": ["h", "n"], "rows": [[0, 43], [1, 3], [2, 1], [3, 0], [4, 1], [5, None]]}
        ok, reason = pilot_marking.compare_tables(HOURS_EXPECTED, got, False, HOURS_SPEC)
        self.assertTrue(ok, reason)
        self.assertIn("2 zero-filled row(s) ignored", reason)

    def test_an_extra_row_with_a_real_figure_fails(self):
        got = {"columns": ["h", "n"], "rows": [[0, 43], [1, 3], [2, 1], [3, 2], [4, 1]]}
        self.assertFalse(pilot_marking.compare_tables(HOURS_EXPECTED, got, False, HOURS_SPEC)[0])

    def test_zero_rows_need_a_spec(self):
        got = {"columns": ["h", "n"], "rows": [[0, 43], [1, 3], [2, 1], [3, 0], [4, 1]]}
        self.assertFalse(pilot_marking.compare_tables(HOURS_EXPECTED, got, False)[0])

    def test_a_missing_real_row_is_not_hidden_by_a_zero_row(self):
        got = {"columns": ["h", "n"], "rows": [[0, 43], [1, 3], [2, 1], [3, 0]]}           # hour 4 left out
        self.assertFalse(pilot_marking.compare_tables(HOURS_EXPECTED, got, False, HOURS_SPEC)[0])

    def test_order_still_counts_for_a_top_n(self):
        expected = {"columns": ["sku", "units"], "rows": [["A", 10.0], ["B", 8.0]]}
        spec = {"dimensions": ["sku"], "required": ["sku", "units"], "alternatives": []}
        self.assertTrue(pilot_marking.compare_tables(expected, {"columns": ["s", "u"], "rows": [["A", 10], ["B", 8], ["C", 0]]}, True, spec)[0])
        self.assertFalse(pilot_marking.compare_tables(expected, {"columns": ["s", "u"], "rows": [["B", 8], ["A", 10], ["C", 0]]}, True, spec)[0])


class TestMarkingRequiredColumns(unittest.TestCase):
    """Fix 3: the asked-for measure is required; the accepted query's supporting columns are not."""

    def test_the_headline_alone_passes_with_a_spec(self):
        self.assertTrue(pilot_marking.compare_tables(SINGLE_EXPECTED, {"columns": ["lfl"], "rows": [[2.84]]}, False, SINGLE_SPEC)[0])
        got = {"columns": ["region", "share"], "rows": [["East", 58.44], ["North", 55.38], ["Online", 69.94]]}
        self.assertTrue(pilot_marking.compare_tables(REGION_EXPECTED, got, False, REGION_SPEC)[0])

    def test_without_a_spec_every_column_is_still_required(self):
        self.assertFalse(pilot_marking.compare_tables(SINGLE_EXPECTED, {"columns": ["lfl"], "rows": [[2.84]]}, False)[0])

    def test_a_missing_required_column_fails(self):
        got = {"columns": ["region", "net"], "rows": [["East", 1000], ["North", 2000], ["Online", 500]]}
        ok, reason = pilot_marking.compare_tables(REGION_EXPECTED, got, False, REGION_SPEC)
        self.assertFalse(ok)
        self.assertIn("member_share_pct", reason)

    def test_a_wrong_headline_fails(self):
        self.assertFalse(pilot_marking.compare_tables(SINGLE_EXPECTED, {"columns": ["lfl"], "rows": [[4.48]]}, False, SINGLE_SPEC)[0])

    def test_every_pilot_spec_names_real_columns(self):
        for request_id in cfg.PILOT_REQUEST_IDS:
            spec = pilot_marking.answer_spec(request_id)
            self.assertIsNotNone(spec, request_id)
            columns = pilot_marking.compute_expected(cfg.WAREHOUSE_PATH, DEV[request_id]["accepted_sql"])["columns"]
            self.assertTrue(set(spec["required"]) <= set(columns), request_id)
            self.assertTrue(set(spec["dimensions"]) <= set(spec["required"]), request_id)
            self.assertTrue([name for name in spec["required"] if name not in spec["dimensions"]], f"{request_id} requires no measure")


class TestMarkingAlternatives(unittest.TestCase):
    """Fix 4: accepted alternative readings, computed on the warehouse from the accepted query."""

    @classmethod
    def setUpClass(cls):
        cls.sets = {request_id: pilot_marking.compute_expected_set(cfg.WAREHOUSE_PATH, request_id, DEV[request_id]["accepted_sql"])
                    for request_id in ("REQ-D02", "REQ-D20")}

    def mark(self, request_id: str, result: dict) -> dict:
        entry = self.sets[request_id]
        return pilot_marking.mark_run(answer_summary(result), entry["table"], entry["ordered"],
                                      spec=pilot_marking.answer_spec(request_id), alternatives=entry["alternatives"])

    def test_alternatives_run_and_differ_from_the_accepted_result(self):
        for request_id in cfg.PILOT_REQUEST_IDS:
            entry = pilot_marking.compute_expected_set(cfg.WAREHOUSE_PATH, request_id, DEV[request_id]["accepted_sql"])
            self.assertEqual(entry["marker_version"], pilot_marking.MARKER_VERSION)
            for alternative in entry["alternatives"]:
                self.assertTrue(alternative["table"]["rows"], alternative["label"])
                self.assertTrue(alternative["why"])
                self.assertNotEqual(alternative["table"], entry["table"], alternative["label"])

    def test_d02_four_week_totals_are_accepted(self):
        # The shape both models gave in the pilot: one row per format, the four weeks summed.
        result = {"columns": ["format", "ty", "ly"], "rows": [["Large", 378643.23, 371412.07], ["Medium", 502760.45, 517689.45],
                                                             ["Small", 129074.84, 131190.94], ["Web", 184965.47, 155372.15]]}
        mark = self.mark("REQ-D02", result)
        self.assertEqual(mark["outcome"], "correct", mark["reason"])
        self.assertIn("four-week total per format", mark["reason"])

    def test_d02_weekly_rows_still_pass_on_the_accepted_result(self):
        mark = self.mark("REQ-D02", json.loads(json.dumps(self.sets["REQ-D02"]["table"])))
        self.assertEqual(mark["outcome"], "correct")
        self.assertNotIn("alternative", mark["reason"])

    def test_d02_stores_only_with_calendar_dates_stays_wrong(self):
        result = {"columns": ["format", "ty", "ly"], "rows": [["Large", 378643.23, 363294.58], ["Medium", 502760.45, 505996.94],
                                                             ["Small", 129074.84, 130726.75]]}
        mark = self.mark("REQ-D02", result)
        self.assertEqual(mark["outcome"], "wrong")
        self.assertIn("four-week total per format", mark["reason"])     # the reason reports the alternative's verdict too

    def test_d20_without_the_test_order_is_accepted(self):
        rows = [list(row) for row in self.sets["REQ-D20"]["table"]["rows"]]
        for row in rows:
            if row[0] == 15:
                row[1] -= 1
        mark = self.mark("REQ-D20", {"columns": ["h", "n"], "rows": rows})
        self.assertEqual(mark["outcome"], "correct", mark["reason"])
        self.assertIn("test web orders left out", mark["reason"])

    def test_d20_with_cancelled_orders_counted_stays_wrong(self):
        rows = [list(row) for row in self.sets["REQ-D20"]["table"]["rows"]]
        rows[0][1] += 4
        self.assertEqual(self.mark("REQ-D20", {"columns": ["h", "n"], "rows": rows})["outcome"], "wrong")


class TestRequestDate(unittest.TestCase):
    """The received date reaches the model as written in the request: the dev request's own date, and 5-9 Oct 2026 for a test request."""

    def test_dev_requests_carry_their_own_received_date(self):
        for request_id in cfg.PILOT_REQUEST_IDS:
            request = DEV[request_id]["request"]
            self.assertRegex(request["received"], r"^20\d\d-\d\d-\d\d$")
            self.assertIn(f"Request received {request['received']}", harness.task_text(request))
        self.assertEqual(DEV["REQ-D20"]["request"]["received"], "2024-12-04")

    def test_test_requests_carry_dates_in_the_week_after_the_data_cut(self):
        allowed = {day.isoformat() for day in cfg.TEST_RECEIVED_DATES}
        for request_id in ("REQ-T01", "REQ-T60"):
            request = harness.load_test_request(request_id)
            self.assertIn(request["received"], allowed)
            self.assertIn(f"Request received {request['received']}", harness.task_text(request))


class TestRemark(TempDirCase):
    """Re-marking finished logs: no model call, nothing written beside the logs, new results elsewhere."""

    def test_remark_reads_logs_and_writes_elsewhere(self):
        logs = self.tmp / "pilot"
        run_pilot.run_pilot(models=list(cfg.PILOT_MODELS), arms=["S", "L"], request_ids=["REQ-D20"], repeats=1, cap_usd=1000.0,
                            out_dir=logs, dry_run=True, client=make_client(), quiet=True)
        before = {path.name: path.read_bytes() for path in logs.iterdir() if path.is_file()}
        summary = run_pilot.remark_pilot(from_dir=logs, out_dir=self.tmp / "remarked", models=list(cfg.PILOT_MODELS),
                                         arms=["S", "L"], request_ids=["REQ-D20"], repeats=1, dry_run=True, quiet=True)
        after = {path.name: path.read_bytes() for path in logs.iterdir() if path.is_file()}
        self.assertEqual(before, after)
        results = run_pilot.read_jsonl(self.tmp / "remarked" / "pilot_results.jsonl")
        self.assertEqual(len(results), 4)
        self.assertTrue(all(entry["marker_version"] == pilot_marking.MARKER_VERSION for entry in results))
        self.assertTrue(all(entry["outcome_before"] is not None for entry in results))
        self.assertEqual(summary["plan_runs"], 4)
        self.assertIn("RE-MARK", (self.tmp / "remarked" / "pilot_summary.txt").read_text(encoding="utf-8"))

    def test_remark_refuses_to_write_into_the_logs_folder(self):
        with self.assertRaises(SystemExit):
            run_pilot.remark_pilot(from_dir=self.tmp, out_dir=self.tmp, models=list(cfg.PILOT_MODELS), arms=["S"],
                                   request_ids=["REQ-D20"], repeats=1, quiet=True)


# ---------------------------------------------------------------------------

class TestPilot(TempDirCase):
    def pilot(self, cap=1000.0, requests=("REQ-D20", "REQ-D32"), out_dir=None, client=None):
        return run_pilot.run_pilot(models=list(cfg.PILOT_MODELS), arms=list(cfg.ARM_LABELS), request_ids=list(requests), repeats=1,
                                   cap_usd=cap, out_dir=out_dir or self.tmp / "pilot", dry_run=True,
                                   client=client or make_client(), quiet=True)

    def test_dry_pilot_end_to_end(self):
        summary = self.pilot()
        out = self.tmp / "pilot"
        results = run_pilot.read_jsonl(out / "pilot_results.jsonl")
        self.assertEqual(len(results), 2 * 4 * 2)
        self.assertEqual({r["model"] for r in results}, set(cfg.PILOT_MODELS))
        self.assertEqual(len(list(out.glob("claude-*__r1.jsonl"))), 16)
        for name in ("expected_results.json", "pilot_summary.json", "pilot_summary.txt", "runs_index.jsonl"):
            self.assertTrue((out / name).exists(), name)
        text = (out / "pilot_summary.txt").read_text(encoding="utf-8")
        for needed in ("DRY RUN", "Correct, out of runs", "Cost per correct answer", "Tokens per run", "Seconds per run",
                       "Full plan estimate", "as the main model", "as the replication model"):
            self.assertIn(needed, text)
        for model in cfg.PILOT_MODELS:
            data = summary["models"][model]
            self.assertEqual(data["overall"]["runs"], 8)
            self.assertEqual(set(data["by_arm"]), set(cfg.ARM_LABELS))
            main = data["full_plan"]["as_main_model"]
            self.assertEqual(main["runs"], 60 * 5 * 4)
            expected_main = sum(data["by_arm"][arm]["cost_warm_per_run_usd"] * 300 for arm in cfg.ARM_LABELS)
            self.assertAlmostEqual(main["usd"], expected_main, places=6)
            replication = data["full_plan"]["as_replication_model"]
            self.assertEqual(replication["runs"], 600)
            self.assertAlmostEqual(replication["usd"], sum(data["by_arm"][arm]["cost_warm_per_run_usd"] * 300 for arm in ("S", "L")), places=6)
        self.assertAlmostEqual(summary["spent_usd"], sum(r["cost_usd"] for r in results), places=6)

    def test_pilot_uses_dev_requests_only(self):
        with self.assertRaises(SystemExit):
            self.pilot(requests=("REQ-T01",))

    def test_hard_cap_stops_the_pilot_and_resume_finishes_it(self):
        cap = 0.30
        summary = self.pilot(cap=cap)
        out = self.tmp / "pilot"
        self.assertIsNotNone(summary["stopped_early"])
        self.assertLessEqual(run_pilot.spent_so_far(out), cap)
        statuses = {r["status"] for r in run_pilot.read_jsonl(out / "pilot_results.jsonl")}
        self.assertIn("cap_stop", statuses)
        finished_before = {e["run_id"] for e in run_pilot.latest_by_run_id(run_pilot.read_jsonl(out / "pilot_results.jsonl")).values()
                           if e["status"] != "cap_stop"}
        summary = self.pilot(cap=1000.0)
        self.assertIsNone(summary["stopped_early"])
        latest = run_pilot.latest_by_run_id(run_pilot.read_jsonl(out / "pilot_results.jsonl"))
        self.assertEqual(len(latest), 16)
        self.assertTrue(all(e["status"] != "cap_stop" for e in latest.values()))
        self.assertTrue(list(out.glob("*.attempt1.jsonl")))            # the stopped attempt's log was kept
        self.assertTrue(finished_before)                                # runs finished before the stop were not repeated
        lines = (out / "runs_index.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len([l for l in lines if json.loads(l)["status"] != "cap_stop"]), 16)

    def test_spend_already_logged_counts_toward_the_cap(self):
        self.pilot(cap=1000.0)
        spent = run_pilot.spent_so_far(self.tmp / "pilot")
        summary = self.pilot(cap=spent + 0.0001)          # nothing left to run, and nothing may be added
        self.assertAlmostEqual(run_pilot.spent_so_far(self.tmp / "pilot"), spent, places=6)

    def test_three_api_errors_in_a_row_abort_the_pilot(self):
        class AlwaysFails(ScriptedClient):
            def create(self, **request):
                raise harness.ModelCallError("down", status=500)
        client = AlwaysFails({}, policy="correct")
        summary = self.pilot(client=client, out_dir=self.tmp / "failing")
        self.assertIn("API errors in a row", summary["stopped_early"])
        self.assertEqual(len(run_pilot.read_jsonl(self.tmp / "failing" / "pilot_results.jsonl")), cfg.PILOT_CONSECUTIVE_API_ERRORS_ABORT)

    def test_output_may_not_go_into_an_input_folder(self):
        for folder in (cfg.WORLD_DIR, cfg.ARMS_DIR / "library", cfg.KEY_DIR, cfg.REQUESTS_DIR, cfg.WAREHOUSE_DIR):
            with self.assertRaises(SystemExit):
                run_pilot.assert_output_is_safe(folder / "pilot")
        run_pilot.assert_output_is_safe(cfg.RUNS_DIR / "pilot")

    def test_logs_contain_no_test_request_and_no_key_material(self):
        self.pilot()
        for path in (self.tmp / "pilot").rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn("REQ-T0", text, path.name)
                self.assertNotIn("sk-ant", text, path.name)

    def test_without_a_key_the_real_pilot_refuses_to_start(self):
        existed_before = (cfg.RUNS_DIR / "pilot").exists()
        environment = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        done = subprocess.run([sys.executable, str(CODE_DIR / "run_pilot.py"), "--cap-usd", "5", "--yes"], capture_output=True, text=True,
                              env=environment, encoding="utf-8", errors="replace")
        self.assertEqual(done.returncode, 2)
        self.assertIn("ANTHROPIC_API_KEY is not set", done.stdout)
        self.assertEqual((cfg.RUNS_DIR / "pilot").exists(), existed_before)

    def test_with_a_key_but_no_yes_or_no_cap_nothing_is_spent(self):
        existed_before = (cfg.RUNS_DIR / "pilot").exists()
        environment = dict(os.environ, ANTHROPIC_API_KEY="not-a-real-key")
        done = subprocess.run([sys.executable, str(CODE_DIR / "run_pilot.py"), "--cap-usd", "5"], capture_output=True, text=True,
                              env=environment, encoding="utf-8", errors="replace")
        self.assertEqual(done.returncode, 0)
        self.assertIn("Nothing has been spent", done.stdout)
        done = subprocess.run([sys.executable, str(CODE_DIR / "run_pilot.py"), "--yes"], capture_output=True, text=True,
                              env=environment, encoding="utf-8", errors="replace")
        self.assertEqual(done.returncode, 2)
        self.assertIn("--cap-usd is required", done.stdout)
        self.assertEqual((cfg.RUNS_DIR / "pilot").exists(), existed_before)

    def test_estimate_only_needs_no_key(self):
        environment = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        done = subprocess.run([sys.executable, str(CODE_DIR / "run_pilot.py"), "--estimate-only"], capture_output=True, text=True,
                              env=environment, encoding="utf-8", errors="replace")
        self.assertEqual(done.returncode, 0)
        self.assertIn("suggested cap", done.stdout)


class TestAnthropicClientShape(TempDirCase):
    """The real client, against an in-process mock transport: checks the request the SDK would send and how a
    Messages response (text, tool use, thinking, cache usage) is read. Nothing leaves the process."""

    def mock_client(self, handler, retries=0):
        import httpx
        return harness.AnthropicClient("not-a-real-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                                       max_retries=retries)

    def test_request_shape_and_response_reading(self):
        import httpx
        sent = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            turn = len(sent)
            if turn == 1:
                content = [{"type": "thinking", "thinking": "", "signature": "sig123"},
                           {"type": "text", "text": "Checking."},
                           {"type": "tool_use", "id": "fake_tool_use_1", "name": "run_sql", "input": {"sql": DEV[SMALL_REQUEST]["accepted_sql"]}}]
                stop = "tool_use"
            else:
                payload = harness.parse_final_answer  # noqa: F841
                content = [{"type": "text", "text": json.dumps({"sql": "x", "result": EXPECTED_SMALL, "definitions_applied": [],
                                                                  "assumptions": [], "caveats": []})}]
                stop = "end_turn"
            return httpx.Response(200, json={"id": f"msg_{turn}", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
                                             "content": content, "stop_reason": stop, "stop_sequence": None,
                                             "usage": {"input_tokens": 12, "cache_creation_input_tokens": 3000,
                                                       "cache_read_input_tokens": 40000, "output_tokens": 345}})
        client = self.mock_client(handler)
        summary = harness.run_one(request=DEV[SMALL_REQUEST]["request"], arm="L", model="claude-sonnet-5-5", client=client, out_dir=self.tmp)
        self.assertEqual(summary["status"], "ok", summary["problem"])
        self.assertEqual(pilot_marking.mark_run(summary, EXPECTED_SMALL, False)["outcome"], "correct")
        self.assertEqual(summary["tokens"]["cache_read_input_tokens"], 80000)
        self.assertEqual(summary["model_returned"], "claude-sonnet-5-5")
        first, second = sent
        self.assertEqual(first["model"], "claude-sonnet-5-5")
        self.assertEqual(first["max_tokens"], cfg.MAX_OUTPUT_TOKENS)
        self.assertEqual(first["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual([tool["name"] for tool in first["tools"]], ["run_sql", "load_skill", "run_script"])
        for forbidden in ("temperature", "top_p", "top_k", "thinking", "tool_choice", "stream"):
            self.assertNotIn(forbidden, first)
        self.assertNotIn("cache_control", json.dumps(first["messages"]))
        assistant = second["messages"][1]["content"]
        self.assertEqual(assistant[0], {"type": "thinking", "thinking": "", "signature": "sig123"})
        self.assertEqual(assistant[2]["type"], "tool_use")
        self.assertEqual(second["messages"][2]["content"][0]["type"], "tool_result")
        self.assertEqual(second["messages"][2]["content"][0]["tool_use_id"], "fake_tool_use_1")
        self.assertEqual(second["messages"][2]["content"][-1]["cache_control"], {"type": "ephemeral"})

    def test_api_errors_become_model_call_errors(self):
        import httpx

        def handler(request):
            return httpx.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})
        client = self.mock_client(handler)
        with self.assertRaises(harness.ModelCallError) as caught:
            client.create(model="claude-sonnet-5-5", max_tokens=10, messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.status, 529)
        summary = harness.run_one(request=DEV[SMALL_REQUEST]["request"], arm="S", model="claude-sonnet-5-5", client=client, out_dir=self.tmp)
        self.assertEqual(summary["status"], "api_error")


class TestZNoNetworkWasNeeded(unittest.TestCase):
    def test_the_dry_run_never_imports_the_sdk(self):
        """Run a scripted run in a fresh interpreter and check the anthropic SDK was not imported."""
        program = (
            "import sys, tempfile\n"
            f"sys.path.insert(0, {str(CODE_DIR)!r})\n"
            "import harness\n"
            "from fake_client import ScriptedClient\n"
            "dev = harness.load_dev_requests()\n"
            "entry = dev['REQ-D20']\n"
            "client = ScriptedClient({entry['request']['request_text']: entry['accepted_sql']})\n"
            "out = tempfile.mkdtemp()\n"
            "summary = harness.run_one(request=entry['request'], arm='L', model='claude-haiku-4-5-20251001', client=client, out_dir=out)\n"
            "assert summary['status'] == 'ok', summary\n"
            "assert 'anthropic' not in sys.modules\n"
            "print('no sdk import')\n")
        done = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertIn("no sdk import", done.stdout, done.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
