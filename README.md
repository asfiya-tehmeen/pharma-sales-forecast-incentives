> **Data honesty:** all sales, rep, target and payout data in this project is **simulated** for a fictional company ("Nakheel Pharma"), because rep-level pharma data is confidential everywhere. Market-level inputs (regional population, diabetes prevalence, prices, market growth) are calibrated to public sources cited in [`docs/calibration.md`](docs/calibration.md); any figure that could not be verified is marked there as an **assumption**. Results show how well the **methods** work, not real-world forecast accuracy or real incentive outcomes.

# Fair Targets: Ramadan-Aware Forecasting and Incentive Fairness for a GCC Pharma Affiliate

**Status:** Complete: pipeline, memo and Power BI dashboard (seed 42, 51 tests passing) | **Data:** HYBRID (simulated, calibrated to public data) | **Effort:** 5 days
**Target roles:** Commercial Excellence, Sales Force Effectiveness (SFE), Business Insights & Analytics at GCC pharma affiliates and consultancies.

Earlier versions: [`docs/original-brief.md`](docs/original-brief.md)

**Quick links:**
- Memo to the SFE head: [`reports/REPORT.md`](reports/REPORT.md)
- Effect scorecard: [`reports/SCORECARD.md`](reports/SCORECARD.md)
- Power BI dashboard: [`reports/powerbi/fair_targets.pbix`](reports/powerbi/fair_targets.pbix)
- Calibration sources: [`docs/calibration.md`](docs/calibration.md)

![Power BI dashboard: 2025 Targets, Fair or Not?](reports/figures/05_powerbi_dashboard.png)

*One-page Power BI dashboard on simulated data. It has 5 KPI cards, the target-fairness dot plot, attainment by territory, forecast vs actual with Ramadan months shaded, and the flagged-territories table, plus a drill-through page for each territory.*

---

## 1. The pitch

A GCC pharma affiliate sets annual sales targets for about 40 reps. Two things go wrong every year:

1. **Forecasts miss around Ramadan.** Ramadan moves about 11 days earlier each Gregorian year, so a model that learns "March is weak" is wrong next year.
2. **Targets feel unfair.** "Last year + X%" punishes reps after a strong year and rewards territories that had a vacancy.

**The central idea:** a target is fair when every rep has about the **same probability of hitting it**. A probabilistic forecast gives each territory's target a percentile. For example, a target at the P85 of a territory's forecast is much harder than one at the P50. Territories far from the median get flagged, and the flags are scored against a hidden answer key.

## 2. Business questions

| # | Question |
|---|---|
| Q1 | Which forecast model should we use? Does it beat seasonal naive on WAPE and bias, by product? |
| Q2 | Does a Hijri-aware model beat a Gregorian-only model around Ramadan and Eid? |
| Q3 | Which territories have unfair targets, and how far off are they? |
| Q4 | "Last year + X%" vs potential-based targets: which gives lower payout cost risk, a fairer payout spread (Gini) and a tighter fairness spread? |

## 3. Simulated world

**Company:** "Nakheel Pharma" (fictional) sells a cardiometabolic portfolio in **KSA and the UAE**. There are about 40 reps, one per territory, mapped to real regions. The data covers **36 months**: years 1–2 are history and year 3 is the target year.

| Product (fictional) | Role | Story planted |
|---|---|---|
| Glucora (DPP-4 inhibitor) | Mature brand | **Generic entry** partway through history, then sales erode |
| Semavia (GLP-1 injectable) | Launch | **Launch ramp** plus **stock-out months** where recorded sales understate demand |
| Cardivex (statin) | Stable control | Seasonality only |

**Territory potential** = regional population × diabetes prevalence × a price/market-size factor, from the sources in `docs/calibration.md`, split across territories.

### Planted effects (hidden answer key)

| # | Effect | How recovery is tested |
|---|---|---|
| E1 | Ramadan dip and Eid holiday dip on the **Hijri** calendar | Hijri-aware vs Gregorian-only model error in Ramadan months; LightGBM feature importance |
| E2 | Semavia launch ramp | Forecast error on the ramp; fitted vs true ramp shape |
| E3 | Semavia stock-out months | Stock-out months flagged by the anomaly checks vs the planted months |
| E4 | Glucora generic entry | Change point found vs planted month |
| E5 | Rep vacancies (a few territories, 2–4 months) | Vacancy months detected from zero/near-zero activity |
| E6 | About 5 unfairly targeted territories (realistic causes: "last year + X%" after a vacancy year, a new account not in the base year, manual top-down uplifts) | **Precision and recall** of fairness flags |

**Answer key rule:** the generator writes `data/raw/answer_key.json`. Only the final scoring step (`src/fairtargets/scorecard.py`) reads it. A test fails if any other module references it.

### Realistic messiness in the raw feed
Late files (a month arrives in the next delivery), duplicate rows, **valid negative returns** (kept, not dropped), and restatements (a later file corrects an earlier month; the latest version wins).

## 4. Approach

### A. Seeded generator (Python)
`src/fairtargets/generator.py` takes a single seed. It produces the raw monthly feed files, rep and territory master data, year-3 targets, and the answer key.

