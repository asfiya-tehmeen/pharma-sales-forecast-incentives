"""Project-wide settings: paths, the simulation window, and decision rules.

Planted-effect parameters live in generator.py (they are part of the hidden world).
Analysis settings below (flag threshold, payout curve) were fixed BEFORE any results
were produced, and must not be tuned after looking at the scorecard.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_CLEAN = ROOT / "data" / "clean"
CALIBRATION = ROOT / "data" / "calibration"
SQL_DIR = ROOT / "sql"
REPORTS = ROOT / "reports"
RESULTS = REPORTS / "results"
FIGURES = REPORTS / "figures"
POWERBI = REPORTS / "powerbi"
WAREHOUSE = DATA_CLEAN / "warehouse.duckdb"
ANSWER_KEY = DATA_RAW / "answer_key.json"  # read ONLY by scorecard.py

DEFAULT_SEED = 42

# Simulation window: 36 months, Jan 2023 to Dec 2025. Years 1-2 = history, year 3 = target year.
START = "2023-01-01"
N_MONTHS = 36
TARGET_YEAR = 2025
HISTORY_END_MONTH = 24  # month index (1-based) of Dec 2024

N_TERRITORIES = 40

# Backtest design (fixed in the README before running)
BACKTEST_ORIGINS = list(range(24, 34))  # last observed month index at each origin
BACKTEST_HORIZON = 3

# Fairness flag rule (pre-registered): a territory is flagged when its target percentile
# differs from the median territory's percentile by at least this many percentage points.
FLAG_DELTA = 0.25

# Payout curve on annual attainment (pre-registered)
PAYOUT_THRESHOLD = 0.90      # below this attainment, payout = 0
PAYOUT_AT_THRESHOLD = 0.50   # payout fraction of target bonus at the threshold
PAYOUT_ACCELERATOR = 2.0     # above 100% attainment, +2% payout per +1% attainment
PAYOUT_CAP = 1.50            # max payout fraction of target bonus
TARGET_BONUS_SAR = 40_000    # annual on-target bonus per rep (assumption, see calibration.md)

MONTE_CARLO_DRAWS = 10_000
