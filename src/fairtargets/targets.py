"""Fairness core: where does each territory's target sit in its own forecast distribution?

A target is fair when every rep has about the same probability of hitting it.

1. Point forecast: Hijri-aware LightGBM trained on data through Dec 2024 (month 24), forecasting
   the 12 months of 2025 recursively. It never sees 2025 actuals.
2. Uncertainty: one-step-ahead backtest residuals for Jan-Dec 2024 (log actual/forecast, territory
   value level). Months flagged as stock-outs are excluded; vacancy months are excluded (a vacancy
   is an event, not normal noise).
3. Simulation: each simulated year draws 12 residual months jointly for all territories (keeps the
   cross-territory correlation of a national shock): sim_t = sum_m forecast_tm * exp(R[t, k_m]).
4. Target percentile = share of simulated years below the target = P(missing the target).
5. Flag: |percentile - median percentile| >= FLAG_DELTA (pre-registered in config.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import forecast as F
from .config import FLAG_DELTA, HISTORY_END_MONTH, MONTE_CARLO_DRAWS, WAREHOUSE
from .warehouse import query

RESIDUAL_ORIGINS = range(12, HISTORY_END_MONTH)  # one-step forecasts for months 13..24


def _value(fc: pd.DataFrame, col: str) -> pd.Series:
    return (fc[col] * fc.list_price_sar).groupby([fc.territory_code, fc.m]).sum()


def residual_matrix(panel: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    fc = F.backtest(panel[panel.m <= HISTORY_END_MONTH], cal, RESIDUAL_ORIGINS, 1, models=["lgbm_hijri"])
    flags = F.detect_stockouts(panel, upto=HISTORY_END_MONTH)
    bad_months = sorted({m for ms in flags.values() for m in ms})
    r = np.log(_value(fc, "actual") / _value(fc, "forecast")).unstack("m")
    r = r.drop(columns=[m for m in bad_months if m in r.columns])
    vac = panel[(~panel.rep_present) & panel.m.isin(r.columns)][["territory_code", "m"]].drop_duplicates()
    for t, m in vac.itertuples(index=False):
        r.loc[t, m] = np.nan
    return r.apply(lambda row: row.fillna(row.median()), axis=1)


def target_year_forecast(panel: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    o = HISTORY_END_MONTH
    hist = panel[panel.m <= o]
    train = F.unconstrain(hist, F.detect_stockouts(panel, upto=o), upto=o)
    fc = F.lightgbm(train, cal, o, 12, hijri=True)
    prices = panel.drop_duplicates("product_code").set_index("product_code").list_price_sar
    fc["forecast_value"] = fc.forecast * fc.product_code.map(prices)
    return fc


def reconcile_to_budget(fc: pd.DataFrame, budget_by_product: pd.Series) -> pd.DataFrame:
    """Top-down reconciliation: scale each product's territory forecasts so they sum to the national budget.

    The national budget is a company decision; the forecast's job in target setting is to say how
    that budget should be SPLIT across territories and how uncertain each territory is.
    (Added after run 1, where the unreconciled 12-month forecast overshot 2025 by 26% and pushed
    every target percentile to ~0. Disclosed in REPORT.md.)
    """
    fc = fc.copy()
    nat = fc.groupby("product_code").forecast_value.sum()
    scale = budget_by_product.reindex(nat.index) / nat
    fc["forecast_value"] = fc.forecast_value * fc.product_code.map(scale)
    fc["forecast"] = fc.forecast * fc.product_code.map(scale)
    return fc


def simulate(fc: pd.DataFrame, resid: pd.DataFrame, n: int = MONTE_CARLO_DRAWS, seed: int = 0) -> pd.DataFrame:
    """Simulated annual sales value per territory (n draws x territories)."""
    f = fc.groupby(["territory_code", "m"]).forecast_value.sum().unstack("m")
    resid = resid.loc[f.index]
    R = resid.to_numpy()
    rng = np.random.default_rng(seed)
    k = rng.integers(0, R.shape[1], size=(n, f.shape[1]))
    sims = np.zeros((n, len(f)))
    for j in range(f.shape[1]):
        sims += f.to_numpy()[:, j][None, :] * np.exp(R[:, k[:, j]].T)
    return pd.DataFrame(sims, columns=f.index)


def percentiles(sims: pd.DataFrame, targets: pd.Series) -> pd.Series:
    t = targets.reindex(sims.columns)
    return pd.Series((sims.to_numpy() < t.to_numpy()[None, :]).mean(axis=0), index=sims.columns)


def flag(pct: pd.Series, delta: float = FLAG_DELTA) -> pd.DataFrame:
    med = pct.median()
    out = pd.DataFrame({"target_percentile": pct, "gap_vs_median": pct - med})
    out["flag"] = out.gap_vs_median.abs() >= delta
    out["direction"] = np.where(~out.flag, "", np.where(out.gap_vs_median > 0, "hard", "easy"))
    return out


def issued_targets(db=WAREHOUSE) -> pd.DataFrame:
    t = query("select territory_code, product_code, sum(target_value) as target_value "
              "from gold.fact_targets group by all order by 1, 2", db)
    t["target_value"] = t.target_value.astype(float)
    return t
