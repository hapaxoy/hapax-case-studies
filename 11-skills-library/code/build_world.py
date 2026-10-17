"""Build facts.yaml and the in-world documents (Project 11, Phase 2).

Run after generate_warehouse.py:  python code/build_world.py

Writes
  data/facts.yaml                      structured facts, one ID per fact (held out of world/)
  world/metric_dictionary.md           the wiki page with the company definitions
  world/data_quality_register.md       the team's known-issues log
  world/team_notes.md                  the head of data's pinned notes
  world/schema_ddl.sql                 DDL for every object, with the warehouse's own comments
  world/schema_comments.csv            table, column, type, comment for every object
  world/request_history/REQ-D01..D40   past requests with the analyst's accepted query and note
  world/index.md                       the wiki front page

The prose lives in code/world_templates/ (written by hand under brief discipline: it may not add or remove a fact,
and validate_world.py checks that every fact appears where it is meant to and nothing else does). Values (dates,
rates, store numbers) are filled in from config.py through facts_spec.world_context(), so the documents and the
data cannot drift apart.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import duckdb
import yaml

import config as cfg
import dev_requests
import facts_spec
from wh_common import log

CANONICAL_ORDER = ["dim_date", "ref_fiscal_calendar", "dim_store", "ref_store_closure", "dim_product", "dim_member",
                   "dim_channel", "dim_campaign", "campaign_holdout", "fact_sales_line", "fact_return_line",
                   "fact_web_order", "fact_stock_week", "fact_campaign_exposure", "rpt_daily_store_sales"]


def safe_write(path: Path, text: str) -> None:
    """Write a text file, refusing anything outside the permitted output folders (world/ and data/)."""
    resolved = path.resolve()
    allowed = [cfg.WORLD_DIR.resolve(), cfg.DATA_DIR.resolve()]
    if not any(folder in resolved.parents for folder in allowed):
        raise PermissionError(f"Refusing to write outside world/ and data/: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text, encoding="utf-8", newline="\n")


def render_template(name: str, context: dict) -> str:
    """Fill {{placeholders}} in a world template; fail if any placeholder is left unresolved."""
    source = (cfg.WORLD_TEMPLATE_DIR / name).read_text(encoding="utf-8")
    for key, value in context.items():
        source = source.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{[^}]+\}\}", source)
    if leftover:
        raise ValueError(f"{name}: unresolved placeholders {sorted(set(leftover))}")
    return source


def write_schema(connection) -> None:
    """DDL and comment listings straight from the warehouse, so the schema-only arm sees what an analyst would."""
    tables = connection.execute(
        "SELECT schema_name, table_name, sql, comment FROM duckdb_tables() WHERE NOT internal ORDER BY schema_name, table_name").fetchall()
    by_name = {t[1]: t for t in tables}
    ordered = [by_name[n] for n in CANONICAL_ORDER if n in by_name] + sorted(
        [t for t in tables if t[1] not in CANONICAL_ORDER], key=lambda t: t[1])
    views = connection.execute(
        "SELECT schema_name, view_name, sql, comment FROM duckdb_views() WHERE NOT internal ORDER BY schema_name, view_name").fetchall()
    columns = connection.execute(
        "SELECT table_name, column_name, data_type, comment, column_index FROM duckdb_columns() WHERE NOT internal ORDER BY table_name, column_index").fetchall()

    lines = ["-- Tuomimetsä Oy warehouse (DuckDB). Object definitions as created, with the comments the warehouse carries.", ""]
    rows = []
    for schema_name, table_name, sql_text, table_comment in ordered:
        lines.append(sql_text.rstrip(";") + ";")
        if table_comment:
            lines.append(f"COMMENT ON TABLE {table_name} IS '{table_comment}';")
        for column_table, column_name, data_type, comment, _ in columns:
            if column_table == table_name:
                if comment:
                    lines.append(f"COMMENT ON COLUMN {table_name}.{column_name} IS '{comment}';")
                rows.append([table_name, column_name, data_type, comment or ""])
        lines.append("")
    for schema_name, view_name, sql_text, _ in views:
        lines.append(sql_text.rstrip(";") + ";")
        lines.append("")
        for column_table, column_name, data_type, comment, _ in columns:
            if column_table == view_name:
                rows.append([view_name, column_name, data_type, comment or ""])
    safe_write(cfg.WORLD_DIR / "schema_ddl.sql", "\n".join(lines))

    csv_path = cfg.WORLD_DIR / "schema_comments.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["table_name", "column_name", "data_type", "comment"])
        writer.writerows(rows)
    log(f"  schema: {len(ordered)} tables, {len(views)} views, {len(rows)} columns")


def write_request_history() -> None:
    """One markdown file per dev request, plus an index."""
    index_lines = ["# Request history", "",
                   "Past requests from the queue with the query the analyst sent back (accepted by the requester) and a one-line note.", "",
                   "| Request | Received | From | Department | Request |", "|---|---|---|---|---|"]
    for request in dev_requests.DEV_REQUESTS:
        body = "\n".join([
            f"# {request['id']}", "",
            f"- Received: {request['received'].isoformat()}",
            f"- From: {request['requester']}, {request['department']}", "",
            "## Request", "", f"> {request['request_text']}", "",
            "## Accepted query", "", "```sql", request["sql"].rstrip(), "```", "",
            "## Note", "", request["note"], ""])
        safe_write(cfg.WORLD_DIR / "request_history" / f"{request['id']}.md", body)
        short = request["request_text"].replace("|", "/")
        index_lines.append(f"| [{request['id']}]({request['id']}.md) | {request['received'].isoformat()} | {request['requester']} | "
                           f"{request['department']} | {short} |")
    safe_write(cfg.WORLD_DIR / "request_history" / "index.md", "\n".join(index_lines) + "\n")
    log(f"  request history: {len(dev_requests.DEV_REQUESTS)} requests")


def main() -> int:
    if not cfg.WAREHOUSE_PATH.exists():
        print(f"ERROR: {cfg.WAREHOUSE_PATH} not found; run generate_warehouse.py first.")
        return 1
    try:
        log("Building facts.yaml")
        facts = facts_spec.build_facts()
        header = ("# Structured facts for the Tuomimetsä world (Project 11). Generated by code/build_world.py from config.py.\n"
                  "# One ID per fact. Held out of world/: the arm builders read world/ only. 'stale' marks schema comments that\n"
                  "# are out of date on purpose; trap_class is internal.\n")
        safe_write(cfg.FACTS_PATH, header + yaml.safe_dump(facts, sort_keys=False, allow_unicode=True, width=120))
        log(f"  {len(facts)} facts ({sum(1 for f in facts if f['kind'] != 'schema')} curated, "
            f"{sum(1 for f in facts if f['kind'] == 'schema')} schema comments)")

        context = facts_spec.world_context()
        context["refits_text"] = "; ".join(context["refits"])
        context = {key: value for key, value in context.items() if isinstance(value, str)}
        log("Rendering world documents")
        for name in ("metric_dictionary.md", "data_quality_register.md", "team_notes.md"):
            safe_write(cfg.WORLD_DIR / name, render_template(name, context))
            log(f"  wrote world/{name}")

        connection = duckdb.connect(str(cfg.WAREHOUSE_PATH), read_only=True)
        try:
            write_schema(connection)
        finally:
            connection.close()
        write_request_history()

        index = ["# Data & Analytics wiki", "",
                 "- [Metric dictionary](metric_dictionary.md): the company definitions.",
                 "- [Data quality register](data_quality_register.md): known issues in the warehouse.",
                 "- [Team notes](team_notes.md): pinned notes from the head of data.",
                 "- [Schema](schema_ddl.sql) and [column comments](schema_comments.csv).",
                 "- [Request history](request_history/index.md): past requests and the queries we sent back.", ""]
        safe_write(cfg.WORLD_DIR / "index.md", "\n".join(index))
    except Exception as error:
        import traceback
        traceback.print_exc()
        print(f"\nERROR: building the world failed: {error}")
        return 1
    log("Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
