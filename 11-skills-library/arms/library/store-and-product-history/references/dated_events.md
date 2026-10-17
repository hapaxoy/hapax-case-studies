# Dated events

Every dated change recorded in the data quality register and the calendar rules, in date order. Check any request range against it.

<!-- facts: REG-REFITS, REG-VAT-CHANGE, REG-STORE-EVENTS, REG-UTC, REG-REGION-REORG, REG-OUTDOOR-LIGHTING, REG-MIGRATION, REG-DEPRECATED, CAL-FY-DATES, CAL-WEEK53, CAL-DATA-THROUGH -->
| Date | Event | Source |
|---|---|---|
| 29 Apr 2024 | FY2024/25 starts (52 weeks, to 27 Apr 2025) | CAL-FY-DATES |
| 8 Jul - 11 Aug 2024 | Vantaa Tammisto (104) shut for refit, 5 weeks | REG-REFITS |
| 1 Sep 2024 | General VAT rate 24% to 25.5%; 14% and 10% unchanged | REG-VAT-CHANGE |
| 2 Sep 2024 | Tampere Lamminpää (136) opens | REG-STORE-EVENTS |
| 4 Nov 2024 | Lohja (137) opens | REG-STORE-EVENTS |
| 30 Mar 2025 | Clocks change (Finland UTC+2 in winter, UTC+3 in summer) | REG-UTC |
| 27 Apr 2025 | rpt_weekly_sales_by_region stops refreshing | REG-DEPRECATED |
| 28 Apr 2025 | FY2025/26 starts (53 weeks, to 3 May 2026); four regions become five with the Capital Region | CAL-FY-DATES, REG-REGION-REORG |
| 8 Sep - 12 Oct 2025 | Pori (119) shut for refit, 5 weeks | REG-REFITS |
| 26 Oct 2025 | Clocks change | REG-UTC |
| 27 Oct 2025 | Outdoor lighting moves from Garden to Electrical (FY2025/26 P7) | REG-OUTDOOR-LIGHTING |
| 3 Nov 2025 | Web platform migration: channel_code no longer filled, channel_id used, click-and-collect key 3 | REG-MIGRATION |
| 25 Jan 2026 | Savonlinna (129) closes | REG-STORE-EVENTS |
| 27 Apr - 3 May 2026 | Week 53 of FY2025/26, added to P12 | CAL-WEEK53 |
| 4 May 2026 | FY2026/27 starts | CAL-FY-DATES |
| 15 Jun - 26 Jul 2026 | Kuopio (125) shut for refit, 6 weeks | REG-REFITS |
| 4 Oct 2026 | Warehouse loaded through this Sunday (FY2026/27 week 22) | CAL-DATA-THROUGH |

<!-- facts: TEAM-LFL-EDGE -->
LFL edge cases. A store back from a refit is excluded for the refit weeks only. The two new stores enter the LFL base on 1 September 2025 (136) and 3 November 2025 (137). The closed store (129) drops out from its closure. Week 53 is never LFL. The web shop is never LFL.
