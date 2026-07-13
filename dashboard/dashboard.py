import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
else:
    # Streamlit may place dashboard/ before the project root, which makes
    # dashboard.py shadow the dashboard package.
    sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)

from dashboard.common import pipeline_controls
from dashboard.views.book import page_order_book
from dashboard.views.performance import page_overview, page_pnl_monitor
from dashboard.views.risk_macro import page_macro_scorecard, page_risk_monitor


def main() -> None:
    st.set_page_config(page_title="EM FX Risk Book", layout="wide")
    st.markdown(
        """
        <style>
        .block-container {max-width: 1450px; padding-top: 1.5rem; padding-bottom: 2rem;}
        div[data-testid="stMetric"] {border: 1px solid rgba(128, 128, 128, 0.28);
            border-radius: 0.55rem; padding: 0.75rem 1rem; background: transparent;}
        div[data-testid="stMetricValue"] {font-size: 1.55rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    pipeline_controls()
    pages = {
        "Overview": page_overview,
        "Order Book": page_order_book,
        "P&L Monitor": page_pnl_monitor,
        "Macro Scorecard": page_macro_scorecard,
        "Risk Monitor": page_risk_monitor,
    }
    pages[st.sidebar.radio("Page", list(pages))]()


if __name__ == "__main__":
    main()
