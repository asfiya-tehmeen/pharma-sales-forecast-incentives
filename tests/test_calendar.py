import pandas as pd
import pytest

from fairtargets.calendar import build_dim_date, build_month_calendar

# Officially observed Saudi dates, verified against news sources (docs/calibration.md, S6).
RAMADAN_START = ["2023-03-23", "2024-03-11", "2025-03-01"]
EID_FITR = ["2023-04-21", "2024-04-10", "2025-03-30"]
EID_ADHA = ["2023-06-28", "2024-06-16", "2025-06-06"]


@pytest.fixture(scope="module")
def dd():
    return build_dim_date("2023-01-01", "2025-12-31").set_index("date")


@pytest.mark.parametrize("d", RAMADAN_START)
def test_ramadan_start(dd, d):
    day = pd.Timestamp(d)
    assert dd.loc[day, "is_ramadan"]
    assert dd.loc[day, "hijri_day"] == 1
    assert not dd.loc[day - pd.offsets.Day(1), "is_ramadan"]
    assert dd.loc[day - pd.offsets.Day(1), "is_pre_ramadan"]


@pytest.mark.parametrize("d", EID_FITR)
def test_eid_fitr(dd, d):
    assert dd.loc[pd.Timestamp(d), "is_eid_fitr"]
    assert (dd.loc[pd.Timestamp(d), "hijri_month"], dd.loc[pd.Timestamp(d), "hijri_day"]) == (10, 1)


@pytest.mark.parametrize("d", EID_ADHA)
def test_eid_adha(dd, d):
    assert dd.loc[pd.Timestamp(d), "is_eid_adha"]


def test_month_rollup():
    m = build_month_calendar(build_dim_date("2025-01-01", "2025-12-31")).set_index("month_start")
    assert m.loc["2025-03-01", "ramadan_days"] == 29
    assert m.loc["2025-02-01", "pre_ramadan_days"] == 10
    assert m.ramadan_days.sum() == 29
    assert m.eid_days.sum() == 8


def test_weekends(dd):
    assert dd.loc[pd.Timestamp("2025-01-03"), "is_weekend_ksa"]      # Friday
    assert not dd.loc[pd.Timestamp("2025-01-03"), "is_weekend_uae"]
    assert dd.loc[pd.Timestamp("2025-01-05"), "is_weekend_uae"]      # Sunday
