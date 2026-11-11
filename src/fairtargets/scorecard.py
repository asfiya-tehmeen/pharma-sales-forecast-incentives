"""Final scoring step: the ONLY analysis module allowed to read the hidden answer key.

Compares the estimates in reports/results/*.json (produced without the key) with the planted truth.
Pass/fail criteria are fixed here and do not change after seeing results.
"""
from __future__ import annotations

import json

import pandas as pd

from .calendar import month_index
from .config import ANSWER_KEY, REPORTS, RESULTS, START


def _status(ok: bool, partial: bool = False) -> str:
    return "recovered" if ok else ("partially recovered" if partial else "missed")


def _m(date_str: str) -> int:
    return int(month_index(pd.Series(pd.to_datetime([date_str])), START).iloc[0])


def score() -> dict:
    key = json.loads(ANSWER_KEY.read_text())
    eff = json.loads((RESULTS / "effects.json").read_text())
    fc = json.loads((RESULTS / "forecast_accuracy.json").read_text())
    fair = pd.read_csv(RESULTS / "fairness_issued.csv")
    dq = json.loads((RESULTS / "dq_summary.json").read_text())
    rows = []

    # E1 Ramadan / Eid
    planted = key["E1_ramadan_eid"]["daily_multipliers"]
    est = eff["E1_ramadan_eid"]
    inside = {k: est[k]["ci95_multiplier"][0] <= planted[k] <= est[k]["ci95_multiplier"][1] for k in planted}
    hijri_wins = fc["ramadan_window"]["lgbm_hijri"]["wape"] < fc["ramadan_window"]["lgbm_gregorian"]["wape"]
    rows.append({
        "effect": "E1 Ramadan / pre-Ramadan / Eid (Hijri)",
        "planted": ", ".join(f"{k} x{v}" for k, v in planted.items()),
        "estimated": ", ".join(f"{k} x{est[k]['implied_daily_multiplier']:.2f} "
                               f"(95% CI {est[k]['ci95_multiplier'][0]:.2f}-{est[k]['ci95_multiplier'][1]:.2f})"
                               for k in planted)
                     + f"; Hijri LightGBM WAPE in Feb-Apr 2025 {fc['ramadan_window']['lgbm_hijri']['wape']:.1%} vs "
                       f"Gregorian {fc['ramadan_window']['lgbm_gregorian']['wape']:.1%}",
        "status": _status(all(inside.values()) and hijri_wins, any(inside.values()) or hijri_wins),
    })

    # E2 launch ramp
    k2, e2 = key["E2_launch"], eff["E2_launch"]
    ok = abs(e2["t_mid_month"] - k2["t_mid"]) <= 1 and abs(e2["scale"] - k2["scale"]) <= 1
    rows.append({"effect": "E2 Semavia launch ramp",
                 "planted": f"midpoint month {k2['t_mid']}, scale {k2['scale']}",
                 "estimated": f"midpoint month {e2['t_mid_month']:.1f}, scale {e2['scale']:.2f}",
                 "status": _status(ok, abs(e2["t_mid_month"] - k2["t_mid"]) <= 2)})

    # E3 stock-outs
    planted_m = set(key["E3_stockout"]["months"])
    found = set(eff["E3_stockout_months"].get("SEM", []))
    found_all = {(p, m) for p, ms in eff["E3_stockout_months"].items() for m in ms}
    tp = len(planted_m & found)
    prec = tp / len(found_all) if found_all else 0.0
    rec = tp / len(planted_m)
    rows.append({"effect": "E3 Semavia stock-out months", "planted": f"months {sorted(planted_m)}",
                 "estimated": f"flagged {sorted(found_all)}; precision {prec:.0%}, recall {rec:.0%}",
                 "status": _status(prec == 1 and rec == 1, rec > 0)})

    # E4 generic entry
    k4, e4 = key["E4_generic_entry"], eff["E4_generic_entry"]
    ok = abs(e4["entry_month"] - k4["month"]) <= 1 and abs(e4["max_loss"] - k4["max_loss"]) <= 0.10
    rows.append({"effect": "E4 Glucora generic entry",
                 "planted": f"month {k4['month']}, max volume loss {k4['max_loss']:.0%}, tau {k4['tau']}",
                 "estimated": f"month {e4['entry_month']}, max volume loss {e4['max_loss']:.0%}, tau {e4['tau']}",
                 "status": _status(ok, abs(e4["entry_month"] - k4["month"]) <= 2)})

    # E5 vacancies
    k5, e5 = key["E5_vacancies"], eff["E5_vacancy"]
    planted_w = {(w["territory_code"], w["first_month"], w["last_month"]) for w in k5["windows"]}
    found_w = {(w["territory_code"], w["first_month"], w["last_month"]) for w in e5["vacancy_windows_from_roster"]}
    in_ci = e5["ci95"][0] <= k5["sales_multiplier"] <= e5["ci95"][1]
    rows.append({"effect": "E5 Rep vacancies", "planted": f"{len(planted_w)} windows, sales x{k5['sales_multiplier']}",
                 "estimated": f"{len(planted_w & found_w)}/{len(planted_w)} windows matched from roster; "
                              f"sales x{e5['sales_multiplier']:.3f} (95% CI {e5['ci95'][0]:.3f}-{e5['ci95'][1]:.3f})",
                 "status": _status(in_ci and planted_w == found_w,
                                   abs(e5["sales_multiplier"] - k5["sales_multiplier"]) <= 0.10)})

    # E6 unfair targets
    truth = {u["territory_code"]: u["direction"] for u in key["E6_unfair_targets"]}
    flagged = dict(zip(fair[fair.flag].territory_code, fair[fair.flag].direction))
    tp = [t for t in flagged if t in truth]
    right_dir = [t for t in tp if flagged[t] == truth[t]]
    prec = len(tp) / len(flagged) if flagged else 0.0
    rec = len(tp) / len(truth)
    fp = sorted(set(flagged) - set(truth))
    fn = sorted(set(truth) - set(flagged))
    rows.append({"effect": "E6 Unfairly targeted territories",
                 "planted": f"{len(truth)} territories ({sum(v == 'easy' for v in truth.values())} easy, "
                            f"{sum(v == 'hard' for v in truth.values())} hard)",
                 "estimated": f"{len(flagged)} flagged; precision {prec:.0%}, recall {rec:.0%}, "
                              f"direction correct {len(right_dir)}/{len(tp)}; "
                              f"false positives {fp or 'none'}; missed {fn or 'none'}",
                 "status": _status(prec >= 0.8 and rec >= 0.8, rec >= 0.4)})

    # Data quality
    m = key["messiness"]
    checks = {
        "quarantined_non_positive_sale": m["invalid_negative_sale_rows"],
        "quarantined_unknown_product": m["orphan_product_rows"],
        "duplicate_rows_removed": m["duplicate_rows_same_file"] + m["duplicate_rows_resent"],
        "restated_lines_resolved": m["restated_lines"],
        "valid_return_lines_kept": m["valid_return_lines"],
    }
    match = {k: dq.get(k) == v for k, v in checks.items()}
    rows.append({"effect": "Feed messiness (data validation)",
                 "planted": "; ".join(f"{k} {v}" for k, v in checks.items()),
                 "estimated": "; ".join(f"{k} {dq.get(k)}" for k in checks),
                 "status": _status(all(match.values()), any(match.values()))})

    out = {"rows": rows, "unfair_precision": prec, "unfair_recall": rec,
           "unfair_false_positives": fp, "unfair_missed": fn}
    (RESULTS / "scorecard.json").write_text(json.dumps(out, indent=2))
    md = ["# Effect recovery scorecard", "",
          "> Simulated data. This compares estimates made WITHOUT the answer key against the planted truth.", "",
          "| Effect | Planted | Estimated from data | Status |", "|---|---|---|---|"]
    md += [f"| {r['effect']} | {r['planted']} | {r['estimated']} | **{r['status']}** |" for r in rows]
    (REPORTS / "SCORECARD.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return out
