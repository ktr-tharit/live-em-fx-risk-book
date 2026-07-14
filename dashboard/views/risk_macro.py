import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from config import DATA_DIR
from dashboard.common import active_positions, money, percent, read_csv


def _var_card(row: pd.Series) -> None:
    confidence = int(float(row["confidence"]) * 100)
    st.markdown(f"### {confidence}% VaR")
    historical = row.get("historical_var_usd", np.nan)
    parametric = row.get("parametric_var_usd", np.nan)
    standalone = row.get("sum_individual_historical_var_usd", np.nan)
    benefit = row.get("historical_diversification_benefit_usd", np.nan)
    benefit_pct = row.get("historical_diversification_benefit_pct", np.nan)

    cols = st.columns(2)
    cols[0].metric("Historical VaR", money(historical))
    cols[1].metric("Parametric VaR", money(parametric))
    cols = st.columns(2)
    cols[0].metric("Sum of stand-alone VaR", money(standalone))
    cols[1].metric("Diversification benefit", money(benefit), percent(benefit_pct))


def _var_chart(var: pd.DataFrame) -> None:
    chart_data = var.assign(confidence=var["confidence"].map(lambda x: f"{x:.0%}"))[
        ["confidence", "historical_var_usd", "parametric_var_usd", "sum_individual_historical_var_usd"]
    ].rename(columns={
        "historical_var_usd": "Historical VaR",
        "parametric_var_usd": "Parametric VaR",
        "sum_individual_historical_var_usd": "Stand-alone VaR sum",
    }).melt("confidence", var_name="Method", value_name="VaR USD")
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("confidence:N", title="Confidence", sort=["95%", "99%"]),
            xOffset="Method:N",
            y=alt.Y("VaR USD:Q", title="VaR (USD)"),
            color=alt.Color("Method:N", legend=alt.Legend(orient="bottom")),
            tooltip=["confidence", "Method", alt.Tooltip("VaR USD:Q", format="$,.0f")],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, width="stretch")


def _backtest_summary(data: pd.DataFrame, label: str, historical: bool) -> None:
    if data.empty:
        st.info(f"No {label.lower()} output yet. Run the pipeline first.")
        return

    data = data.sort_values("date").copy()
    observations = len(data)
    total_breaches = int(data["exception"].sum())
    breach_rate = total_breaches / observations if observations else np.nan
    latest = data.iloc[-1]
    rolling_breaches = int(latest.get("rolling_exceptions", 0))
    zone = str(latest.get("traffic_light_zone", "n/a"))
    worst_loss = data["actual_pnl_usd"].min()

    cols = st.columns(4)
    cols[0].metric("Observations", f"{observations:,}")
    breach_delta = breach_rate - 0.01
    cols[1].metric(
        "Total breaches",
        f"{total_breaches:,}",
        f"{breach_delta:+.1%} vs expected",
        delta_color="inverse",
    )
    cols[2].metric("Rolling 250d breaches", f"{rolling_breaches} / 250")
    cols[2].caption(f"Traffic light: {zone}")
    cols[3].metric("Worst daily P&L", money(worst_loss, signed=True))

    if historical:
        active = active_positions()
        if active.empty:
            st.warning("There is no active position to replay. Layer A may reflect the last pipeline run.")
        else:
            signed = active.assign(
                signed_notional=active["notional_usd"]
                * active["direction"].map({"LONG_USD": 1, "SHORT_USD": -1, "FLAT": 0})
            ).groupby("pair")["signed_notional"].sum()
            book = " · ".join(f"{pair} {money(value, signed=True)}" for pair, value in signed.items())
            st.caption(f"Constant-book replay using the current net positions: {book}")
        st.caption("Expected breach rate at 99% VaR is approximately 1%; Layer A tests this book against historical FX moves.")
    else:
        st.caption("Layer B uses the positions that were actually active on each date. A short live history is not yet a formal Basel test.")

    plot = data[["date", "actual_pnl_usd", "var_usd", "exception"]].copy()
    plot["Loss threshold"] = -plot["var_usd"]
    base = alt.Chart(plot).encode(x=alt.X("date:T", title=None))
    pnl_line = base.mark_line(color="#4c78a8", strokeWidth=1).encode(
        y=alt.Y("actual_pnl_usd:Q", title="USD"),
        tooltip=[alt.Tooltip("date:T"), alt.Tooltip("actual_pnl_usd:Q", format="$,.0f")],
    )
    threshold = base.mark_line(color="#f58518", strokeDash=[5, 4]).encode(y="Loss threshold:Q")
    breaches = base.transform_filter("datum.exception == 1").mark_point(
        color="#e45756", filled=True, size=55
    ).encode(y="actual_pnl_usd:Q", tooltip=[alt.Tooltip("date:T"), alt.Tooltip("actual_pnl_usd:Q", format="$,.0f")])
    st.altair_chart((pnl_line + threshold + breaches).properties(height=330), width="stretch")

    breach_rows = data.loc[data["exception"] == 1, [
        "date", "actual_pnl_usd", "var_usd", "rolling_exceptions", "traffic_light_zone",
    ]].copy()
    breach_rows["excess_loss_usd"] = (-breach_rows["actual_pnl_usd"] - breach_rows["var_usd"]).clip(lower=0)
    with st.expander(f"Breach history ({len(breach_rows)})"):
        st.dataframe(
            breach_rows.sort_values("date", ascending=False).style.format({
                "actual_pnl_usd": "${:,.0f}", "var_usd": "${:,.0f}", "excess_loss_usd": "${:,.0f}",
            }), width="stretch", hide_index=True,
        )


