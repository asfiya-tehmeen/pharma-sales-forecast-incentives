# Power BI model and DAX measures

> Simulated data for a fictional company ("Nakheel Pharma"). Regenerate the CSVs with `python -m fairtargets.run_all --seed 42`.

## Tables (CSV, in this folder)

| Table | Grain | Key columns |
|---|---|---|
| `fact_sales` | territory × product × month (2023-01 to 2025-12) | `territory_code`, `product_code`, `month_start`, `rep_id` (blank = vacant), `units_net`, `value_net` (SAR, returns netted) |
| `fact_targets` | territory × product × month (2025 only) | `target_value` (SAR, as issued) |
| `fact_forecast` | forecast type × model × territory × product × month | `forecast_type` = `backtest_1m_ahead` (all 4 models, 2025) or `target_year_from_dec_2024` (LightGBM, before budget reconciliation); `forecast_value`, `actual_value` |
| `fact_fairness` | territory × target rule | `rule` (`issued`, `last_year_plus_x`, `potential_based`), `annual_target`, `target_percentile` (P(missing target)), `flag`, `direction`, `forecast_p10/p50/p90`, `actual_2025` |
| `dim_territory` | territory | `country`, `region`, `potential_diabetics`, `potential_share` |
| `dim_product` | product | `product_name`, `lifecycle`, `list_price_sar`, `launch_month`, `generic_entry_month` |
| `dim_rep` | rep | `territory_code`, `start_date`, `end_date` |
| `dim_date` | day (2023–2025) | Gregorian fields, `hijri_year/month/day/month_name`, `is_ramadan`, `is_pre_ramadan`, `is_eid`, KSA/UAE holiday and workday flags |

## Relationships (single direction, one-to-many)

- `dim_date[date]` → `fact_sales[month_start]`, `fact_targets[month_start]`, `fact_forecast[month_start]`. Mark `dim_date` as the date table. Monthly facts sit on the 1st of each month.
- `dim_territory[territory_code]` → all four fact tables.
- `dim_product[product_code]` → `fact_sales`, `fact_targets`, `fact_forecast`.
- `dim_rep[rep_id]` → `fact_sales[rep_id]`, `fact_targets[rep_id]`.
- `fact_fairness` has no product or date grain. Filter it with a `rule` slicer, and default the slicer to `issued`.

## Measures

```dax
-- Sales and targets ----------------------------------------------------------
Sales Value = SUM ( fact_sales[value_net] )

Sales Units = SUM ( fact_sales[units_net] )

Target Value = SUM ( fact_targets[target_value] )

-- Sales only in months that carry a target, so attainment compares like with like.
Sales Value (Target Months) =
CALCULATE (
    [Sales Value],
    TREATAS ( VALUES ( fact_targets[month_start] ), dim_date[date] )
)

Attainment % = DIVIDE ( [Sales Value (Target Months)], [Target Value] )

Sales Value PY = CALCULATE ( [Sales Value], SAMEPERIODLASTYEAR ( dim_date[date] ) )

Growth vs PY % = DIVIDE ( [Sales Value] - [Sales Value PY], [Sales Value PY] )

-- Payout (same curve as config.py and sql/05_kpi_views.sql) ------------------
-- < 90% -> 0; 90-100% -> 50-100% linear; > 100% -> +2% per +1%, capped at 150%.
Payout % (Territory) =
VAR a = [Attainment %]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( a ), BLANK (),
        a < 0.90, 0,
        a < 1.00, 0.50 + ( a - 0.90 ) / 0.10 * 0.50,
        MIN ( 1 + 2 * ( a - 1 ), 1.50 )
    )

-- Payout is decided per territory on annual attainment, then summed.
-- Not prorated for partial tenure; gold.v_payout in DuckDB prorates by months in role.
Payout SAR =
SUMX (
    VALUES ( dim_territory[territory_code] ),
    [Payout % (Territory)] * 40000
)

Payout % of Budget =
DIVIDE ( [Payout SAR], 40000 * DISTINCTCOUNT ( dim_territory[territory_code] ) )

Reps Below Threshold =
COUNTROWS (
    FILTER ( VALUES ( dim_territory[territory_code] ), [Attainment %] < 0.90 )
)

-- Forecast error (filter fact_forecast[model] and [forecast_type] with slicers) -
Forecast Value = SUM ( fact_forecast[forecast_value] )

Forecast Actual Value = SUM ( fact_forecast[actual_value] )

Forecast Abs Error =
SUMX ( fact_forecast, ABS ( fact_forecast[forecast_value] - fact_forecast[actual_value] ) )

WAPE % = DIVIDE ( [Forecast Abs Error], [Forecast Actual Value] )

Bias % = DIVIDE ( [Forecast Value] - [Forecast Actual Value], [Forecast Actual Value] )

WAPE % (Ramadan Months) =
CALCULATE ( [WAPE %], dim_date[is_ramadan] = TRUE () )
-- As built in fair_targets.pbix: dim_date has a calculated column [Month Ramadan Days]
-- (Ramadan days in that row's month), and this measure filters [Month Ramadan Days] > 0.
-- A plain filter on is_ramadan would only select months whose FIRST day is in Ramadan.

-- Fairness percentile ----------------------------------------------------------
Target Percentile =
-- Probability of MISSING the target, from the forecast distribution. 0.5 = a coin flip.
AVERAGE ( fact_fairness[target_percentile] )

Median Target Percentile =
CALCULATE (
    MEDIANX ( VALUES ( fact_fairness[territory_code] ), [Target Percentile] ),
    ALLSELECTED ( fact_fairness[territory_code] )
)

Gap vs Median (pp) = ( [Target Percentile] - [Median Target Percentile] ) * 100

Flagged Territories =
CALCULATE ( COUNTROWS ( fact_fairness ), fact_fairness[flag] = TRUE () )

Fairness Spread IQR (pp) =
VAR t = VALUES ( fact_fairness[territory_code] )
RETURN
    ( PERCENTILEX.INC ( t, [Target Percentile], 0.75 )
      - PERCENTILEX.INC ( t, [Target Percentile], 0.25 ) ) * 100
```

## Checks after loading

These totals should match the DuckDB warehouse (seed 42):

| Check | Expected |
|---|---|
| `Target Value` (2025) | 550,565,475.90 SAR |
| `Sales Value` for 2023 / 2024 / 2025 | 247,270,676.35 / 383,029,004.55 / 506,727,689.75 SAR |
| `Attainment %`, total | 92.0% |
| `Payout % of Budget`, total, rule `issued` | 57.7% (no proration) |
| `WAPE %`, `backtest_1m_ahead`, by model | lgbm_hijri 13.4%, lgbm_gregorian 15.0%, ets 15.4%, seasonal_naive 46.1% |
| `Flagged Territories` by rule | issued 22, last_year_plus_x 25, potential_based 38 |

**WAPE here is value-weighted (SAR), so it differs from the report.** The README and REPORT.md quote unit-based WAPE pooled over horizons 1–3 (lgbm_hijri 10.4%). Value weighting gives Semavia, the most expensive product, more weight. Both are correct; label the dashboard card "WAPE (value, 1 month ahead)".
