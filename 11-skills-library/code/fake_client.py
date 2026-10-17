"""A scripted stand-in for the model client, for the dry run and the tests. No network, no key.

ScriptedClient has the same create() as harness.AnthropicClient and returns the same plain-dict responses, but the
"model" is a fixed script (a policy) that issues real tool calls, so a dry run exercises everything the harness does on
a real run: the tool fences, the budgets, the cache bookkeeping, the logs, the marker. Tool results are real
(DuckDB on the warehouse, the library's own scripts); only the model is fake.

Policies (what the scripted model does):
  correct       plans a few tool calls, runs the request's accepted query, answers with that query's result
  wrong         as correct, but the answer's numbers are 50% too high
  malformed     as correct, but the final message is not the JSON contract
  fenced        as correct, but the JSON arrives inside a markdown fence after a sentence of preamble
  thinking      as correct, with a thinking block in every assistant turn (tests that blocks are passed back)
  parallel      as correct, but the first turn makes two tool calls at once
  budget_hog    runs SELECT after SELECT and never answers (ends on the query budget)
  skill_hog     opens seven skills (the seventh is refused), then as correct (library arms)
  escape        tries to reach the key, design documents, other files and other tools through every tool, then as correct
  api_error     the second call fails with an API error

Tokens are estimated at four characters per token; caching is simulated (the system prefix is written on the first
call and read after, and the conversation grows through the moving breakpoint), so costs from a dry run are
simulated and say nothing about real spend. The client's `kind` is written into every run log so a dry-run log can
never be mistaken for a real one.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable, Optional, Union

from harness import ModelCallError

CASE_ROOT_POSIX = Path(__file__).resolve().parent.parent.as_posix()
POLICIES = ("correct", "wrong", "malformed", "fenced", "thinking", "parallel", "budget_hog", "skill_hog", "escape", "api_error")

# Things the escape policy tries. None may succeed, and none may leave a trace of the key or another request in a log.
ESCAPE_SQL = [
    f"SELECT * FROM read_csv('{CASE_ROOT_POSIX}/data/key/key.json')",
    "COPY (SELECT 1) TO 'escaped.csv'",
    "ATTACH 'other.duckdb' AS other",
    "SET enable_external_access=true",
    "SELECT * FROM glob('*')",
    "DROP TABLE dim_date",
    "SELECT 1; SELECT 2",
]


def estimate_tokens(obj) -> int:
    return max(1, len(json.dumps(obj, ensure_ascii=False)) // 4)


class ScriptedClient:
    kind = "scripted-fake"

    def __init__(self, accepted_sql_by_text: dict, policy: Union[str, Callable[[str], str]] = "correct"):
        """accepted_sql_by_text: {request text: SQL}. policy: a policy name, or a function from request text to a name."""
        self.accepted_sql_by_text = {text.strip(): sql for text, sql in accepted_sql_by_text.items()}
        self.policy = policy
        self.warm_prefixes: set = set()
        self.conversation_cached_tokens: dict = {}
        self.calls = 0

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _request_text(messages: list) -> str:
        first = messages[0]["content"][0]["text"]
        match = re.search(r"^> (.+)$", first, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _policy_for(self, request_text: str) -> str:
        name = self.policy(request_text) if callable(self.policy) else self.policy
        if name not in POLICIES:
            raise ValueError(f"Unknown fake policy {name!r}")
        return name

    @staticmethod
    def _last_sql_result(messages: list) -> Optional[dict]:
        for message in reversed(messages):
            if message["role"] != "user" or isinstance(message["content"], str):
                continue
            for block in reversed(message["content"]):
                if block.get("type") == "tool_result" and not block.get("is_error"):
                    try:
                        payload = json.loads(block["content"])
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if isinstance(payload, dict) and "columns" in payload:
                        return payload
        return None

    def _steps(self, policy: str, tool_names: list, accepted_sql: str) -> list:
        """The planned tool calls, one list of (name, input) per assistant turn, before the final answer."""
        library = "load_skill" in tool_names
        scripts = "run_script" in tool_names
        steps: list = []
        if policy == "budget_hog":
            return [[("run_sql", {"sql": f"SELECT {index} AS n"})] for index in range(1, 40)]
        if policy == "escape":
            steps += [[("run_sql", {"sql": sql})] for sql in ESCAPE_SQL]
            if library:
                steps += [[("load_skill", {"skill": "warehouse-map", "path": "../../../data/key/key.json"})],
                          [("load_skill", {"skill": "../../data/key"})],
                          [("load_skill", {"skill": "warehouse-map", "path": "C:/Users/someone/notes.md"})],
                          [("load_skill", {"skill": "warehouse-map", "path": "../../build_notes.md"})]]
            if scripts:
                steps += [[("run_script", {"script": "query-check/scripts/query_check.py",
                                           "args": ["--sql", f"SELECT * FROM read_text('{CASE_ROOT_POSIX}/data/key/key.json')"]})],
                          [("run_script", {"script": "../../code/config.py"})],
                          [("run_script", {"script": "query-check/scripts/query_check.py", "args": ["--file", "../../../data/key/key.json"]})],
                          [("run_script", {"script": "fiscal-calendar/scripts/fiscal.py", "args": ["C:/other/place.duckdb", "last period"]})]]
            else:
                steps += [[("run_script", {"script": "fiscal-calendar/scripts/fiscal.py", "args": ["last period"]})]]
        if library:
            if policy == "skill_hog":
                names = ["warehouse-map", "fiscal-calendar", "metric-dictionary", "sales-reporting", "lfl-and-store-league",
                         "store-and-product-history", "web-orders"]
                steps += [[("load_skill", {"skill": name})] for name in names]
            else:
                first = [("load_skill", {"skill": "warehouse-map"})]
                if policy == "parallel":
                    first.append(("run_sql", {"sql": "SELECT COUNT(*) AS n FROM dim_date"}))
                steps.append(first)
                steps.append([("load_skill", {"skill": "warehouse-map", "path": "references/tables.md"})])
            if scripts:
                steps.append([("run_script", {"script": "fiscal-calendar/scripts/fiscal.py", "args": ["last period", "--as-of", "2026-10-05"]})])
                steps.append([("run_script", {"script": "query-check/scripts/query_check.py",
                                              "args": ["--file", "check.sql", "--grain", "n"],
                                              "files": {"check.sql": "SELECT 1 AS n"}})])
        else:
            first = [("run_sql", {"sql": "SELECT COUNT(*) AS n FROM dim_date"})]
            if policy == "parallel":
                first.append(("run_sql", {"sql": "SELECT MAX(calendar_date) AS last_day FROM dim_date"}))
            steps.append(first)
            steps.append([("run_sql", {"sql": "SELEC broken"})])
        steps.append([("run_sql", {"sql": accepted_sql})])
        return steps

    def _final_text(self, policy: str, messages: list, accepted_sql: str) -> str:
        if policy == "malformed":
            return "Net sales rose compared with last year, as far as I can tell."
        payload = self._last_sql_result(messages) or {"columns": [], "rows": []}
        rows = payload["rows"]
        if policy == "wrong":
            rows = [[cell * 1.5 if isinstance(cell, (int, float)) and not isinstance(cell, bool) else cell for cell in row] for row in rows]
        answer = {"sql": accepted_sql, "result": {"columns": payload["columns"], "rows": rows},
                  "definitions_applied": ["scripted definition"], "assumptions": ["scripted assumption"], "caveats": []}
        text = json.dumps(answer, ensure_ascii=False)
        return f"Here is the answer.\n```json\n{text}\n```" if policy == "fenced" else text

    # -- the model call ----------------------------------------------------------

    def create(self, *, model: str, max_tokens: int, system: list, tools: list, messages: list, **extras) -> dict:
        self.calls += 1
        request_text = self._request_text(messages)
        policy = self._policy_for(request_text)
        accepted_sql = self.accepted_sql_by_text.get(request_text, "SELECT 1 AS n")
        turn_index = sum(1 for message in messages if message["role"] == "assistant")
        if policy == "api_error" and turn_index >= 1:
            raise ModelCallError("scripted API failure", status=529)
        steps = self._steps(policy, [tool["name"] for tool in tools], accepted_sql)
        content: list = []
        if policy == "thinking":
            content.append({"type": "thinking", "thinking": "", "signature": "scripted-signature"})
        if turn_index < len(steps):
            if turn_index == 0:
                content.append({"type": "text", "text": "Let me look."})
            for number, (name, tool_input) in enumerate(steps[turn_index]):
                content.append({"type": "tool_use", "id": f"fake_tool_use_{turn_index}_{number}", "name": name, "input": tool_input})
            stop_reason = "tool_use"
        else:
            content.append({"type": "text", "text": self._final_text(policy, messages, accepted_sql)})
            stop_reason = "end_turn"
        return {"id": f"msg_fake_{self.calls}", "model": model, "stop_reason": stop_reason, "content": content,
                "usage": self._usage(system, tools, messages, content)}

    def _usage(self, system: list, tools: list, messages: list, content: list) -> dict:
        """Simulated usage: static prefix cached on first sight, conversation cached through the moving breakpoint."""
        prefix_tokens = estimate_tokens(system) + estimate_tokens(tools)
        prefix_key = hashlib.sha256(json.dumps([system, tools], sort_keys=True).encode()).hexdigest()
        creation = read = uncached = 0
        if prefix_key in self.warm_prefixes:
            read += prefix_tokens
        else:
            creation += prefix_tokens
            self.warm_prefixes.add(prefix_key)
        message_tokens = estimate_tokens(messages)
        marker_present = "cache_control" in json.dumps(messages[-1])
        conversation_key = hashlib.sha256(json.dumps(messages[0], sort_keys=True).encode()).hexdigest()
        if marker_present:
            previously_cached = min(self.conversation_cached_tokens.get(conversation_key, 0), message_tokens)
            read += previously_cached
            creation += message_tokens - previously_cached
            self.conversation_cached_tokens[conversation_key] = message_tokens
        else:
            uncached += message_tokens
        return {"input_tokens": uncached, "cache_creation_input_tokens": creation, "cache_read_input_tokens": read,
                "output_tokens": estimate_tokens(content) + 20}
