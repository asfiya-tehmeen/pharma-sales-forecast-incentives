"""Build the DuckDB warehouse by running sql/01..05 in order."""
from pathlib import Path

import duckdb
import pandas as pd

from .calendar import build_dim_date
from .config import DATA_RAW, SQL_DIR, WAREHOUSE

SQL_FILES = ["01_load.sql", "02_validate.sql", "03_fact.sql", "04_dims.sql", "05_kpi_views.sql"]


def build(raw: Path = DATA_RAW, db_path: Path = WAREHOUSE) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    dim_date = build_dim_date("2023-01-01", "2025-12-31")
    con.execute("create schema if not exists staging")
    con.register("dim_date_df", dim_date)
    con.execute("""create or replace table staging.dim_date as
                   select * replace (cast(date as date) as date, cast(month_start as date) as month_start)
                   from dim_date_df""")
    con.unregister("dim_date_df")
    for name in SQL_FILES:
        sql = (SQL_DIR / name).read_text().replace("{raw}", raw.as_posix())
        con.execute(sql)
    return con


def query(sql: str, db_path: Path = WAREHOUSE) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return con.sql(sql).df()


if __name__ == "__main__":
    con = build()
    print(con.sql("select * from silver.dq_summary").df().to_string(index=False))
    con.close()
