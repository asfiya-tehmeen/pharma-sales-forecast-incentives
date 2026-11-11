"""Seeded generator for the simulated "Nakheel Pharma" affiliate (fictional).

Produces, from a single seed:
  * a messy monthly distributor feed (one CSV per delivery file),
  * master data (territories, rep roster, products),
  * the year-3 targets as issued by the company,
  * the hidden answer key (planted effects + messiness counts).

The clean ledger (the truth the warehouse should recover) is returned in memory for tests;
it is never written to disk.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import calibration
from .calendar import build_dim_date, build_month_calendar, month_index
from .config import ANSWER_KEY, DATA_RAW, DEFAULT_SEED, HISTORY_END_MONTH, N_MONTHS, N_TERRITORIES, START

# ---------------------------------------------------------------------------
# Planted world parameters (hidden; copied into the answer key)
# ---------------------------------------------------------------------------
PRODUCTS = {
    # code: name, role, molecule class
    "GLU": ("Glucora", "mature brand, generic entry", "DPP-4 inhibitor"),
    "SEM": ("Semavia", "launch with stock-outs", "GLP-1 injectable"),
    "CAR": ("Cardivex", "stable control", "statin"),
}
# Monthly packs per adult with diabetes in the territory (company uptake; assumption A5)
UPTAKE = {"GLU": 0.020, "SEM": 0.010, "CAR": 0.030}
MARKET_GROWTH = 0.05  # annual volume growth, from GTAI/Fitch ~5%/yr for KSA (S5); UAE assumed equal

DAILY_EFFECTS = {"ramadan": 0.85, "pre_ramadan": 1.10, "eid": 0.40}  # E1 multipliers per day
SUMMER = {7: 0.92, 8: 0.92}  # Gregorian summer dip (expat travel), not tested as a planted effect
LAUNCH = {"product": "SEM", "launch_month": 7, "t_mid": 18.0, "scale": 3.5}  # E2 logistic ramp
STOCKOUT = {"product": "SEM", "months": [21, 22, 33], "fill_rate": 0.30}  # E3
GENERIC_ENTRY = {"product": "GLU", "month": 20, "max_loss": 0.45, "tau": 4.0}  # E4
VACANCY_EFFECT = 0.65  # E5: sales multiplier while a territory has no rep
NEW_ACCOUNT_UPLIFT = 1.30  # a new hospital opens in one territory (cause of an easy target)
TOP_DOWN_UPLIFT = 1.25  # manager adds extra target to two territories (cause of hard targets)
BUDGET_STRETCH = 1.03  # national budget = expected year-3 sales x stretch
NOISE_SIGMA = 0.08
ACCESS_SIGMA = 0.15
SKILL_SIGMA = 0.10
RETURN_RATE = 0.02

# Messiness rates
LATE_RATE = 0.05
DUP_SAME_FILE_RATE = 0.004
DUP_RESEND_RATE = 0.003
RESTATE_RATE = 0.005
N_INVALID_NEGATIVE = 8
N_ORPHAN_PRODUCT = 6


@dataclass
class World:
    seed: int
    territories: pd.DataFrame
    roster: pd.DataFrame
    products: pd.DataFrame
    month_cal: pd.DataFrame
    cells: pd.DataFrame          # territory x product x month truth (demand, recorded)
    ledger: pd.DataFrame         # clean line items (truth for the warehouse)
    feed: pd.DataFrame           # messy feed incl. file_id
    targets: pd.DataFrame        # year-3 monthly targets as issued
    answer_key: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
def _allocate(weights: pd.Series, total: int, minimum: int = 1) -> pd.Series:
    """Largest-remainder allocation of `total` seats with a per-item minimum."""
    base = pd.Series(minimum, index=weights.index)
    remaining = total - base.sum()
    raw = weights / weights.sum() * total - minimum
    raw = raw.clip(lower=0)
    raw = raw / raw.sum() * remaining
    seats = base + np.floor(raw).astype(int)
    left = total - seats.sum()
    order = (raw - np.floor(raw)).sort_values(ascending=False).index[:left]
    seats[order] += 1
    return seats


def _territories(rng: np.random.Generator) -> pd.DataFrame:
    reg = calibration.region_diabetics()
    country_dia = reg.groupby("country").diabetics.sum()
    n_country = _allocate(country_dia, N_TERRITORIES, minimum=1)
    rows = []
    for country, sub in reg.groupby("country", sort=False):
        seats = _allocate(sub.set_index("region_code").diabetics, int(n_country[country]))
        for _, r in sub.iterrows():
            k = int(seats[r.region_code])
            shares = rng.dirichlet(np.full(k, 8.0)) if k > 1 else np.array([1.0])
            for i in range(k):
                rows.append({
                    "territory_code": f"{country}-{r.region_code}-{i + 1:02d}",
                    "country": country,
                    "region": r.region,
                    "potential_diabetics": round(float(r.diabetics * shares[i])),
                })
    t = pd.DataFrame(rows)
    t["access_mult"] = np.exp(rng.normal(0, ACCESS_SIGMA, len(t)))  # hidden
    return t


def _choose_special_territories(rng, territories):
    """Pick disjoint mid-sized territories for vacancies, new account and top-down targets."""
    pot = territories.potential_diabetics
    mid = territories[(pot > pot.quantile(0.2)) & (pot < pot.quantile(0.9))].territory_code.tolist()
    pick = list(rng.choice(mid, size=8, replace=False))
    return {
        "vacancy_y1": pick[0],
        "vacancy_y2": pick[1:3],
        "vacancy_y3": pick[3],
        "new_account": pick[4],
        "top_down": pick[5:7],
    }


def _roster(rng, territories, special):
    """One rep per territory; vacancies end one rep's tenure and a new hire starts later."""
    vac = {
        special["vacancy_y1"]: (5, 7),
        special["vacancy_y2"][0]: (14, 17),
        special["vacancy_y2"][1]: (16, 18),
        special["vacancy_y3"]: (29, 31),
    }
    rows, next_id = [], 1
    for code in territories.territory_code:
        skill = float(np.exp(rng.normal(0, SKILL_SIGMA)))
        if code in vac:
            a, b = vac[code]
            rows.append((f"R{next_id:03d}", code, 1, a - 1, skill))
            next_id += 1
            rows.append((f"R{next_id:03d}", code, b + 1, N_MONTHS, float(np.exp(rng.normal(0, SKILL_SIGMA)))))
        else:
            rows.append((f"R{next_id:03d}", code, 1, N_MONTHS, skill))
        next_id += 1
    r = pd.DataFrame(rows, columns=["rep_id", "territory_code", "start_month", "end_month", "skill_mult"])
    return r, vac


