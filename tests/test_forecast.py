import numpy as np
import pandas as pd

from fairtargets import forecast as F


def _panel():
    rows = []
    for t in ("A", "B"):
        for m in range(1, 13):
            units = 100 if m != 7 else 30  # national stock-out in month 7
            rows.append((t, "P", m, units))
    return pd.DataFrame(rows, columns=["territory_code", "product_code", "m", "units_net"])


def test_detect_stockouts_finds_planted_dip():
    assert F.detect_stockouts(_panel(), upto=12) == {"P": [7]}


def test_detect_stockouts_ignores_normal_dip():
    p = _panel()
    p.loc[p.m == 7, "units_net"] = 85  # a Ramadan-sized dip is not a stock-out
    assert F.detect_stockouts(p, upto=12) == {"P": []}


def test_unconstrain_replaces_only_flagged_month():
    p = _panel()
    p.loc[(p.territory_code == "A") & (p.m == 8), "units_net"] = 120
    out = F.unconstrain(p, {"P": [7]}, upto=12)
    a = out[out.territory_code == "A"].set_index("m").units_train
    assert a[7] == 110.0  # mean of month 6 (100) and month 8 (120)
    assert a.drop(7).equals(p[p.territory_code == "A"].set_index("m").units_net.drop(7).astype(float))


def test_accuracy_metrics():
    fc = pd.DataFrame({"model": ["x", "x"], "forecast": [110.0, 90.0], "actual": [100.0, 100.0]})
    acc = F.accuracy(fc, ["model"]).iloc[0]
    assert np.isclose(acc.wape, 0.10) and np.isclose(acc.bias, 0.0)
