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
TRADE_THESES_FILE = MACRO_DIR / "trade_theses.csv"

# -----------------------------
# FX universe
# -----------------------------
FX_PAIRS = {
    "USDTHB": "THB=X",
    "USDINR": "INR=X",
    "USDBRL": "BRL=X",
    "USDZAR": "ZAR=X",
    "USDMXN": "MXN=X",
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
# Trade thesis settings
# -----------------------------
TRADE_THESIS_DRIVERS = [
    "Fed rate path",
    "EM carry demand",
    "Risk-off / DXY",
    "Commodity prices",
    "Local CB policy",
    "Political / event risk",
    "China / global growth",
]
