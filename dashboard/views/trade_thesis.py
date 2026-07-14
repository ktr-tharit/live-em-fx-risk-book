from datetime import date

import pandas as pd
import streamlit as st

from config import FX_PAIRS, TRADE_THESIS_DRIVERS
from macro.trade_thesis import load_trade_theses, next_thesis_id, save_trade_theses

DIRECTION_LABELS = {
    "Long USD (local weakens)": "LONG_USD",
    "Short USD (local strengthens)": "SHORT_USD",
}


def _direction_label(direction: str) -> str:
    return next((label for label, value in DIRECTION_LABELS.items() if value == direction), direction)


def _thesis_history(theses: pd.DataFrame) -> None:
    st.subheader("Thesis history")
    if theses.empty:
        st.info("No trade thesis yet. Add the first one above.")
        return

    filter_cols = st.columns([1, 1, 2])
    pair_filter = filter_cols[0].selectbox("Filter pair", ["All", *FX_PAIRS], key="thesis_pair_filter")
    conviction_filter = filter_cols[1].selectbox(
        "Filter conviction", ["All", "high", "medium", "low"], key="thesis_conviction_filter"
    )
    view = theses.copy()
    if pair_filter != "All":
        view = view.loc[view["pair"] == pair_filter]
    if conviction_filter != "All":
        view = view.loc[view["conviction"].str.lower() == conviction_filter]

    view = view.sort_values(["as_of_date", "thesis_id"], ascending=False).copy()
    view["direction"] = view["direction"].map(_direction_label)
    view["drivers"] = view.apply(
        lambda row: "; ".join(
            part for part in [str(row["drivers"]) if pd.notna(row["drivers"]) else "", str(row["custom_driver"]) if pd.notna(row["custom_driver"]) else ""]
            if part
        ), axis=1,
    )
    st.dataframe(
        view[["thesis_id", "as_of_date", "pair", "direction", "drivers", "thesis", "conviction"]],
        width="stretch", hide_index=True,
        column_config={
            "as_of_date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "thesis": st.column_config.TextColumn("Thesis", width="large"),
            "drivers": st.column_config.TextColumn("Drivers", width="large"),
        },
    )


def page_trade_thesis() -> None:
    st.title("Trade Thesis")
    st.caption("Write the directional view first, then link it to a position when you trade.")
    theses = load_trade_theses()

    with st.form("trade_thesis_form", clear_on_submit=True, border=False):
        top = st.columns([1, 1, 0.65])
        as_of = top[0].date_input("Date", value=date.today())
        pair = top[1].selectbox("Pair", list(FX_PAIRS))
        direction_label = top[2].selectbox("Direction", list(DIRECTION_LABELS))

        with st.container(border=True):
            st.markdown("**What's driving this pair right now?**")
            drivers = st.pills(
                "Macro drivers",
                TRADE_THESIS_DRIVERS,
                selection_mode="multi",
                label_visibility="collapsed",
            )
            custom_driver = st.text_input(
                "Other driver", placeholder="Something else...", label_visibility="collapsed"
            )

        with st.container(border=True):
            st.markdown("**Thesis**")
            st.caption("Write 1–2 sentences. What will happen and why?")
            thesis = st.text_area(
                "Trade thesis",
                placeholder=(
                    "e.g. THB will weaken because the Fed–BOT rate differential is widening — "
                    "BOT has no room to hike while the Fed stays higher for longer."
                ),
                height=150,
                max_chars=500,
                label_visibility="collapsed",
            )

        conviction = st.segmented_control(
            "Conviction", ["High", "Medium", "Low"], default="Medium", width="stretch"
        )
        submitted = st.form_submit_button("Save trade thesis", type="primary", width="stretch")
        if submitted:
            if not drivers and not custom_driver.strip():
                st.error("Select at least one driver or enter another driver.")
            elif not thesis.strip():
                st.error("Write the thesis before saving.")
            else:
                row = {
                    "thesis_id": next_thesis_id(theses),
                    "as_of_date": as_of,
                    "pair": pair,
                    "direction": DIRECTION_LABELS[direction_label],
                    "drivers": ";".join(drivers or []),
                    "custom_driver": custom_driver.strip(),
                    "thesis": thesis.strip(),
                    "conviction": str(conviction).lower(),
                }
                save_trade_theses(pd.concat([theses, pd.DataFrame([row])], ignore_index=True))
                st.success(f"Saved {row['thesis_id']}. You can now link it from Order Book.")
                st.rerun()

    st.divider()
    _thesis_history(theses)
