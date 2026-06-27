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
MACRO_DIR = PROJECT_ROOT / "macro"

FX_RATES_FILE = DATA_DIR / "fx_rates.csv"
STRESS_SCENARIOS_FILE = DATA_DIR / "stress_scenarios.csv"
POSITIONS_FILE = POSITIONS_DIR / "positions.csv"
SCORECARD_INPUTS_FILE = MACRO_DIR / "scorecard_inputs.csv"

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

# -----------------------------
# Macro scorecard settings
# -----------------------------
# Scores are directional for USDXXX:
#   +2 = strong USD / local-currency weakness lean
#   -2 = strong local-currency strength / USD weakness lean
SCORECARD_FACTORS = [
    "rate_differential",
    "risk_sentiment",
    "commodity",
    "event_risk",
    "technical",
]

SCORECARD_WEIGHTS = {
    "default": {
        "rate_differential": 0.35,
        "risk_sentiment": 0.25,
        "commodity": 0.15,
        "event_risk": 0.15,
        "technical": 0.10,
    },
    "USDTHB": {
        "rate_differential": 0.40,
        "risk_sentiment": 0.25,
        "commodity": 0.00,
        "event_risk": 0.20,
        "technical": 0.15,
    },
    "USDINR": {
        "rate_differential": 0.40,
        "risk_sentiment": 0.25,
        "commodity": 0.00,
        "event_risk": 0.20,
        "technical": 0.15,
    },
    "USDZAR": {
        "rate_differential": 0.25,
        "risk_sentiment": 0.20,
        "commodity": 0.30,
        "event_risk": 0.15,
        "technical": 0.10,
    },
    "USDBRL": {
        "rate_differential": 0.25,
        "risk_sentiment": 0.20,
        "commodity": 0.30,
        "event_risk": 0.15,
        "technical": 0.10,
    },
    "USDMXN": {
        "rate_differential": 0.30,
        "risk_sentiment": 0.25,
        "commodity": 0.20,
        "event_risk": 0.15,
        "technical": 0.10,
    },
}
