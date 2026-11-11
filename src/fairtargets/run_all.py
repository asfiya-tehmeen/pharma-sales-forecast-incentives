"""Run the whole project from one seed:  python -m fairtargets.run_all --seed 42

generate -> warehouse (SQL) -> forecast backtest -> fairness -> incentives -> effects
-> Power BI export -> figures -> scorecard (the only step that reads the answer key).
"""
from __future__ import annotations

import argparse
import json
import time
import warnings

import numpy as np
import pandas as pd

from . import effects, export_powerbi, figures, generator, incentives, scorecard, warehouse
from . import forecast as F
from . import targets as T
from .config import (BACKTEST_HORIZON, BACKTEST_ORIGINS, DEFAULT_SEED, FIGURES, HISTORY_END_MONTH,
                     MONTE_CARLO_DRAWS, RESULTS, TARGET_BONUS_SAR)

RAMADAN_WINDOW = [26, 27, 28]  # Feb-Apr 2025: pre-Ramadan, Ramadan + Eid al-Fitr, Eid al-Fitr tail


def _save(name, obj):
    (RESULTS / name).write_text(json.dumps(obj, indent=2, default=float))


def _acc_dict(df, key):
    return {r[key]: {"wape": r.wape, "bias": r.bias, "n": int(r.n)} for _, r in df.iterrows()}