def _monthly_calendar_effect(month_cal: pd.DataFrame) -> pd.Series:
    """Average of the planted daily multipliers within each month."""
    other = (month_cal.days_in_month - month_cal.ramadan_days - month_cal.pre_ramadan_days - month_cal.eid_days)
    eff = (
        month_cal.ramadan_days * DAILY_EFFECTS["ramadan"]
        + month_cal.pre_ramadan_days * DAILY_EFFECTS["pre_ramadan"]
        + month_cal.eid_days * DAILY_EFFECTS["eid"]
        + other
    ) / month_cal.days_in_month
    return eff * month_cal.month.map(SUMMER).fillna(1.0)


def _product_curve(code: str, m: np.ndarray) -> np.ndarray:
    growth = (1 + MARKET_GROWTH) ** ((m - 1) / 12)
    if code == "SEM":
        ramp = 1 / (1 + np.exp(-(m - LAUNCH["t_mid"]) / LAUNCH["scale"]))
        return np.where(m >= LAUNCH["launch_month"], ramp, 0.0)
    if code == "GLU":
        t = np.clip(m - GENERIC_ENTRY["month"], 0, None)
        erosion = 1 - GENERIC_ENTRY["max_loss"] * (1 - np.exp(-t / GENERIC_ENTRY["tau"]))
        return growth * np.where(m >= GENERIC_ENTRY["month"], erosion, 1.0)
    return growth


def _cells(rng, territories, roster, month_cal, special, prices):
    months = np.arange(1, N_MONTHS + 1)
    cal = _monthly_calendar_effect(month_cal).to_numpy()
    recs = []
    for _, t in territories.iterrows():
        reps = roster[roster.territory_code == t.territory_code]
        rep_skill = np.full(N_MONTHS, VACANCY_EFFECT)
        rep_of = np.full(N_MONTHS, None, dtype=object)
        for _, r in reps.iterrows():
            idx = slice(r.start_month - 1, r.end_month)
            rep_skill[idx] = r.skill_mult
            rep_of[idx] = r.rep_id
        local = np.where((t.territory_code == special["new_account"]) & (months >= 19), NEW_ACCOUNT_UPLIFT, 1.0)
        for code in PRODUCTS:
            expected = (t.potential_diabetics * UPTAKE[code] * _product_curve(code, months)
                        * t.access_mult * rep_skill * cal * local)
            noise = np.exp(rng.normal(0, NOISE_SIGMA, N_MONTHS))
            demand = np.round(expected * noise).astype(int)
            recorded = demand.copy()
            if code == STOCKOUT["product"]:
                for mo in STOCKOUT["months"]:
                    recorded[mo - 1] = int(round(demand[mo - 1] * STOCKOUT["fill_rate"]))
            for i, mo in enumerate(months):
                recs.append((t.territory_code, code, mo, rep_of[i], expected[i], demand[i], recorded[i]))
    c = pd.DataFrame(recs, columns=["territory_code", "product_code", "month_idx", "rep_id",
                                    "expected_units", "demand_units", "recorded_units"])
    c["unit_price"] = c.product_code.map(prices)
    c["month_start"] = c.month_idx.map(lambda i: pd.Timestamp(START) + pd.DateOffset(months=i - 1))
    return c


