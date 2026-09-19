import streamlit as st
import requests
import pandas as pd

# ============================================================
# COCOA INTELLIGENCE HUB — STREAMLIT COMMAND CENTER
# ============================================================

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Cocoa Intelligence Hub",
    page_icon="🍫",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Premium UI ----------
st.markdown("""
<style>
    /* Page */
    .stApp {
        background:
            radial-gradient(circle at 10% 0%, rgba(126, 86, 48, .13), transparent 30%),
            radial-gradient(circle at 100% 0%, rgba(35, 94, 76, .10), transparent 28%),
            #f5f6f3;
    }

    .block-container {
        max-width: 1450px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #18251f 0%, #101713 100%);
    }
    [data-testid="stSidebar"] * {
        color: #eef3ed;
    }

    /* Typography */
    h1, h2, h3 {
        color: #17231d !important;
        letter-spacing: -0.02em;
    }

    .hero {
        padding: 1.7rem 2rem;
        border-radius: 24px;
        background: linear-gradient(135deg, #17231d 0%, #274d3e 58%, #6d4a2d 100%);
        box-shadow: 0 16px 40px rgba(28, 42, 35, .18);
        margin-bottom: 1.4rem;
    }
    .hero-title {
        color: white !important;
        font-size: 2.25rem;
        font-weight: 800;
        margin: 0;
    }
    .hero-sub {
        color: rgba(255,255,255,.78);
        font-size: 1rem;
        margin-top: .35rem;
    }

    .section-label {
        color: #6d4a2d;
        font-size: .76rem;
        font-weight: 800;
        letter-spacing: .14em;
        text-transform: uppercase;
        margin: 1.25rem 0 .5rem;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: rgba(255,255,255,.88);
        border: 1px solid rgba(23,35,29,.08);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        min-height: 118px;
        box-shadow: 0 8px 24px rgba(23,35,29,.07);
    }
    [data-testid="stMetricLabel"] {
        color: #647067 !important;
        font-weight: 650 !important;
    }
    [data-testid="stMetricValue"] {
        color: #17231d !important;
        font-weight: 800 !important;
    }

    /* Cards around columns */
    .panel {
        background: rgba(255,255,255,.9);
        border: 1px solid rgba(23,35,29,.08);
        border-radius: 20px;
        padding: 1.25rem;
        box-shadow: 0 8px 28px rgba(23,35,29,.06);
    }

    .badge {
        display: inline-block;
        padding: .35rem .75rem;
        border-radius: 999px;
        background: rgba(255,255,255,.13);
        color: white;
        font-size: .78rem;
        font-weight: 700;
        border: 1px solid rgba(255,255,255,.15);
    }

    .mini-card {
        background: #ffffff;
        border: 1px solid rgba(23,35,29,.08);
        border-radius: 16px;
        padding: 1rem;
        margin-bottom: .7rem;
        box-shadow: 0 5px 18px rgba(23,35,29,.05);
    }

    .mini-title {
        color: #68736c;
        font-size: .8rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: .05em;
    }

    .mini-value {
        color: #17231d;
        font-size: 1.25rem;
        font-weight: 800;
        margin-top: .25rem;
    }

    /* Tables */
    [data-testid="stDataFrame"] {
        border-radius: 16px;
        overflow: hidden;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: .35rem;
        background: #e9ede9;
        padding: .35rem;
        border-radius: 14px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: .55rem 1rem;
    }
    .stTabs [aria-selected="true"] {
        background: white;
        box-shadow: 0 3px 12px rgba(23,35,29,.08);
    }

    /* Buttons */
    .stButton > button {
        border-radius: 12px;
        border: 1px solid rgba(23,35,29,.12);
        font-weight: 700;
    }

    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ---------- Helpers ----------
@st.cache_data(ttl=300)
def get_json(endpoint):
    try:
        response = requests.get(f"{API_BASE}{endpoint}", timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"_error": str(exc)}


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


def first(*values, default="—"):
    for value in values:
        if value is not None and value != "":
            return value
    return default


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


def rows_from(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def show_error(label, value):
    if isinstance(value, dict) and "_error" in value:
        st.warning(f"{label}: {value['_error']}")
        return True
    return False


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("## 🍫 Cocoa Hub")
    st.caption("Market intelligence command center")
    st.divider()

    if st.button("↻  Refresh intelligence", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("### Live architecture")
    st.markdown("**PostgreSQL**  →  **ML Engine**  →  **FastAPI**  →  **Streamlit**")

    st.divider()
    st.markdown("### Intelligence layers")
    st.markdown("• International cocoa prices")
    st.markdown("• FX context")
    st.markdown("• Weather & crop risk")
    st.markdown("• XGBoost")
    st.markdown("• Random Forest")
    st.markdown("• Time-Series")
    st.markdown("• Ensemble intelligence")

    st.divider()
    st.caption("ML outputs are experimental and require further historical validation.")


# ============================================================
# MAIN
# ============================================================
data = get_json("/market-intelligence")

if show_error("FastAPI connection failed", data):
    st.info("Keep the FastAPI backend running on port 8000.")
    st.stop()

intel = data.get("intelligence", data.get("market_intelligence", data))

latest = intel.get("latest_price")
forecast = intel.get("forecast_price")
change = intel.get("expected_change_pct")
low = intel.get("forecast_low")
high = intel.get("forecast_high")
confidence = intel.get("confidence_index")
risk = first(intel.get("risk_level"), intel.get("risk"))
direction = first(
    intel.get("ensemble_direction"),
    intel.get("direction"),
    intel.get("market_direction")
)
agreement = first(intel.get("model_agreement"), intel.get("agreement"))
signal = first(intel.get("signal"), intel.get("market_signal"))
market_state = first(intel.get("market_state"), intel.get("market"))
horizon = first(
    intel.get("horizon"),
    intel.get("forecast_horizon"),
    default="30-trading-days"
)
models = intel.get("models", [])

xgb = model_value(models, ["xgboost", "xgb"])
rf = model_value(models, ["random forest", "random_forest", "randomforest", "rf"])
ts = model_value(models, ["time-series", "time_series", "timeseries", "time series"])


# ---------- Hero ----------
st.markdown("""
<div class="hero">
    <div class="badge">● LIVE INTELLIGENCE ENGINE</div>
    <div class="hero-title">Cocoa Intelligence Hub</div>
    <div class="hero-sub">
        Evidence-based market intelligence for cocoa traders, exporters and researchers.
    </div>
</div>
""", unsafe_allow_html=True)


# ---------- Executive summary ----------
st.markdown('<div class="section-label">Executive Market View</div>', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest ICCO Price", f"${fmt_num(latest)}")
c2.metric("30-Day Ensemble", f"${fmt_num(forecast)}")
c3.metric("Expected Change", fmt_pct(change))
c4.metric("Confidence", f"{fmt_num(confidence, 0)}/100" if confidence is not None else "—")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Direction", direction)
c2.metric("Risk", risk)
c3.metric("Market State", market_state)
c4.metric("Signal", signal)


# ============================================================
# TABS
# ============================================================
tab_market, tab_models, tab_context, tab_nigeria, tab_system = st.tabs([
    "📊 Market",
    "🧠 ML Models",
    "🌦️ Market Context",
    "🇳🇬 Nigeria",
    "⚙️ System",
])


# ============================================================
# MARKET
# ============================================================
with tab_market:
    st.markdown('<div class="section-label">Forecast Intelligence</div>', unsafe_allow_html=True)

    left, right = st.columns([1.05, 1])

    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("### Forecast Range")
        r1, r2 = st.columns(2)
        r1.metric("Lower Bound", f"${fmt_num(low)}")
        r2.metric("Upper Bound", f"${fmt_num(high)}")
        st.write(f"**Horizon:** {horizon}")
        st.write(f"**Model agreement:** {agreement}")

        if low is not None and high is not None and forecast is not None:
            chart = pd.DataFrame(
                {"Price": [low, forecast, high]},
                index=["Lower", "Ensemble", "Upper"],
            )
            st.bar_chart(chart, height=260)

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("### Intelligence Drivers")

        drivers = intel.get("drivers", intel.get("key_drivers", []))
        if isinstance(drivers, list) and drivers:
            for item in drivers:
                st.markdown(f"• {item}")
        elif drivers:
            st.write(drivers)
        else:
            st.write("No driver details returned.")

        st.markdown("### Cautions")
        cautions = intel.get(
            "cautions",
            intel.get("risks", intel.get("warnings", [])),
        )
        if isinstance(cautions, list) and cautions:
            for item in cautions:
                st.markdown(f"• {item}")
        elif cautions:
            st.write(cautions)
        else:
            st.write("No caution details returned.")

        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# ML MODELS
# ============================================================
with tab_models:
    st.markdown('<div class="section-label">Machine Learning Layer</div>', unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("XGBoost", f"${fmt_num(xgb)}")
    m2.metric("Random Forest", f"${fmt_num(rf)}")
    m3.metric("Time-Series", f"${fmt_num(ts)}")
    m4.metric("Ensemble", f"${fmt_num(forecast)}")

    if models:
        model_table = []
        for m in models:
            model_table.append({
                "Model": m.get("model", "—"),
                "Forecast": m.get("forecast"),
                "Weight": m.get("weight"),
                "MAE": m.get("mae"),
                "RMSE": m.get("rmse"),
                "MAPE": m.get("mape"),
                "Eligible": m.get("eligible"),
            })
        st.markdown("### Model Performance & Forecasts")
        st.dataframe(
            pd.DataFrame(model_table),
            use_container_width=True,
            hide_index=True,
        )

    if models:
        chart_rows = []
        for m in models:
            if isinstance(m, dict) and isinstance(m.get("forecast"), (int, float)):
                chart_rows.append({
                    "Model": str(m.get("model", "Model")),
                    "Forecast": m.get("forecast"),
                })
        if chart_rows:
            st.markdown("### Forecast Comparison")
            chart_df = pd.DataFrame(chart_rows).set_index("Model")
            st.bar_chart(chart_df, height=320)

    st.info(
        "Model status: EXPERIMENTAL — the ensemble should be validated against a larger "
        "historical dataset before being treated as a production trading model."
    )


# ============================================================
# MARKET CONTEXT
# ============================================================
with tab_context:
    st.markdown('<div class="section-label">External Market Context</div>', unsafe_allow_html=True)

    # International prices
    st.markdown("### 🍫 International Cocoa Market")
    prices = get_json("/prices")
    if not show_error("Price feed unavailable", prices):
        price_rows = rows_from(prices)
        if price_rows:
            st.dataframe(
                pd.DataFrame(price_rows),
                use_container_width=True,
                hide_index=True,
            )

    # FX
    st.markdown("### 💱 Foreign Exchange")
    fx = get_json("/fx")
    if not show_error("FX feed unavailable", fx):
        fx_rows = []
        source_items = fx if isinstance(fx, list) else fx.get("pairs", []) if isinstance(fx, dict) else []

        if isinstance(source_items, dict):
            source_items = list(source_items.items())
            for pair, item in source_items:
                if isinstance(item, dict):
                    fx_rows.append({
                        "Pair": pair,
                        "Base": item.get("base_currency", "—"),
                        "Quote": item.get("quote_currency", "—"),
                        "Rate": item.get("rate"),
                        "Date": item.get("rate_date", "—"),
                        "Source": item.get("source", "—"),
                    })
        elif isinstance(source_items, list):
            for item in source_items:
                if isinstance(item, dict):
                    fx_rows.append({
                        "Pair": f"{item.get('base_currency', '—')}/{item.get('quote_currency', '—')}",
                        "Base": item.get("base_currency", "—"),
                        "Quote": item.get("quote_currency", "—"),
                        "Rate": item.get("rate"),
                        "Date": item.get("rate_date", "—"),
                        "Source": item.get("source", "—"),
                    })

        if fx_rows:
            st.dataframe(
                pd.DataFrame(fx_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No FX pairs returned.")

    # Weather
    st.markdown("### 🌦️ Weather & Crop-Risk Context")
    weather = get_json("/weather")

    if not show_error("Weather feed unavailable", weather):
        observations = weather.get("observations", []) if isinstance(weather, dict) else []
        forecasts = weather.get("forecasts", []) if isinstance(weather, dict) else []

        forecast_rows = forecasts if isinstance(forecasts, list) else []
        temps, rain, risks = [], [], []

        for item in forecast_rows:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("temperature_max_c"), (int, float)):
                temps.append(item["temperature_max_c"])
            if isinstance(item.get("temperature_min_c"), (int, float)):
                temps.append(item["temperature_min_c"])
            if isinstance(item.get("rainfall_mm"), (int, float)):
                rain.append(item["rainfall_mm"])
            if isinstance(item.get("crop_risk_score"), (int, float)):
                risks.append(item["crop_risk_score"])

        avg_temp = weather.get("average_temperature_c")
        if avg_temp is None and temps:
            avg_temp = sum(temps) / len(temps)

        avg_rain = weather.get("average_rainfall_mm")
        if avg_rain is None and rain:
            avg_rain = sum(rain) / len(rain)

        crop_risk = weather.get("average_crop_risk_score")
        if crop_risk is None and risks:
            crop_risk = sum(risks) / len(risks)

        w1, w2, w3, w4 = st.columns(4)
        w1.metric("Weather Records", fmt_num(len(observations), 0))
        w2.metric("Avg Temperature", f"{fmt_num(avg_temp)} °C")
        w3.metric("Avg Rainfall", f"{fmt_num(avg_rain)} mm")
        w4.metric("Crop Risk", fmt_num(crop_risk))

        if forecast_rows:
            weather_table = []
            for item in forecast_rows:
                if isinstance(item, dict):
                    weather_table.append({
                        "Location": item.get("location", "—"),
                        "Date": item.get("date", "—"),
                        "Rainfall (mm)": item.get("rainfall_mm"),
                        "Max °C": item.get("temperature_max_c"),
                        "Min °C": item.get("temperature_min_c"),
                        "Rain Probability %": item.get("rain_probability_pct"),
                        "Crop Risk": item.get("crop_risk_score"),
                        "Source": item.get("source", "—"),
                    })
            if weather_table:
                st.dataframe(
                    pd.DataFrame(weather_table),
                    use_container_width=True,
                    hide_index=True,
                )


# ============================================================
# NIGERIA
# ============================================================
with tab_nigeria:
    st.markdown('<div class="section-label">Nigeria Cocoa Intelligence</div>', unsafe_allow_html=True)

    countries = get_json("/countries")
    if not show_error("Country data unavailable", countries):
        country_rows = rows_from(countries)
        if country_rows:
            st.dataframe(
                pd.DataFrame(country_rows),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("### 📰 Latest Cocoa News")
    news = get_json("/news")
    if not show_error("News feed unavailable", news):
        news_rows = rows_from(news)
        if news_rows:
            for item in news_rows[:10]:
                if not isinstance(item, dict):
                    continue
                title = item.get("title", "Untitled")
                url = item.get("url")
                published = item.get("published_at", "")
                if url:
                    st.markdown(f"**[{title}]({url})**")
                else:
                    st.markdown(f"**{title}**")
                if published:
                    st.caption(str(published))
                st.divider()
        else:
            st.info("No stored news records returned.")


# ============================================================
# SYSTEM
# ============================================================
with tab_system:
    st.markdown('<div class="section-label">Platform Health</div>', unsafe_allow_html=True)

    h1, h2 = st.columns(2)

    with h1:
        st.markdown("### API Health")
        health = get_json("/health")
        if not show_error("API health unavailable", health):
            st.json(health)

    with h2:
        st.markdown("### Database Health")
        db = get_json("/db-health")
        if not show_error("Database health unavailable", db):
            st.json(db)

    st.markdown("### Connected Architecture")
    a, b, c, d = st.columns(4)
    a.metric("Database", "Connected")
    b.metric("FastAPI", "Online")
    c.metric("ML Engine", "Active")
    d.metric("Streamlit", "Online")

    with st.expander("Raw /market-intelligence response"):
        st.json(data)


# ---------- Footer ----------
st.markdown("---")
st.caption(
    "Cocoa Intelligence Hub • Experimental ML intelligence layer • "
    "International prices • FX • Weather • Crop Risk • Nigerian Cocoa Context"
)