def page_risk_monitor() -> None:
    st.title("Risk & Diversification")
    st.caption("Current-book VaR, diversification, historical replay, and live exception monitoring")
    var = read_csv(DATA_DIR / "var_summary.csv")
    backtest_a = read_csv(DATA_DIR / "backtest_layer_a_historical.csv", parse_dates=["date"])
    backtest_b = read_csv(DATA_DIR / "backtest_layer_b_live.csv", parse_dates=["date"])
    stress = read_csv(DATA_DIR / "stress_test_results.csv")

    var_tab, historical_tab, live_tab, stress_tab = st.tabs([
        "VaR & Diversification", "Historical Layer A", "Live Layer B", "Stress",
    ])
    with var_tab:
        if var.empty:
            st.info("No VaR output yet. Run the pipeline first.")
        else:
            _var_chart(var)
            cols = st.columns(len(var))
            for col, (_, row) in zip(cols, var.sort_values("confidence").iterrows()):
                with col.container(border=True):
                    _var_card(row)

            active_pairs = active_positions()["pair"].nunique()
            latest = var.sort_values("confidence").iloc[-1]
            benefit_pct = latest.get("historical_diversification_benefit_pct", 0)
            if active_pairs <= 1:
                st.info("Diversification benefit is zero because the current book has only one net currency-pair exposure.")
            elif benefit_pct < 0:
                st.warning("Negative diversification benefit means the current positions reinforce each other's tail risk.")
            else:
                st.success(f"At 99% confidence, diversification reduces stand-alone VaR by {benefit_pct:.1%}.")

    with historical_tab:
        _backtest_summary(backtest_a, "Historical Layer A", historical=True)
    with live_tab:
        _backtest_summary(backtest_b, "Live Layer B", historical=False)
    with stress_tab:
        if stress.empty:
            st.info("No stress output yet. Run the pipeline first.")
        else:
            worst = stress.sort_values("portfolio_pnl_usd").iloc[0]
            st.metric("Worst scenario", worst["scenario"], money(worst["portfolio_pnl_usd"], signed=True))
            st.dataframe(stress, width="stretch", hide_index=True)
