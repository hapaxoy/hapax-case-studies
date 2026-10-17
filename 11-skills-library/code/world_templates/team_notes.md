# Team notes (pinned)

From Outi Kallio, head of data. Read before you pick up a request.

<!-- facts: TEAM-ASIS -->
Report history as-is (current regions and categories restated back) unless the requester asks for as-was. Say which one you used.

<!-- facts: TEAM-EXPLICIT-REQUEST -->
When a request explicitly asks for something that differs from a company default (gross instead of net, as-was instead of as-is, UTC instead of Helsinki time, and so on), follow the request and say that you did.

<!-- facts: TEAM-NO-LEGACY-VIEW -->
Do not use rpt.v_daily_sales. It loses web sales after the migration.

<!-- facts: TEAM-EXCLUSIONS -->
Always filter out store {{training_store_id}} and category {{test_category}} in sales work, and say so when the filter changes a total.

<!-- facts: TEAM-CONTROL-TOTALS -->
Before sending a store-level figure, check the total against rpt_daily_store_sales for the same days.

<!-- facts: TEAM-LFL-EDGE -->
LFL edge cases. A store back from a refit is excluded for the refit weeks only. The two new stores enter the LFL base on {{lfl_ready_136}} (136) and {{lfl_ready_137}} (137). The closed store ({{closed_store_id}}) drops out from its closure. Week 53 is never LFL. The web shop is never LFL.