def _ledger(rng, cells: pd.DataFrame) -> pd.DataFrame:
    """Split each cell's recorded units into invoice lines, with valid returns netting out."""
    lines = []
    inv_counter = 0
    for (terr, mo), grp in cells.groupby(["territory_code", "month_idx"], sort=True):
        ms = grp.month_start.iloc[0]
        ndays = ms.days_in_month
        cell_lines = []
        for _, c in grp.iterrows():
            units = int(c.recorded_units)
            if units <= 0:
                continue
            ret = int(rng.binomial(units, RETURN_RATE))
            gross = units + ret
            k = int(min(gross, 1 + rng.poisson(5)))
            split = rng.multinomial(gross, np.full(k, 1 / k))
            for q in split[split > 0]:
                cell_lines.append((c.product_code, "SALE", int(q), c.unit_price))
            if ret > 0:
                cell_lines.append((c.product_code, "RETURN", -ret, c.unit_price))
        order = rng.permutation(len(cell_lines))
        i = 0
        while i < len(order):
            size = int(rng.integers(1, 4))
            inv_counter += 1
            inv = f"INV{inv_counter:07d}"
            day = int(rng.integers(1, ndays + 1))
            for ln, j in enumerate(order[i:i + size], start=1):
                prod, typ, qty, price = cell_lines[j]
                lines.append((inv, ln, 1, ms + np.timedelta64(day - 1, "D"), terr, prod, typ, qty, price))
            i += size
    led = pd.DataFrame(lines, columns=["invoice_id", "line_no", "record_version", "invoice_date",
                                       "territory_code", "product_code", "txn_type", "qty", "unit_price"])
    led["net_value"] = (led.qty * led.unit_price).round(2)
    return led


