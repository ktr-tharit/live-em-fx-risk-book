import sys
from pathlib import Path
from statistics import NormalDist

sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

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
    """Load exact USD P&L returns for USDXXX pairs, one column per pair."""
    df = pd.read_csv(FX_RATES_FILE, parse_dates=["date"])
    wide = df.pivot(index="date", columns="pair", values="rate").sort_index()
    # USD P&L on a USD notional: (S_t - S_t-1) / S_t.
    returns = (1 - wide.shift(1) / wide).dropna(how="all")
    return returns


def load_current_positions(as_of_date: pd.Timestamp | None = None) -> pd.DataFrame:
    df = pd.read_csv(POSITIONS_FILE, parse_dates=["as_of_date", "end_date"])
    if as_of_date is None:
        as_of_date = pd.Timestamp.today().normalize()
    else:
        as_of_date = pd.Timestamp(as_of_date).normalize()

    df = df[
        (df["as_of_date"] <= as_of_date)
        & (df["end_date"].isna() | (df["end_date"] > as_of_date))
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
    if not common_pairs:
        return 0.0, pd.Series(dtype=float)
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
    if not common_pairs:
        return 0.0
    recent = recent[common_pairs]
    weights = positions[common_pairs].values  # USD notional per pair

    cov_matrix = recent.cov()  # daily return covariance
    portfolio_variance = weights @ cov_matrix.values @ weights.T
    portfolio_std_usd = np.sqrt(portfolio_variance)

    z_score = NormalDist().inv_cdf(confidence)
    var_estimate = z_score * portfolio_std_usd
    return var_estimate


def annualized_portfolio_volatility(hypothetical_pnl: pd.Series, gross_notional: float) -> float:
    if hypothetical_pnl.empty or gross_notional == 0:
        return 0.0
    daily_return = hypothetical_pnl / gross_notional
    return daily_return.std() * np.sqrt(252)


def sum_individual_historical_var(
    returns: pd.DataFrame,
    positions: pd.Series,
    lookback_days: int,
    confidence: float,
) -> float:
    individual_vars = []
    for pair, signed_notional in positions.items():
        pair_position = pd.Series({pair: signed_notional})
        pair_var, _ = historical_var(returns, pair_position, lookback_days, confidence)
        individual_vars.append(pair_var)
    return float(np.sum(individual_vars))


def main():
    returns = load_returns_wide()
    positions = load_current_positions()

    print("Current net position (USD, signed):")
    print(positions.round(0))
    print()

    summary_rows = []
    gross_notional = positions.abs().sum()
    for confidence in VAR_CONFIDENCE_LEVELS:
        hist_var, hypothetical_pnl = historical_var(returns, positions, VAR_LOOKBACK_DAYS, confidence)
        param_var = parametric_var(returns, positions, VAR_LOOKBACK_DAYS, confidence)
        sum_individual_var = sum_individual_historical_var(
            returns,
            positions,
            VAR_LOOKBACK_DAYS,
            confidence,
        )
        diversification_benefit = sum_individual_var - hist_var
        diversification_benefit_pct = (
            diversification_benefit / sum_individual_var if sum_individual_var else 0.0
        )
        volatility = annualized_portfolio_volatility(hypothetical_pnl, gross_notional)

        print(f"--- {int(confidence*100)}% confidence, {VAR_LOOKBACK_DAYS}-day lookback ---")
        print(f"Historical VaR : ${hist_var:,.0f}")
        print(f"Parametric VaR : ${param_var:,.0f}")
        print(f"Sum individual VaR : ${sum_individual_var:,.0f}")
        print(f"Diversification benefit : ${diversification_benefit:,.0f} ({diversification_benefit_pct:.1%})")
        print(f"Portfolio volatility : {volatility:.1%}")
        print()

        summary_rows.append({
            "confidence": confidence,
            "lookback_days": VAR_LOOKBACK_DAYS,
            "historical_var_usd": hist_var,
            "parametric_var_usd": param_var,
            "portfolio_volatility_annualized": volatility,
            "sum_individual_historical_var_usd": sum_individual_var,
            "historical_diversification_benefit_usd": diversification_benefit,
            "historical_diversification_benefit_pct": diversification_benefit_pct,
        })

    pd.DataFrame(summary_rows).to_csv(OUTPUT_FILE, index=False)
    print(f"Saved VaR summary to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
