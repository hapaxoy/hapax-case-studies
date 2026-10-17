"""Phase 2 checks on the in-world material: facts, documents, schema comments and the 40 dev requests.

Called by validate_data.py (run(connection, record)). These checks belong to the provenance rules in spirit
(17: everything in world/ traces to a fact and no undocumented incident appears anywhere in world/) and to the Phase 2
brief (40 dev requests whose accepted queries run and are unaffected by the planted incidents). Rules 16 and 18 apply
once the arm materials and the test set exist (later phases).
"""
from __future__ import annotations

import json
import re
import shutil
import time
from datetime import date, timedelta

import duckdb
import pandas as pd
import yaml

import config as cfg
import dev_requests
import facts_spec

MARKER = re.compile(r"<!--\s*facts:\s*([^>]+?)\s*-->")
DOCS = {"metric_dictionary": "metric_dictionary.md", "data_quality_register": "data_quality_register.md",
        "team_notes": "team_notes.md"}
STALE_EXPECTED = {("dim_store", "region"), ("dim_store", "format"), ("dim_product", "standard_unit_cost"),
                  ("fact_sales_line", "channel_code")}


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def parse_document(path):
    """Return {fact_id: text of the blocks it marks} and a list of unmarked prose snippets."""
    blocks: dict[str, list[str]] = {}
    unmarked: list[str] = []
    current: list[str] | None = None
    seen_first_section = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        marker = MARKER.search(line)
        if marker:
            current = [item.strip() for item in marker.group(1).split(",")]
            for fact_id in current:
                blocks.setdefault(fact_id, [])
            continue
        if line.startswith("#"):
            current = None
            if line.startswith("##"):
                seen_first_section = True
            continue
        if not line:
            continue
        if current is None:
            if seen_first_section:
                unmarked.append(line[:80])
            continue
        for fact_id in current:
            blocks[fact_id].append(line)
    return {k: " ".join(v) for k, v in blocks.items()}, unmarked


def check_facts_and_documents(record) -> list[dict]:
    print("World: facts and documents")
    facts = yaml.safe_load(cfg.FACTS_PATH.read_text(encoding="utf-8"))
    current = json.loads(json.dumps(facts_spec.build_facts()))
    record("W1", "facts.yaml equals the facts derived from config.py", facts == current, f"{len(facts)} facts")
    ids = [f["id"] for f in facts]
    record("W1", "fact IDs are unique", len(ids) == len(set(ids)))
    by_id = {f["id"]: f for f in facts}

    parsed = {}
    for doc, filename in DOCS.items():
        path = cfg.WORLD_DIR / filename
        if not path.exists():
            record("W2", f"{filename} exists", False)
            return facts
        parsed[doc] = parse_document(path)
        text = path.read_text(encoding="utf-8")
        record("W2", f"{filename}: no unresolved placeholders", "{{" not in text)
    for doc, (blocks, unmarked) in parsed.items():
        record("W2", f"{DOCS[doc]}: all prose sits under a fact marker", not unmarked, "; ".join(unmarked[:3]))
        unknown = [fid for fid in blocks if fid not in by_id]
        record("W2", f"{DOCS[doc]}: every marker names a known fact", not unknown, str(unknown))
        stray = [fid for fid in blocks if fid in by_id and doc not in by_id[fid]["docs"]]
        record("W2", f"{DOCS[doc]}: no fact appears in a document it is not assigned to", not stray, str(stray))

    missing, absent_phrases = [], []
    for fact in facts:
        if fact["kind"] == "schema":
            continue
        for doc in fact["docs"]:
            blocks = parsed[doc][0]
            if fact["id"] not in blocks:
                missing.append(f"{fact['id']} in {doc}")
                continue
            text = normalise(blocks[fact["id"]])
            for phrase in fact["must_contain"]:
                if normalise(phrase) not in text:
                    absent_phrases.append(f"{fact['id']}: '{phrase}'")
    record("W2", "every curated fact appears in each document it is assigned to", not missing, "; ".join(missing[:5]))
    record("W2", "every fact's key values appear in its text (dates, rates, store numbers, names)", not absent_phrases,
           "; ".join(absent_phrases[:5]))
    curated = [f for f in facts if f["kind"] != "schema"]
    record("W2", "curated facts and parity-required facts counted", all(f["parity_required"] for f in curated),
           f"{len(curated)} curated facts, all parity-required")
    return facts


