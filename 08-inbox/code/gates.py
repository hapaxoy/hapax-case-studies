"""
08 Inbox — Phase 4 deterministic gates + router (pipeline steps 4-5).

This module is the pipeline's entire judgment-free core: three gates and a
router, every one a pure function over structured data. No function here
makes a model call, reads a file, or uses randomness — they operate only on
the draft's own structured JSON output (whatever the future draft-writing
model emits, following the contract in `build_draft_tasks.py`) plus facts
already retrieved deterministically by `retrieval.py`. This is what "gates
(deterministic)" means in the design: the semantic work of reading English
happened one step earlier, in the model's draft; the gate only checks that
the draft's own structured self-report is internally consistent with the
in-world artefacts (the design: "Gates check internal consistency against
in-world artefacts only") — never against the answer key, which this module
never imports or reads.

Because every function is pure, this module is unit-tested against
hand-built fixtures kept in a temporary working folder, never against pytest
files committed under code/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import config


@dataclass
class GateResult:
    """The verdict of one gate: whether it passed, and — if not — every
    reason it failed (a gate never stops at the first problem; it reports
    everything wrong, mirroring the validators in every case)."""

    passed: bool = True
    reasons: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.passed = False
        self.reasons.append(reason)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "reasons": list(self.reasons)}


# ---------------------------------------------------------------------------
# Gate 1: policy gate — "citations exist, are real, within authority".
# ---------------------------------------------------------------------------

def run_policy_gate(draft: dict, handbook_clause_ids: set[str]) -> GateResult:
    result = GateResult()
    for i, commitment in enumerate(draft.get("commitments", [])):
        commitment_type = commitment.get("type")
        clause_id = commitment.get("clause_id")
        description = commitment.get("description", "<no description given>")

        if commitment_type in config.COMMITMENT_TYPES_REQUIRING_CITATION:
            if not clause_id:
                result.fail(
                    f"commitment {i} ('{description}') is a {commitment_type} "
                    "with no policy-clause citation"
                )
            elif clause_id not in handbook_clause_ids:
                result.fail(
                    f"commitment {i} ('{description}') cites clause "
                    f"{clause_id!r}, which does not exist in the policy "
                    "handbook"
                )

        if commitment_type == "waiver_or_discount":
            discount_pct = commitment.get("discount_pct")
            if discount_pct is not None and discount_pct > config.MAX_DISCOUNT_AUTHORITY:
                result.fail(
                    f"commitment {i} ('{description}') grants a "
                    f"{discount_pct:.0%} discount, exceeding the highest "
                    f"authority level held anywhere in the company "
                    f"({config.MAX_DISCOUNT_AUTHORITY:.0%})"
                )
    return result


# ---------------------------------------------------------------------------
# Gate 2: consistency gate — "no contradiction with any prior promise in
# the thread".
# ---------------------------------------------------------------------------

def run_consistency_gate(draft: dict, prior_staff_message_count: int) -> GateResult:
    result = GateResult()
    reviewed = draft.get("prior_commitments_reviewed", [])

    if len(reviewed) != prior_staff_message_count:
        result.fail(
            f"draft reviewed {len(reviewed)} prior staff message(s) but "
            f"the retrieved thread history contains {prior_staff_message_count}"
        )

    for entry in reviewed:
        treatment = entry.get("treatment")
        if treatment == "contradicted":
            staff_name = entry.get("staff_name", "<unknown staff member>")
            summary = entry.get("commitment_summary", "<no summary given>")
            result.fail(
                f"draft contradicts a prior commitment from {staff_name}: "
                f"{summary}"
            )
        elif treatment not in config.PRIOR_COMMITMENT_TREATMENTS:
            result.fail(
                f"prior-commitment review for staff message index "
                f"{entry.get('source_message_index')} uses an unrecognised "
                f"treatment {treatment!r}"
            )
    return result


# ---------------------------------------------------------------------------
# Gate 3: completeness gate — "every question in the email addressed".
# ---------------------------------------------------------------------------

def run_completeness_gate(draft: dict) -> GateResult:
    result = GateResult()
    customer_questions = draft.get("customer_questions", [])
    addressed = draft.get("questions_addressed", [])

    if len(addressed) != len(customer_questions):
        result.fail(
            f"identified {len(customer_questions)} customer question(s) "
            f"but addressed {len(addressed)}"
        )

    for i, qa in enumerate(addressed):
        question = qa.get("question", "<unknown question>")
        if qa.get("answered") is not True:
            result.fail(f"question {i} ('{question}') was not answered")
        elif not (qa.get("answer_summary") or "").strip():
            result.fail(
                f"question {i} ('{question}') is marked answered but has "
                "no answer summary"
            )
    return result


def run_all_gates(
    draft: dict,
    handbook_clause_ids: set[str],
    prior_staff_message_count: int,
) -> dict[str, GateResult]:
    """Run all three gates and return every verdict — a route decision
    never short-circuits on the first gate failure, since the marking pass
    needs to know about every gate that fired, not just the
    first one."""
    return {
        "policy_gate": run_policy_gate(draft, handbook_clause_ids),
        "consistency_gate": run_consistency_gate(draft, prior_staff_message_count),
        "completeness_gate": run_completeness_gate(draft),
    }


# ---------------------------------------------------------------------------
# Router (pipeline step 5) — "rules fixed here, never tuned".
# ---------------------------------------------------------------------------

def route_email(
    intent_class: str,
    gate_results: dict[str, GateResult] | None,
) -> tuple[str, str]:
    """The router rule, applied deterministically:

    - ESCALATE for the safety and data classes on classification alone —
      those classes never receive a drafted reply at all, so
      `gate_results` must be None for them.
    - AUTO-SEND only when the intent class is in the pre-declared
      auto-approved set AND every gate passed.
    - HUMAN QUEUE for commercial judgment / prior-promise / needs-info
      intent classes regardless of gate outcome, and for any auto-approved
      draft that a gate blocked.

    Returns (route, reason) — the reason is written straight into the
    per-email decision record (the per-email trace).
    """
    if intent_class in config.ESCALATE_INTENT_CLASSES:
        if gate_results is not None:
            raise ValueError(
                f"intent class {intent_class!r} is escalate-on-"
                "classification and must never have gate results attached "
                "(the design: no drafted reply at all)"
            )
        return (
            "escalate",
            "classified into an escalate-on-classification intent class "
            "(safety or personal-data matter); no draft was attempted",
        )

    if gate_results is None:
        raise ValueError(
            f"gate_results is required to route a non-escalate intent "
            f"class ({intent_class!r})"
        )

    all_passed = all(gate.passed for gate in gate_results.values())
    failed_gate_names = [name for name, gate in gate_results.items() if not gate.passed]

    if intent_class in config.AUTO_APPROVED_INTENT_CLASSES:
        if all_passed:
            return "auto_send", "auto-approved intent class and every gate passed"
        return (
            "human_queue",
            "auto-approved intent class, but blocked by: "
            + ", ".join(failed_gate_names),
        )

    if intent_class in config.HUMAN_QUEUE_INTENT_CLASSES:
        reason = (
            "commercial-judgment, prior-promise, or needs-info intent "
            "class — always queued for a human regardless of gate outcome"
        )
        if not all_passed:
            reason += " (also blocked by: " + ", ".join(failed_gate_names) + ")"
        return "human_queue", reason

    raise ValueError(f"unknown intent class: {intent_class!r}")
