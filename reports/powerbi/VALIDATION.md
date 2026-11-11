# Power BI validation

The checks below were run as DAX queries against the refreshed Power BI Desktop model through the Power BI MCP server. Money is compared to the cent and percentages to the precision specified in MEASURES.md.

| Check | Expected | Power BI | Result |
|---|---:|---:|---|
| 2025 target value | 550,565,475.90 SAR | 550,565,475.90 SAR | PASS |
| 2023 sales | 247,270,676.35 SAR | 247,270,676.35 SAR | PASS |
| 2024 sales | 383,029,004.55 SAR | 383,029,004.55 SAR | PASS |
| 2025 sales | 506,727,689.75 SAR | 506,727,689.75 SAR | PASS |
| Total attainment | 92.0% | 92.0% | PASS |
| Payout as % of budget, issued, without proration | 57.7% | 57.7% | PASS |
| 1-month value WAPE, lgbm_hijri | 13.4% | 13.4% | PASS |
| 1-month value WAPE, lgbm_gregorian | 15.0% | 15.0% | PASS |
| 1-month value WAPE, ets | 15.4% | 15.4% | PASS |
| 1-month value WAPE, seasonal_naive | 46.1% | 46.1% | PASS |
| Flagged territories, issued | 22 | 22 | PASS |
| Flagged territories, last_year_plus_x | 25 | 25 | PASS |
| Flagged territories, potential_based | 38 | 38 | PASS |
| fact_sales rows | 4,320 | 4,320 | PASS |
| fact_targets rows | 1,440 | 1,440 | PASS |
| fact_forecast rows | 6,240 | 6,240 | PASS |
| fact_fairness rows | 120 | 120 | PASS |
| dim_territory rows | 40 | 40 | PASS |
| dim_product rows | 3 | 3 | PASS |
| dim_rep rows | 44 | 44 | PASS |
| dim_date rows | 1,096 | 1,096 | PASS |
| Sales rows with blank rep ID, checked against the CSV | 39 | 39 | PASS |

## Model and report notes

- The requested Ramadan correction uses `dim_date[Month Ramadan Days] > 0` in the Ramadan WAPE measure. Monthly facts join on the first day, so the monthly count lets a month qualify when Ramadan begins later in the month.
- Territory code breaks tied percentile ranks within each rule so every territory has a distinct vertical position.
- The rule slicer filters the fairness fact. Attainment and payout use issued product-month targets as defined in MEASURES.md. Fairness is calculated at territory and rule grain, so the product slicer affects sales, attainment and forecast measures.
- The flagged table uses territory-context measures for the same fields and a visual gap measure that evaluates the median over the selected territory population. The original spec measure is also present.
- The monthly forecast chart uses pale Ramadan columns behind the two lines. The column height is derived from the displayed series so the Ramadan months can be read on the shared SAR scale.
- The fairness scatter uses dynamic reference lines at the selected median ±25 percentage points, clipped to the 0–100% axis. The area between the lines is unshaded. The scatter uses the requested point colors and has territory labels and direction in the tooltip. Desktop can suppress overlapping labels at fit-to-page zoom. The flagged table shows the direction in text with blue for easy and red for hard.
- The attainment bar is sorted by the same per-rule rank as the scatter, from hardest to easiest. The bar and flagged table scroll independently when their rows exceed the visual height.
- Verified the saved default selections in Desktop: all countries, all products, issued, lgbm_hijri, and backtest_1m_ahead. Verified drill-through from an attainment bar into the territory's three product charts and filtered rep-tenure table.
- The PBIX contains imported data. The Power Query refresh sources use the absolute CSV paths on the build machine. If the project moves, update the CSV paths before refreshing.
