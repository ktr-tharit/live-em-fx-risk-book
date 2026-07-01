import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    DATA_DIR,
    FX_PAIRS,
    PROJECT_ROOT,
    SCORECARD_FACTORS,
    SCORECARD_INPUTS_FILE,
    POSITIONS_FILE,
)

POSITION_COLUMNS = [
    "as_of_date",
    "end_date",
    "pair",
    "direction",
    "notional_usd",
    "entry_rate",
    "view_tag",
    "rationale",
    "linked_scorecard_date",
]

SCORECARD_COLUMNS = [
    "as_of_date",
    "pair",
    *SCORECARD_FACTORS,
    "confidence",
    "notes",
]

PIPELINE_STEPS = [
    ("Macro scorecard", "macro/scorecard_calc.py"),
    ("P&L", "pnl/pnl_calc.py"),
    ("VaR", "risk/var_calc.py"),
    ("Backtest", "risk/backtest_var.py"),
    ("Stress test", "risk/stress_test.py"),
]


def money(value: float | int | None) -> str:
    if pd.isna(value):
        return "n/a"
    return f"${value:,.0f}"


def read_csv(path: Path, parse_dates: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates or [])


def load_positions() -> pd.DataFrame:
    df = read_csv(POSITIONS_FILE, parse_dates=["as_of_date", "end_date", "linked_scorecard_date"])
    for col in POSITION_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[POSITION_COLUMNS]


def save_positions(df: pd.DataFrame) -> None:
    df = df.copy()
    for col in ["as_of_date", "end_date", "linked_scorecard_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")
        df[col] = df[col].fillna("")
    df.to_csv(POSITIONS_FILE, index=False)


