"""Phase 2 corpus-normalisation tool for Project 7 (Tenders) -- Job 2 of the
pre-arm integrity pass ("id-strip normalisation").

Two things happen here, in one pass so the clause map is always built from
the same information that produced (or already exists in) the document text:

  (a) STRIP PRINTED REQ_IDS. Four gnarly tenders (T13-T16) leaked their
      internal req_ids into the document text as visible "**Txx-Rnnn**"
      tags -- unrealistic, and it trivialises Arm B's extraction step (the
      thing Project 7 is supposed to be measuring). T01-T12 already use
      realistic clause numbering (confirmed by grep before this script was
      written: only T13-T16 matched \\bT\\d\\d-R\\d\\d\\d\\b). This script
      replaces every printed tag in T13-T16 with a realistic clause number,
      mirroring the convention already established across the rest of the
      corpus (T05-T12 in particular):
        - Body requirements number "N.M", where N is the body section's own
          "## N. Title" heading number and M runs 1, 2, 3... in document
          order within that section.
        - Annex requirements number "Letter.M" (flat, e.g. "A.1", "B.2")
          UNLESS the annex has its own numbered "### N. Title" subsections,
          in which case items number "N.M" per subsection (dropping the
          annex letter entirely) -- exactly how T05/T06/T08 already do it.
        - Where a subsection already carries a pre-existing nested bold
          title announcing its own number (T13's Liite A section 3 has
          "**3.1 Preventive maintenance plan**" / "**3.2 Response time...**"
          immediately before their requirement paragraphs), the redundant
          req_id tag on the paragraph below is simply removed rather than
          re-numbered -- the number is already visible on the title line.
      This is a numbering-LABEL transform only: requirement TEXT and ORDER
      are never touched. The one exception is that
      T13-R047's prose contains a stale self-reference
      ("see Section 3.2 of this annex") left over from a shared config.py
      trap-text template, corrected in a follow-up pass (see
      fix_annex_disqualifier_self_reference.py) once its real clause label
      was known -- that is a genuine document-defect fix (Job 3), not part
      of this label transform.

  (b) EMIT data/tenders/clause_map_NN.json for ALL 16 tenders: document
      clause label <-> req_id <-> location. For T13-T16 the map comes
      directly from the tags found during the strip. For T01-T12 (already
      realistic, no tags to read) the map is recovered by parsing the
      existing clause-number labels in document order and zipping them,
      1:1, against the answer key's own req_number order -- which is safe
      because the Phase 2/3 generation rules forbid the prose agent from reordering
      or relocating requirements (see brief_NN.json's
      prose_agent_constraints). Every row flagged mentioned_once (the
      hidden-form traps) is deliberately excluded from this zip: those are
      the ONE trap type designed to be buried and unlabelled in the
      document text, in every tender that carries one (T03, T09, T14) --
      never fewer than that.

These clause maps are GROUND-TRUTH-SIDE TOOLING for the future marking
script. NO ARM MAY EVER READ THEM -- not Arm A personas, not Arm B's
pipeline. They exist only for `code/mark.py` (Phase 5), the sole other
reader of the answer key.

ONE-OFF MIGRATION TOOL, not part of the regular pipeline order, and NOT
idempotent: it strips req_id tags out of T13-T16, so a second run against
an already-migrated corpus finds no tags left to strip and FAILS LOUDLY
(the "missing requirement(s) ... not found as a printed tag" check in
strip_and_map) rather than silently reprocessing. Re-run only after
restoring tender_13.md-tender_16.md from a pre-migration backup -- the
same one-off-tool convention the churn project's repair scripts
(fix_ticket_dates.py etc.) already use.

Run: python build_clause_maps.py
Then: python validate_structure.py   (still must pass -- this script does
      not touch the answer key, only tender documents and a new sidecar
      clause-map file per tender)
      python validate_corpus.py      (Job 3 -- checks the result)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

import config

STRIP_TARGETS = ["T13", "T14", "T15", "T16"]

TAG_RE = re.compile(r"^\*\*(T\d\d-R\d\d\d)\*\*(.*)$")
BODY_HEADER_RE = re.compile(r"^##\s+(\d+)\.\s")
ANNEX_HEADER_RE = re.compile(r"^#{1,2}\s*(?:Liite|Annex)\s+([A-Z])\b")
SUBSECTION_RE = re.compile(r"^###\s+(\d+)\.\s")
NESTED_TITLE_RE = re.compile(r"^\*\*(\d+\.\d+)\s+.+\*\*$")
EXISTING_LABEL_RE = re.compile(r"^(\d+\.\d+|[A-Z]\.\d+)\s+(.*)$")


def log(message: str) -> None:
    print(f"[build_clause_maps] {message}", flush=True)


def fail(message: str) -> None:
    raise ValueError(message)


def load_requirements(tender_id: str) -> pd.DataFrame:
    path = config.ANSWER_KEY_DIR / f"requirements_{tender_id[1:]}.csv"
    df = pd.read_csv(path, keep_default_na=False)
    df["mentioned_once_bool"] = (
        df["mentioned_once"].astype(str).str.strip().str.lower() == "true")
    return df


# ---------------------------------------------------------------------------
# T13-T16: strip printed tags, building the map from the tags themselves.
# ---------------------------------------------------------------------------

def strip_and_map(tender_id: str, lines: list[str], requirements: pd.DataFrame
                   ) -> tuple[list[str], list[dict]]:
    out_lines: list[str] = []
    entries: list[dict] = []
    context_mode: str | None = None
    body_section: str | None = None
    annex_letter: str | None = None
    subsection: str | None = None
    counters: dict[str, int] = {}
    prev_nonblank = ""

    for line in lines:
        m_body = BODY_HEADER_RE.match(line)
        m_annex = ANNEX_HEADER_RE.match(line)
        m_sub = SUBSECTION_RE.match(line)
        if m_body:
            context_mode, body_section, subsection = "body", m_body.group(1), None
        elif m_annex:
            context_mode, annex_letter, subsection = "annex", m_annex.group(1), None
        elif m_sub and context_mode == "annex":
            subsection = m_sub.group(1)

        m_tag = TAG_RE.match(line)
        if m_tag:
            req_id, rest = m_tag.group(1), m_tag.group(2)
            if context_mode == "body":
                key = f"body-{body_section}"
                counters[key] = counters.get(key, 0) + 1
                label = f"{body_section}.{counters[key]}"
                new_line = f"{label}{rest}"
                location_note = f"body section {body_section}"
            elif context_mode == "annex" and subsection is not None:
                key = f"sub-{annex_letter}-{subsection}"
                next_n = counters.get(key, 0) + 1
                expected = f"{subsection}.{next_n}"
                nested_match = NESTED_TITLE_RE.match(prev_nonblank)
                if nested_match and nested_match.group(1) == expected:
                    # A preceding bold mini-title already announces this
                    # exact number -- drop the redundant tag rather than
                    # print the number twice.
                    counters[key] = next_n
                    label = expected
                    new_line = rest.lstrip()
                else:
                    counters[key] = next_n
                    label = expected
                    new_line = f"{label}{rest}"
                location_note = f"Liite {annex_letter}, subsection {subsection}"
            elif context_mode == "annex":
                key = f"flat-{annex_letter}"
                counters[key] = counters.get(key, 0) + 1
                label = f"{annex_letter}.{counters[key]}"
                new_line = f"{label}{rest}"
                location_note = f"Liite {annex_letter}"
            else:
                fail(f"{tender_id}: tag {req_id} found before any recognised "
                     f"section/annex header")
            entries.append({"req_id": req_id, "clause_label": label,
                             "doc_location": location_note})
            out_lines.append(new_line)
        else:
            out_lines.append(line)

        if line.strip():
            prev_nonblank = line

    # --- coherence checks on the result -----------------------------------
    mentioned_once_ids = set(requirements.loc[requirements["mentioned_once_bool"], "req_id"])
    tagged_ids = {e["req_id"] for e in entries}
    if mentioned_once_ids & tagged_ids:
        fail(f"{tender_id}: mentioned_once requirement(s) "
             f"{sorted(mentioned_once_ids & tagged_ids)} were printed with a "
             f"visible tag -- expected them buried/untagged by design")

    all_ids = set(requirements["req_id"])
    missing = all_ids - tagged_ids - mentioned_once_ids
    if missing:
        fail(f"{tender_id}: requirement(s) {sorted(missing)} in the answer "
             f"key were not found as a printed tag in the document and are "
             f"not flagged mentioned_once -- cannot place them in the "
             f"clause map")
    extra = tagged_ids - all_ids
    if extra:
        fail(f"{tender_id}: found tag(s) {sorted(extra)} in the document "
             f"that do not exist in the answer key")
    if len(tagged_ids) != len(entries):
        fail(f"{tender_id}: duplicate req_id tag found in the document")

    # Add the buried/untagged rows to the map explicitly, with no label.
    for req_id in mentioned_once_ids:
        row = requirements.loc[requirements["req_id"] == req_id].iloc[0]
        entries.append({"req_id": req_id, "clause_label": None,
                         "doc_location": f"{row['location']} (buried, "
                         f"deliberately untagged -- hidden_form trap)"})

    return out_lines, entries


# ---------------------------------------------------------------------------
# T01-T12: already realistic -- recover the map by parsing existing labels.
# ---------------------------------------------------------------------------

def extract_existing_map(tender_id: str, lines: list[str],
                          requirements: pd.DataFrame) -> list[dict]:
    labels_in_order: list[tuple[str, str]] = []  # (label, location_note)
    context_mode: str | None = None
    body_section: str | None = None
    annex_letter: str | None = None
    subsection: str | None = None

    for line in lines:
        m_body = BODY_HEADER_RE.match(line)
        m_annex = ANNEX_HEADER_RE.match(line)
        m_sub = SUBSECTION_RE.match(line)
        if m_body:
            context_mode, body_section, subsection = "body", m_body.group(1), None
            continue
        if m_annex:
            context_mode, annex_letter, subsection = "annex", m_annex.group(1), None
            continue
        if m_sub and context_mode == "annex":
            subsection = m_sub.group(1)
            continue
        m_label = EXISTING_LABEL_RE.match(line)
        if m_label:
            label = m_label.group(1)
            if context_mode == "body":
                loc = f"body section {body_section}"
            elif context_mode == "annex" and subsection is not None:
                loc = f"Liite {annex_letter}, subsection {subsection}"
            elif context_mode == "annex":
                loc = f"Liite {annex_letter}"
            else:
                loc = "unknown"
            labels_in_order.append((label, loc))

    reqs_sorted = requirements.sort_values("req_number")
    visible = reqs_sorted[~reqs_sorted["mentioned_once_bool"]]
    buried = reqs_sorted[reqs_sorted["mentioned_once_bool"]]

    if len(labels_in_order) != len(visible):
        fail(f"{tender_id}: found {len(labels_in_order)} existing clause "
             f"labels in the document but {len(visible)} non-buried "
             f"requirements in the answer key -- counts must match to "
             f"safely zip labels to req_ids (got labels: {labels_in_order})")

    entries = []
    for (label, loc), (_, row) in zip(labels_in_order, visible.iterrows()):
        entries.append({"req_id": row["req_id"], "clause_label": label,
                         "doc_location": loc})
    for _, row in buried.iterrows():
        entries.append({"req_id": row["req_id"], "clause_label": None,
                         "doc_location": f"{row['location']} (buried, "
                         f"deliberately untagged -- hidden_form trap)"})
    return entries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_clause_map(tender_id: str, entries: list[dict]) -> None:
    requirements = load_requirements(tender_id)
    by_id = {row["req_id"]: row for _, row in requirements.iterrows()}
    order = {rid: i for i, rid in enumerate(requirements.sort_values("req_number")["req_id"])}
    entries_sorted = sorted(entries, key=lambda e: order[e["req_id"]])

    clauses = []
    for e in entries_sorted:
        row = by_id[e["req_id"]]
        clauses.append({
            "req_id": e["req_id"],
            "clause_label": e["clause_label"],
            "doc_location": e["doc_location"],
            "type": row["type"],
            "answer_key_location": row["location"],
            "trap_code": row["trap_code"] or None,
        })

    payload = {
        "_meta": {
            "notice": ("GROUND-TRUTH-SIDE TOOLING for the future marking "
                       "script (Phase 5, code/mark.py). NO ARM MAY READ "
                       "THIS FILE -- not Arm A personas, not Arm B's "
                       "pipeline."),
            "tender_id": tender_id,
            "n_clauses": len(clauses),
        },
        "clauses": clauses,
    }
    path = config.DATA_DIR / "tenders" / f"clause_map_{tender_id[1:]}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def main() -> None:
    tenders_dir = config.DATA_DIR / "tenders"
    strip_counts: dict[str, int] = {}

    for tender in config.TENDERS:
        tid = tender["id"]
        path = tenders_dir / f"tender_{tid[1:]}.md"
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        requirements = load_requirements(tid)

        if tid in STRIP_TARGETS:
            new_lines, entries = strip_and_map(tid, lines, requirements)
            new_text = "\n".join(new_lines)
            path.write_text(new_text, encoding="utf-8")
            n_stripped = sum(1 for e in entries if e["clause_label"] is not None
                              and e not in ())  # tags actually replaced
            n_stripped = len([e for e in entries if e["doc_location"] and
                               "buried" not in e["doc_location"]])
            strip_counts[tid] = n_stripped
            log(f"{tid}: stripped {n_stripped} printed req_id tags, "
                f"replaced with realistic clause numbers")
        else:
            entries = extract_existing_map(tid, lines, requirements)
            log(f"{tid}: already realistic -- recovered {len(entries)} "
                f"clause labels from existing document numbering")

        write_clause_map(tid, entries)

    log("--- id-strip counts (T13-T16) ---")
    for tid, n in strip_counts.items():
        log(f"  {tid}: {n} tags stripped")
    log(f"clause_map_NN.json written for all {len(config.TENDERS)} tenders")
    log("done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # graceful, informative failure
        print(f"[build_clause_maps] FAILED: {exc}", file=sys.stderr)
        raise
