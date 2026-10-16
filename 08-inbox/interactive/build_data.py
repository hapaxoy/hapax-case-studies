"""build_data.py -- assembles interactive/_data.json for the inbox-automation
interactive page, then inlines it into _template.html to produce inbox.html.

Follows the same pattern as the other cases (07 Tenders, 09 Training Outcomes,
10 Talent Screening: interactive/build_data.py + _template.html -> single
self-contained HTML file): a deterministic, re-runnable Python build step
assembles ONE JSON blob from the project's real data directories under
data/, and a hand-written template with an embedded
<script type="application/json" id="hpx-data"> renders it client-side.

Data sources:
  data/emails/email_*.json            -- the 150 inbound customer emails
  data/threads_prose/thread_*.json    -- the ~90 threads (full message history)
  data/pipeline/decisions/decision_*.json
                                       -- per-email pipeline trace: intent
                                          class + rationale, draft (or null
                                          for the escalate shortcut), each
                                          gate's verdict, route + reason
  data/pipeline/routing_summary.csv   -- flat per-email route/gate summary,
                                          used here only to cross-check the
                                          richer decision JSON never drifted
                                          from the flat log
  data/analysis/marks.json            -- the frozen marking
                                          output -- embedded near-verbatim as
                                          the scoreboard's numbers; this
                                          script computes nothing that counts
                                          as a verdict, it only re-groups
                                          marks.json's own figures for the
                                          flow diagram
  data/answer_key/answer_key.csv      -- the held-out key: ideal route, trap
                                          type, binding clauses, correct
                                          commitments -- shown ONLY behind the
                                          page's answer-key toggle
  data/policy/handbook.yaml           -- the 30-clause policy handbook, so a
                                          cited clause id (e.g. "H-19") can be
                                          shown with its title and text
                                          in-line rather than as a bare code
  code/config.py                      -- COMPANY, TRAP_TYPES, the three
                                          intent-class sets and the router
                                          rule (route_for_intent) -- reused
                                          directly rather than re-typed, so
                                          this page can never state a
                                          different router rule than the one
                                          that actually ran

Reading the answer key here is the same deliberate, logged exception as case
10's build_data.py: marking is frozen, so this is display packaging AFTER the fact, never a leak into
a run that produced a result.

This script and the page it feeds never rank emails or issue a verdict of
their own beyond displaying the pipeline's logged decisions and the key's
record: every
number under a MET/NOT MET chip is copied from marks.json, not recomputed;
the only new grouping done here is the flow diagram's column/link structure,
built by joining routing_summary.csv's actual per-email route against
marks.json's own frozen misroute/false-block lists -- a re-presentation of
already-marked facts, not a new judgment. Every grouping total is asserted
against marks.json's headline numbers below (an assertion failure means the
two data sources have drifted, which is a bug in this script, not a
judgment call).

All reader-facing PAGE COPY (headings, intros, empty states, button labels,
tooltips) lives in the STRINGS object inside _template.html. Structural labels that
are themselves case content fixed in config.py
(trap labels, "correct behaviour" text, intent-class names, route names) are
treated as DATA and travel through meta below, the same split case 10 used
for its archetype labels and requirement descriptions.

Run from this directory or the project root:
    python interactive/build_data.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"
CODE_DIR = PROJECT_ROOT / "code"

sys.path.insert(0, str(CODE_DIR))
import config  # noqa: E402 -- the project's own config module

EMAILS_DIR = DATA_DIR / "emails"
THREADS_DIR = DATA_DIR / "threads_prose"
DECISIONS_DIR = DATA_DIR / "pipeline" / "decisions"
ROUTING_SUMMARY_PATH = DATA_DIR / "pipeline" / "routing_summary.csv"
MARKS_PATH = DATA_DIR / "analysis" / "marks.json"
ANSWER_KEY_PATH = DATA_DIR / "answer_key" / "answer_key.csv"
HANDBOOK_PATH = DATA_DIR / "policy" / "handbook.yaml"

OUT_JSON = HERE / "_data.json"
TEMPLATE_PATH = HERE / "_template.html"
OUT_HTML = HERE / "inbox.html"

# Plain, non-narrative capitalisations of the router's own class/route ids --
# these are labels for enum values, not page copy, so they stay here rather
# than in the template's STRINGS object (same split case 10 used for
# archetype_labels).
INTENT_CLASS_LABELS = {
    "routine": "Routine",
    "policy_correction": "Policy correction",
    "commercial_discount": "Commercial discount",
    "prior_promise": "Prior promise",
    "needs_info": "Needs info",
    "safety": "Safety",
    "data_request": "Data request",
}
ROUTE_LABELS = {
    "auto_send": "Auto-sent",
    "human_queue": "Human queue",
    "escalate": "Escalated",
}
GATE_LABELS = {
    "policy_gate": "Policy gate",
    "consistency_gate": "Consistency gate",
    "completeness_gate": "Completeness gate",
}


def log(message: str) -> None:
    print(f"[build_data] {message}")


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"required data file missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"required data file missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def email_sort_key(email_id: str) -> int:
    # "EML-001" -> 1
    return int(email_id.split("-")[1])


# ---------------------------------------------------------------------------
# Policy handbook -- clause id -> title/text/category, for in-line display
# wherever a decision or the answer key cites a clause.
# ---------------------------------------------------------------------------

def load_clauses() -> dict:
    log("loading policy handbook (clause lookup)...")
    handbook = yaml.safe_load(HANDBOOK_PATH.read_text(encoding="utf-8"))
    clauses = {}
    for clause in handbook["clauses"]:
        clauses[clause["id"]] = {
            "id": clause["id"],
            "category": clause["category"],
            "title": clause["title"],
            "text": clause["text"],
        }
    log(f"  {len(clauses)} clauses loaded")
    return clauses, handbook


# ---------------------------------------------------------------------------
# Threads -- full message history, keyed by thread id
# ---------------------------------------------------------------------------

def load_threads() -> dict:
    log("loading threads (customer + staff message history)...")
    out = {}
    paths = sorted(THREADS_DIR.glob("thread_*.json"))
    if not paths:
        raise FileNotFoundError(f"no threads found under {THREADS_DIR}")
    for path in paths:
        t = load_json(path)
        out[t["thread_id"]] = t
    log(f"  {len(out)} threads loaded")
    return out


# ---------------------------------------------------------------------------
# Emails -- the 150-row core dataset, joining brief + decision + key
# ---------------------------------------------------------------------------

def load_email_briefs() -> dict:
    log("loading the 150 inbound emails...")
    out = {}
    paths = sorted(EMAILS_DIR.glob("email_*.json"))
    if not paths:
        raise FileNotFoundError(f"no emails found under {EMAILS_DIR}")
    for path in paths:
        e = load_json(path)
        out[e["email_id"]] = e
    log(f"  {len(out)} emails loaded")
    return out


def load_decisions() -> dict:
    log("loading pipeline decisions (the full trace, per email)...")
    out = {}
    paths = sorted(DECISIONS_DIR.glob("decision_EML-*.json"))
    if not paths:
        raise FileNotFoundError(f"no decisions found under {DECISIONS_DIR}")
    for path in paths:
        d = load_json(path)
        out[d["email_id"]] = d
    log(f"  {len(out)} decisions loaded")
    return out


def load_routing_summary() -> dict:
    log("loading routing_summary.csv (cross-check only)...")
    rows = load_csv_rows(ROUTING_SUMMARY_PATH)
    out = {row["email_id"]: row for row in rows}
    log(f"  {len(out)} routing-summary rows loaded")
    return out


def load_answer_key() -> dict:
    log("loading the answer key (shown only behind the page's toggle)...")
    rows = load_csv_rows(ANSWER_KEY_PATH)
    out = {row["email_id"]: row for row in rows}
    log(f"  {len(out)} answer-key rows loaded")
    return out


def compact_gate(gate: dict | None) -> dict | None:
    if gate is None:
        return None
    return {"passed": gate["passed"], "reasons": gate["reasons"]}


def compact_draft(draft: dict | None) -> dict | None:
    if draft is None:
        return None
    return {
        "reply_body": draft["reply_body"],
        "commitments": draft["commitments"],
        "customer_questions": draft["customer_questions"],
        "questions_addressed": draft["questions_addressed"],
        "prior_commitments_reviewed": draft["prior_commitments_reviewed"],
    }


def compact_key_row(row: dict) -> dict:
    clause_ids = [c.strip() for c in row["binding_clause_ids"].split(",") if c.strip()]
    return {
        "trap_type": row["trap_type"],
        "correct_route": row["correct_route"],
        "binding_clause_ids": clause_ids,
        "correct_commitments": row["correct_commitments"],
    }


def build_emails(briefs: dict, decisions: dict, routing: dict, key: dict) -> list:
    log("assembling the 150-email dataset...")
    email_ids = sorted(briefs.keys(), key=email_sort_key)
    out = []
    missing_decision, missing_routing, missing_key = [], [], []
    mismatches = []
    for eid in email_ids:
        brief = briefs[eid]
        decision = decisions.get(eid)
        routing_row = routing.get(eid)
        key_row = key.get(eid)
        if decision is None:
            missing_decision.append(eid)
            continue
        if routing_row is None:
            missing_routing.append(eid)
            continue
        if key_row is None:
            missing_key.append(eid)
            continue
        # Cross-check: the flat routing_summary.csv log must agree with the
        # richer per-email decision JSON on route and intent class -- any
        # disagreement means the two artefacts drifted after the run and is
        # a data bug, not a display choice.
        if routing_row["route"] != decision["route"] or routing_row["intent_class"] != decision["intent_class"]:
            mismatches.append(eid)
            continue
        out.append({
            "id": eid,
            "thread_id": brief["thread_id"],
            "customer_id": brief["customer_id"],
            "customer_name": brief["customer_name"],
            "position_in_thread": brief["position_in_thread"],
            "thread_customer_message_count": brief["thread_customer_message_count"],
            "date": brief["date"],
            "timestamp": brief["timestamp"],
            "subject": brief["subject"],
            "body": brief["body"],
            "intent_class": decision["intent_class"],
            "classification_rationale": decision["classification_rationale"],
            "draft": compact_draft(decision["draft"]),
            "gates": {
                "policy_gate": compact_gate(decision["gate_results"]["policy_gate"]) if decision["gate_results"] else None,
                "consistency_gate": compact_gate(decision["gate_results"]["consistency_gate"]) if decision["gate_results"] else None,
                "completeness_gate": compact_gate(decision["gate_results"]["completeness_gate"]) if decision["gate_results"] else None,
            },
            "route": decision["route"],
            "route_reason": decision["route_reason"],
            "key": compact_key_row(key_row),
        })
    if missing_decision or missing_routing or missing_key or mismatches:
        raise ValueError(
            f"data gaps -- missing decision: {missing_decision}, "
            f"missing routing row: {missing_routing}, missing key row: {missing_key}, "
            f"routing/decision mismatches: {mismatches}"
        )
    log(f"  {len(out)} emails assembled, no data gaps, routing_summary.csv matches decisions exactly")
    return out


# ---------------------------------------------------------------------------
# The river flow -- classify -> gates -> route, built by grouping
# routing_summary.csv's ACTUAL per-email intent class and route (never the
# key), then overlaying marks.json's own frozen misroute / false-block lists.
# ---------------------------------------------------------------------------

def build_river(routing: dict, marks: dict) -> dict:
    log("assembling the river-flow structure (classify -> gates -> route)...")

    auto_approved = config.AUTO_APPROVED_INTENT_CLASSES
    human_queue_classes = config.HUMAN_QUEUE_INTENT_CLASSES
    escalate_classes = config.ESCALATE_INTENT_CLASSES

    # Column 1: classify -- count of ACTUAL (as-run) intent class per email.
    classify_counts = {ic: 0 for ic in config.ALL_INTENT_CLASSES}
    for row in routing.values():
        classify_counts[row["intent_class"]] += 1

    # Column 2: gates -- only the auto-approved-classified group actually
    # branches on gate outcome; the other two groups pass straight through
    # by router rule, so they get a single pass-through node
    # each rather than a fabricated gate split.
    gates_passed = 0   # auto-approved class, route == auto_send
    gates_blocked = 0  # auto-approved class, route == human_queue (a false block)
    for row in routing.values():
        if row["intent_class"] in auto_approved:
            if row["route"] == "auto_send":
                gates_passed += 1
            elif row["route"] == "human_queue":
                gates_blocked += 1
            else:
                raise ValueError(
                    f"unexpected route {row['route']!r} for auto-approved-class email {row['email_id']}"
                )
    queued_direct = sum(classify_counts[ic] for ic in human_queue_classes)
    escalated_direct = sum(classify_counts[ic] for ic in escalate_classes)

    # Column 3: route -- the three terminal outcomes.
    n_auto_send = gates_passed
    n_human_queue = gates_blocked + queued_direct
    n_escalate = escalated_direct

    # Cross-check every total against marks.json's own frozen headline
    # numbers -- a mismatch here is a bug in this script's grouping logic,
    # not a judgment call.
    assert n_auto_send == marks["straight_through_rate"]["n_auto_sent"], (
        f"auto_send count {n_auto_send} != marks.json n_auto_sent "
        f"{marks['straight_through_rate']['n_auto_sent']}"
    )
    assert gates_blocked == len(marks["false_blocks"]), (
        f"gates_blocked count {gates_blocked} != marks.json false_blocks length {len(marks['false_blocks'])}"
    )
    assert n_escalate == marks["escalation_recall"]["n_escalated"], (
        f"escalate count {n_escalate} != marks.json n_escalated {marks['escalation_recall']['n_escalated']}"
    )
    n_total = n_auto_send + n_human_queue + n_escalate
    assert n_total == 150, f"river total {n_total} != 150"

    nodes_classify = [
        {"id": f"classify_{ic}", "label": INTENT_CLASS_LABELS[ic], "count": classify_counts[ic],
         "bucket": ("auto_send" if ic in auto_approved else "human_queue" if ic in human_queue_classes else "escalate")}
        for ic in config.ALL_INTENT_CLASSES if classify_counts[ic] > 0
    ]
    nodes_gates = [
        {"id": "gates_passed", "label": "Gates passed", "count": gates_passed, "bucket": "auto_send"},
        {"id": "gates_blocked", "label": "Gates blocked (false block)", "count": gates_blocked, "bucket": "human_queue"},
        {"id": "queued_direct", "label": "Always queued (commercial / prior-promise / needs-info)", "count": queued_direct, "bucket": "human_queue"},
        {"id": "escalated_direct", "label": "Escalated on classification (safety / data)", "count": escalated_direct, "bucket": "escalate"},
    ]
    nodes_route = [
        {"id": "auto_send", "label": ROUTE_LABELS["auto_send"], "count": n_auto_send, "bucket": "auto_send"},
        {"id": "human_queue", "label": ROUTE_LABELS["human_queue"], "count": n_human_queue, "bucket": "human_queue"},
        {"id": "escalate", "label": ROUTE_LABELS["escalate"], "count": n_escalate, "bucket": "escalate"},
    ]

    links_classify_to_gates = []
    for ic in config.ALL_INTENT_CLASSES:
        count = classify_counts[ic]
        if count == 0:
            continue
        if ic in auto_approved:
            # split this class's own count across gates_passed / gates_blocked
            passed = sum(1 for row in routing.values() if row["intent_class"] == ic and row["route"] == "auto_send")
            blocked = sum(1 for row in routing.values() if row["intent_class"] == ic and row["route"] == "human_queue")
            if passed:
                links_classify_to_gates.append({"from": f"classify_{ic}", "to": "gates_passed", "count": passed})
            if blocked:
                links_classify_to_gates.append({"from": f"classify_{ic}", "to": "gates_blocked", "count": blocked})
        elif ic in human_queue_classes:
            links_classify_to_gates.append({"from": f"classify_{ic}", "to": "queued_direct", "count": count})
        else:
            links_classify_to_gates.append({"from": f"classify_{ic}", "to": "escalated_direct", "count": count})

    links_gates_to_route = [
        {"from": "gates_passed", "to": "auto_send", "count": gates_passed},
        {"from": "gates_blocked", "to": "human_queue", "count": gates_blocked},
        {"from": "queued_direct", "to": "human_queue", "count": queued_direct},
        {"from": "escalated_direct", "to": "escalate", "count": escalated_direct},
    ]
    links_gates_to_route = [link for link in links_gates_to_route if link["count"] > 0]

    misroutes = [
        {
            "email_id": m["email_id"],
            "thread_id": m["thread_id"],
            "key_route": m["key_route"],
            "actual_route": m["actual_route"],
            "direction": m["direction"],
            "route_reason": m["route_reason"],
            "trap_type": m["trap_type"],
        }
        for m in marks["route_confusion"]["misroutes"]
    ]
    false_block_ids = [fb["email_id"] for fb in marks["false_blocks"]]

    log(f"  river assembled: auto_send {n_auto_send}, human_queue {n_human_queue}, escalate {n_escalate}; "
        f"{len(misroutes)} misroutes, {len(false_block_ids)} false blocks")

    return {
        "n_total": n_total,
        "columns": [
            {"key": "classify", "label": "Classified", "nodes": nodes_classify},
            {"key": "gates", "label": "Gates", "nodes": nodes_gates},
            {"key": "route", "label": "Route", "nodes": nodes_route},
        ],
        "links": links_classify_to_gates + links_gates_to_route,
        "misroutes": misroutes,
        "false_block_ids": false_block_ids,
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        clauses, handbook = load_clauses()
        threads = load_threads()
        briefs = load_email_briefs()
        decisions = load_decisions()
        routing = load_routing_summary()
        key = load_answer_key()
        marks = load_json(MARKS_PATH)

        emails = build_emails(briefs, decisions, routing, key)
        river = build_river(routing, marks)

        # Sanity: every email's thread_id must resolve to a loaded thread.
        missing_threads = sorted({e["thread_id"] for e in emails} - set(threads.keys()))
        if missing_threads:
            raise ValueError(f"emails reference threads that were not loaded: {missing_threads}")

        trap_labels = {
            trap_id: {"label": spec["label"], "correct_behaviour": spec["correct_behaviour"], "count": spec["count"]}
            for trap_id, spec in config.TRAP_TYPES.items()
        }
        trap_labels["none"] = {"label": "No trap (plain routine traffic)", "correct_behaviour": "Answer straight through.", "count": config.ROUTINE_EMAIL_COUNT - config.PROMISE_SETUP_COUNT}

        data = {
            "meta": {
                "project": "08 Inbox",
                "company": config.COMPANY,
                "window": {"start": config.WINDOW_START, "end": config.WINDOW_END},
                "seed": config.RANDOM_SEED,
                "n_emails": len(emails),
                "n_threads": len(threads),
                "intent_class_labels": INTENT_CLASS_LABELS,
                "route_labels": ROUTE_LABELS,
                "gate_labels": GATE_LABELS,
                "trap_labels": trap_labels,
                "auto_approved_intent_classes": sorted(config.AUTO_APPROVED_INTENT_CLASSES),
                "human_queue_intent_classes": sorted(config.HUMAN_QUEUE_INTENT_CLASSES),
                "escalate_intent_classes": sorted(config.ESCALATE_INTENT_CLASSES),
                "discount_authority_limits": handbook["discount_authority_limits"],
                "escalation_contacts": handbook["escalation_contacts"],
                "clauses": clauses,
            },
            "emails": emails,
            "threads": threads,
            "marks": marks,
            "river": river,
        }

        log(f"writing {OUT_JSON} ...")
        OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        size_mb = OUT_JSON.stat().st_size / (1024 * 1024)
        log(f"  wrote {size_mb:.2f} MB")

        log("inlining data into template...")
        if not TEMPLATE_PATH.exists():
            raise FileNotFoundError(f"required template missing: {TEMPLATE_PATH}")
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        data_json_text = OUT_JSON.read_text(encoding="utf-8")

        if "/*__HPX_DATA_JSON__*/" not in template:
            raise ValueError("_template.html is missing the /*__HPX_DATA_JSON__*/ placeholder")

        if "</script" in data_json_text.lower():
            data_json_text = data_json_text.replace("</script", "<\\/script")

        html = template.replace("/*__HPX_DATA_JSON__*/", data_json_text)

        # Safety: output path must never equal an input path (project rule).
        if OUT_HTML.resolve() == TEMPLATE_PATH.resolve():
            raise RuntimeError("refusing to write: output path equals template path")
        for input_path in (EMAILS_DIR, THREADS_DIR, DECISIONS_DIR, ROUTING_SUMMARY_PATH,
                           MARKS_PATH, ANSWER_KEY_PATH, HANDBOOK_PATH):
            if OUT_HTML.resolve() == input_path.resolve():
                raise RuntimeError(f"refusing to write: output path equals input path {input_path}")

        OUT_HTML.write_text(html, encoding="utf-8")
        out_mb = OUT_HTML.stat().st_size / (1024 * 1024)
        log(f"wrote {OUT_HTML} ({out_mb:.2f} MB)")
        if out_mb > 4.0:
            log(f"WARNING: page is {out_mb:.2f} MB, over the 4 MB budget")
        return 0
    except Exception as exc:  # noqa: BLE001 -- build script must report, never crash bare
        print(f"[build_data] FATAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
