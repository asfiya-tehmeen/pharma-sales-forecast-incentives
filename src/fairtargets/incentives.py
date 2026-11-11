"""Incentive simulation: compare target-setting rules on payout cost, payout Gini and fairness spread.

Both rules split the SAME national product budgets (the sum of the issued targets), so they
differ only in how the budget is shared across territories:
  * last_year_plus_x : share of last year's (2024) sales, i.e. LY x (1 + X%) with product-level X
  * potential_based  : share of territory potential (adults with diabetes, from public data)
The targets as issued (including the manager's manual changes) are reported for reference.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import targets as T
from .config import (FLAG_DELTA, PAYOUT_ACCELERATOR, PAYOUT_AT_THRESHOLD, PAYOUT_CAP,
                     PAYOUT_THRESHOLD, TARGET_BONUS_SAR)


def payout_pct(attainment):
    a = np.asarray(attainment, dtype=float)
    below = np.where(a < PAYOUT_THRESHOLD, 0.0,
                     PAYOUT_AT_THRESHOLD + (a - PAYOUT_THRESHOLD) / (1 - PAYOUT_THRESHOLD) * (1 - PAYOUT_AT_THRESHOLD))
    above = np.minimum(1.0 + PAYOUT_ACCELERATOR * (a - 1.0), PAYOUT_CAP)
    return np.where(a < 1.0, below, above)


def gini(x, axis=-1):
    """Gini coefficient along `axis` (0 = perfectly equal)."""
    x = np.sort(np.asarray(x, dtype=float), axis=axis)
    n = x.shape[axis]
    idx = np.arange(1, n + 1)
    shape = [1] * x.ndim
    shape[axis] = n
    idx = idx.reshape(shape)
    total = x.sum(axis=axis)
    g = (2 * (idx * x).sum(axis=axis) / (n * np.where(total == 0, 1, total))) - (n + 1) / n
    return np.where(total == 0, 0.0, g)


def rule_targets(panel: pd.DataFrame, issued: pd.DataFrame, potential: pd.Series) -> pd.DataFrame:
    """Annual territory targets under each rule (columns), same national product budgets."""
    budget = issued.groupby("product_code").target_value.sum()
    ly = panel[panel.m.between(13, 24)].groupby(["territory_code", "product_code"]).value_net.sum().unstack()
    ly_share = ly / ly.sum()
    pot_share = potential / potential.sum()
    out = pd.DataFrame({
        "issued": issued.groupby("territory_code").target_value.sum(),
        "last_year_plus_x": (ly_share * budget).sum(axis=1),
        "potential_based": pd.DataFrame({p: pot_share * budget[p] for p in budget.index}).sum(axis=1),
    })
    return out


def evaluate_rule(target: pd.Series, sims: pd.DataFrame, actual: pd.Series) -> dict:
    t = target.reindex(sims.columns)
    pct = T.percentiles(sims, t)
    fl = T.flag(pct)
    att = sims.to_numpy() / t.to_numpy()[None, :]
    pay = payout_pct(att) * TARGET_BONUS_SAR
    cost = pay.sum(axis=1)
    act_att = actual.reindex(sims.columns).to_numpy() / t.to_numpy()
    act_pay = payout_pct(act_att) * TARGET_BONUS_SAR
    budget = TARGET_BONUS_SAR * len(t)
    return {
        "fairness_spread_iqr_pp": float((pct.quantile(0.75) - pct.quantile(0.25)) * 100),
        "fairness_spread_sd_pp": float(pct.std() * 100),
        "n_flagged": int(fl.flag.sum()),
        "mc_cost_mean_pct_of_budget": float(cost.mean() / budget * 100),
        "mc_cost_p90_pct_of_budget": float(np.percentile(cost, 90) / budget * 100),
        "mc_gini_mean": float(gini(pay, axis=1).mean()),
        "mc_zero_payout_share_mean": float((pay == 0).mean()),
        "actual_cost_pct_of_budget": float(act_pay.sum() / budget * 100),
        "actual_gini": float(gini(act_pay)),
        "actual_zero_payout_reps": int((act_pay == 0).sum()),
        "actual_attainment_min": float(act_att.min()),
        "actual_attainment_max": float(act_att.max()),
        "flag_delta": FLAG_DELTA,
    }