def main(seed: int = DEFAULT_SEED) -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)
    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print("1/8 generate")
    world = generator.generate(seed)
    generator.write(world)

    print("2/8 warehouse")
    con = warehouse.build()
    dq = con.execute("select check_name, n_rows from silver.dq_summary order by check_name").df()
    con.close()
    _save("dq_summary.json", dict(zip(dq.check_name, dq.n_rows.astype(int))))

    panel, cal = F.load_panel(), F.load_month_calendar()

    print("3/8 forecast backtest")
    bt = F.backtest(panel, cal, BACKTEST_ORIGINS, BACKTEST_HORIZON)
    stock = F.detect_stockouts(panel, upto=panel.m.max())
    so_months = {m for ms in stock.values() for m in ms}
    by_prod = F.accuracy(bt, ["model", "product_code"])
    overall = F.accuracy(bt, ["model"])
    excl = F.accuracy(bt[~bt.m.isin(so_months)], ["model"])
    ram = F.accuracy(bt[bt.m.isin(RAMADAN_WINDOW)], ["model"])
    by_h = F.accuracy(bt, ["model", "h"])
    by_prod.to_csv(RESULTS / "forecast_accuracy_by_product.csv", index=False)
    by_h.to_csv(RESULTS / "forecast_accuracy_by_horizon.csv", index=False)
    _, model = F.lightgbm(F.unconstrain(panel[panel.m <= HISTORY_END_MONTH],
                                        F.detect_stockouts(panel, HISTORY_END_MONTH), HISTORY_END_MONTH),
                          cal, HISTORY_END_MONTH, 1, hijri=True, return_model=True)
    gain = pd.Series(model.feature_importance("gain"), index=model.feature_name())
    gain = (gain / gain.sum()).sort_values(ascending=False)
    best = overall.sort_values("wape").iloc[0].model
    _save("forecast_accuracy.json", {
        "overall": _acc_dict(overall, "model"),
        "excluding_stockout_months": _acc_dict(excl, "model"),
        "ramadan_window": _acc_dict(ram, "model"),
        "by_product": {m: _acc_dict(g, "product_code") for m, g in by_prod.groupby("model")},
        "stockout_months_detected": stock,
        "best_model_by_overall_wape": best,
        "lgbm_hijri_gain_share": gain.round(4).to_dict(),
        "hijri_features_gain_share": float(gain[gain.index.isin(F.HIJRI_FEATURES)].sum()),
        "backtest": {"origins": BACKTEST_ORIGINS, "horizon": BACKTEST_HORIZON, "rows": len(bt)},
    })

    print("4/8 fairness")
    resid = T.residual_matrix(panel, cal)
    tfc_raw = T.target_year_forecast(panel, cal)
    issued = T.issued_targets()
    actual = panel[panel.m > HISTORY_END_MONTH].groupby("territory_code").value_net.sum()
    # Run-1 method (unreconciled), kept for transparency.
    sims_raw = T.simulate(tfc_raw, resid, n=MONTE_CARLO_DRAWS, seed=seed)
    raw_fl = T.flag(T.percentiles(sims_raw, issued.groupby("territory_code").target_value.sum()))
    q_raw = sims_raw.quantile([0.1, 0.9]).T
    _save("fairness_unreconciled.json", {
        "note": "Run-1 method: 12-month LightGBM forecast NOT reconciled to the national budget.",
        "target_year_forecast_total_vs_actual": float(tfc_raw.forecast_value.sum() / actual.sum() - 1),
        "by_product_forecast_vs_actual": (tfc_raw.groupby("product_code").forecast_value.sum()
                                          / panel[panel.m > HISTORY_END_MONTH].groupby("product_code").value_net.sum()
                                          - 1).round(4).to_dict(),
        "median_percentile": float(raw_fl.target_percentile.median()),
        "n_flagged": int(raw_fl.flag.sum()),
        "flagged": raw_fl[raw_fl.flag].index.tolist(),
        "p10_p90_coverage_of_actual_2025": float(((actual >= q_raw[0.1]) & (actual <= q_raw[0.9])).mean()),
    })
    raw_fl.reset_index(names="territory_code").to_csv(RESULTS / "fairness_issued_unreconciled.csv", index=False)
    # Main method: reconcile territory forecasts to the national product budget (sum of issued targets).
    tfc = T.reconcile_to_budget(tfc_raw, issued.groupby("product_code").target_value.sum())
    sims = T.simulate(tfc, resid, n=MONTE_CARLO_DRAWS, seed=seed)
    pot = panel.drop_duplicates("territory_code").set_index("territory_code").potential_diabetics
    rules = incentives.rule_targets(panel, issued, pot)
    q = sims.quantile([0.1, 0.5, 0.9]).T
    q.columns = ["forecast_p10", "forecast_p50", "forecast_p90"]
    frames = []
    for rule in rules.columns:
        fl = T.flag(T.percentiles(sims, rules[rule]))
        fl = fl.join(q).assign(rule=rule, annual_target=rules[rule], actual_2025=actual)
        frames.append(fl.reset_index(names="territory_code"))
    fair_all = pd.concat(frames, ignore_index=True)
    fair_issued = fair_all[fair_all.rule == "issued"]
    fair_issued.to_csv(RESULTS / "fairness_issued.csv", index=False)
    fair_all.to_csv(RESULTS / "fairness_all_rules.csv", index=False)
    within = ((actual >= q.forecast_p10) & (actual <= q.forecast_p90)).mean()
    _save("fairness.json", {
        "n_territories": len(fair_issued),
        "n_flagged_issued": int(fair_issued.flag.sum()),
        "flagged": fair_issued[fair_issued.flag][["territory_code", "direction", "target_percentile"]]
        .to_dict("records"),
        "median_percentile_issued": float(fair_issued.target_percentile.median()),
        "p10_p90_coverage_of_actual_2025": float(within),
        "residual_months_used": [int(c) for c in resid.columns],
        "target_year_forecast_total_vs_actual": float(tfc.forecast_value.sum() / actual.sum() - 1),
    })

    print("5/8 incentives")
    results, costs, spread = {}, {}, {}
    for rule in rules.columns:
        results[rule] = incentives.evaluate_rule(rules[rule], sims, actual)
        att = sims.to_numpy() / rules[rule].reindex(sims.columns).to_numpy()[None, :]
        costs[rule] = incentives.payout_pct(att).sum(axis=1) * TARGET_BONUS_SAR / (TARGET_BONUS_SAR * len(rules)) * 100
        spread[rule] = results[rule]["fairness_spread_iqr_pp"]
    _save("incentives.json", results)

    print("6/8 effects")
    _save("effects.json", effects.estimate_all(panel, cal))

    print("7/8 power bi export + figures")
    export_powerbi.export(bt, tfc, fair_all)
    figures.national_sales(panel, cal, stock)
    figures.wape_by_model(by_prod)
    figures.target_percentiles(fair_issued.set_index("territory_code"))
    figures.rule_comparison(costs, spread)

    print("8/8 scorecard (reads answer key)")
    sc = scorecard.score()
    for r in sc["rows"]:
        print(f"  {r['status']:>20}  {r['effect']}")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    main(ap.parse_args().seed)