def check_schema(connection, record, facts) -> None:
    print("World: schema comments")
    csv_rows = pd.read_csv(cfg.WORLD_DIR / "schema_comments.csv", keep_default_na=False)
    db_columns = connection.execute(
        "SELECT table_name, column_name, data_type, coalesce(comment, '') FROM duckdb_columns() WHERE NOT internal").df()
    db_columns.columns = ["table_name", "column_name", "data_type", "comment"]
    merged = csv_rows.merge(db_columns, on=["table_name", "column_name"], how="outer", suffixes=("_csv", "_db"), indicator=True)
    same = (merged["_merge"] == "both").all() and (merged["comment_csv"] == merged["comment_db"]).all() and \
           (merged["data_type_csv"] == merged["data_type_db"]).all()
    record("W3", "world/schema_comments.csv equals the warehouse's own comments and types", bool(same), f"{len(csv_rows)} columns")
    schema_facts = {f["id"]: f for f in facts if f["kind"] == "schema"}
    wrong = []
    for row in csv_rows.itertuples():
        fact = schema_facts.get(f"SCH-{row.table_name}.{row.column_name}")
        if fact is None:
            if row.comment:
                wrong.append(f"{row.table_name}.{row.column_name} has a comment but no fact")
        elif fact["statement"] != row.comment:
            wrong.append(f"{row.table_name}.{row.column_name}")
    record("W3", "every schema comment traces to a schema fact and back", not wrong, "; ".join(wrong[:5]))
    canonical = csv_rows[csv_rows["table_name"].isin(schema_facts_tables(schema_facts))]
    coverage = (canonical["comment"] != "").mean()
    record("W3", "most canonical columns carry a comment (not an empty schema)", coverage >= 0.95, f"{coverage:.0%}")
    stale = {tuple(fid[4:].split(".", 1)) for fid, f in schema_facts.items() if f.get("stale")}
    record("W3", "the four deliberately stale comments are exactly the expected ones", stale == STALE_EXPECTED, str(sorted(stale)))
    # Evidence that each stale comment really is out of date.
    regions = connection.execute("SELECT count(DISTINCT region) FROM dim_store WHERE is_current").fetchone()[0]
    formats = {r[0] for r in connection.execute("SELECT DISTINCT format FROM dim_store").fetchall()}
    cost_changes = connection.execute(
        "SELECT count(*) FROM (SELECT sku FROM dim_product GROUP BY sku HAVING count(DISTINCT standard_unit_cost) > 1)").fetchone()[0]
    filled_after = connection.execute(
        f"SELECT count(*) FROM fact_sales_line WHERE channel_code IS NOT NULL AND sale_date >= DATE '{cfg.MIGRATION_DATE}'").fetchone()[0]
    evidence = regions > 4 and not (formats & {"Hyper", "Standard", "Express"}) and cost_changes == 0 and filled_after == 0
    record("W3", "each stale comment disagrees with the data (regions, formats, cost revaluation, channel_code)", evidence,
           f"{regions} current regions, formats {sorted(formats)}, {cost_changes} cost changes, {filled_after} late channel_code rows")


def schema_facts_tables(schema_facts) -> set:
    return {fid[4:].split(".", 1)[0] for fid in schema_facts}


def incident_tokens() -> list[str]:
    tokens = ["double-post", "double post", "doubly posted", "posted twice", "re-sync", "resync", "reload", "re-load", "loaded twice",
              "orphan", "mislabel", "mis-label", "duplicate posting", "till sync"]
    windows = [cfg.INCIDENT_DOUBLE_POST["week_start"], cfg.INCIDENT_DOUBLE_POST["week_end"], cfg.INCIDENT_LOGIN_ORPHANS["start"],
               cfg.INCIDENT_LOGIN_ORPHANS["end"], cfg.INCIDENT_STOCK_RELOAD["week_ending"], cfg.INCIDENT_CNC_MISLABEL["start"],
               cfg.INCIDENT_CNC_MISLABEL["end"]]
    for value in windows:
        tokens.append(value.isoformat())
        tokens.append(facts_spec.fmt_date(value).lower())
    return tokens


