"""One-off: copy the SFDA list prices for the three reference molecules out of Project A.

Project A (../a-sfda-drug-price-analysis) scraped the public SFDA drugs list
(https://www.sfda.gov.sa/en/drugs-list) on 2026-11-09. This script copies only the rows
needed here into data/calibration/sfda_reference_prices.csv, so this project does not
depend on Project A at runtime.

Run: python scripts/extract_sfda_prices.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "a-sfda-drug-price-analysis" / "data" / "clean" / "products_clean.parquet"
OUT = ROOT / "data" / "calibration" / "sfda_reference_prices.csv"

QUERY = f"""
select lower(scientific_name) as molecule, trade_name, dosage_form, strength_raw,
       price as price_sar, register_no
from read_parquet('{SRC.as_posix()}')
where not is_combo
  and lower(scientific_name) in ('sitagliptin', 'semaglutide', 'atorvastatin calcium')
order by molecule, strength_first, price
"""

if __name__ == "__main__":
    df = duckdb.sql(QUERY).df()
    df.to_csv(OUT, index=False)
    print(f"wrote {len(df)} rows to {OUT}")
