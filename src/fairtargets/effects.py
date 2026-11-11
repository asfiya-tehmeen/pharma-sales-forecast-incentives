"""Estimate market effects from the warehouse only (no answer key).

The scorecard later compares these estimates with the planted values.
  E1 Ramadan / pre-Ramadan / Eid : panel OLS on the control product (Cardivex)
  E2 launch ramp                 : logistic fit to national Semavia sales (stock-outs removed)
  E3 stock-outs                  : forecast.detect_stockouts on the full history
  E4 generic entry               : change-point search on log(Glucora / Cardivex)
  E5 vacancy effect              : two-way fixed-effects regression with a roster-based vacancy flag
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from . import forecast as F


def _ols(X: np.ndarray, y: np.ndarray):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - np.linalg.matrix_rank(X)
    sigma2 = resid @ resid / dof
    cov = sigma2 * np.linalg.pinv(X.T @ X)
    return beta, np.sqrt(np.diag(cov))


def _dummies(s: pd.Series, prefix: str, drop_first=True) -> pd.DataFrame:
    return pd.get_dummies(s.astype(str), prefix=prefix, drop_first=drop_first, dtype=float)


def ramadan_effect(panel: pd.DataFrame, cal: pd.DataFrame) -> dict:
    d = panel[(panel.product_code == "CAR") & panel.rep_present & (panel.units_net > 0)].copy()
    c = cal.set_index("m")
    for col in ("ramadan_share", "pre_ramadan_share", "eid_share"):
        d[col] = d.m.map(c[col])
    d["month"] = d.m.map(c["month"])
    X = pd.concat([
        pd.Series(1.0, index=d.index, name="const"),
        (d.m / 12.0).rename("trend"),
        _dummies(d.territory_code, "t"),
        _dummies(d.month, "mo"),
        d[["ramadan_share", "pre_ramadan_share", "eid_share"]],
    ], axis=1)
    beta, se = _ols(X.to_numpy(), np.log(d.units_net.to_numpy(dtype=float)))
    names = list(X.columns)
    out = {}
    for k in ("ramadan_share", "pre_ramadan_share", "eid_share"):
        i = names.index(k)
        out[k.replace("_share", "")] = {
            "log_coef": float(beta[i]), "se": float(se[i]),
            "implied_daily_multiplier": float(np.exp(beta[i])),
            "ci95_multiplier": [float(np.exp(beta[i] - 1.96 * se[i])), float(np.exp(beta[i] + 1.96 * se[i]))],
        }
    return out


def _logistic(m, k, t0, s):
    return k / (1 + np.exp(-(m - t0) / s))


def launch_ramp(panel: pd.DataFrame) -> dict:
    flags = F.detect_stockouts(panel, upto=panel.m.max())["SEM"]
    nat = panel[panel.product_code == "SEM"].groupby("m").units_net.sum()
    nat = nat[(nat > 0) & ~nat.index.isin(flags)]
    p, cov = curve_fit(_logistic, nat.index.to_numpy(float), nat.to_numpy(float),
                       p0=[nat.max(), 18, 3], maxfev=20000)
    se = np.sqrt(np.diag(cov))
    return {"t_mid_month": float(p[1]), "t_mid_se": float(se[1]), "scale": float(p[2]), "scale_se": float(se[2]),
            "first_month_with_sales": int(nat.index.min())}


def generic_entry(panel: pd.DataFrame) -> dict:
    """Grid search over entry month k and decay tau for log(GLU/CAR) = a + b * erosion_k,tau(m)."""
    nat = panel.groupby(["product_code", "m"]).units_net.sum().unstack(0)
    y = np.log(nat.GLU / nat.CAR).to_numpy()
    m = nat.index.to_numpy(float)
    best = None
    for k in range(6, int(m.max()) - 3):
        for tau in np.arange(1.0, 10.01, 0.5):
            x = np.where(m >= k, 1 - np.exp(-(m - k) / tau), 0.0)
            X = np.column_stack([np.ones_like(m), x])
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            sse = float(((y - X @ beta) ** 2).sum())
            if best is None or sse < best[0]:
                best = (sse, k, tau, beta)
    _, k, tau, beta = best
    return {"entry_month": int(k), "tau": float(tau), "max_loss": float(1 - np.exp(beta[1]))}


def vacancy_effect(panel: pd.DataFrame) -> dict:
    d = panel[(panel.units_net > 0)].copy()
    d = d[~((d.product_code == "SEM") & d.m.isin(F.detect_stockouts(panel, panel.m.max())["SEM"]))]
    X = pd.concat([
        pd.Series(1.0, index=d.index, name="const"),
        _dummies(d.territory_code + "|" + d.product_code, "tp"),
        _dummies(d.product_code + "|" + d.m.astype(str), "pm"),
        (~d.rep_present).astype(float).rename("vacant"),
    ], axis=1)
    beta, se = _ols(X.to_numpy(), np.log(d.units_net.to_numpy(dtype=float)))
    i = list(X.columns).index("vacant")
    vac = panel.loc[~panel.rep_present, ["territory_code", "month_start"]].drop_duplicates()
    windows = vac.groupby("territory_code").month_start.agg(["min", "max", "count"]).reset_index()
    return {"sales_multiplier": float(np.exp(beta[i])),
            "ci95": [float(np.exp(beta[i] - 1.96 * se[i])), float(np.exp(beta[i] + 1.96 * se[i]))],
            "vacancy_windows_from_roster": [
                {"territory_code": r.territory_code, "first_month": str(r["min"].date()),
                 "last_month": str(r["max"].date()), "months": int(r["count"])} for _, r in windows.iterrows()]}


def estimate_all(panel: pd.DataFrame, cal: pd.DataFrame) -> dict:
    return {
        "E1_ramadan_eid": ramadan_effect(panel, cal),
        "E2_launch": launch_ramp(panel),
        "E3_stockout_months": F.detect_stockouts(panel, upto=panel.m.max()),
        "E4_generic_entry": generic_entry(panel),
        "E5_vacancy": vacancy_effect(panel),
    }
