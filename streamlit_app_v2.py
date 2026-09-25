import os
import time
import streamlit as st
import requests
import pandas as pd

# ============================================================
# COCOA INTELLIGENCE HUB — STREAMLIT COMMAND CENTER V2
# ============================================================

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
AUTO_REFRESH_SECONDS = int(os.getenv("COCOA_REFRESH_SECONDS", "300"))

st.set_page_config(
    page_title="Cocoa Intelligence Hub",
    page_icon="file_0000000090e881f49f628ec095ce682d.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# COCOA THEME — CHOCOLATE V2
# ============================================================

st.markdown(
    """
<style>
.stApp {
    background: #3b2118;
    color: #fff8f1;
}

.stApp, .stApp p, .stApp label, .stApp span {
    color: #fff8f1;
}

.hero {
    background: linear-gradient(135deg, #24120d 0%, #5a2b19 52%, #8b4a25 100%);
    color: #ffffff;
    border-radius: 22px;
    padding: 2rem 2.2rem;
    margin-bottom: 1.5rem;
    border: 1px solid #9b5a31;
    box-shadow: 0 10px 30px rgba(0, 0, 0, .25);
}

.hero * {
    color: #ffffff !important;
}

.hero-title {
    font-size: 2.35rem;
    font-weight: 850;
}

.panel {
    background: #fffaf4;
    color: #241812;
    border: 1px solid #d8b99e;
    border-radius: 20px;
    padding: 1.5rem 1.7rem;
    margin-bottom: 1.1rem;
    box-shadow: 0 7px 20px rgba(0, 0, 0, .16);
}

.panel h1, .panel h2, .panel h3, .panel h4,
.panel p, .panel span, .panel label {
    color: #241812 !important;
}

[data-testid="stMetric"] {
    background: #fffaf4;
    color: #241812;
    border: 1px solid #d8b99e;
    border-radius: 18px;
    padding: 1.15rem 1.05rem;
    min-height: 138px;
    box-shadow: 0 7px 20px rgba(0, 0, 0, .16);
}

.stApp [data-testid="stMetricLabel"],
.stApp [data-testid="stMetricLabel"] * {
    color: #6b4632 !important;
    font-size: 0.78rem !important;
    line-height: 1.15 !important;
    font-weight: 750 !important;
}

.stApp [data-testid="stMetricValue"],
.stApp [data-testid="stMetricValue"] * {
    color: #4a2416 !important;
    font-size: 1.28rem !important;
    line-height: 1.15 !important;
    font-weight: 850 !important;
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    word-break: normal !important;
}

.stApp [data-testid="stMetricDelta"],
.stApp [data-testid="stMetricDelta"] * {
    font-size: 0.82rem !important;
    line-height: 1.15 !important;
}

.section-label {
    color: #f0b77c !important;
    font-size: .85rem;
    font-weight: 850;
    text-transform: uppercase;
    letter-spacing: .08em;
    margin: 1.25rem 0 .8rem;
}

.stButton > button {
    background: #8b4a25;
    color: #ffffff !important;
    border: 1px solid #b66b3c;
    border-radius: 13px;
    font-weight: 750;
    min-height: 44px;
}

.stButton > button:hover {
    background: #a85a2b;
    color: #ffffff !important;
}

section[data-testid="stSidebar"] {
    background: #2b1711;
}

section[data-testid="stSidebar"] * {
    color: #fff4eb !important;
}

button[data-baseweb="tab"] {
    color: #f0d0b5 !important;
    font-weight: 750;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #f0b77c !important;
}

[data-testid="stDataFrame"] {
    border: 1px solid #d8b99e;
    border-radius: 13px;
}

.stAlert {
    border-radius: 13px;
}

[data-testid="stExpander"] {
    border-color: #b98767;
    border-radius: 14px;
}

div[data-testid="stCaptionContainer"] p {
    color: #d9bca8 !important;
}

.news-card {
    background: #fffaf4;
    color: #241812;
    border: 1px solid #d8b99e;
    border-radius: 16px;
    padding: 1rem 1.15rem;
    margin-bottom: .8rem;
}

.news-card * {
    color: #241812 !important;
}

#MainMenu, footer {
    visibility: hidden;
}
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# HELPERS
# ============================================================

@st.cache_data(ttl=AUTO_REFRESH_SECONDS, show_spinner=False)
def get_json(endpoint):
    """
    Fetch data from FastAPI with controlled retry handling for Render
    cold starts and transient network/gateway errors.

    The FastAPI backend itself is not changed. Streamlit simply waits
    and retries when the API is temporarily unavailable while waking.
    """
    max_attempts = 4
    request_timeout = 45
    retry_delays = (0, 5, 10, 20)

    last_error = None

    for attempt in range(max_attempts):
        try:
            response = requests.get(
                f"{API_BASE}{endpoint}",
                timeout=request_timeout,
            )

            if response.status_code in (502, 503, 504):
                last_error = (
                    f"HTTP {response.status_code} from FastAPI "
                    f"while requesting {endpoint}"
                )
                if attempt < max_attempts - 1:
                    time.sleep(retry_delays[attempt + 1])
                    continue

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            if attempt < max_attempts - 1:
                time.sleep(retry_delays[attempt + 1])
                continue
            break

        except Exception as exc:
            last_error = str(exc)
            break

    return {
        "_error": (
            f"FastAPI is temporarily unavailable after {max_attempts} attempts. "
            f"Render may still be waking the service. Last error: {last_error}"
        )
    }


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


def as_number(value):
    try:
        return float(value)
    except Exception:
        return None


def country_key(item):
    text = " ".join(
        str(item.get(k, ""))
        for k in ("country", "country_name", "region", "title", "description", "source")
    ).lower()

    if "nigeria" in text or "naira" in text:
        return "Nigeria"
    if "ghana" in text:
        return "Ghana"
    if "côte d'ivoire" in text or "cote d'ivoire" in text or "ivory coast" in text:
        return "Côte d’Ivoire"
    if "cameroon" in text:
        return "Cameroon"
    return "Other"


def news_items_for_country(items, country):
    matches = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if country_key(item) == country:
            matches.append(item)
    return matches


def render_news_item(item):
    title = item.get("title", "Untitled")
    url = item.get("url")
    source = item.get("source")
    published = item.get("published_at") or item.get("published") or item.get("date")

    if url:
        st.markdown(f"**[{title}]({url})**")
    else:
        st.markdown(f"**{title}**")

    metadata = []
    if source:
        metadata.append(str(source))
    if published:
        metadata.append(str(published))

    if metadata:
        st.caption(" • ".join(metadata))


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

    st.markdown("### Automatic refresh")
    st.caption(
        f"Live API data refreshes automatically every "
        f"{AUTO_REFRESH_SECONDS // 60} minute(s)."
    )

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
# AUTOMATIC REFRESH
# ============================================================

now = time.time()
last_refresh = st.session_state.get("_last_auto_refresh", 0)

if now - last_refresh >= AUTO_REFRESH_SECONDS:
    st.session_state["_last_auto_refresh"] = now
    st.cache_data.clear()

# ============================================================
# MARKET INTELLIGENCE API
# ============================================================

data = get_json("/market-intelligence")

if show_error("FastAPI connection failed", data):
    st.info(
        "The FastAPI service may be waking from Render sleep. "
        "Refresh the dashboard in a moment if the service is still unavailable."
    )
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
forecast_7 = intel.get("forecast_7_price")
change_7 = intel.get("expected_change_7_pct")
forecast_30 = intel.get("forecast_price")
change_30 = intel.get("expected_change_pct")

ensemble = intel.get("ensemble", {})
ensemble_7 = ensemble.get("7", {}) if isinstance(ensemble, dict) else {}
ensemble_30 = ensemble.get("30", {}) if isinstance(ensemble, dict) else {}

forecast_7 = first(
    forecast_7,
    ensemble_7.get("ensemble_forecast"),
    ensemble_7.get("forecast"),
    default=None,
)
change_7 = first(
    change_7,
    ensemble_7.get("ensemble_expected_change_pct"),
    default=None,
)
direction_7 = first(
    ensemble_7.get("ensemble_direction"),
    ensemble_7.get("direction"),
    default="—",
)

forecast_30 = first(
    forecast_30,
    ensemble_30.get("ensemble_forecast"),
    ensemble_30.get("forecast"),
    default=None,
)
change_30 = first(
    change_30,
    ensemble_30.get("ensemble_expected_change_pct"),
    default=None,
)
direction_30 = first(
    ensemble_30.get("ensemble_direction"),
    ensemble_30.get("direction"),
    default="—",
)

forecast = forecast_30
change = change_30
low = intel.get("forecast_low")
high = intel.get("forecast_high")
confidence = intel.get("confidence_index")

risk = first(intel.get("risk_level"), intel.get("risk"))
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
rf = model_value(models, ["random forest", "random_forest", "randomforest", "rf"])
ts = model_value(models, ["time-series", "time_series", "timeseries", "time series"])

nigeria_price = as_number(intel.get("nigeria_price_ngn"))
nigeria_forecast_30 = as_number(intel.get("nigeria_forecast_ngn"))

# Optional top-level Nigerian 7-day fields if/when the API provides them.
nigeria_forecast_7 = as_number(
    first(
        intel.get("nigeria_forecast_7_ngn"),
        intel.get("nigeria_7_day_forecast_ngn"),
        intel.get("nigeria_forecast_7"),
        default=None,
    )
)

nigeria_change_7 = as_number(
    first(
        intel.get("nigeria_expected_change_7_pct"),
        intel.get("nigeria_forecast_7_change_pct"),
        intel.get("nigeria_7_day_change_pct"),
        default=None,
    )
)

nigeria_change_30 = as_number(
    first(
        intel.get("nigeria_expected_change_30_pct"),
        intel.get("nigeria_forecast_30_change_pct"),
        intel.get("nigeria_30_day_change_pct"),
        default=None,
    )
)

# If the backend has not yet exposed separate Nigerian 7-day fields,
# derive a transparent 7-day Nigerian estimate from the international
# 7-day move and current Nigerian benchmark.
if nigeria_forecast_7 is None and nigeria_price is not None and as_number(change_7) is not None:
    nigeria_forecast_7 = nigeria_price * (1 + float(change_7) / 100)

if nigeria_change_7 is None and nigeria_price is not None and nigeria_forecast_7 is not None:
    nigeria_change_7 = ((nigeria_forecast_7 / nigeria_price) - 1) * 100

if nigeria_change_30 is None and nigeria_price is not None and nigeria_forecast_30 is not None:
    nigeria_change_30 = ((nigeria_forecast_30 / nigeria_price) - 1) * 100


# ============================================================
# HERO
# ============================================================

st.markdown(
    """
<div class="hero">
    <div><b>● LIVE INTELLIGENCE ENGINE</b></div>
    <div class="hero-title">🍫 Cocoa Intelligence Hub</div>
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

a, b, c, d, e = st.columns(5)

a.metric("Latest ICCO Price", f"${fmt_num(latest)}")
b.metric(
    "7-Day Forecast",
    f"${fmt_num(forecast_7)}",
    fmt_pct(change_7),
)
c.metric(
    "30-Day Forecast",
    f"${fmt_num(forecast_30)}",
    fmt_pct(change_30),
)
d.metric("Expected Change", fmt_pct(change_30))
e.metric(
    "Confidence",
    f"{fmt_num(confidence, 0)}/100"
    if confidence is not None
    else "—",
)

a, b, c, d, e = st.columns(5)

a.metric("Direction", direction)
b.metric("Risk", risk)
c.metric("Market State", market_state)
d.metric("Signal", signal)
e.metric("Model Agreement", agreement)


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

    mh1, mh2 = st.columns(2)

    with mh1:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("### 7-Day International Forecast")

        x, y = st.columns(2)
        x.metric("Forecast", f"${fmt_num(forecast_7)}")
        y.metric("Expected Change", fmt_pct(change_7))

        st.write(f"**Direction:** {direction_7}")
        st.write("**Horizon:** 7 trading days")
        st.markdown("</div>", unsafe_allow_html=True)

    with mh2:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("### 30-Day International Forecast")

        x, y = st.columns(2)
        x.metric("Forecast", f"${fmt_num(forecast_30)}")
        y.metric("Expected Change", fmt_pct(change_30))

        st.write(f"**Direction:** {direction_30}")
        st.write(f"**Horizon:** {horizon}")
        st.markdown("</div>", unsafe_allow_html=True)

    left, right = st.columns([1.05, 1])

    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("### Forecast Range")

        p, q = st.columns(2)
        p.metric("Lower Bound", f"${fmt_num(low)}")
        q.metric("Upper Bound", f"${fmt_num(high)}")

        st.write(f"**Horizon:** {horizon}")
        st.write(f"**Model agreement:** {agreement}")

        if low is not None and high is not None and forecast is not None:
            st.bar_chart(
                pd.DataFrame(
                    {"Price": [low, forecast, high]},
                    index=["Lower", "Ensemble", "Upper"],
                ),
                height=280,
            )

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
                            "Date": item.get("rate_date", item.get("date", "—")),
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
                            "Date": item.get("rate_date", item.get("date", "—")),
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
            len(observations) if isinstance(observations, list) else 0,
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

    n1, n2, n3, n4, n5 = st.columns(5)

    n1.metric(
        "Current Benchmark",
        f"₦{fmt_num(nigeria_price)}" if nigeria_price is not None else "—",
    )

    n2.metric(
        "7-Day Forecast",
        f"₦{fmt_num(nigeria_forecast_7)}"
        if nigeria_forecast_7 is not None
        else "—",
        fmt_pct(nigeria_change_7),
    )

    n3.metric(
        "7-Day Change",
        fmt_pct(nigeria_change_7),
    )

    n4.metric(
        "30-Day Forecast",
        f"₦{fmt_num(nigeria_forecast_30)}"
        if nigeria_forecast_30 is not None
        else "—",
        fmt_pct(nigeria_change_30),
    )

    n5.metric(
        "30-Day Change",
        fmt_pct(nigeria_change_30),
    )

    st.markdown(
        '<div class="panel">',
        unsafe_allow_html=True,
    )

    st.markdown("#### Nigerian Benchmark")

    st.markdown(
        f"### ₦{fmt_num(nigeria_price)}"
        if nigeria_price is not None
        else "### —"
    )

    st.write("Estimated Nigerian cocoa benchmark per tonne.")
    st.markdown("</div>", unsafe_allow_html=True)

    p1, p2 = st.columns(2)

    with p1:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### 🇳🇬 7-Day Nigerian Forecast")
        st.markdown(
            f"### ₦{fmt_num(nigeria_forecast_7)}"
            if nigeria_forecast_7 is not None
            else "### —"
        )
        st.write(f"Expected change: **{fmt_pct(nigeria_change_7)}**")
        st.write("Horizon: **7 trading days**")
        st.markdown("</div>", unsafe_allow_html=True)

    with p2:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### 🇳🇬 30-Day Nigerian Forecast")
        st.markdown(
            f"### ₦{fmt_num(nigeria_forecast_30)}"
            if nigeria_forecast_30 is not None
            else "### —"
        )
        st.write(f"Expected change: **{fmt_pct(nigeria_change_30)}**")
        st.write(f"Horizon: **{horizon}**")
        st.markdown("</div>", unsafe_allow_html=True)

    st.caption(
        "The Nigerian estimate and forecast are generated automatically "
        "from the international cocoa benchmark and current FX context."
    )

    # --------------------------------------------------------
    # REGIONAL NEWS
    # --------------------------------------------------------

    st.markdown("### 🌍 Regional Cocoa News")
    st.caption("Nigeria 🇳🇬 · Ghana 🇬🇭 · Côte d’Ivoire 🇨🇮 · Cameroon 🇨🇲")

    news = get_json("/news")

    if not show_error("Regional news feed unavailable", news):
        nr = rows_from(news)

        countries = [
            ("Nigeria", "🇳🇬"),
            ("Ghana", "🇬🇭"),
            ("Côte d’Ivoire", "🇨🇮"),
            ("Cameroon", "🇨🇲"),
        ]

        grouped = {
            country: news_items_for_country(nr, country)
            for country, _ in countries
        }

        # If the API already returns explicit country labels, use them.
        # If it does not, retain the full feed in an "Other" bucket instead
        # of incorrectly attributing stories to a country.
        news_tabs = st.tabs([f"{flag} {country}" for country, flag in countries])

        for tab, (country, flag) in zip(news_tabs, countries):
            with tab:
                items = grouped[country][:8]

                if items:
                    for item in items:
                        render_news_item(item)
                        st.divider()
                else:
                    st.info(
                        f"No country-specific {country} cocoa news record "
                        "was returned by the current /news feed."
                    )


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

        if not show_error("API health unavailable", health):
            st.json(health)

    with b:
        st.markdown("### Database Health")
        db = get_json("/db-health")

        if not show_error("Database health unavailable", db):
            st.json(db)

    a, b, c, d = st.columns(4)

    a.metric("Database", "Connected")
    b.metric("FastAPI", "Online")
    c.metric("ML Engine", "Active")
    d.metric("Streamlit", "Online")

    with st.expander("Raw /market-intelligence response"):
        st.json(data)


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "Cocoa Intelligence Hub • Experimental ML intelligence layer • "
    "International prices • FX • Weather • Crop Risk • Nigerian Cocoa Context"
)
