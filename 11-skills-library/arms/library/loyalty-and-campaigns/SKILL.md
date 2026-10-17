---
name: loyalty-and-campaigns
description: Loyalty members and marketing campaigns - active members over the trailing 52 fiscal weeks, member share of sales, new members by enrolling store, campaign uplift against the holdout - with member versions, guest orders and the one-row-per-contact exposure table handled.
---

# Loyalty and campaigns

## Steps

1. Fix the as-of week or the period with `fiscal-calendar/scripts/fiscal.py`.
2. Start from a template; edit `params`.
3. Check with `query-check/scripts/query_check.py`, declaring the member grain (e.g. `--grain member_id` on a member list) to catch version or exposure fan-out.

| Template | Gives | Reproduces |
|---|---|---|
| `templates/active_members.sql` | active members as of a week, by tier and total | REQ-D29 (total), REQ-D30 (by tier) |
| `templates/member_share_of_sales.sql` | member share of net sales before returns, by region as-is | REQ-D32 |
| `templates/new_members.sql` | new members by period and enrolling store | - |
| `templates/campaign_uplift.sql` | targeted and holdout means, uplift, and an overlap check; `{{campaign_id}}` is required (no default): look the campaign up in dim_campaign by the request's name or dates | - |

## Members

<!-- facts: REG-MEMBER-VERSIONS -->
dim_member gets a new version when a member's tier, home store or marketing consent changes. Count members by distinct member_id. The member_key on a line is the version at that date.

<!-- facts: DEF-ACTIVE-MEMBER -->
An active member has made at least one purchase in the trailing 52 fiscal weeks, ending with the as-of week and including it, in any channel. Count distinct member_id. The accepted queries (REQ-D29, REQ-D30) take sale_date > as-of Sunday - 364 and <= as-of Sunday, and read the tier from the member version valid on the as-of Sunday.

<!-- source: REQ-D29, REQ-D30 -->
"End of last year" asked on 6 May 2025 was Sunday 27 April 2025 (REQ-D29); "the last Sunday of September" in October 2025 was 28 September 2025 (REQ-D30).

<!-- facts: DEF-MEMBER-SHARE -->
Member share of sales is net sales before returns on lines linked to a member, divided by all net sales before returns. Receipts without a member, and guest web orders, count as non-member.

<!-- facts: REG-GUEST-ORDERS -->
Guest web orders (checkout without logging in) have no member key. Logged-in orders carry the member's key.

<!-- source: REQ-D31, REQ-D32 -->
The accepted member-share queries date web lines on the dispatch date, keep store 999 and ZZ Test out, and show Online as its own region (REQ-D31 by calendar month, REQ-D32 by region).

<!-- facts: DEF-NEW-MEMBER -->
A new member is counted on their join date, at the home store in their first version in dim_member (the store where they enrolled). Online sign-ups sit under store 900.

## Campaigns

<!-- facts: DEF-UPLIFT -->
Campaign uplift is the mean net sales per targeted member minus the mean per holdout member, over the campaign window plus seven days. A targeted member has at least one exposure row in the campaign. Members with no sales count as zero, and net sales are before returns, on lines linked to the member.

<!-- facts: REG-EXPOSURE-FANOUT, REG-CONSENT -->
fact_campaign_exposure has one row per contact, so a member can appear several times in one campaign: reduce to one row per member (distinct member_id, through dim_member) before joining to sales. Members are contacted only if they have marketing consent on the contact date. Holdout members (10% of each mailing list) are never contacted. campaign_holdout holds member_id, not member_key.

The uplift template applies the net-sales dating and exclusions (web on the dispatch date, store 999 and ZZ Test out) to the member's lines, and its last row counts members found in both groups, which should be zero.

<!-- facts: DEF-NET-SALES-SCOPE, DEF-WEB-RECOGNITION -->
Store 999 and test articles (category ZZ Test) are left out of net sales. Staff purchases are included. Web sales are recognised on the dispatch date in Helsinki time.

<!-- source: schema_comments.csv -->
dim_campaign holds the window (start_date, end_date), the channels (joined with +), the target group, holdout_pct, mailing_list_size (including the holdout) and holdout_size.

## Past requests for this skill

Copied from `warehouse-map/references/request_history_digest.md`. Date asked in brackets; the reading the requester accepted after the colon.

<!-- source: REQ-D29, REQ-D30, REQ-D31, REQ-D32 -->
- D29 (6 May 2025) active members at the end of last year: as of Sunday 27 Apr 2025; distinct member_id. -> loyalty-and-campaigns/templates/active_members.sql
- D30 (8 Oct 2025) active members by tier, last Sunday of September: 28 Sep 2025; tier from the version valid that day. -> active_members.sql
- D31 (14 May 2025) member share by month, November to April: 1 Nov 2024-27 Apr 2025; before returns; web on dispatch date.
- D32 (9 Jun 2026) member share by region, P1 this year: FY2026/27 P1; as-is with Online. -> loyalty-and-campaigns/templates/member_share_of_sales.sql
