"""Daily date dimension with Hijri (Umm al-Qura) fields and KSA/UAE holidays, plus a monthly rollup.

Ramadan = Hijri month 9. Pre-Ramadan = the 10 days before 1 Ramadan.
Eid al-Fitr holiday window = 1-4 Shawwal. Eid al-Adha holiday window = 10-13 Dhu al-Hijjah.
"""
from datetime import date, timedelta

import holidays
import pandas as pd
from hijridate import Gregorian

PRE_RAMADAN_DAYS = 10


def build_dim_date(start: str, end: str) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    rows = []
    for d in days:
        h = Gregorian(d.year, d.month, d.day).to_hijri()
        rows.append((d.date(), h.year, h.month, h.day, h.month_name()))
    df = pd.DataFrame(rows, columns=["date", "hijri_year", "hijri_month", "hijri_day", "hijri_month_name"])
    df["date"] = pd.to_datetime(df.date)
    df["year"] = df.date.dt.year
    df["month"] = df.date.dt.month
    df["month_start"] = df.date.dt.to_period("M").dt.to_timestamp()
    df["day_of_week"] = df.date.dt.day_name()

    df["is_ramadan"] = df.hijri_month == 9
    starts = df.loc[(df.hijri_month == 9) & (df.hijri_day == 1), "date"]
    pre = set()
    for s in starts:
        pre.update(s - timedelta(days=k) for k in range(1, PRE_RAMADAN_DAYS + 1))
    df["is_pre_ramadan"] = df.date.isin(pre)
    df["is_eid_fitr"] = (df.hijri_month == 10) & (df.hijri_day <= 4)
    df["is_eid_adha"] = (df.hijri_month == 12) & df.hijri_day.between(10, 13)
    df["is_eid"] = df.is_eid_fitr | df.is_eid_adha

    years = sorted(df.year.unique())
    for code, col in (("SA", "ksa"), ("AE", "uae")):
        hol = holidays.country_holidays(code, years=years, language="en_US")
        df[f"is_holiday_{col}"] = df.date.dt.date.map(lambda x: x in hol)
        df[f"holiday_name_{col}"] = df.date.dt.date.map(lambda x: hol.get(x))
    # Weekends: KSA Friday-Saturday; UAE Saturday-Sunday (since January 2022).
    df["is_weekend_ksa"] = df.day_of_week.isin(["Friday", "Saturday"])
    df["is_weekend_uae"] = df.day_of_week.isin(["Saturday", "Sunday"])
    df["is_workday_ksa"] = ~df.is_weekend_ksa & ~df.is_holiday_ksa
    df["is_workday_uae"] = ~df.is_weekend_uae & ~df.is_holiday_uae
    return df


def build_month_calendar(dim_date: pd.DataFrame) -> pd.DataFrame:
    g = dim_date.groupby("month_start")
    m = pd.DataFrame({
        "days_in_month": g.size(),
        "ramadan_days": g.is_ramadan.sum(),
        "pre_ramadan_days": g.is_pre_ramadan.sum(),
        "eid_days": g.is_eid.sum(),
        "workdays_ksa": g.is_workday_ksa.sum(),
        "workdays_uae": g.is_workday_uae.sum(),
        "holidays_ksa": g.is_holiday_ksa.sum(),
        "holidays_uae": g.is_holiday_uae.sum(),
    }).reset_index()
    for c in ("ramadan", "pre_ramadan", "eid"):
        m[f"{c}_share"] = m[f"{c}_days"] / m.days_in_month
    m["month"] = m.month_start.dt.month
    m["year"] = m.month_start.dt.year
    return m


def month_index(month_start: pd.Series, start: str) -> pd.Series:
    """1-based month index relative to the simulation start."""
    s = pd.Timestamp(start)
    return (month_start.dt.year - s.year) * 12 + (month_start.dt.month - s.month) + 1


def month_start_of(index: int, start: str) -> date:
    return (pd.Timestamp(start) + pd.DateOffset(months=index - 1)).date()
