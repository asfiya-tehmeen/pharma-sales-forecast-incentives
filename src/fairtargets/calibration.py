"""Load the public calibration inputs (see docs/calibration.md for sources and status)."""
import pandas as pd

from .config import CALIBRATION

# Each reference product maps to a public SFDA list-price filter.
PRICE_RULES = {
    # product_code: (molecule, dosage-form contains, strengths kept)
    "GLU": ("sitagliptin", "tablet", {"100"}),
    "SEM": ("semaglutide", "pen", {"0.25", "0.5", "1"}),
    "CAR": ("atorvastatin calcium", "tablet", {"20"}),
}


def regions() -> pd.DataFrame:
    return pd.read_csv(CALIBRATION / "regions.csv")


def country_diabetes() -> pd.DataFrame:
    return pd.read_csv(CALIBRATION / "country_diabetes.csv")


def reference_prices() -> dict[str, float]:
    """Median SFDA list price (SAR per pack) for each product's reference molecule and strength."""
    df = pd.read_csv(CALIBRATION / "sfda_reference_prices.csv", dtype={"strength_raw": str})
    out = {}
    for code, (molecule, form, strengths) in PRICE_RULES.items():
        sel = df[
            (df.molecule == molecule)
            & df.dosage_form.str.lower().str.contains(form)
            & df.strength_raw.isin(strengths)
        ]
        if sel.empty:
            raise ValueError(f"no SFDA reference price rows for {code}")
        out[code] = round(float(sel.price_sar.median()), 2)
    return out


def region_diabetics() -> pd.DataFrame:
    """Adults with diabetes per region = country count (IDF) x region population share.

    Assumes the same prevalence in every region of a country (assumption A2).
    """
    reg = regions()
    dia = country_diabetes().set_index("country")
    reg["pop_share"] = reg.population / reg.groupby("country").population.transform("sum")
    reg["diabetics"] = reg.pop_share * reg.country.map(dia.adults_with_diabetes_k) * 1000
    return reg
