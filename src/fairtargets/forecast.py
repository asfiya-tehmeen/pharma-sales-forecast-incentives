"""Forecasting ladder: seasonal naive -> ETS -> global LightGBM (Gregorian-only and Hijri-aware).

Everything here uses only the warehouse (what a real analyst would have). No answer key.

Series grain: territory x product x month, units_net.
Training data is "unconstrained" first: months detected as national stock-outs are replaced by
the average of the nearest normal months, so models learn demand rather than the supply cap.
Accuracy is always measured against recorded sales.
"""
from __future__ import annotations

import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd

from .calendar import month_index
from .config import START, WAREHOUSE
from .warehouse import query

STOCKOUT_RATIO = 0.60  # flag a month whose national sales are < 60% of the median of its +/-2 neighbours
LGB_ROUNDS = 400
LGB_PARAMS = dict(objective="regression", learning_rate=0.03, num_leaves=15, min_data_in_leaf=20,
                  bagging_fraction=0.8, bagging_freq=1, feature_fraction=0.8, seed=0,
                  deterministic=True, force_row_wise=True, num_threads=1, verbose=-1)
HIJRI_FEATURES = ["ramadan_share", "pre_ramadan_share", "eid_share",
                  "ramadan_share_l12", "pre_ramadan_share_l12", "eid_share_l12"]
GREG_FEATURES = ["month"]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_panel(db=WAREHOUSE) -> pd.DataFrame:
    df = query("""
        select s.territory_code, s.product_code, s.month_start, s.units_net, s.value_net,
               s.rep_id is not null as rep_present,
               t.country, t.potential_diabetics, p.list_price_sar, p.launch_month, p.generic_entry_month
        from gold.fact_sales s
        join gold.dim_territory t using (territory_code)
        join gold.dim_product p using (product_code)
        order by 1, 2, 3""", db)
    df["month_start"] = pd.to_datetime(df.month_start)
    df["m"] = month_index(df.month_start, START)
    df["value_net"] = df.value_net.astype(float)
    df["list_price_sar"] = df.list_price_sar.astype(float)
    return df


def load_month_calendar(db=WAREHOUSE) -> pd.DataFrame:
    cal = query("select * from gold.dim_month order by month_start", db)
    cal["month_start"] = pd.to_datetime(cal.month_start)
    cal["m"] = month_index(cal.month_start, START)
    for c in ("ramadan", "pre_ramadan", "eid"):
        cal[f"{c}_share"] = cal[f"{c}_days"] / cal.days_in_month
    return cal


# ---------------------------------------------------------------------------
# Stock-out detection and unconstraining
# ---------------------------------------------------------------------------
def detect_stockouts(panel: pd.DataFrame, upto: int) -> dict[str, list[int]]:
    """National months whose sales fall below STOCKOUT_RATIO x median of the +/-2 neighbouring months."""
    nat = panel[panel.m <= upto].groupby(["product_code", "m"]).units_net.sum()
    flags = {}
    for prod, s in nat.groupby(level=0):
        s = s.droplevel(0)
        s = s[s > 0]
        out = []
        for m in s.index:
            nb = s[(s.index >= m - 2) & (s.index <= m + 2) & (s.index != m)]
            if len(nb) >= 2 and s[m] < STOCKOUT_RATIO * nb.median():
                out.append(int(m))
        flags[prod] = out
    return flags


def unconstrain(panel: pd.DataFrame, flags: dict[str, list[int]], upto: int) -> pd.DataFrame:
    """Replace flagged months with the mean of the nearest unflagged months (before and after, <= upto)."""
    df = panel.copy()
    df["units_train"] = df.units_net.astype(float)
    for prod, months in flags.items():
        if not months:
            continue
        bad = set(months)
        sel = df.product_code == prod
        for terr, g in df[sel].groupby("territory_code"):
            s = g.set_index("m").units_net.astype(float)
            for m in months:
                before = [k for k in range(m - 1, 0, -1) if k not in bad and k in s.index]
                after = [k for k in range(m + 1, upto + 1) if k not in bad and k in s.index]
                vals = [s[before[0]]] if before else []
                if after:
                    vals.append(s[after[0]])
                if vals:
                    df.loc[g.index[g.m == m], "units_train"] = float(np.mean(vals))
    return df


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def seasonal_naive(train: pd.DataFrame, origin: int, horizon: int) -> pd.DataFrame:
    s = train.pivot_table(index=["territory_code", "product_code"], columns="m", values="units_train")
    out = []
    for h in range(1, horizon + 1):
        m = origin + h
        out.append(s[m - 12].rename("forecast").reset_index().assign(m=m, h=h))
    return pd.concat(out, ignore_index=True)


def ets(train: pd.DataFrame, origin: int, horizon: int) -> pd.DataFrame:
    from statsforecast import StatsForecast
    from statsforecast.models import AutoETS

    df = train[(train.m <= origin)].copy()
    df = df[df.month_start >= df.launch_month.fillna(pd.Timestamp(START))]  # drop pre-launch zeros
    df["unique_id"] = df.territory_code + "|" + df.product_code
    sf_in = df.rename(columns={"month_start": "ds", "units_train": "y"})[["unique_id", "ds", "y"]]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sf = StatsForecast(models=[AutoETS(season_length=12)], freq="MS", n_jobs=1)
        fc = sf.forecast(df=sf_in, h=horizon)
    fc = fc.reset_index() if "unique_id" not in fc.columns else fc
    fc[["territory_code", "product_code"]] = fc.unique_id.str.split("|", expand=True)
    fc["m"] = month_index(pd.to_datetime(fc.ds), START)
    fc["h"] = fc.m - origin
    fc["forecast"] = fc.AutoETS.clip(lower=0)
    return fc[["territory_code", "product_code", "forecast", "m", "h"]]


