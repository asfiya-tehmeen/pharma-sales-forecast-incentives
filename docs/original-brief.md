# Project D: Pharma Sales Forecasting and Incentive Fairness

**Status:** Not started | **Data:** HYBRID (simulated sales, calibrated to real public market data) | **Effort:** about 5 days
**Target roles:** sales force effectiveness, commercial analytics, forecasting (for example MSD-style GLE + KSA roles)

> **Data honesty:** rep-level sales and incentive data is confidential at every company, so it is simulated here. Market size and growth are calibrated to public IQVIA MEA briefs and company filings. State this in the first lines of the README and every report.

## 1. Business question

How accurate are sales forecasts across products and territories, what drives forecast error, and are incentive targets fair relative to territory potential?

## 2. Data

| Source | What | Notes |
|---|---|---|
| Simulated sales data (you build the generator) | About 40 reps, 5 products, 24 to 36 months, territories with different potential | Seeded and tested so results reproduce. |
| IQVIA MEA briefs (public PDFs) | Market size and growth for Saudi and UAE | Use for calibration only; cite the brief and period. |
| Calendar | Hijri months, Ramadan, public holidays | Build the calendar table in code. |

Plant known effects in the generator (keep a hidden answer key): Ramadan seasonality, a launch ramp for one product, a competitor entry, a stock-out month, and a few territories with deliberately unfair targets. Then test whether your methods find them.

## 3. Setup (PowerShell)

```powershell
cd projects\d-pharma-sales-forecast-incentives
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 4. Folder structure

```
data/raw/        generator output (seeded) plus calibration inputs
data/clean/      monthly fact table, calendar table
notebooks/       01_generate, 02_clean, 03_eda, 04_forecast, 05_incentives
src/             generator.py, calendar.py, features.py, forecast.py, incentives.py
tests/           test_generator.py, test_features.py
reports/         figures and REPORT.md
```

## 5. Tasks

### Phase 1: Generate (Day 1)
- [ ] Pull market size and growth figures from IQVIA briefs; record the values and page numbers.
- [ ] Write `src/generator.py` with a fixed random seed; reps, territories (with potential), products, months.
- [ ] Add the planted effects and save the answer key separately (`data/raw/answer_key.json`).
- [ ] Add realistic messiness: late data, missing months, corrections, rep transfers.
- [ ] Tests: same seed gives same data; planted effects exist in the output.

### Phase 2: Clean (Day 2)
- [ ] Validate the feed as if it were real: duplicates, negative sales, missing reps, transfers.
- [ ] Build a monthly fact table in DuckDB or parquet.
- [ ] Add calendar features: Hijri month, Ramadan flag, holiday count.

### Phase 3: Explore (Day 2)
- [ ] Seasonality plots, product lifecycle curves, attainment distribution by rep.

### Phase 4: Forecast (Day 3 to 4)
- [ ] Models: seasonal naive, ETS, SARIMA, global LightGBM with lag, rolling and calendar features.
- [ ] Rolling-origin backtests; metrics WAPE, bias and MAPE by product.
- [ ] Test model differences with a Diebold-Mariano test.
- [ ] Check if the models recover planted effects (for example, does the Ramadan feature matter, is the launch ramp captured?).
- [ ] Optional: hierarchical reconciliation (product to territory to total).

### Phase 5: Incentives (Day 4)
- [ ] Define a simple incentive plan: target attainment, payout curve, cap.
- [ ] Regress attainment on territory potential; test whether potential explains attainment.
- [ ] Compute the Gini coefficient of payouts and the correlation of payout with underlying potential.
- [ ] Monte Carlo of payout cost under different target-setting rules and payout curves.
- [ ] Check that the unfair territories you planted are detected.

### Phase 6: Write up (Day 5)
- [ ] `reports/REPORT.md`: which model to use, how to set targets, which territories need adjustment.
- [ ] README results section with real numbers only.

## 6. Definition of done

- The generator is seeded and tested.
- Every forecast model is compared with the seasonal naive baseline.
- The report states which planted effects were recovered and which were not.
- The first line says the data is simulated.

## 7. Limitations

- Findings apply to simulated data, so they show method performance, not real-world accuracy.
- Planted effects are simpler than reality.

## 8. Do not claim

- Real-world forecast accuracy or incentive outcomes.
- That the data came from a real company.

## 9. Resume line template

> Simulated [N] reps x [N] months of pharma sales calibrated to IQVIA market data; backtested [N] forecast models (WAPE [x] vs [y] seasonal naive); quantified target unfairness (potential explains [R-squared] of attainment).
