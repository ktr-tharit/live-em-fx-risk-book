import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import FX_PAIRS, TRADE_THESES_FILE, TRADE_THESIS_DRIVERS

THESIS_COLUMNS = [
    "thesis_id", "as_of_date", "pair", "direction", "drivers",
    "custom_driver", "thesis", "conviction",
]
DIRECTIONS = {"LONG_USD", "SHORT_USD"}
CONVICTIONS = {"high", "medium", "low"}


def load_trade_theses() -> pd.DataFrame:
    if not TRADE_THESES_FILE.exists():
        return pd.DataFrame(columns=THESIS_COLUMNS)
    df = pd.read_csv(TRADE_THESES_FILE, parse_dates=["as_of_date"])
    for column in THESIS_COLUMNS:
        if column not in df:
            df[column] = pd.NA
    return df[THESIS_COLUMNS]


def validate_trade_theses(df: pd.DataFrame) -> None:
    missing = set(THESIS_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing trade thesis column(s): {sorted(missing)}")
    if df["thesis_id"].isna().any() or df["thesis_id"].duplicated().any():
        raise ValueError("thesis_id must be present and unique")
    invalid_pairs = sorted(set(df["pair"].dropna()) - set(FX_PAIRS))
    if invalid_pairs:
        raise ValueError(f"Unsupported pair(s): {invalid_pairs}")
    invalid_directions = sorted(set(df["direction"].dropna()) - DIRECTIONS)
    if invalid_directions:
        raise ValueError(f"Invalid direction(s): {invalid_directions}")
    invalid_convictions = sorted(set(df["conviction"].dropna().str.lower()) - CONVICTIONS)
    if invalid_convictions:
        raise ValueError(f"Invalid conviction(s): {invalid_convictions}")

    allowed_drivers = set(TRADE_THESIS_DRIVERS)
    for thesis_id, drivers in df.set_index("thesis_id")["drivers"].fillna("").items():
        selected = {driver.strip() for driver in str(drivers).split(";") if driver.strip()}
        unknown = selected - allowed_drivers
        if unknown:
            raise ValueError(f"{thesis_id} has unknown driver(s): {sorted(unknown)}")


def next_thesis_id(df: pd.DataFrame) -> str:
    numbers = pd.to_numeric(
        df["thesis_id"].astype(str).str.extract(r"(\d+)$", expand=False),
        errors="coerce",
    )
    number = int(numbers.max()) + 1 if numbers.notna().any() else 1
    return f"THESIS-{number:04d}"


def save_trade_theses(df: pd.DataFrame) -> None:
    output = df[THESIS_COLUMNS].copy()
    validate_trade_theses(output)
    output["as_of_date"] = pd.to_datetime(output["as_of_date"], errors="raise").dt.strftime("%Y-%m-%d")
    output["conviction"] = output["conviction"].str.lower()
    output.to_csv(TRADE_THESES_FILE, index=False)


def main() -> None:
    theses = load_trade_theses()
    validate_trade_theses(theses)
    print(f"Validated {len(theses)} trade theses in {TRADE_THESES_FILE}")
    if not theses.empty:
        print(theses[["thesis_id", "as_of_date", "pair", "direction", "conviction"]].tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
