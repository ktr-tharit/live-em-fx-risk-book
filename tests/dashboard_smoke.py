from streamlit.testing.v1 import AppTest


app = AppTest.from_file("dashboard/dashboard.py", default_timeout=20)
app.run()
assert not app.exception, app.exception

for page in ["Order Book", "P&L Monitor", "Macro Scorecard", "Risk Monitor"]:
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception, f"{page}: {app.exception}"

print("Dashboard smoke test passed for every page")
