import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import yfinance as yf
import pandas as pd
from datetime import datetime

from config import FX_PAIRS, FX_RATES_FILE, DATA_DIR

LOOKBACK_PERIOD = "10y"
INTERVAL = "1d"


def fetch_pair(ticker: str) -> pd.DataFrame:
    """Fetch historical daily close prices for a single FX ticker."""
    df = yf.download(ticker, period=LOOKBACK_PERIOD, interval=INTERVAL, progress=False)
    if df.empty:
        print(f"  [WARNING] No data returned for {ticker}")
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Close"]].rename(columns={"Close": "rate"})
    df.index.name = "date"
    return df


def fetch_all_pairs() -> pd.DataFrame:
    """Fetch all configured FX pairs and combine into a single long-format dataframe."""
    all_data = []
    for pair_name, ticker in FX_PAIRS.items():
        print(f"Fetching {pair_name} ({ticker})...")
        df = fetch_pair(ticker)
        if df.empty:
            continue
        df = df.reset_index()
        df["pair"] = pair_name
        all_data.append(df)

    if not all_data:
        raise RuntimeError("No FX data could be fetched for any pair. Check tickers / network.")

    combined = pd.concat(all_data, ignore_index=True)

    missing = [c for c in ["date", "pair", "rate"] if c not in combined.columns]
    if missing:
        raise RuntimeError(
            f"Expected columns {missing} not found after fetching. "
            f"Got columns: {list(combined.columns)}. "
            f"This usually means yfinance returned an unexpected column shape "
            f"(e.g. a MultiIndex) — check the fetch_pair() flattening logic."
        )

    combined = combined[["date", "pair", "rate"]]
    combined["date"] = pd.to_datetime(combined["date"]).dt.date
    return combined


def merge_and_save(new_data: pd.DataFrame) -> None:
    """Merge freshly fetched data with existing CSV, dedupe on (date, pair), and save."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if FX_RATES_FILE.exists():
        existing = pd.read_csv(FX_RATES_FILE, parse_dates=["date"])
        existing["date"] = existing["date"].dt.date
        combined = pd.concat([existing, new_data], ignore_index=True)
    else:
        combined = new_data

    combined = combined.drop_duplicates(subset=["date", "pair"], keep="last")
    combined = combined.sort_values(["pair", "date"]).reset_index(drop=True)

    combined.to_csv(FX_RATES_FILE, index=False)
    print(f"\nSaved {len(combined)} total rows to {FX_RATES_FILE}")
    print(f"Date range: {combined['date'].min()} to {combined['date'].max()}")
    print(f"Pairs included: {sorted(combined['pair'].unique())}")


def main():
    print(f"=== FX Data Fetch run: {datetime.now().isoformat(timespec='seconds')} ===\n")
    new_data = fetch_all_pairs()
    merge_and_save(new_data)
    print("\nDone.")


if __name__ == "__main__":
    main()