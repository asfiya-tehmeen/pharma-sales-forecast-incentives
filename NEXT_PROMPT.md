I'm a Dubai-based analyst job seeker targeting pharma commercial excellence, sales force effectiveness (SFE) and business insights roles at GCC affiliates (MSD, Novartis, AstraZeneca, Sanofi, Pfizer) and consultancies (IQVIA, ZS). This project hasn't started. `README.md` is an ~8-day plan, and the original brief is in `docs/original-brief.md`.

I'm job hunting full-time, so **first rewrite the plan into a 5-day core version** and show me the diff before writing code.

## Keep (this is the pitch)
- The simulated affiliate ("Nakheel Pharma", fictional) with the data-honesty statement on the first line, calibrated to cited public sources in `docs/calibration.md`. Verify every source and figure you cite, and mark anything you couldn't verify as an assumption.
- **Scope cut:** 3 products, not 5 (a mature brand with generic entry, a launch with stock-out months, and a stable control product); KSA + UAE territories; about 40 reps; 36 months.
- Planted effects: Ramadan/Eid on the Hijri calendar, the launch ramp, stock-outs, generic entry, rep vacancies, and about 5 unfairly targeted territories. Keep the hidden answer key in `data/raw/answer_key.json`. Analysis code must not read it until a final scoring step.
- Realistic messiness: late files, duplicates, valid negative returns, restatements.
- **A SQL warehouse:** build the validated monthly fact table and the KPI views in DuckDB SQL (`sql/`), including attainment vs target, a payout calculation, and like-for-like growth.
- **The forecasting ladder:** seasonal naive → ETS → one LightGBM global model with lag, calendar and Hijri features; rolling-origin backtest; WAPE and bias by product; Gregorian-only vs Hijri-aware comparison.
- **The fairness core:** a target is fair when each rep has about the same probability of hitting it. Use the forecast distribution to give each territory's target a percentile, flag the outliers, and score the flags against the answer key (precision and recall).
- An incentive simulation: compare 2 target-setting rules ("last year + X%" vs potential-based) on payout cost, a Gini coefficient of payouts and the fairness spread.
- `REPORT.md` written as a memo to an SFE head: which forecast model to use, how to set targets, and which territories to adjust.

## Drop or park (list them under "Future work")
- Hierarchical forecast reconciliation
- Primary vs secondary sales and distributor inventory modelling (keep one paragraph explaining the difference)
- Tender (institutional) channel, call-activity simulation, HCP deciles
- Management-overlay forecast value added
- The deployed Streamlit app

## Instead of Streamlit
Export a star schema (`fact_sales`, `fact_targets`, `dim_rep`, `dim_territory`, `dim_product`, `dim_date` with Hijri fields) to `reports/powerbi/`, plus `MEASURES.md` with DAX for attainment, payout, forecast error and fairness percentile, and a one-page layout spec. Pharma SFE teams use Power BI and Excel. I'll build the page myself.

## Rules
- Everything runs from a seeded generator, so results reproduce. Write tests for the generator and the data validation.
- Never report a number you haven't run. If a model doesn't beat seasonal naive, or a planted effect isn't recovered, say so plainly.
- Don't claim real-world accuracy or real incentive outcomes.
- At the end, run the tests, show the results, and give me 2 resume bullets that use only measured numbers.
