/* quickplay_score.src.js -- the "Play a Tender Yourself" marking core.
 *
 * This is the ONE source of truth for how the game scores a visitor's play.
 * It is inlined verbatim into tender-workflow.html by build_data.py (between
 * markers, see that script), and it is ALSO loaded directly, unmodified, by
 * code/verify_interactive_07.py, which runs it under Node against the real
 * per-requirement "addressed" flags and bid decisions that code/mark.py
 * already computed for the twelve real Arm A attempts on T04/T08/T11 -- the
 * spot-check the page requires ("a JS port of mark.py's coverage
 * scoring, spot-checked against it"). Editing the scoring logic in the built
 * HTML without editing this file (or vice versa) will make that check fail
 * on the next QA run, by design.
 *
 * WHY THIS IS A PORT, NOT A CLONE, OF mark.py: the game's interaction is
 * clause-ticking (does the visitor recognise a numbered clause as a live
 * requirement?) plus one bid/no-bid call, not a drafted document -- mark.py
 * scores free text. Three things port EXACTLY, because they do not depend on
 * drafted prose in mark.py's own logic either:
 *
 *   1. Coverage % -- mark.py: matched_requirements / total_requirements.
 *      Here: matched = number of the tender's key requirements whose own
 *      clause was ticked, over the same total. Identical arithmetic given
 *      identical "addressed" inputs -- verified by the QA spot-check below.
 *   2. The eligibility_fail trap (T11-R005) -- mark.py's assess_traps()
 *      defines "caught" as bid_decision == "no-bid" OR explicit conflict-
 *      language in the drafted text; ticking the clause plays no part in
 *      mark.py's own catch condition either. Here: caught = the visitor's
 *      call is "no-bid". Exact port.
 *   3. The contradiction trap (T08-R014 / T08-R029) -- mark.py's caught
 *      requires BOTH paired requirements addressed AND explicit conflict-
 *      flagging language found in the draft. The game cannot produce
 *      drafted prose, so it asks the visitor directly, once both members of
 *      the pair are ticked: "flag the conflict?" caught = both ticked AND
 *      the visitor flagged it. Exact port of the same two-part condition,
 *      with the flag question standing in for conflict language mark.py
 *      would otherwise search for.
 *
 * The format_trap (T04-R013) is scored as caught = ticked. In mark.py this
 * trap's own check (check_format_trap) is a compliance check on the drafted
 * text, not a bare "addressed" flag -- but for this specific trap "addressed"
 * and "compliant" have been the same value on every one of the four real T04
 * Arm A attempts (see the QA script's fixture), because the requirement IS
 * "state the 11pt minimum", so noticing it and stating it are the same
 * chatbot output. That equivalence is empirical, reported as such, and
 * spot-checked below -- not assumed.
 */
(function (root) {
  "use strict";

  // Python's round(x, 2) rounds half-to-even on the true binary value of x
  // (not the naive decimal string) -- e.g. round(65.625, 2) == 65.62, not
  // 65.63. JS's Math.round always rounds halves up, which silently disagreed
  // with mark.py's own `round(100.0 * n_addressed / len(matchers), 2)` on
  // exact-eighths coverage fractions (found by this file's own QA spot-check
  // against real Arm A attempts on T08). This replicates Python's rule so
  // the two languages agree bit-for-bit wherever the underlying arithmetic
  // (both are IEEE754 doubles) is identical.
  function pyRound2(x) {
    var scaled = x * 100;
    var floor = Math.floor(scaled);
    var diff = scaled - floor;
    var rounded;
    if (Math.abs(diff - 0.5) < 1e-9) {
      rounded = (floor % 2 === 0) ? floor : floor + 1;
    } else if (diff > 0.5) {
      rounded = floor + 1;
    } else {
      rounded = floor;
    }
    return rounded / 100;
  }

  function hpxScoreQuickplay(input) {
    // input: {
    //   keyReqIds: [string],        -- every requirement id in this tender's key
    //   tickedReqIds: [string],     -- requirement ids whose clause the visitor ticked
    //   bidCall: "bid" | "no-bid",  -- the visitor's final call
    //   flagConflict: boolean,      -- only asked/used when a contradiction trap exists
    //   trapMeta: {
    //     format_trap: {req_id} | null,
    //     contradiction: {req_ids: [a, b]} | null,
    //     eligibility_fail: {req_id} | null
    //   }
    // }
    var ticked = {};
    (input.tickedReqIds || []).forEach(function (r) { ticked[r] = true; });

    var total = input.keyReqIds.length;
    var matched = 0;
    input.keyReqIds.forEach(function (r) { if (ticked[r]) matched += 1; });
    // Same order of operations as mark.py's own
    // `round(100.0 * n_addressed / len(matchers), 2)` -- multiply before
    // dividing -- so the pre-rounding double is bit-identical.
    var coveragePct = total > 0 ? pyRound2((100.0 * matched) / total) : 0;

    var traps = [];
    var meta = input.trapMeta || {};

    if (meta.format_trap) {
      var ftCaught = !!ticked[meta.format_trap.req_id];
      traps.push({
        trap_code: "format_trap",
        req_ids: [meta.format_trap.req_id],
        caught: ftCaught
      });
    }

    if (meta.contradiction) {
      var ids = meta.contradiction.req_ids;
      var bothTicked = ids.every(function (r) { return !!ticked[r]; });
      var caught = bothTicked && !!input.flagConflict;
      traps.push({
        trap_code: "contradiction",
        req_ids: ids,
        both_ticked: bothTicked,
        caught: caught
      });
    }

    if (meta.eligibility_fail) {
      var elCaught = input.bidCall === "no-bid";
      traps.push({
        trap_code: "eligibility_fail",
        req_ids: [meta.eligibility_fail.req_id],
        caught: elCaught
      });
    }

    return {
      matched: matched,
      total: total,
      coverage_pct: coveragePct,
      traps: traps
    };
  }

  var api = { hpxScoreQuickplay: hpxScoreQuickplay };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.hpxScoreQuickplay = hpxScoreQuickplay;
})(typeof window !== "undefined" ? window : globalThis);