def active_positions(as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    df = load_positions()
    if df.empty:
        return df
    if as_of is None:
        as_of = pd.Timestamp.today().normalize()
    df = df.copy()
    df["_row_id"] = df.index
    return df[
        (df["as_of_date"] <= as_of)
        & (df["end_date"].isna() | (df["end_date"] > as_of))
    ]


def load_latest_macro() -> pd.DataFrame:
    df = read_csv(DATA_DIR / "macro_scorecard.csv", parse_dates=["as_of_date"])
    if df.empty:
        return df
    latest_date = df["as_of_date"].max()
    return df[df["as_of_date"] == latest_date].copy()


def suggested_decision(lean: str) -> str:
    mapping = {
        "Strong USD lean": "Consider LONG_USD",
        "Mild USD lean": "Watch / small LONG_USD",
        "Neutral/no clear edge": "No clear trade",
        "Mild local-ccy lean": "Watch / small SHORT_USD",
        "Strong local-ccy lean": "Consider SHORT_USD",
    }
    return mapping.get(lean, "Review manually")


def suggested_size(score: float) -> str:
    abs_score = abs(score)
    if abs_score > 1.0:
        return "1.0x base notional"
    if abs_score >= 0.3:
        return "0.5x base notional"
    return "0.0x"


def run_script(script_path: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    return result.returncode == 0, output


def run_pipeline(refresh_fx: bool = False) -> list[tuple[str, bool, str]]:
    steps = PIPELINE_STEPS.copy()
    if refresh_fx:
        steps.insert(0, ("FX refresh", "data_ingestion/fetch_fx.py"))
    return [(name, *run_script(script)) for name, script in steps]


def pipeline_controls() -> None:
    st.sidebar.header("Pipeline")
    refresh_fx = st.sidebar.checkbox("Refresh FX rates first", value=False)
    if st.sidebar.button("Run pipeline", type="primary"):
        with st.spinner("Running pipeline..."):
            results = run_pipeline(refresh_fx=refresh_fx)
        for name, ok, output in results:
            with st.sidebar.expander(f"{name}: {'OK' if ok else 'FAILED'}", expanded=not ok):
                st.code(output or "No output")
        st.cache_data.clear()


def page_overview() -> None:
    st.title("Overview")
    positions = active_positions()
    pnl = read_csv(DATA_DIR / "daily_pnl.csv", parse_dates=["date"])
    var = read_csv(DATA_DIR / "var_summary.csv")
    stress = read_csv(DATA_DIR / "stress_test_results.csv")
    backtest = read_csv(DATA_DIR / "backtest_layer_a_historical.csv", parse_dates=["date"])
    macro = load_latest_macro()

    gross = positions["notional_usd"].sum() if not positions.empty else 0
    direction_sign = positions["direction"].map({"LONG_USD": 1, "SHORT_USD": -1, "FLAT": 0})
    net = (positions["notional_usd"] * direction_sign).sum() if not positions.empty else 0
    latest_pnl = pnl.groupby("date")["daily_pnl_usd"].sum().iloc[-1] if not pnl.empty else pd.NA
    mtd_pnl = pd.NA
    if not pnl.empty:
        latest_date = pnl["date"].max()
        mtd_pnl = pnl[pnl["date"].dt.to_period("M") == latest_date.to_period("M")]["daily_pnl_usd"].sum()

    var_99 = pd.NA
    if not var.empty and 0.99 in set(var["confidence"]):
        var_99 = var.loc[var["confidence"] == 0.99, "historical_var_usd"].iloc[0]

    worst_stress_name = "n/a"
    worst_stress_pnl = pd.NA
    if not stress.empty:
        worst = stress.sort_values("portfolio_pnl_usd").iloc[0]
        worst_stress_name = worst["scenario"]
        worst_stress_pnl = worst["portfolio_pnl_usd"]

    zone = "n/a"
    if not backtest.empty:
        zone = backtest.iloc[-1].get("traffic_light_zone", "n/a")

    cols = st.columns(6)
    cols[0].metric("Gross notional", money(gross))
    cols[1].metric("Net notional", money(net))
    cols[2].metric("Latest daily P&L", money(latest_pnl))
    cols[3].metric("MTD P&L", money(mtd_pnl))
    cols[4].metric("99% Hist VaR", money(var_99))
    cols[5].metric("Backtest zone", zone)

    st.subheader("Current Book")
    st.dataframe(positions.drop(columns=["_row_id"], errors="ignore"), use_container_width=True)

    st.subheader("Risk Summary")
    st.write(f"Worst stress scenario: **{worst_stress_name}** ({money(worst_stress_pnl)})")
    if not macro.empty:
        view = macro[["pair", "weighted_score", "lean", "confidence"]].copy()
        st.dataframe(view, use_container_width=True)


def page_macro_scorecard() -> None:
    st.title("Macro Scorecard")
    latest = load_latest_macro()
    if latest.empty:
        st.info("No macro output yet. Run the scorecard after adding inputs.")
    else:
        view = latest.copy()
        view["suggested_decision"] = view["lean"].apply(suggested_decision)
        view["suggested_size"] = view["weighted_score"].apply(suggested_size)
        st.dataframe(
            view[
                [
                    "pair",
                    *SCORECARD_FACTORS,
                    "weighted_score",
                    "lean",
                    "confidence",
                    "suggested_decision",
                    "suggested_size",
                    "notes",
                ]
            ],
            use_container_width=True,
        )

    st.subheader("Add Scorecard Row")
    with st.form("scorecard_form", clear_on_submit=True):
        cols = st.columns(3)
        as_of = cols[0].date_input("as_of_date", value=date.today())
        pair = cols[1].selectbox("pair", list(FX_PAIRS.keys()))
        confidence = cols[2].selectbox("confidence", ["low", "medium", "high"])

        score_cols = st.columns(len(SCORECARD_FACTORS))
        scores = {}
        for col, factor in zip(score_cols, SCORECARD_FACTORS):
            scores[factor] = col.number_input(factor, min_value=-2, max_value=2, value=0, step=1)

        notes = st.text_area("notes")
        submitted = st.form_submit_button("Append scorecard input")
        if submitted:
            df = read_csv(SCORECARD_INPUTS_FILE, parse_dates=["as_of_date"])
            row = {
                "as_of_date": as_of.isoformat(),
                "pair": pair,
                **scores,
                "confidence": confidence,
                "notes": notes,
            }
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            df = df[SCORECARD_COLUMNS].copy()
            df["as_of_date"] = pd.to_datetime(
                df["as_of_date"], errors="coerce", format="mixed"
            ).dt.strftime("%Y-%m-%d")
            df.to_csv(SCORECARD_INPUTS_FILE, index=False)
            ok, output = run_script("macro/scorecard_calc.py")
            st.success("Scorecard input appended." if ok else "Saved input, but scorecard run failed.")
            st.code(output)


def page_position_book() -> None:
    st.title("Position Book")
    positions = load_positions()

    st.subheader("Active Positions")
    active = active_positions()
    if active.empty:
        st.info("No active positions.")
    else:
        header = st.columns([1.1, 1, 1, 1, 1, 1.3, 2.2, 0.9])
        for col, label in zip(
            header,
            ["Opened", "Pair", "Direction", "Notional", "Entry", "View", "Rationale", ""],
        ):
            col.caption(label)

        for _, row in active.iterrows():
            cols = st.columns([1.1, 1, 1, 1, 1, 1.3, 2.2, 0.9])
            cols[0].write(row["as_of_date"].strftime("%Y-%m-%d"))
            cols[1].write(row["pair"])
            cols[2].write(row["direction"])
            cols[3].write(money(row["notional_usd"]))
            cols[4].write(f"{row['entry_rate']:.4f}")
            cols[5].write(row["view_tag"])
            cols[6].write(row["rationale"])
            if cols[7].button("Close", key=f"close_{row['_row_id']}", type="secondary"):
                positions.loc[int(row["_row_id"]), "end_date"] = pd.Timestamp.today().normalize()
                save_positions(positions)
                st.success(f"Closed {row['pair']} {row['direction']} as of today.")
                st.rerun()

    st.subheader("Position History")
    st.dataframe(positions, use_container_width=True)

    st.subheader("Open New Position")
    with st.form("open_position_form", clear_on_submit=True):
        cols = st.columns(4)
        as_of = cols[0].date_input("as_of_date", value=date.today(), key="open_as_of")
        pair = cols[1].selectbox("pair", list(FX_PAIRS.keys()), key="open_pair")
        direction = cols[2].selectbox("direction", ["LONG_USD", "SHORT_USD", "FLAT"])
        notional = cols[3].number_input("notional_usd", min_value=0.0, value=1_000_000.0, step=50_000.0)

        cols = st.columns(3)
        entry_rate = cols[0].number_input("entry_rate", min_value=0.0, value=0.0, step=0.0001, format="%.4f")
        linked_date = cols[1].date_input("linked_scorecard_date", value=as_of)
        view_tag = cols[2].text_input("view_tag")
        rationale = st.text_area("rationale")

        submitted = st.form_submit_button("Append new position")
        if submitted:
            row = {
                "as_of_date": as_of.isoformat(),
                "end_date": "",
                "pair": pair,
                "direction": direction,
                "notional_usd": notional,
                "entry_rate": entry_rate,
                "view_tag": view_tag,
                "rationale": rationale,
                "linked_scorecard_date": linked_date.isoformat(),
            }
            updated = pd.concat([positions, pd.DataFrame([row])], ignore_index=True)
            save_positions(updated)
            st.success("Position appended. Run the pipeline to refresh P&L and risk outputs.")


def page_pnl_monitor() -> None:
    st.title("P&L Monitor")
    pnl = read_csv(DATA_DIR / "daily_pnl.csv", parse_dates=["date"])
    if pnl.empty:
        st.info("No P&L output yet. Run pnl_calc.py or the full pipeline.")
        return

    portfolio_daily = pnl.groupby("date", as_index=True)["daily_pnl_usd"].sum().sort_index()
    cumulative = portfolio_daily.cumsum()

    st.subheader("Portfolio Cumulative P&L")
    st.line_chart(cumulative)

    st.subheader("Daily P&L")
    st.bar_chart(portfolio_daily.tail(60))

    st.subheader("P&L by Pair")
    by_pair = pnl.groupby("pair")["daily_pnl_usd"].agg(["sum", "mean", "count"]).reset_index()
    st.dataframe(by_pair, use_container_width=True)

    st.subheader("Raw Daily P&L")
    st.dataframe(pnl.sort_values("date", ascending=False), use_container_width=True)


def page_risk_monitor() -> None:
    st.title("Risk Monitor")
    var = read_csv(DATA_DIR / "var_summary.csv")
    backtest_a = read_csv(DATA_DIR / "backtest_layer_a_historical.csv", parse_dates=["date"])
    backtest_b = read_csv(DATA_DIR / "backtest_layer_b_live.csv", parse_dates=["date"])
    stress = read_csv(DATA_DIR / "stress_test_results.csv")

    st.subheader("VaR")
    st.dataframe(var, use_container_width=True)

    st.subheader("Backtest")
    if not backtest_a.empty:
        latest = backtest_a.iloc[-1]
        cols = st.columns(3)
        cols[0].metric("Layer A rolling exceptions", int(latest["rolling_exceptions"]))
        cols[1].metric("Traffic light zone", latest["traffic_light_zone"])
        cols[2].metric("Latest VaR", money(latest["var_usd"]))
        st.dataframe(backtest_a.tail(30).sort_values("date", ascending=False), use_container_width=True)
    if not backtest_b.empty:
        st.caption("Layer B live position backtest")
        st.dataframe(backtest_b.sort_values("date", ascending=False), use_container_width=True)

    st.subheader("Stress")
    if not stress.empty:
        worst = stress.sort_values("portfolio_pnl_usd").iloc[0]
        st.metric("Worst scenario", worst["scenario"], money(worst["portfolio_pnl_usd"]))
        st.dataframe(stress, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="EM FX Risk Book", layout="wide")
    pipeline_controls()

    page = st.sidebar.radio(
        "Page",
        ["Overview", "Macro Scorecard", "Position Book", "P&L Monitor", "Risk Monitor"],
    )

    if page == "Overview":
        page_overview()
    elif page == "Macro Scorecard":
        page_macro_scorecard()
    elif page == "Position Book":
        page_position_book()
    elif page == "P&L Monitor":
        page_pnl_monitor()
    elif page == "Risk Monitor":
        page_risk_monitor()


if __name__ == "__main__":
    main()
