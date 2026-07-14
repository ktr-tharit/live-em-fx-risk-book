from datetime import date

import pandas as pd
import streamlit as st

from config import FX_PAIRS
from dashboard.common import (
    active_positions, load_positions, money, next_position_id, order_summary,
    run_script, save_positions,
)
from macro.trade_thesis import load_trade_theses

DIRECTION_LABELS = {
    "LONG_USD": "Long USD (local weakens)",
    "SHORT_USD": "Short USD (local strengthens)",
}


def _display_text(value, fallback: str) -> str:
    if pd.isna(value) or not str(value).strip():
        return fallback
    return str(value)


def _refresh_pnl() -> None:
    ok, output = run_script("pnl/pnl_calc.py")
    if not ok:
        st.error("Position saved, but P&L refresh failed.")
        st.code(output)


def page_order_book() -> None:
    st.title("Order Book")
    st.caption("Open, close, and audit every position with its own P&L attribution.")
    positions = load_positions()
    orders = order_summary(positions=positions)
    theses = load_trade_theses()
    thesis_lookup = theses.set_index("thesis_id") if not theses.empty else pd.DataFrame()

    open_tab, closed_tab, new_tab = st.tabs(["Open positions", "Closed positions", "Open new position"])
    with open_tab:
        active = active_positions(positions)
        active_orders = orders.loc[orders["status"] == "OPEN"].set_index("position_id")
        if active.empty:
            st.info("No open positions.")
        for _, row in active.iterrows():
            marked = active_orders.loc[row["position_id"]]
            with st.container(border=True):
                info, thesis, action = st.columns([1.5, 2.4, 0.8])
                info.markdown(f"**{row['position_id']} · {row['pair']}**")
                info.write(f"{row['direction']} · {money(row['notional_usd'])}")
                info.caption(f"Opened {row['as_of_date']:%Y-%m-%d}")
                thesis.write(_display_text(row["view_tag"], "No view tag"))
                thesis.caption(_display_text(row["rationale"], "No rationale"))
                linked_id = row.get("linked_thesis_id")
                if pd.notna(linked_id) and linked_id in thesis_lookup.index:
                    linked = thesis_lookup.loc[linked_id]
                    thesis.caption(f"Linked thesis: {linked_id} · {linked['conviction']} conviction")
                action.metric("Unrealized P&L", money(marked["pnl_usd"], signed=True))
                if action.button("Close position", key=f"close_{row['position_id']}"):
                    positions.loc[int(row["_row_id"]), "end_date"] = pd.Timestamp.today().normalize()
                    save_positions(positions)
                    _refresh_pnl()
                    st.success(f"Closed {row['position_id']} as of today.")
                    st.rerun()

    with closed_tab:
        closed = orders.loc[orders["status"] == "CLOSED"].sort_values("end_date", ascending=False)
        if closed.empty:
            st.info("No closed positions.")
        else:
            st.dataframe(
                closed[[
                    "position_id", "pair", "direction", "as_of_date", "end_date",
                    "notional_usd", "pnl_usd", "return_on_notional", "linked_thesis_id",
                ]].style.format({
                    "notional_usd": "${:,.0f}", "pnl_usd": "${:+,.0f}",
                    "return_on_notional": "{:+.2%}",
                }), width="stretch", hide_index=True,
            )

    with new_tab:
        with st.form("open_position_form", clear_on_submit=True):
            cols = st.columns(4)
            opened = cols[0].date_input("Open date", value=date.today())
            pair = cols[1].selectbox("Pair", list(FX_PAIRS))
            direction = cols[2].selectbox(
                "Direction", list(DIRECTION_LABELS), format_func=lambda value: DIRECTION_LABELS[value]
            )
            notional = cols[3].number_input("Notional USD", min_value=1.0, value=1_000_000.0, step=50_000.0)
            view_tag = st.text_input("View tag")
            rationale = st.text_area("Execution notes")
            thesis_options = [""]
            thesis_labels = {"": "No linked thesis"}
            if not theses.empty:
                for _, thesis_row in theses.sort_values("as_of_date", ascending=False).iterrows():
                    thesis_id = thesis_row["thesis_id"]
                    thesis_options.append(thesis_id)
                    thesis_labels[thesis_id] = (
                        f"{thesis_id} · {thesis_row['pair']} · {thesis_row['direction']} · "
                        f"{thesis_row['conviction']}"
                    )
            linked_thesis_id = st.selectbox(
                "Linked trade thesis",
                thesis_options,
                format_func=lambda value: thesis_labels[value],
                help="Create a thesis on the Trade Thesis page first, then link the position here.",
            )
            if st.form_submit_button("Open position", type="primary"):
                linked = thesis_lookup.loc[linked_thesis_id] if linked_thesis_id else None
                if linked is not None and (linked["pair"] != pair or linked["direction"] != direction):
                    st.error("The linked thesis must use the same pair and direction as the position.")
                else:
                    row = {
                        "position_id": next_position_id(positions), "as_of_date": opened.isoformat(),
                        "end_date": "", "pair": pair, "direction": direction,
                        "notional_usd": notional,
                        "view_tag": view_tag or (linked["drivers"] if linked is not None else ""),
                        "rationale": rationale or (linked["thesis"] if linked is not None else ""),
                        "linked_thesis_id": linked_thesis_id,
                    }
                    save_positions(pd.concat([positions, pd.DataFrame([row])], ignore_index=True))
                    _refresh_pnl()
                    st.success(f"Opened {row['position_id']}. P&L starts from the next available close.")