### B. SQL warehouse (DuckDB)
All of this is SQL in `sql/`, run by a small Python runner:
- `01_load.sql`: load raw files as delivered.
- `02_validate.sql`: duplicates, restatements (latest file wins), late files, negative values checked against the returns flag, orphan reps/products. Produces a data-quality summary table.
- `03_fact.sql`: the validated monthly fact table `fact_sales` (rep × territory × product × month) and `fact_targets`.
- `04_dims.sql`: `dim_rep`, `dim_territory`, `dim_product`, and `dim_date` with Hijri month, Ramadan-day share, Eid days, and KSA/UAE holidays (the calendar is generated in Python and loaded).
- `05_kpi_views.sql`: views for **attainment vs target**, **payout calculation** (threshold, linear band, cap), and **like-for-like growth** (same territory-product pairs active in both periods, excluding vacancy months and the launch product).

### C. Forecasting ladder
- Models: **seasonal naive → ETS → one global LightGBM** (lags, recent level, lifecycle and vacancy features, Gregorian month, and Hijri features: share of the month in Ramadan, in the 10 pre-Ramadan days and in Eid holidays, this year and the same month last year).
- **Rolling-origin backtest**: forecast origins at months 24–33, horizons of 1–3 months, so every model has at least 2 full seasons to train on. Metrics: **WAPE and bias by product**.
- **Target-year forecast** (for fairness): a single 12-month forecast using data through month 24 only, so it never sees year-3 actuals.
- **Gregorian-only vs Hijri-aware** LightGBM, compared overall and in Ramadan/Eid months.
- If a model does not beat seasonal naive, the report says so.

### D. Fairness core
- Year-3 forecast distribution per territory: the point forecast from the chosen model, **scaled so each product sums to the national budget** (top-down reconciliation; added after run 1, see REPORT.md section 4), plus an empirical spread from bootstrapped one-month-ahead backtest errors in 2024.
- **Target percentile** = where the official target sits in that territory's distribution.
- Flag territories whose percentile is far from the median (threshold set before scoring and documented).
- Final scoring step: precision and recall of the flags against the answer key.

### E. Incentive simulation
- Two target-setting rules: **"last year + X%"** vs **potential-based** (national target split by share of potential).
- Monte Carlo draws from the forecast distribution. Outputs per rule: **payout cost** (mean and P90 vs budget), **Gini of payouts**, and **fairness spread** (spread of target percentiles across territories).

### F. Power BI dashboard (instead of an app)
`reports/powerbi/` contains:
- **A star schema as CSV:**
  - fact tables: `fact_sales`, `fact_targets`, `fact_forecast` (backtest and target-year forecasts), `fact_fairness` (target percentiles for each territory and rule)
  - dimensions: `dim_rep`, `dim_territory`, `dim_product`, `dim_date` (daily, with Hijri, Ramadan, Eid and KSA/UAE holiday fields)
- **`MEASURES.md`:** DAX for attainment %, payout, forecast error (WAPE, bias) and fairness percentile, plus the expected values to check against.
- **`LAYOUT.md`:** the one-page layout spec.
- **`fair_targets.pbix`:** the built dashboard, with one main page and a drill-through page per territory.
- **`VALIDATION.md`:** 22 checks of the Power BI model against the warehouse (totals, attainment, payout, WAPE by model, flag counts, row counts). All pass.

The dashboard imports the CSVs from absolute paths on the build machine. If you clone the repo, repoint the sources in Power Query before refreshing.

### G. Report
`reports/REPORT.md` is written as a memo to an SFE head. It covers which forecast model to use, how to set targets, which territories to adjust, and which planted effects were recovered or missed.

## 5. A note on primary vs secondary sales (not modelled)

**Primary sales** are what the affiliate invoices to its distributor. **Secondary sales** are what the distributor sells on to pharmacies and hospitals. The gap between them is distributor inventory, which can swing at quarter-end when stock is loaded into the channel. Reps are usually measured on secondary sales; supply planning works on primary. This project simulates **secondary sales only**, since that is what targets and incentives are based on.

## 6. Stack and structure

Python, DuckDB SQL, pandas, statsforecast (ETS), LightGBM, SciPy, hijridate (Umm al-Qura), holidays, matplotlib, pytest, Power BI (DAX).

```
data/calibration/  public inputs: regions.csv, country_diabetes.csv, sfda_reference_prices.csv (committed)
data/raw/          generator output + answer_key.json (read only by scorecard.py; git-ignored, regenerated)
data/clean/        warehouse.duckdb (git-ignored, regenerated)
docs/              calibration.md, original-brief.md
sql/               01_load  02_validate  03_fact  04_dims  05_kpi_views
src/fairtargets/   config.py  calibration.py  calendar.py  generator.py  warehouse.py  forecast.py
                   targets.py  incentives.py  effects.py  figures.py  export_powerbi.py  scorecard.py  run_all.py
scripts/           extract_sfda_prices.py (one-off copy of SFDA prices from Project A)
tests/             test_generator  test_calendar  test_validation  test_forecast  test_incentives
                   test_answer_key_isolation
reports/           REPORT.md (memo)  SCORECARD.md  figures/  results/ (JSON/CSV)
reports/powerbi/   fair_targets.pbix  8 CSVs  MEASURES.md  LAYOUT.md  VALIDATION.md
```