def _messy_feed(rng, ledger: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    feed = ledger.copy()
    feed["month_idx"] = month_index(feed.invoice_date.dt.to_period("M").dt.to_timestamp(), START)
    feed["file_month"] = feed.month_idx  # delivered in the file for its own month by default

    # Late files: a whole territory-month arrives in the next delivery.
    tm = feed[["territory_code", "month_idx"]].drop_duplicates()
    late = tm.sample(frac=LATE_RATE, random_state=int(rng.integers(1 << 31)))
    late_key = set(map(tuple, late.to_numpy()))
    is_late = [k in late_key for k in zip(feed.territory_code, feed.month_idx)]
    feed.loc[is_late, "file_month"] += 1
    n_late_rows = int(sum(is_late))

    # Restatements: version 1 keyed wrong (qty x10), corrected version 2 sent 2 files later.
    eligible = feed[(feed.txn_type == "SALE") & (feed.month_idx <= N_MONTHS - 2)]
    restated = eligible.sample(frac=RESTATE_RATE, random_state=int(rng.integers(1 << 31)))
    v2 = restated.copy()
    v2["record_version"] = 2
    v2["file_month"] = v2.file_month + 2
    feed.loc[restated.index, "qty"] = feed.loc[restated.index, "qty"] * 10
    feed.loc[restated.index, "net_value"] = (feed.loc[restated.index, "qty"] * feed.loc[restated.index, "unit_price"]).round(2)
    feed = pd.concat([feed, v2], ignore_index=True)

    # Exact duplicates in the same file, and re-sends of old rows in the next file.
    dup_same = feed.sample(frac=DUP_SAME_FILE_RATE, random_state=int(rng.integers(1 << 31)))
    resend = feed[feed.file_month < N_MONTHS].sample(frac=DUP_RESEND_RATE, random_state=int(rng.integers(1 << 31))).copy()
    resend["file_month"] += 1
    feed = pd.concat([feed, dup_same, resend], ignore_index=True)

    # Invalid rows: SALE with negative qty (test/junk rows) and unknown product codes.
    junk = feed.sample(n=N_INVALID_NEGATIVE + N_ORPHAN_PRODUCT, random_state=int(rng.integers(1 << 31))).copy()
    junk["invoice_id"] = [f"TST{i:05d}" for i in range(len(junk))]
    junk["line_no"] = 1
    junk["record_version"] = 1
    neg = junk.iloc[:N_INVALID_NEGATIVE].index
    junk.loc[neg, "txn_type"] = "SALE"
    junk.loc[neg, "qty"] = -junk.loc[neg, "qty"].abs()
    orphan = junk.iloc[N_INVALID_NEGATIVE:].index
    junk.loc[orphan, "product_code"] = "XXX"
    junk.loc[orphan, "qty"] = junk.loc[orphan, "qty"].abs()
    junk.loc[orphan, "txn_type"] = "SALE"
    junk["net_value"] = (junk.qty * junk.unit_price).round(2)
    feed = pd.concat([feed, junk], ignore_index=True)

    first = pd.Timestamp(START)
    feed["file_id"] = feed.file_month.map(lambda m: (first + pd.DateOffset(months=m - 1)).strftime("F%Y_%m"))
    feed["delivered_on"] = feed.file_month.map(lambda m: (first + pd.DateOffset(months=m)).replace(day=10).date())
    feed = feed.sample(frac=1.0, random_state=int(rng.integers(1 << 31))).reset_index(drop=True)
    counts = {
        "late_territory_months": len(late_key),
        "late_rows": n_late_rows,
        "restated_lines": int(len(restated)),
        "duplicate_rows_same_file": int(len(dup_same)),
        "duplicate_rows_resent": int(len(resend)),
        "invalid_negative_sale_rows": N_INVALID_NEGATIVE,
        "orphan_product_rows": N_ORPHAN_PRODUCT,
        "valid_return_lines": int((ledger.txn_type == "RETURN").sum()),
    }
    return feed, counts


def _targets(cells: pd.DataFrame, special) -> tuple[pd.DataFrame, dict]:
    """Year-3 targets as issued: last year (same month) x (1 + X_p), X_p from the national budget.

    The national budget is the noise-free expected year-3 volume x BUDGET_STRETCH (the company
    does not plan for unknown future stock-outs or vacancies). Two territories get a top-down uplift.
    """
    cells = cells.copy()
    cells["recorded_value"] = cells.recorded_units * cells.unit_price
    cells["expected_value"] = cells.expected_units * cells.unit_price
    y2 = cells[cells.month_idx.between(HISTORY_END_MONTH - 11, HISTORY_END_MONTH)]
    y3 = cells[cells.month_idx > HISTORY_END_MONTH]
    ly_nat = y2.groupby("product_code").recorded_value.sum()
    budget = y3.groupby("product_code").expected_value.sum() * BUDGET_STRETCH
    growth = (budget / ly_nat - 1).round(4)
    t = y2[["territory_code", "product_code", "month_idx", "recorded_value"]].copy()
    t["month_idx"] += 12
    t["target_value"] = t.recorded_value * (1 + t.product_code.map(growth))
    top = t.territory_code.isin(special["top_down"])
    t.loc[top, "target_value"] *= TOP_DOWN_UPLIFT
    t["target_value"] = t.target_value.round(2)
    t["month_start"] = t.month_idx.map(lambda i: pd.Timestamp(START) + pd.DateOffset(months=i - 1))
    return t[["territory_code", "product_code", "month_start", "target_value"]], growth.to_dict()


def generate(seed: int = DEFAULT_SEED) -> World:
    rng = np.random.default_rng(seed)
    prices = calibration.reference_prices()
    end = (pd.Timestamp(START) + pd.DateOffset(months=N_MONTHS) - np.timedelta64(1, "D")).date()
    dim_date = build_dim_date(START, str(end))
    month_cal = build_month_calendar(dim_date)

    territories = _territories(rng)
    special = _choose_special_territories(rng, territories)
    roster, vac = _roster(rng, territories, special)
    cells = _cells(rng, territories, roster, month_cal, special, prices)
    ledger = _ledger(rng, cells)
    feed, mess = _messy_feed(rng, ledger)
    targets, growth = _targets(cells, special)

    products = pd.DataFrame(
        [(k, v[0], v[1], v[2], prices[k]) for k, v in PRODUCTS.items()],
        columns=["product_code", "product_name", "lifecycle", "molecule_class", "list_price_sar"],
    )
    products["launch_month"] = products.product_code.map(
        lambda c: str(pd.Timestamp(START) + pd.DateOffset(months=LAUNCH["launch_month"] - 1))[:10] if c == "SEM" else None)
    products["generic_entry_month"] = products.product_code.map(
        lambda c: str(pd.Timestamp(START) + pd.DateOffset(months=GENERIC_ENTRY["month"] - 1))[:10] if c == "GLU" else None)

    def ms(i):
        return str((pd.Timestamp(START) + pd.DateOffset(months=i - 1)).date())

    unfair = (
        [{"territory_code": c, "direction": "easy", "cause": "vacancy in year 2 depressed last-year base"}
         for c in special["vacancy_y2"]]
        + [{"territory_code": special["new_account"], "direction": "easy",
            "cause": "new hospital account from month 19 not reflected in last-year base"}]
        + [{"territory_code": c, "direction": "hard", "cause": f"top-down uplift x{TOP_DOWN_UPLIFT}"}
           for c in special["top_down"]]
    )
    answer_key = {
        "seed": seed,
        "note": "Hidden ground truth. Only scorecard.py may read this file.",
        "E1_ramadan_eid": {"daily_multipliers": DAILY_EFFECTS, "pre_ramadan_days": 10,
                           "eid_windows": "1-4 Shawwal, 10-13 Dhu al-Hijjah", "summer_mult": SUMMER},
        "E2_launch": {**LAUNCH, "launch_month_start": ms(LAUNCH["launch_month"]),
                      "t_mid_month_start": ms(int(LAUNCH["t_mid"]))},
        "E3_stockout": {**STOCKOUT, "month_starts": [ms(m) for m in STOCKOUT["months"]]},
        "E4_generic_entry": {**GENERIC_ENTRY, "month_start": ms(GENERIC_ENTRY["month"])},
        "E5_vacancies": {"sales_multiplier": VACANCY_EFFECT, "windows": [
            {"territory_code": k, "first_month": ms(a), "last_month": ms(b)} for k, (a, b) in vac.items()]},
        "E6_unfair_targets": unfair,
        "new_account": {"territory_code": special["new_account"], "from_month": ms(19), "uplift": NEW_ACCOUNT_UPLIFT},
        "budget": {"stretch": BUDGET_STRETCH, "growth_x_by_product": growth},
        "noise": {"cell_sigma": NOISE_SIGMA, "access_sigma": ACCESS_SIGMA, "skill_sigma": SKILL_SIGMA},
        "messiness": mess,
    }
    return World(seed, territories, roster, products, month_cal, cells, ledger, feed, targets, answer_key)


def write(world: World, out: Path = DATA_RAW) -> None:
    """Write what a real analyst would receive, plus the hidden answer key."""
    (out / "feed").mkdir(parents=True, exist_ok=True)
    (out / "master").mkdir(parents=True, exist_ok=True)
    for f in (out / "feed").glob("*.csv"):
        f.unlink()
    cols = ["file_id", "delivered_on", "invoice_id", "line_no", "record_version", "invoice_date",
            "territory_code", "product_code", "txn_type", "qty", "unit_price", "net_value"]
    feed = world.feed.copy()
    feed["invoice_date"] = feed.invoice_date.dt.date
    for fid, grp in feed.groupby("file_id"):
        grp[cols].to_csv(out / "feed" / f"sales_{fid}.csv", index=False)

    terr = world.territories[["territory_code", "country", "region", "potential_diabetics"]]
    terr.to_csv(out / "master" / "territories.csv", index=False)
    r = world.roster.copy()
    r["start_date"] = r.start_month.map(lambda i: (pd.Timestamp(START) + pd.DateOffset(months=i - 1)).date())
    r["end_date"] = r.end_month.map(
        lambda i: (pd.Timestamp(START) + pd.DateOffset(months=i) - np.timedelta64(1, "D")).date())
    r[["rep_id", "territory_code", "start_date", "end_date"]].to_csv(out / "master" / "reps.csv", index=False)
    world.products.to_csv(out / "master" / "products.csv", index=False)
    t = world.targets.copy()
    t["month_start"] = t.month_start.dt.date
    t.to_csv(out / "master" / "targets_2025.csv", index=False)
    with open(out / ANSWER_KEY.name, "w") as fh:
        json.dump(world.answer_key, fh, indent=2, default=str)


if __name__ == "__main__":
    w = generate()
    write(w)
    print(f"seed={w.seed} feed_rows={len(w.feed)} ledger_rows={len(w.ledger)} territories={len(w.territories)}")
