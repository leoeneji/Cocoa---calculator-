import streamlit as st
import requests
import pandas as pd

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Cocoa Intelligence Hub",
    page_icon="🍫",
    layout="wide",
)

st.title("🍫 Cocoa Intelligence Hub")
st.caption("Experimental ML intelligence dashboard")

def get_json(endpoint):
    try:
        response = requests.get(f"{API_BASE}{endpoint}", timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"_error": str(e)}

def fmt_num(value, decimals=2):
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{decimals}f}"
    except Exception:
        return str(value)

def fmt_pct(value):
    if value is None:
        return "—"
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return str(value)

def model_value(models, names):
    wanted = {
        str(x).lower().replace("-", "").replace("_", "").replace(" ", "")
        for x in names
    }
    for model in models or []:
        actual = str(model.get("model", "")).lower()
        actual = actual.replace("-", "").replace("_", "").replace(" ", "")
        if actual in wanted:
            return model.get("forecast")
    return None

data = get_json("/market-intelligence")

if "_error" in data:
    st.error(f"Could not connect to FastAPI: {data['_error']}")
    st.info("Make sure the Cocoa Intelligence Hub backend is running on port 8000.")
    st.stop()

intelligence = data.get("intelligence", data.get("market_intelligence", data))

# Core values
latest = intelligence.get("latest_price")
forecast = intelligence.get("forecast_price")
change = intelligence.get("expected_change_pct")
low = intelligence.get("forecast_low")
high = intelligence.get("forecast_high")
confidence = intelligence.get("confidence_index")
risk = intelligence.get("risk_level", intelligence.get("risk"))
direction = intelligence.get(
    "ensemble_direction",
    intelligence.get("direction", intelligence.get("market_direction"))
)
agreement = intelligence.get("model_agreement", intelligence.get("agreement"))
signal = intelligence.get("signal", intelligence.get("market_signal"))
state = intelligence.get("market_state", intelligence.get("market"))
horizon = intelligence.get("horizon", intelligence.get("forecast_horizon", "30-trading-days"))

models = intelligence.get("models", [])

xgb = model_value(models, ["xgboost", "xgb"])
rf = model_value(models, ["random forest", "random_forest", "randomforest", "rf"])
ts = model_value(models, ["time-series", "time_series", "timeseries", "time series"])
persistence = model_value(models, ["persistence"])

st.subheader("Market Intelligence")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest Price", f"${fmt_num(latest)}")
c2.metric("30-Day Forecast", f"${fmt_num(forecast)}")
c3.metric("Expected Change", fmt_pct(change))
c4.metric("Confidence", f"{fmt_num(confidence, 0)}/100" if confidence is not None else "—")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Direction", direction or "—")
c6.metric("Risk", risk or "—")
c7.metric("Market State", state or "—")
c8.metric("Signal", signal or "—")

st.divider()

st.subheader("ML Model Forecasts")

m1, m2, m3, m4 = st.columns(4)
m1.metric("XGBoost", f"${fmt_num(xgb)}")
m2.metric("Random Forest", f"${fmt_num(rf)}")
m3.metric("Time-Series", f"${fmt_num(ts)}")
m4.metric("Ensemble", f"${fmt_num(forecast)}")

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Forecast Range")
    st.metric("Low", f"${fmt_num(low)}")
    st.metric("High", f"${fmt_num(high)}")
    st.write(f"**Horizon:** {horizon}")

with right:
    st.subheader("Model Agreement")
    st.write(agreement or "—")

st.divider()

drivers = intelligence.get("drivers", intelligence.get("key_drivers", []))
cautions = intelligence.get(
    "cautions",
    intelligence.get("risks", intelligence.get("warnings", []))
)

d1, d2 = st.columns(2)

with d1:
    st.subheader("Key Drivers")
    if isinstance(drivers, list) and drivers:
        for item in drivers:
            st.write(f"• {item}")
    elif drivers:
        st.write(drivers)
    else:
        st.write("—")

with d2:
    st.subheader("Cautions")
    if isinstance(cautions, list) and cautions:
        for item in cautions:
            st.write(f"• {item}")
    elif cautions:
        st.write(cautions)
    else:
        st.write("—")

st.divider()

st.subheader("Connected Intelligence Sources")

s1, s2, s3 = st.columns(3)
s1.metric("FX Context", "Connected")
s2.metric("Weather Context", "Connected")
s3.metric("News Context", "Connected")

with st.expander("Raw /market-intelligence response"):
    st.json(data)

st.caption("Cocoa Intelligence Hub • ML outputs are experimental and should be validated against historical data.")
