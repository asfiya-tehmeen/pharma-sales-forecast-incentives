"""Export the star schema for Power BI as CSV (reports/powerbi/)."""
from __future__ import annotations

import pandas as pd

from .config import POWERBI, START, WAREHOUSE
from .warehouse import query

TABLES = {
    "fact_sales": "select * from gold.fact_sales order by 1, 2, 3",
    "fact_targets": "select * from gold.fact_targets order by 1, 2, 3",
    "dim_rep": "select * from gold.dim_rep order by 1",
    "dim_territory": "select * from gold.dim_territory order by 1",
    "dim_product": "select * from gold.dim_product order by 1",
    "dim_date": """select date, year, month, month_start, day_of_week,
                          hijri_year, hijri_month, hijri_day, hijri_month_name,
                          is_ramadan, is_pre_ramadan, is_eid_fitr, is_eid_adha, is_eid,
                          is_holiday_ksa, holiday_name_ksa, is_holiday_uae, holiday_name_uae,
                          is_weekend_ksa, is_weekend_uae, is_workday_ksa, is_workday_uae
                   from gold.dim_date order by date""",
}


def export(backtest: pd.DataFrame, target_fc: pd.DataFrame, fairness: pd.DataFrame, db=WAREHOUSE) -> list[str]:
    POWERBI.mkdir(parents=True, exist_ok=True)
    written = []
    for name, sql in TABLES.items():
        query(sql, db).to_csv(POWERBI / f"{name}.csv", index=False)
        written.append(name)

    # Forecasts: 1-month-ahead backtest forecasts (all models) + the 2025 target-year forecast.
    bt = backtest[backtest.h == 1].copy()
    bt["forecast_type"] = "backtest_1m_ahead"
    tf = target_fc.assign(model="lgbm_hijri", forecast_type="target_year_from_dec_2024")
    tf = tf.merge(backtest[["territory_code", "product_code", "m", "actual", "list_price_sar"]]
                  .drop_duplicates(["territory_code", "product_code", "m"]),
                  on=["territory_code", "product_code", "m"], how="left")
    cols = ["forecast_type", "model", "territory_code", "product_code", "month_start",
            "forecast_units", "actual_units", "forecast_value", "actual_value"]
    out = []
    for d in (bt, tf):
        d = d.copy()
        d["month_start"] = [(pd.Timestamp(START) + pd.DateOffset(months=int(i) - 1)).date() for i in d.m]
        d["forecast_units"] = d.forecast.round(1)
        d["actual_units"] = d.actual
        d["forecast_value"] = (d.forecast * d.list_price_sar).round(2)
        d["actual_value"] = (d.actual * d.list_price_sar).round(2)
        out.append(d[cols])
    pd.concat(out).to_csv(POWERBI / "fact_forecast.csv", index=False)
    written.append("fact_forecast")

    fairness.to_csv(POWERBI / "fact_fairness.csv", index=False)
    written.append("fact_fairness")
    return written
