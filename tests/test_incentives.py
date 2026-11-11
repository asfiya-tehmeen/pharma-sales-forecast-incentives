import numpy as np
import pandas as pd
import pytest

from fairtargets import incentives, targets


@pytest.mark.parametrize("a,expected", [
    (0.80, 0.0), (0.8999, 0.0), (0.90, 0.50), (0.95, 0.75), (1.00, 1.00), (1.10, 1.20), (1.25, 1.50), (1.60, 1.50),
])
def test_payout_curve(a, expected):
    assert incentives.payout_pct(a) == pytest.approx(expected)


def test_sql_payout_matches_python(built):
    grid = np.round(np.arange(0.70, 1.40, 0.005), 4)
    sql = built.execute(
        "select a, gold.payout_pct(a) as p from (select unnest(?::double[]) as a)", [grid.tolist()]).df()
    assert np.allclose(sql.p.to_numpy(), incentives.payout_pct(sql.a.to_numpy()))


def test_sql_payout_view(built):
    v = built.execute("select attainment, payout_pct, payout_sar, months_in_role from gold.v_payout").df()
    assert len(v) >= 40
    assert np.allclose(v.payout_pct, incentives.payout_pct(v.attainment.astype(float)))
    assert (v.payout_sar <= 40000 * 1.5 + 0.01).all()


def test_gini():
    assert incentives.gini(np.ones(10)) == pytest.approx(0.0)
    assert incentives.gini(np.array([0, 0, 0, 1.0])) == pytest.approx(0.75)
    assert incentives.gini(np.zeros(5)) == 0.0
    rows = np.array([[1, 1, 1, 1.0], [0, 0, 0, 1.0]])
    assert np.allclose(incentives.gini(rows, axis=1), [0.0, 0.75])


def test_percentile_and_flags():
    sims = pd.DataFrame({"A": np.arange(100.0), "B": np.arange(100.0), "C": np.arange(100.0)})
    pct = targets.percentiles(sims, pd.Series({"A": 50.0, "B": 10.0, "C": 90.0}))
    assert pct.tolist() == [0.50, 0.10, 0.90]
    fl = targets.flag(pct, delta=0.25)
    assert fl.loc["A", "flag"] == False  # noqa: E712
    assert fl.loc["B", "direction"] == "easy" and fl.loc["C", "direction"] == "hard"


def test_reconcile_to_budget():
    fc = pd.DataFrame({"territory_code": ["A", "B", "A", "B"], "product_code": ["X", "X", "Y", "Y"],
                       "forecast": [10.0, 30, 5, 5], "forecast_value": [100.0, 300, 50, 50]})
    out = targets.reconcile_to_budget(fc, pd.Series({"X": 200.0, "Y": 200.0}))
    assert out.groupby("product_code").forecast_value.sum().tolist() == [200.0, 200.0]
    assert out.forecast_value.tolist() == [50.0, 150.0, 100.0, 100.0]  # shares preserved


def test_rules_split_same_budget():
    panel = pd.DataFrame({
        "territory_code": ["A", "B"] * 2, "product_code": ["X", "X", "Y", "Y"],
        "m": [13] * 4, "value_net": [30.0, 10, 5, 15]})
    issued = pd.DataFrame({"territory_code": ["A", "B", "A", "B"], "product_code": ["X", "X", "Y", "Y"],
                           "target_value": [60.0, 40, 10, 30]})
    r = incentives.rule_targets(panel, issued, pd.Series({"A": 1.0, "B": 3.0}))
    assert r.sum().round(6).tolist() == [140.0, 140.0, 140.0]
    assert r.loc["A", "last_year_plus_x"] == pytest.approx(100 * 0.75 + 40 * 0.25)
    assert r.loc["A", "potential_based"] == pytest.approx(140 * 0.25)