def _features(df: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Features for every row, computed from units_train (lags) and the calendar."""
    df = df.sort_values(["territory_code", "product_code", "m"]).copy()
    g = df.groupby(["territory_code", "product_code"]).units_train
    for k in (1, 2, 3, 12):
        df[f"lag{k}"] = g.shift(k)
    df["level"] = df[["lag1", "lag2", "lag3"]].mean(axis=1)
    df["lag1_rel"] = np.log1p(df.lag1) - np.log1p(df.level)
    df["lag12_rel"] = np.log1p(df.lag12) - np.log1p(df.level)
    df["log_level"] = np.log1p(df.level)
    df["log_potential"] = np.log(df.potential_diabetics)
    df["is_uae"] = (df.country == "UAE").astype(int)
    df["prod"] = df.product_code.map({"GLU": 0, "SEM": 1, "CAR": 2})
    launch = month_index(pd.to_datetime(df.launch_month), START)
    entry = month_index(pd.to_datetime(df.generic_entry_month), START)
    df["months_since_launch"] = (df.m - launch).where(launch.notna())
    df["months_since_entry"] = (df.m - entry).where(entry.notna() & (df.m >= entry))
    c = cal.set_index("m")
    for col in ("ramadan_share", "pre_ramadan_share", "eid_share", "month"):
        df[col] = df.m.map(c[col])
    for col in ("ramadan_share", "pre_ramadan_share", "eid_share"):
        df[f"{col}_l12"] = (df.m - 12).map(c[col])
    df["rep_present"] = df.rep_present.astype(int)
    return df


BASE_FEATURES = ["lag1_rel", "lag12_rel", "log_level", "log_potential", "is_uae", "prod",
                 "months_since_launch", "months_since_entry", "rep_present"]


def feature_list(hijri: bool) -> list[str]:
    return BASE_FEATURES + GREG_FEATURES + (HIJRI_FEATURES if hijri else [])


def lightgbm(train: pd.DataFrame, cal: pd.DataFrame, origin: int, horizon: int, hijri: bool = True,
             return_model: bool = False):
    """Global LightGBM on log(y+1) - log(level+1), forecast recursively for `horizon` months."""
    feats = feature_list(hijri)
    work = train[train.m <= origin].copy()
    fe = _features(work, cal)
    fe = fe[(fe.m >= 4) & fe.level.notna()]
    fe = fe[fe.month_start >= fe.launch_month.fillna(pd.Timestamp(START)) + pd.DateOffset(months=3)]
    y = np.log1p(fe.units_train) - np.log1p(fe.level)
    model = lgb.train(LGB_PARAMS, lgb.Dataset(fe[feats], y, categorical_feature=["prod"]),
                      num_boost_round=LGB_ROUNDS)

    # Recursive forecast: future months assume a rep is in place (vacancies are not known in advance).
    hist = work.copy()
    template = train.drop_duplicates(["territory_code", "product_code"]).copy()
    out = []
    for h in range(1, horizon + 1):
        m = origin + h
        nxt = template.assign(m=m, units_train=np.nan, rep_present=True,
                              month_start=pd.Timestamp(START) + pd.DateOffset(months=m - 1))
        frame = pd.concat([hist, nxt], ignore_index=True)
        f = _features(frame, cal)
        f = f[f.m == m]
        pred = np.clip(np.expm1(model.predict(f[feats]) + np.log1p(f.level.to_numpy())), 0, None)
        launched = f.month_start >= f.launch_month.fillna(pd.Timestamp(START))
        pred = np.where(launched, pred, 0.0)
        res = f[["territory_code", "product_code"]].assign(forecast=pred, m=m, h=h)
        out.append(res)
        hist = pd.concat([hist, nxt.drop(columns="units_train").merge(
            res[["territory_code", "product_code", "forecast"]], on=["territory_code", "product_code"]
        ).rename(columns={"forecast": "units_train"})], ignore_index=True)
    fc = pd.concat(out, ignore_index=True)
    return (fc, model) if return_model else fc


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
MODELS = ("seasonal_naive", "ets", "lgbm_gregorian", "lgbm_hijri")


def run_model(name, train, cal, origin, horizon):
    if name == "seasonal_naive":
        return seasonal_naive(train, origin, horizon)
    if name == "ets":
        return ets(train, origin, horizon)
    if name == "lgbm_gregorian":
        return lightgbm(train, cal, origin, horizon, hijri=False)
    if name == "lgbm_hijri":
        return lightgbm(train, cal, origin, horizon, hijri=True)
    raise ValueError(name)


def backtest(panel: pd.DataFrame, cal: pd.DataFrame, origins, horizon, models=MODELS) -> pd.DataFrame:
    rows = []
    last = panel.m.max()
    for o in origins:
        flags = detect_stockouts(panel, upto=o)
        train = unconstrain(panel[panel.m <= o], flags, upto=o)
        h = min(horizon, last - o)
        for name in models:
            fc = run_model(name, train, cal, o, h).assign(model=name, origin=o)
            rows.append(fc)
    fc = pd.concat(rows, ignore_index=True)
    act = panel[["territory_code", "product_code", "m", "units_net", "list_price_sar"]]
    fc = fc.merge(act, on=["territory_code", "product_code", "m"])
    fc["actual"] = fc.units_net.astype(float)
    return fc.drop(columns="units_net")


def accuracy(fc: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    g = fc.assign(abs_err=(fc.forecast - fc.actual).abs(), err=fc.forecast - fc.actual).groupby(by)
    out = pd.DataFrame({"wape": g.abs_err.sum() / g.actual.sum(), "bias": g.err.sum() / g.actual.sum(),
                        "n": g.size()})
    return out.reset_index()
