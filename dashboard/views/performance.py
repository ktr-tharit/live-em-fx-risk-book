import numpy as np
import pandas as pd
import streamlit as st

from config import DATA_DIR
from dashboard.common import active_positions, money, order_summary, percent, read_csv


def _portfolio_daily(pnl: pd.DataFrame) -> pd.Series:
    if pnl.empty:
        return pd.Series(dtype=float)
    return pnl.groupby("date")["daily_pnl_usd"].sum().sort_index()


def page_overview() -> None:
    st.title("EM FX Risk Book")
    st.caption("Live exposure, order-level performance, and risk at a glance")
    pnl = read_csv(DATA_DIR / "daily_pnl.csv", parse_dates=["date"])
    orders = order_summary(pnl=pnl)
    active = orders.loc[orders["status"] == "OPEN"]
    daily = _portfolio_daily(pnl)

    gross = active["notional_usd"].sum()
    signs = active["direction"].map({"LONG_USD": 1, "SHORT_USD": -1, "FLAT": 0})
    net = (active["notional_usd"] * signs).sum()
    realized = orders.loc[orders["status"] == "CLOSED", "pnl_usd"].sum()
    unrealized = active["pnl_usd"].sum()

    cols = st.columns(4)
    cols[0].metric("Open gross notional", money(gross))
    cols[1].metric("Net USD direction", money(net, signed=True))
    cols[2].metric("Realized P&L", money(realized, signed=True))
    cols[3].metric("Unrealized P&L", money(unrealized, signed=True))

    left, right = st.columns([1.45, 1])
    with left:
        st.subheader("Open positions")
        if active.empty:
            st.info("No open positions.")
        else:
            view = active[[
                "position_id", "as_of_date", "pair", "direction", "notional_usd",
                "last_rate", "pnl_usd", "return_on_notional",
            ]].copy()
            st.dataframe(
                view.style.format({
                    "notional_usd": "${:,.0f}", "last_rate": "{:,.4f}",
                    "pnl_usd": "${:+,.0f}", "return_on_notional": "{:+.2%}",
                }), width="stretch", hide_index=True,
            )
    with right:
        st.subheader("Cumulative P&L")
        if daily.empty:
            st.info("Run the P&L pipeline to populate this chart.")
        else:
            st.line_chart(daily.cumsum(), height=280)

    st.subheader("Recent closed positions")
    closed = orders.loc[orders["status"] == "CLOSED"].sort_values("end_date", ascending=False).head(10)
    if closed.empty:
        st.info("No closed positions yet.")
    else:
        st.dataframe(
            closed[["position_id", "pair", "direction", "as_of_date", "end_date", "pnl_usd", "return_on_notional"]]
            .style.format({"pnl_usd": "${:+,.0f}", "return_on_notional": "{:+.2%}"}),
            width="stretch", hide_index=True,
        )


def page_pnl_monitor() -> None:
    st.title("P&L Monitor")
    st.caption("P&L is marked close-to-close after entry and attributed by position_id.")
    pnl = read_csv(DATA_DIR / "daily_pnl.csv", parse_dates=["date"])
    if pnl.empty:
        st.info("No P&L output yet. Run the pipeline.")
        return

    daily = _portfolio_daily(pnl)
    cumulative = daily.cumsum()
    drawdown = cumulative - cumulative.cummax()
    sharpe = daily.mean() / daily.std() * np.sqrt(252) if daily.std() else np.nan
    cols = st.columns(4)
    cols[0].metric("Total P&L", money(daily.sum(), signed=True))
    cols[1].metric("Latest daily P&L", money(daily.iloc[-1], signed=True))
    cols[2].metric("Max drawdown", money(drawdown.min(), signed=True))
    cols[3].metric("P&L Sharpe", "n/a" if pd.isna(sharpe) else f"{sharpe:.2f}")

    tab1, tab2, tab3 = st.tabs(["Portfolio", "By position", "Daily ledger"])
    with tab1:
        st.line_chart(cumulative, height=300)
        st.bar_chart(daily.tail(60), height=250)
    with tab2:
        orders = order_summary(pnl=pnl).sort_values("pnl_usd", ascending=False)
        st.dataframe(
            orders[[
                "position_id", "status", "pnl_type", "pair", "direction", "as_of_date",
                "end_date", "notional_usd", "pnl_usd", "return_on_notional", "last_mark_date",
            ]].style.format({
                "notional_usd": "${:,.0f}", "pnl_usd": "${:+,.0f}",
                "return_on_notional": "{:+.2%}",
            }), width="stretch", hide_index=True,
        )
    with tab3:
        selected = st.selectbox("Position", ["All", *sorted(pnl["position_id"].unique())])
        detail = pnl if selected == "All" else pnl.loc[pnl["position_id"] == selected]
        st.dataframe(detail.sort_values(["date", "position_id"], ascending=False), width="stretch", hide_index=True)
