import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from config import DATA_DIR, POSITIONS_FILE, PROJECT_ROOT

POSITION_COLUMNS = [
    "position_id", "as_of_date", "end_date", "pair", "direction",
    "notional_usd", "view_tag", "rationale", "linked_scorecard_date",
]
PIPELINE_STEPS = [
    ("Macro scorecard", "macro/scorecard_calc.py"),
    ("P&L", "pnl/pnl_calc.py"),
    ("VaR", "risk/var_calc.py"),
    ("Backtest", "risk/backtest_var.py"),
    ("Stress test", "risk/stress_test.py"),
]


def money(value, signed: bool = False) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}${value:,.0f}"


def percent(value, decimals: int = 1) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:.{decimals}%}"


def read_csv(path: Path, parse_dates=None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates or [])


def load_positions() -> pd.DataFrame:
    df = read_csv(
        POSITIONS_FILE,
        parse_dates=["as_of_date", "end_date", "linked_scorecard_date"],
    )
    for column in POSITION_COLUMNS:
        if column not in df:
            df[column] = pd.NA
    return df[POSITION_COLUMNS]


def save_positions(df: pd.DataFrame) -> None:
    output = df[POSITION_COLUMNS].copy()
    for column in ["as_of_date", "end_date", "linked_scorecard_date"]:
        output[column] = pd.to_datetime(output[column], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    output.to_csv(POSITIONS_FILE, index=False)


def active_positions(positions=None, as_of=None) -> pd.DataFrame:
    positions = load_positions() if positions is None else positions
    as_of = pd.Timestamp.today().normalize() if as_of is None else pd.Timestamp(as_of)
    active = positions.loc[
        (positions["as_of_date"] <= as_of)
        & (positions["end_date"].isna() | (positions["end_date"] > as_of))
    ].copy()
    active["_row_id"] = active.index
    return active


def next_position_id(positions: pd.DataFrame) -> str:
    numbers = pd.to_numeric(
        positions["position_id"].astype(str).str.extract(r"(\d+)$", expand=False),
        errors="coerce",
    )
    number = int(numbers.max()) + 1 if numbers.notna().any() else 1
    return f"POS-{number:04d}"


def order_summary(positions=None, pnl=None) -> pd.DataFrame:
    positions = load_positions() if positions is None else positions
    pnl = read_csv(DATA_DIR / "daily_pnl.csv", parse_dates=["date"]) if pnl is None else pnl
    summary = positions.copy()
    if pnl.empty:
        summary["pnl_usd"] = 0.0
        summary["last_mark_date"] = pd.NaT
        summary["last_rate"] = np.nan
        summary["daily_return"] = np.nan
    else:
        totals = pnl.groupby("position_id", as_index=False).agg(
            pnl_usd=("daily_pnl_usd", "sum"),
            last_mark_date=("date", "max"),
            last_rate=("rate", "last"),
            daily_return=("daily_return", "last"),
        )
        summary = summary.merge(totals, on="position_id", how="left")
        summary["pnl_usd"] = summary["pnl_usd"].fillna(0.0)
    today = pd.Timestamp.today().normalize()
    summary["status"] = np.select(
        [
            summary["as_of_date"] > today,
            summary["end_date"].isna() | (summary["end_date"] > today),
        ],
        ["PENDING", "OPEN"],
        default="CLOSED",
    )
    summary["pnl_type"] = summary["status"].map({
        "PENDING": "NOT STARTED", "OPEN": "UNREALIZED", "CLOSED": "REALIZED",
    })
    summary["return_on_notional"] = summary["pnl_usd"] / summary["notional_usd"].replace(0, np.nan)
    return summary


def run_script(path: str):
    result = subprocess.run([sys.executable, path], cwd=PROJECT_ROOT, capture_output=True, text=True)
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    return result.returncode == 0, output


def pipeline_controls() -> None:
    st.sidebar.header("Pipeline")
    refresh_fx = st.sidebar.checkbox("Refresh FX rates first")
    if st.sidebar.button("Run pipeline", type="primary", width="stretch"):
        steps = PIPELINE_STEPS.copy()
        if refresh_fx:
            steps.insert(0, ("FX refresh", "data_ingestion/fetch_fx.py"))
        with st.spinner("Running pipeline..."):
            results = [(name, *run_script(path)) for name, path in steps]
        for name, ok, output in results:
            with st.sidebar.expander(f"{name}: {'OK' if ok else 'FAILED'}", expanded=not ok):
                st.code(output or "No output")
        st.cache_data.clear()