def check_incident_secrecy(record) -> None:
    print("World: undocumented incidents stay undocumented")
    hits = []
    tokens = incident_tokens()
    for path in sorted(cfg.WORLD_DIR.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8").lower()
            for token in tokens:
                if token in text:
                    hits.append(f"{path.name}: '{token}'")
    record("W4", "no incident keyword or incident date appears anywhere in world/", not hits, "; ".join(hits[:5]))
    facts_text = cfg.FACTS_PATH.read_text(encoding="utf-8").lower()
    record("W4", "no incident appears in facts.yaml", not any(t in facts_text for t in tokens))
    comments = cfg.WORLD_DIR.joinpath("schema_ddl.sql").read_text(encoding="utf-8").lower()
    record("W4", "no incident appears in the schema comments or DDL", not any(t in comments for t in tokens))


def make_clean_copy(target) -> None:
    """Copy the warehouse and undo the four planted incidents, giving the 'truth' database."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cfg.WAREHOUSE_PATH, target)
    # The scratch folder may sit inside a synced folder, which can hold a freshly copied 70 MB file for a few seconds. Retry rather than crash.
    connection = None
    for attempt in range(1, 13):
        try:
            connection = duckdb.connect(str(target))
            break
        except duckdb.IOException as error:
            print(f"  scratch copy is locked by another process (attempt {attempt} of 12), waiting 5 s: {str(error)[:90]}")
            time.sleep(5)
    if connection is None:
        raise RuntimeError(f"Could not open the scratch copy {target} after 12 attempts; pause file syncing for this folder and rerun.")
    connection.execute(f"DELETE FROM fact_sales_line WHERE etl_loaded_at = TIMESTAMP '{cfg.INCIDENT_DOUBLE_POST['reload_ts']}'")
    connection.execute("UPDATE fact_sales_line SET member_key = o.member_key FROM fact_web_order o "
                       "WHERE fact_sales_line.receipt_id = o.web_order_id AND fact_sales_line.member_key IS NULL AND o.member_key IS NOT NULL")
    connection.execute("UPDATE fact_sales_line SET channel_id = 3 FROM fact_web_order o WHERE fact_sales_line.receipt_id = o.web_order_id "
                       "AND o.fulfilment_type = 'click_and_collect' AND fact_sales_line.channel_id = 2")
    connection.execute(f"DELETE FROM fact_stock_week WHERE etl_loaded_at = TIMESTAMP '{cfg.INCIDENT_STOCK_RELOAD['reload_ts']}'")
    connection.execute("CHECKPOINT")
    connection.close()


def overlaps(start: date, end: date, other_start: date, other_end: date) -> bool:
    return start <= other_end and other_start <= end


def check_incident_bite(connection, clean, record) -> None:
    """Each planted incident must change the answer to a natural probe query, or it is not a trap."""
    print("World: the planted incidents change answers (negative control for the dev-request proof)")
    i1, i2, i3, i4 = (cfg.INCIDENT_DOUBLE_POST, cfg.INCIDENT_LOGIN_ORPHANS, cfg.INCIDENT_STOCK_RELOAD, cfg.INCIDENT_CNC_MISLABEL)
    probes = {
        "INC-1 store-week net sales": (
            f"SELECT sum(f.net_amount) FROM fact_sales_line f JOIN dim_store s USING (store_key) "
            f"WHERE s.store_id = {i1['store_id']} AND f.sale_date BETWEEN DATE '{i1['week_start']}' AND DATE '{i1['week_end']}'"),
        "INC-2 member share of web sales in the window": (
            f"SELECT sum(CASE WHEN f.member_key IS NOT NULL THEN f.net_amount ELSE 0 END) / sum(f.net_amount) FROM fact_sales_line f "
            f"JOIN dim_store s USING (store_key) WHERE s.store_id = 900 AND f.sale_date BETWEEN DATE '{i2['start']}' AND DATE '{i2['end']}'"),
        "INC-3 West stock units in the reloaded week": (
            f"SELECT sum(w.closing_units) FROM fact_stock_week w JOIN dim_store s USING (store_key) "
            f"WHERE w.week_ending_date = DATE '{i3['week_ending']}' AND s.region = '{i3['region_new']}'"),
        "INC-4 click-and-collect share by channel_id in the window": (
            f"SELECT sum(CASE WHEN f.channel_id = 3 THEN f.net_amount ELSE 0 END) / sum(f.net_amount) FROM fact_sales_line f "
            f"JOIN dim_store s USING (store_key) WHERE s.store_id = 900 AND f.sale_date BETWEEN DATE '{i4['start']}' AND DATE '{i4['end']}'"),
    }
    for name, sql in probes.items():
        published = float(connection.execute(sql).fetchone()[0])
        repaired = float(clean.execute(sql).fetchone()[0])
        relative = abs(published - repaired) / max(abs(repaired), 1e-9)
        record("W6", f"{name} differs between the published and repaired warehouse", relative > 0.01,
               f"published {published:,.3f} vs repaired {repaired:,.3f} ({relative:.0%})")


def check_dev_requests(connection, clean, record) -> None:
    print("World: the 40 dev requests")
    requests = dev_requests.DEV_REQUESTS
    record("W5", "40 dev requests with unique IDs", len(requests) == cfg.N_DEV_REQUESTS and len({r["id"] for r in requests}) == len(requests))
    patterns = [r["pattern"] for r in requests]
    counts = {p: patterns.count(p) for p in sorted(set(patterns))}
    record("W5", "dev history covers exactly the 10 designed patterns, in the designed counts",
           counts == cfg.DEV_REQUEST_COUNTS and set(patterns) == set(cfg.DEV_PATTERNS_COVERED), str(counts))
    record("W5", "patterns 9, 10, 13 and 14 are absent from the history", not (set(patterns) & set(cfg.DEV_PATTERNS_ABSENT)))
    record("W5", "each request was received after the period it covers, and before the data cut",
           all(r["received"] > r["period_end"] - timedelta(days=0) and r["received"] <= date(2026, 10, 13) for r in requests))
    record("W5", "request wording is not duplicated", len({r["request_text"] for r in requests}) == len(requests))

    # Declared scope against the incident windows.
    i1, i2, i4 = cfg.INCIDENT_DOUBLE_POST, cfg.INCIDENT_LOGIN_ORPHANS, cfg.INCIDENT_CNC_MISLABEL
    clashes = []
    for r in requests:
        if "store_sales" in r["uses"] and overlaps(r["period_start"], r["period_end"], i1["week_start"], i1["week_end"]) \
                and (r["regions"] is None or "West" in r["regions"]):
            clashes.append(f"{r['id']}: INC-1")
        if "member_web" in r["uses"] and overlaps(r["period_start"], r["period_end"], i2["start"], i2["end"]):
            clashes.append(f"{r['id']}: INC-2")
        if "channel_id" in r["uses"] and overlaps(r["period_start"], r["period_end"], i4["start"], i4["end"]):
            clashes.append(f"{r['id']}: INC-4")
        if "stock" in r["uses"]:
            clashes.append(f"{r['id']}: stock is not covered by the history")
    record("W5", "no request's declared scope touches a planted incident", not clashes, "; ".join(clashes))

    # Run on the published warehouse.
    published, failures, timings = {}, [], []
    for r in requests:
        started = time.time()
        try:
            frame = connection.execute(r["sql"]).df()
            published[r["id"]] = frame
            timings.append(time.time() - started)
            if frame.empty:
                failures.append(f"{r['id']}: empty result")
        except Exception as error:
            failures.append(f"{r['id']}: {str(error)[:120]}")
    record("W5", "every accepted query runs on the warehouse and returns rows", not failures,
           "; ".join(failures[:3]) if failures else f"slowest {max(timings):.1f}s")

    # Re-run on the repaired copy: the answers must not move.
    moved = []
    for r in requests:
        frame = clean.execute(r["sql"]).df()
        if not frame.equals(published[r["id"]]):
            moved.append(r["id"])
    record("W5", "all 40 answers are identical on the repaired (incident-free) copy of the warehouse", not moved, "; ".join(moved))

    # History files match the data.
    mismatched = []
    for r in requests:
        path = cfg.WORLD_DIR / "request_history" / f"{r['id']}.md"
        if not path.exists() or r["sql"].strip() not in path.read_text(encoding="utf-8") or r["request_text"] not in path.read_text(encoding="utf-8"):
            mismatched.append(r["id"])
    record("W5", "world/request_history files carry each request, query and note", not mismatched, "; ".join(mismatched))


def run(connection, record) -> None:
    facts = check_facts_and_documents(record)
    check_schema(connection, record, facts)
    check_incident_secrecy(record)
    clean_path = cfg.DATA_DIR / "_clean_check" / "clean.duckdb"        # scratch copy with the incidents undone
    make_clean_copy(clean_path)
    clean = duckdb.connect(str(clean_path), read_only=True)
    try:
        check_incident_bite(connection, clean, record)
        check_dev_requests(connection, clean, record)
    finally:
        clean.close()
        clean_path.unlink(missing_ok=True)
        clean_path.with_suffix(".duckdb.wal").unlink(missing_ok=True)
        try:
            clean_path.parent.rmdir()
        except OSError:
            pass
