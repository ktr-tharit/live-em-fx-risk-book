"""
config.py
---------
Single source of truth for project-wide settings. Every other module imports
from here instead of hardcoding values, so changing a pair list or VaR
confidence level happens in one place.
"""

from pathlib import Path

# -----------------------------
# Paths
# -----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
POSITIONS_DIR = PROJECT_ROOT / "positions"
JOURNAL_DIR = PROJECT_ROOT / "journal"

FX_RATES_FILE = DATA_DIR / "fx_rates.csv"
STRESS_SCENARIOS_FILE = DATA_DIR / "stress_scenarios.csv"
POSITIONS_FILE = POSITIONS_DIR / "positions.csv"

# -----------------------------
# FX universe
# -----------------------------
# Yahoo Finance ticker suffix convention: "<CCY>=X" means USD -> CCY
FX_PAIRS = {
    "USDTHB": "THB=X",
    "USDINR": "INR=X",
    "USDBRL": "BRL=X",
    "USDZAR": "ZAR=X",
    "USDMXN": "MXN=X",
    "USDIDR": "IDR=X",
    "USDTRY": "TRY=X",
}

# -----------------------------
# Risk settings
# -----------------------------
VAR_CONFIDENCE_LEVELS = [0.95, 0.99]
VAR_LOOKBACK_DAYS = 250          # rolling window used to build the return distribution
BACKTEST_WINDOW_DAYS = 250       # rolling window for counting exceptions

# Basel traffic-light zones based on exceptions in a 250-day window (99% VaR)
TRAFFIC_LIGHT_ZONES = {
    "GREEN": (0, 4),
    "YELLOW": (5, 9),
    "RED": (10, 250),
}

# -----------------------------
# Position settings
# -----------------------------
DEFAULT_NOTIONAL_USD = 1_000_000
