"""
var_calc.py
-----------
Calculates portfolio VaR using two methods:

1. Historical simulation VaR:
   Apply each of the last N days' actual % moves to the CURRENT position book,
   build a hypothetical P&L distribution, and take the loss at the chosen
   percentile.

2. Parametric VaR (variance-covariance method):
   Estimate the covariance matrix of pair returns over the lookback window,
   compute portfolio volatility given current position weights, and scale by
   the z-score for the chosen confidence level.

Both methods answer the same question - "how much could this book lose on a
bad day?" - but make different assumptions. Historical VaR makes no
distributional assumption but is limited to shocks that actually happened in
the lookback window. Parametric VaR assumes returns are normally distributed,
which understates tail risk for FX (fat tails), but is fast and smooth.

Usage:
    python risk/var_calc.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scipy.stats import norm

from config import (
    FX_RATES_FILE,
    POSITIONS_FILE,
    VAR_CONFIDENCE_LEVELS,
    VAR_LOOKBACK_DAYS,
    DATA_DIR,
)

DIRECTION_SIGN = {"LONG_USD": 1, "SHORT_USD": -1, "FLAT": 0}
OUTPUT_FILE = DATA_DIR / "var_summary.csv"


def load_returns_wide() -> pd.DataFrame:
    """Load FX rates and pivot to wide format of daily % returns, one column per pair."""
    df = pd.read_csv(FX_RATES_FILE, parse_dates=["date"])
    wide = df.pivot(index="date", columns="pair", values="rate").sort_index()
    returns = wide.pct_change().dropna(how="all")
    return returns


def load_current_positions(as_of_date: pd.Timestamp | None = None) -> pd.DataFrame:
    df = pd.read_csv(POSITIONS_FILE, parse_dates=["as_of_date", "end_date"])
    if as_of_date is None:
        as_of_date = pd.Timestamp.today().normalize()
    else:
        as_of_date = pd.Timestamp(as_of_date).normalize()

    df = df[
        (df["as_of_date"] <= as_of_date)
        & (df["end_date"].isna() | (df["end_date"] >= as_of_date))
    ].copy()
    df["direction_sign"] = df["direction"].map(DIRECTION_SIGN)
    df["signed_notional_usd"] = df["notional_usd"] * df["direction_sign"]
    # if the same pair appears more than once, net the exposure
    netted = df.groupby("pair")["signed_notional_usd"].sum()
    return netted  # Series: index=pair, value=signed USD notional


def historical_var(returns: pd.DataFrame, positions: pd.Series,
                    lookback_days: int, confidence: float) -> float:
    """
    Historical simulation VaR: replay the last `lookback_days` of actual
    returns against the CURRENT position book to build a P&L distribution.
    """
    recent = returns.tail(lookback_days)
    common_pairs = [p for p in positions.index if p in recent.columns]
    recent = recent[common_pairs]
    weights = positions[common_pairs]

    hypothetical_pnl = recent.mul(weights, axis=1).sum(axis=1)  # one P&L per historical day
    loss_percentile = (1 - confidence) * 100
    var_estimate = -np.percentile(hypothetical_pnl, loss_percentile)
    return var_estimate, hypothetical_pnl


def parametric_var(returns: pd.DataFrame, positions: pd.Series,
                    lookback_days: int, confidence: float) -> float:
    """
    Parametric (variance-covariance) VaR using current position weights.
    """
    recent = returns.tail(lookback_days)
    common_pairs = [p for p in positions.index if p in recent.columns]
    recent = recent[common_pairs]
    weights = positions[common_pairs].values  # USD notional per pair

    cov_matrix = recent.cov()  # daily return covariance
    portfolio_variance = weights @ cov_matrix.values @ weights.T
    portfolio_std_usd = np.sqrt(portfolio_variance)

    z_score = norm.ppf(confidence)
    var_estimate = z_score * portfolio_std_usd
    return var_estimate


def main():
    returns = load_returns_wide()
    positions = load_current_positions()

    print("Current net position (USD, signed):")
    print(positions.round(0))
    print()

    summary_rows = []
    for confidence in VAR_CONFIDENCE_LEVELS:
        hist_var, _ = historical_var(returns, positions, VAR_LOOKBACK_DAYS, confidence)
        param_var = parametric_var(returns, positions, VAR_LOOKBACK_DAYS, confidence)

        print(f"--- {int(confidence*100)}% confidence, {VAR_LOOKBACK_DAYS}-day lookback ---")
        print(f"Historical VaR : ${hist_var:,.0f}")
        print(f"Parametric VaR : ${param_var:,.0f}")
        print()

        summary_rows.append({
            "confidence": confidence,
            "lookback_days": VAR_LOOKBACK_DAYS,
            "historical_var_usd": hist_var,
            "parametric_var_usd": param_var,
        })

    pd.DataFrame(summary_rows).to_csv(OUTPUT_FILE, index=False)
    print(f"Saved VaR summary to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
