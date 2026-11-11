# One-page dashboard layout: "2025 Targets: Fair or Not?"

> Built as `fair_targets.pbix`; screenshot at `../figures/05_powerbi_dashboard.png`. Deviations from this spec are listed in `VALIDATION.md`. The main one: the fairness plot marks the median ± 25 pp band with reference lines instead of shading.

**Audience:** SFE / Commercial Excellence head.
**Question it answers in 10 seconds:** are we on plan, which territories have unfair targets, and how good is our forecast?
**Footer on the page:** "Simulated data. Fictional company."

```
+--------------------------------------------------------------------------------------+
| Slicers (one row): Country | Product | Target rule [issued] | Forecast model [lgbm_hijri] |
+--------------------------------------------------------------------------------------+
| KPI cards (5):                                                                       |
| Sales 2025 | Attainment % | Payout % of Budget | WAPE % (1m ahead) | Flagged Territories|
+-------------------------------------------+------------------------------------------+
| A. Target fairness (dot plot)             | B. Attainment by territory (bar)         |
|   y = territory, sorted by percentile     |   y = territory (same sort as A)         |
|   x = Target Percentile (0-100%)          |   x = Attainment %, reference lines at   |
|   shaded band = median +/- 25 pp          |   90% (payout threshold) and 100%        |
|   colour: easy blue / hard red / grey     |   tooltip: Payout SAR, rep_id, vacancy   |
+-------------------------------------------+------------------------------------------+
| C. Forecast vs actual (line, monthly, 2023-2025)                                     |
|   Sales Value (actual) and Forecast Value; background band where Ramadan days > 0    |
|   tooltip: WAPE %, Bias %, Hijri month name                                          |
+--------------------------------------------------------------------------------------+
| D. Table: flagged territories: territory | direction | Target Percentile |            |
|    Gap vs Median (pp) | annual_target | forecast_p50 | Attainment %                  |
+--------------------------------------------------------------------------------------+
```

## Visual notes

- **A** is the hero visual. Use a scatter with `Target Percentile` on x and a rank index on y, or a sorted bar of `Gap vs Median (pp)` as a fallback.
- Keep the **easy = blue / hard = red** encoding in A and D.
- Always show text labels on flagged points, so the colour is never the only cue.
- **C** uses one y-axis only (SAR). Show units in the tooltip, not on a second axis.
- **Sync A and B:** sort B by the same field as A, so one row reads across both.
- **Drill-through:** from any territory to a detail page with monthly sales vs target by product and rep tenure from `dim_rep`.
