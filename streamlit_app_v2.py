import os
import streamlit as st
import requests
import pandas as pd

# ============================================================
# COCOA INTELLIGENCE HUB — STREAMLIT COMMAND CENTER
# ============================================================

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

# IMPORTANT: This must be the FIRST Streamlit command in the file.
st.set_page_config(
    page_title="Cocoa Intelligence Hub",
    page_icon="🍫",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# COCOA THEME
# ============================================================

st.markdown(
    """
<style>
/* Main application */
.stApp {
    background: #f7f1e8;
    color: #241812;
}

/* General text */
.stApp, .stApp p, .stApp label, .stApp span {
    color: #241812;
}

/* Hero */
.hero {
    background: linear-gradient(135deg, #4a2416 0%, #7a3f22 55%, #b36a2c 100%);
    color: #ffffff;
    border-radius: 20px;
    padding: 1.7rem 2rem;
    margin-bottom: 1.4rem;
    border: 1px solid #6b351f;
    box-shadow: 0 8px 24px rgba(74, 36, 22, .16);
}
.hero * {
    color: #ffffff !important;
}
.hero-title {
    font-size: 2.1rem;
    font-weight: 850;
}

/* Cards */
.panel {
    background: #fffdf9;
    color: #241812;
    border: 1px solid #dfcdb9;
    border-radius: 18px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 4px 14px rgba(74, 36, 22, .06);
}
.panel h1, .panel h2, .panel h3, .panel h4, .panel p {
    color: #241812 !important;
}

/* Metrics */
[data-testid="stMetric"] {
    background: #fffdf9;
    border: 1px solid #dfcdb9;
    border-radius: 16px;
    padding: 1rem 1.25rem;
    box-shadow: 0 4px 14px rgba(74, 36, 22, .05);
}
[data-testid="stMetricLabel"] {
    color: #6b4a38 !important;
    font-weight: 700;
}
[data-testid="stMetricValue"] {
    color: #4a2416 !important;
    font-weight: 850;
}

/* Section labels */
.section-label {
    color: #7a3f22 !important;
    font-size: .82rem;
    font-weight: 850;
    text-transform: uppercase;
    letter-spacing: .06em;
    margin: 1.2rem 0 .7rem;
}

/* Buttons */
.stButton > button {
    background: #7a3f22;
    color: #ffffff !important;
    border: 0;
    border-radius: 12px;
    font-weight: 750;
}
.stButton > button:hover {
    background: #5f2e1c;
    color: #ffffff !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #efe2d3;
}
section[data-testid="stSidebar"] * {
    color: #241812 !important;
}

/* Tabs */
button[data-baseweb="tab"] {
    color: #5f3a28 !important;
    font-weight: 700;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #7a3f22 !important;
}

/* Tables */
[data-testid="stDataFrame"] {
    border: 1px solid #dfcdb9;
    border-radius: 12px;
}

/* Hide Streamlit chrome */
#MainMenu, footer {
    visibility: hidden;
}

/* Alerts */
.stAlert {
    border-radius: 12px;
}
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# HELPERS
# ============================================================

@st.cache_data(ttl=300)
def get_json(endpoint):
    try:
        response = requests.get(
            f"{API_BASE}{endpoint}",
            timeout=180,
        )
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
        actual = (
            str(model.get("model", ""))
            .lower()
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )
        if actual in wanted:
            return model.get("forecast")
    return None


def rows_from(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "countries", "prices", "pairs", "items", "rows"):
            if isinstance(value.get(key), list):
                return value[key]
        return [value]
    return []


def show_error(label, value):
    if isinstance(value, dict) and "_error" in value:
        st.warning(f"{label}: {value['_error']}")
        return True
    return False


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown("## 🍫 Cocoa Hub")
    st.caption("Market intelligence command center")
    st.divider()

    if st.button("↻ Refresh intelligence", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("### Live architecture")
    st.markdown("**PostgreSQL → ML Engine → FastAPI → Streamlit**")
    st.divider()

    st.markdown("### Intelligence layers")
    st.markdown(
        """
        • International cocoa prices

        • FX context

        • Weather & crop risk

        • XGBoost

        • Random Forest

        • Time-Series

        • Ensemble intelligence
        """
    )

    st.divider()
    st.caption(
        "ML outputs are experimental and require further historical validation."
    )


# ============================================================
# MARKET INTELLIGENCE API
# ============================================================

data = get_json("/market-intelligence")

if show_error("FastAPI connection failed", data):
    st.info("Keep FastAPI running on port 8000.")
    st.stop()

intel = data.get(
    "intelligence",
    data.get("market_intelligence", data),
)

if not isinstance(intel, dict):
    st.error("Unexpected /market-intelligence response.")
    st.stop()


# ============================================================
# CORE VALUES
# ============================================================

latest = intel.get("latest_price")
forecast = intel.get("forecast_price")
change = intel.get("expected_change_pct")
low = intel.get("forecast_low")
high = intel.get("forecast_high")
confidence = intel.get("confidence_index")

risk = first(
    intel.get("risk_level"),
    intel.get("risk"),
)

direction = first(
    intel.get("ensemble_direction"),
    intel.get("direction"),
    intel.get("market_direction"),
)

agreement = first(
    intel.get("model_agreement"),
    intel.get("agreement"),
)

signal = first(
    intel.get("signal"),
    intel.get("market_signal"),
)

market_state = first(
    intel.get("market_state"),
    intel.get("market"),
)

horizon = first(
    intel.get("horizon"),
    intel.get("forecast_horizon"),
    default="30-trading-days",
)

models = intel.get("models", [])

xgb = model_value(models, ["xgboost", "xgb"])
rf = model_value(
    models,
    ["random forest", "random_forest", "randomforest", "rf"],
)
ts = model_value(
    models,
    ["time-series", "time_series", "timeseries", "time series"],
)

# Nigerian benchmark and forecast returned by FastAPI.
nigeria_price = intel.get("nigeria_price_ngn")
nigeria_forecast = intel.get("nigeria_forecast_ngn")


# ============================================================
# HERO
# ============================================================

st.markdown(
    """
<div class="hero">
    <div><b>● LIVE INTELLIGENCE ENGINE</b></div>
    <div class="hero-title">Cocoa Intelligence Hub</div>
    <div>
        Evidence-based market intelligence for cocoa traders,
        exporters and researchers.
    </div>
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# EXECUTIVE VIEW
# ============================================================

st.markdown(
    '<div class="section-label">Executive Market View</div>',
    unsafe_allow_html=True,
)

a, b, c, d = st.columns(4)

a.metric(
    "Latest ICCO Price",
    f"${fmt_num(latest)}",
)

b.metric(
    "30-Day Ensemble",
    f"${fmt_num(forecast)}",
)

c.metric(
    "Expected Change",
    fmt_pct(change),
)

d.metric(
    "Confidence",
    f"{fmt_num(confidence, 0)}/100"
    if confidence is not None
    else "—",
)

a, b, c, d = st.columns(4)

a.metric("Direction", direction)
b.metric("Risk", risk)
c.metric("Market State", market_state)
d.metric("Signal", signal)


# ============================================================
# TABS
# ============================================================

tab_market, tab_models, tab_context, tab_nigeria, tab_system = st.tabs(
    [
        "📊 Market",
        "🧠 ML Models",
        "🌦️ Market Context",
        "🇳🇬 Nigeria",
        "⚙️ System",
    ]
)


# ============================================================
# MARKET
# ============================================================

with tab_market:
    st.markdown(
        '<div class="section-label">Forecast Intelligence</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.05, 1])

    with left:
        st.markdown(
            '<div class="panel">',
            unsafe_allow_html=True,
        )

        st.markdown("### Forecast Range")

        p, q = st.columns(2)

        p.metric(
            "Lower Bound",
            f"${fmt_num(low)}",
        )

        q.metric(
            "Upper Bound",
            f"${fmt_num(high)}",
        )

        st.write(f"**Horizon:** {horizon}")
        st.write(f"**Model agreement:** {agreement}")

        if (
            low is not None
            and high is not None
            and forecast is not None
        ):
            st.bar_chart(
                pd.DataFrame(
                    {"Price": [low, forecast, high]},
                    index=["Lower", "Ensemble", "Upper"],
                ),
                height=260,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown(
            '<div class="panel">',
            unsafe_allow_html=True,
        )

        st.markdown("### Intelligence Drivers")

        drivers = intel.get(
            "drivers",
            intel.get("key_drivers", []),
        )

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
            intel.get(
                "risks",
                intel.get("warnings", []),
            ),
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
    st.markdown(
        '<div class="section-label">Machine Learning Layer</div>',
        unsafe_allow_html=True,
    )

    a, b, c, d = st.columns(4)

    a.metric("XGBoost", f"${fmt_num(xgb)}")
    b.metric("Random Forest", f"${fmt_num(rf)}")
    c.metric("Time-Series", f"${fmt_num(ts)}")
    d.metric("Ensemble", f"${fmt_num(forecast)}")

    if models:
        table = [
            {
                "Model": model.get("model", "—"),
                "Forecast": model.get("forecast"),
                "Weight": model.get("weight"),
                "MAE": model.get("mae"),
                "RMSE": model.get("rmse"),
                "MAPE": model.get("mape"),
                "Eligible": model.get("eligible"),
            }
            for model in models
        ]

        st.dataframe(
            pd.DataFrame(table),
            use_container_width=True,
            hide_index=True,
        )

    st.info(
        "Model status: EXPERIMENTAL — validate against a larger "
        "historical dataset before production trading use."
    )


# ============================================================
# MARKET CONTEXT
# ============================================================

with tab_context:
    st.markdown(
        '<div class="section-label">External Market Context</div>',
        unsafe_allow_html=True,
    )

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

    st.markdown("### 💱 Foreign Exchange")

    fx = get_json("/fx")

    if not show_error("FX feed unavailable", fx):
        items = (
            fx.get("pairs", fx.get("data", []))
            if isinstance(fx, dict)
            else fx
        )

        out = []

        if isinstance(items, dict):
            for pair, item in items.items():
                if isinstance(item, dict):
                    out.append(
                        {
                            "Pair": pair,
                            "Rate": item.get("rate"),
                            "Date": item.get(
                                "rate_date",
                                item.get("date", "—"),
                            ),
                            "Source": item.get("source", "—"),
                        }
                    )

        elif isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    out.append(
                        {
                            "Pair": (
                                f"{item.get('base_currency', '—')}/"
                                f"{item.get('quote_currency', '—')}"
                            ),
                            "Rate": item.get("rate"),
                            "Date": item.get(
                                "rate_date",
                                item.get("date", "—"),
                            ),
                            "Source": item.get("source", "—"),
                        }
                    )

        if out:
            st.dataframe(
                pd.DataFrame(out),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No FX pairs returned.")

    st.markdown("### 🌦️ Weather & Crop-Risk Context")

    weather = get_json("/weather")

    if not show_error("Weather feed unavailable", weather):
        observations = (
            weather.get("observations", [])
            if isinstance(weather, dict)
            else []
        )

        forecasts = (
            weather.get("forecasts", [])
            if isinstance(weather, dict)
            else []
        )

        st.metric(
            "Weather Records",
            len(observations)
            if isinstance(observations, list)
            else 0,
        )

        if isinstance(forecasts, list) and forecasts:
            st.dataframe(
                pd.DataFrame(forecasts),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# NIGERIA
# ============================================================

with tab_nigeria:
    st.markdown(
        '<div class="section-label">Nigeria Cocoa Intelligence</div>',
        unsafe_allow_html=True,
    )

    st.markdown("### 🇳🇬 Nigerian Cocoa Price Intelligence")

    n1, n2, n3 = st.columns(3)

    n1.metric(
        "Estimated Nigeria Price",
        (
            f"₦{fmt_num(nigeria_price)}"
            if nigeria_price is not None
            else "—"
        ),
    )

    n2.metric(
        "Nigeria Cocoa Forecast",
        (
            f"₦{fmt_num(nigeria_forecast)}"
            if nigeria_forecast is not None
            else "—"
        ),
    )

    if (
        nigeria_price is not None
        and nigeria_forecast is not None
    ):
        nigeria_change = (
            (float(nigeria_forecast) / float(nigeria_price)) - 1
        ) * 100

        n3.metric(
            "Forecast Change",
            f"{nigeria_change:+.2f}%",
        )
    else:
        n3.metric("Forecast Change", "—")

    st.markdown(
        '<div class="panel">',
        unsafe_allow_html=True,
    )

    st.markdown("#### Nigerian Benchmark")

    st.markdown(
        (
            f"### ₦{fmt_num(nigeria_price)}"
            if nigeria_price is not None
            else "### —"
        )
    )

    st.write("Estimated Nigerian cocoa benchmark per tonne.")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="panel">',
        unsafe_allow_html=True,
    )

    st.markdown("#### Nigerian Forecast")

    st.markdown(
        (
            f"### ₦{fmt_num(nigeria_forecast)}"
            if nigeria_forecast is not None
            else "### —"
        )
    )

    st.write(f"Forecast horizon: {horizon}")

    st.markdown("</div>", unsafe_allow_html=True)

    st.caption(
        "The Nigerian estimate and forecast are generated automatically "
        "from the international cocoa benchmark and current FX context."
    )
st.markdown("### 🌍 Regional Cocoa News")
st.caption("Nigeria 🇳🇬 · Ghana 🇬🇭 · Côte d’Ivoire 🇨🇮 · Cameroon 🇨🇲")

news = get_json("/news")

if not show_error("Regional news feed unavailable", news):
    nr = rows_from(news)

    if nr:
        for item in nr[:20]:
            if not isinstance(item, dict):
                continue

            title = item.get("title", "Untitled")
            url = item.get("url")
            country = item.get("country") or item.get("country_name")
            source = item.get("source")

            st.markdown(
                f"**[{title}]({url})**"
                if url
                else f"**{title}**"
            )

            metadata = []

            if country:
                metadata.append(str(country))

            if source:
                metadata.append(str(source))

            if item.get("published_at"):
                metadata.append(str(item["published_at"]))

            if metadata:
                st.caption(" • ".join(metadata))

            st.divider()
    else:
        st.info("No regional cocoa news records returned.")

# ============================================================
# SYSTEM
# ============================================================

with tab_system:
    st.markdown(
        '<div class="section-label">Platform Health</div>',
        unsafe_allow_html=True,
    )

    a, b = st.columns(2)

    with a:
        st.markdown("### API Health")
        health = get_json("/health")

        if not show_error(
            "API health unavailable",
            health,
        ):
            st.json(health)

    with b:
        st.markdown("### Database Health")
        db = get_json("/db-health")

        if not show_error(
            "Database health unavailable",
            db,
        ):
            st.json(db)

    a, b, c, d = st.columns(4)

    a.metric("Database", "Connected")
    b.metric("FastAPI", "Online")
    c.metric("ML Engine", "Active")
    d.metric("Streamlit", "Online")

    with st.expander(
        "Raw /market-intelligence response"
    ):
        st.json(data)


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "Cocoa Intelligence Hub • Experimental ML intelligence layer • "
    "International prices • FX • Weather • Crop Risk • Nigerian Cocoa Context"
)