Run everything (about 1 minute): `pip install -e .` once, then `python -m fairtargets.run_all --seed 42` and `pytest`.

## 7. Setup (PowerShell)

```powershell
cd projects\d-pharma-sales-forecast-incentives
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 8. Plan (5 days)

- [x] **Day 1: Calibrate + generate.** Verify sources and write `docs/calibration.md`. Write the seeded generator with planted effects, messiness and the answer key. Tests: same seed gives identical output; each effect is present; the messiness is present.
- [x] **Day 2: Warehouse.** Calendar dimension; SQL load → validate → fact → dims → KPI views. Tests: validation catches every injected issue; returns are kept; restatements resolve to the latest file.
- [x] **Day 3: Forecast.** Seasonal naive, ETS, LightGBM; rolling-origin backtest; WAPE and bias by product; Gregorian vs Hijri comparison.
- [x] **Day 4: Fairness + incentives.** Target percentiles, flags, two-rule Monte Carlo, then the final scorecard against the answer key.
- [x] **Day 5: Handoff + write-up.** Power BI export, MEASURES.md, LAYOUT.md, REPORT.md, and a README results section with measured numbers only.

## 9. Definition of done

- One seed reproduces every number. All tests pass.
- Every model is compared with seasonal naive, and losses are reported plainly.
- The scorecard lists every planted effect as recovered, partially recovered or missed.
- No number appears in the README or report that was not produced by a run.

## 10. Future work (parked)

- Hierarchical forecast reconciliation (territory → region → country).
- Primary vs secondary sales and distributor inventory modelling.
- Tender / institutional channel, call-activity simulation, HCP decile targeting.
- Calibrated 12-month forecast intervals (the current one-month-error bootstrap is too narrow; see Results).
- Results across several seeds, not just seed 42.
- Management-overlay forecast value added (FVA).
- A deployed interactive app (Streamlit).

## 11. Limitations / do not claim

- Findings apply to simulated data. Planted effects are cleaner than reality, and having an answer key makes recovery easier than in practice.
- Do not claim real-world accuracy, real incentive outcomes, or that Nakheel Pharma or its brands exist.

## 12. Results (seed 42; every number from `reports/results/`)

Full memo: [`reports/REPORT.md`](reports/REPORT.md). Scorecard: [`reports/SCORECARD.md`](reports/SCORECARD.md).

**Data validation.** The feed has 29,134 rows in 37 delivery files. The SQL validation:
- quarantined 14 invalid rows (8 negative sales, 6 unknown product codes)
- removed 200 duplicates
- resolved 117 restatements
- kept 4,034 valid negative returns

The resulting fact table equals the true ledger to the cent (tested).

**Forecasting.** Rolling-origin backtest, 3,600 forecasts per model, 1–3 months ahead:

| Model | WAPE | Bias | WAPE in Feb–Apr 2025 (Ramadan/Eid) |
|---|---|---|---|
| Seasonal naive | 27.0% | +1.5% | 31.5% |
| ETS | 12.5% | +1.8% | 15.1% |
| LightGBM, Gregorian only | 11.1% | +1.3% | 12.1% |
| LightGBM, Hijri-aware | **10.4%** | +2.2% | **10.3%** |

The 12-month recursive LightGBM forecast overshot 2025 by 26.5%, mainly Semavia, so target setting uses it only after scaling to the national budget.

**Effect recovery.** 5 of 6 planted effects were recovered, along with all data-quality checks:
- Ramadan daily effect: estimated 0.87× vs 0.85× planted
- generic entry month: 20 vs 20
- stock-out months: 3/3 found, no false flags
- vacancy effect: 0.654× vs 0.65×

**Unfair targets: partially recovered.** All 5 planted territories were flagged, each in the correct direction, but 22 flags in total means 23% precision. The cause is overconfident forecast ranges: only 15% of actual 2025 territory totals fell inside P10–P90. The first run, without budget scaling, caught only 1 of 5; that change is disclosed in the memo.

**Incentive rules** (10,000 simulated years):

| | Last year + X% | Potential-based |
|---|---|---|
| Payout Gini | 0.10 | 0.37 |
| Reps on zero payout | 0.3% | 25.2% |
| Fairness spread (IQR of target percentiles) | 73 pp | 100 pp |

In this simulation the pure potential-based split is worse, so the memo recommends a corrected "last year + X%" rule.

**Power BI.** The dashboard reproduces the warehouse figures exactly (`reports/powerbi/VALIDATION.md`):
- 2025 sales SAR 506.73M at 92.0% attainment
- payout at 57.7% of the bonus budget
- 22 flagged territories under the issued targets

Its WAPE card is **value-weighted** and one month ahead: 13.4% for the Hijri-aware LightGBM, against 46.1% for seasonal naive. The table above uses unit-based WAPE pooled over 1–3 months, so the two figures differ by design.
