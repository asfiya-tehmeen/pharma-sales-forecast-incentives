import numpy as np
import pandas as pd
import pytest

from fairtargets import generator
from fairtargets.config import N_MONTHS, N_TERRITORIES


def test_same_seed_same_data(world):
    again = generator.generate(seed=42)
    pd.testing.assert_frame_equal(world.feed, again.feed)
    pd.testing.assert_frame_equal(world.targets, again.targets)
    assert world.answer_key == again.answer_key


def test_different_seed_different_data(world):
    other = generator.generate(seed=7)
    assert not world.cells.recorded_units.equals(other.cells.recorded_units)


def test_shape(world):
    assert len(world.territories) == N_TERRITORIES
    assert set(world.territories.country) == {"KSA", "UAE"}
    assert len(world.cells) == N_TERRITORIES * 3 * N_MONTHS


def test_launch_product_zero_before_launch(world):
    c = world.cells
    pre = c[(c.product_code == "SEM") & (c.month_idx < generator.LAUNCH["launch_month"])]
    assert (pre.recorded_units == 0).all()


def test_stockout_months_planted(world):
    c = world.cells[world.cells.product_code == "SEM"]
    nat = c.groupby("month_idx")[["demand_units", "recorded_units"]].sum()
    for m in generator.STOCKOUT["months"]:
        assert nat.loc[m, "recorded_units"] / nat.loc[m, "demand_units"] == pytest.approx(0.30, abs=0.01)
    other = nat.drop(generator.STOCKOUT["months"])
    assert (other.recorded_units == other.demand_units).all()


def test_generic_entry_erodes_glucora(world):
    c = world.cells[world.cells.product_code == "GLU"]
    nat = c.groupby("month_idx").expected_units.sum()
    m = generator.GENERIC_ENTRY["month"]
    assert nat.loc[m + 12] < 0.65 * nat.loc[m - 1]  # >35% lower a year after entry


def test_vacancy_months_have_no_rep_and_lower_sales(world):
    for w in world.answer_key["E5_vacancies"]["windows"]:
        c = world.cells[world.cells.territory_code == w["territory_code"]]
        vac = c[c.rep_id.isna()]
        assert vac.month_start.min() == pd.Timestamp(w["first_month"])
        assert vac.month_start.max() == pd.Timestamp(w["last_month"])
    assert world.cells.rep_id.notna().mean() > 0.95


def test_ramadan_effect_in_expected_units(world):
    """Control product, March 2025 (29 Ramadan days) must sit below Jan 2025 by roughly the planted size."""
    c = world.cells[(world.cells.product_code == "CAR")]
    nat = c.groupby("month_start").expected_units.sum()
    ratio = nat[pd.Timestamp("2025-03-01")] / nat[pd.Timestamp("2025-01-01")]
    assert 0.78 < ratio < 0.88


def test_unfair_targets_planted(world):
    unfair = world.answer_key["E6_unfair_targets"]
    assert len(unfair) == 5
    assert {u["direction"] for u in unfair} == {"easy", "hard"}
    codes = [u["territory_code"] for u in unfair]
    assert len(set(codes)) == 5


def test_top_down_targets_are_uplifted(world):
    t = world.targets.groupby("territory_code").target_value.sum()
    ly = world.cells[world.cells.month_idx.between(13, 24)].assign(
        v=lambda d: d.recorded_units * d.unit_price).groupby("territory_code").v.sum()
    ratio = t / ly
    hard = [u["territory_code"] for u in world.answer_key["E6_unfair_targets"] if u["direction"] == "hard"]
    assert (ratio[hard] > ratio.median() * 1.15).all()


def test_returns_are_negative_and_net_to_recorded(world):
    led = world.ledger
    assert (led.loc[led.txn_type == "RETURN", "qty"] < 0).all()
    assert (led.loc[led.txn_type == "SALE", "qty"] > 0).all()
    net = led.assign(m=led.invoice_date.dt.to_period("M").dt.to_timestamp()).groupby(
        ["territory_code", "product_code", "m"]).qty.sum()
    rec = world.cells.set_index(["territory_code", "product_code", "month_start"]).recorded_units
    rec = rec[rec > 0]
    assert np.array_equal(net.sort_index().to_numpy(), rec.sort_index().to_numpy())


def test_messiness_present(world):
    m = world.answer_key["messiness"]
    for k in ("late_rows", "restated_lines", "duplicate_rows_same_file", "duplicate_rows_resent",
              "invalid_negative_sale_rows", "orphan_product_rows", "valid_return_lines"):
        assert m[k] > 0, k
    assert len(world.feed) > len(world.ledger)
