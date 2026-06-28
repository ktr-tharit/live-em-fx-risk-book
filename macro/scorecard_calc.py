import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import (
    DATA_DIR,
    SCORECARD_FACTORS,
    SCORECARD_INPUTS_FILE,
    SCORECARD_WEIGHTS,
)

OUTPUT_FILE = DATA_DIR / "macro_scorecard.csv"


def get_weights(pair: str) -> dict[str, float]:
    return SCORECARD_WEIGHTS.get(pair, SCORECARD_WEIGHTS["default"])


def validate_inputs(df: pd.DataFrame) -> None:
    required = {"as_of_date", "pair", "confidence", "notes", *SCORECARD_FACTORS}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required column(s): {sorted(missing)}")

    for factor in SCORECARD_FACTORS:
        bad = df[~df[factor].between(-2, 2)]
        if not bad.empty:
            raise ValueError(
                f"{factor} must be between -2 and +2. Bad row(s):\n{bad}"
            )

    for pair, weights in SCORECARD_WEIGHTS.items():
        weight_sum = sum(weights.get(factor, 0.0) for factor in SCORECARD_FACTORS)
        if abs(weight_sum - 1.0) > 0.0001:
            raise ValueError(f"Weights for {pair} sum to {weight_sum:.4f}, not 1.0")


def score_to_lean(score: float) -> str:
    if score > 1.0:
        return "Strong USD lean"
    if score >= 0.3:
        return "Mild USD lean"
    if score > -0.3:
        return "Neutral/no clear edge"
    if score >= -1.0:
        return "Mild local-ccy lean"
    return "Strong local-ccy lean"


def calc_weighted_score(row: pd.Series) -> float:
    weights = get_weights(row["pair"])
    return sum(row[factor] * weights[factor] for factor in SCORECARD_FACTORS)


def calc_scorecard() -> pd.DataFrame:
    df = pd.read_csv(SCORECARD_INPUTS_FILE)
    df["as_of_date"] = pd.to_datetime(
        df["as_of_date"], errors="coerce", format="mixed"
    ).dt.normalize()
    if df["as_of_date"].isna().any():
        bad = df[df["as_of_date"].isna()]
        raise ValueError(f"Invalid as_of_date value(s):\n{bad}")
    validate_inputs(df)

    df["weighted_score"] = df.apply(calc_weighted_score, axis=1)
    df["lean"] = df["weighted_score"].apply(score_to_lean)
    df["weights_used"] = df["pair"].apply(
        lambda pair: "; ".join(
            f"{factor}={get_weights(pair)[factor]:.2f}"
            for factor in SCORECARD_FACTORS
        )
    )

    columns = [
        "as_of_date",
        "pair",
        *SCORECARD_FACTORS,
        "weighted_score",
        "lean",
        "confidence",
        "notes",
        "weights_used",
    ]
    return df[columns].sort_values(["as_of_date", "pair"])


def main() -> None:
    result = calc_scorecard()
    result.to_csv(OUTPUT_FILE, index=False, date_format="%Y-%m-%d")

    latest_date = result["as_of_date"].max()
    latest = result[result["as_of_date"] == latest_date].copy()

    print(f"Saved macro scorecard to {OUTPUT_FILE}")
    print(f"\nLatest scorecard ({latest_date.strftime('%Y-%m-%d')}):")
    print(
        latest[["pair", "weighted_score", "lean", "confidence"]]
        .sort_values("weighted_score", ascending=False)
        .to_string(index=False, formatters={"weighted_score": "{:.2f}".format})
    )


if __name__ == "__main__":
    main()
