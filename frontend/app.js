/* =============================================================== COCOA INTELLIGENCE HUB Frontend Application Layer Corrected app.js =============================================================== Purpose: - Load data from the FastAPI backend. - Render market prices, FX and intelligence safely. - Keep the frontend tolerant of different JSON response wrappers. - Make dashboard navigation work, including Market Prices. - Never fabricate missing market data. */
"use strict";

/* ============================================================= CONFIGURATION ============================================================= */

const API_BASE = "https://cocoa-calculator-api.onrender.com";

/* ============================================================= HELPERS ============================================================= */

function setText(id, value) {
  const element = document.getElementById(id);

  if (element) {
    element.textContent =
      value === null || value === undefined || value === ""
        ? "—"
        : String(value);
  }
}

function setHTML(id, value) {
  const element = document.getElementById(id);

  if (element) {
    element.innerHTML =
      value === null || value === undefined ? "" : String(value);
  }
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const number = Number(value);

  if (Number.isNaN(number)) {
    return "—";
  }

  return number.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatPercent(value, decimals = 2) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const number = Number(value);

  if (Number.isNaN(number)) {
    return "—";
  }

  return `${number >= 0 ? "+" : ""}${number.toFixed(decimals)}%`;
}

function formatDate(value) {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleDateString();
}

function upper(value) {
  return String(value ?? "")
    .trim()
    .toUpperCase();
}

function firstDefined(...values) {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }

  return null;
}

function unwrapArray(data, keys = []) {
  if (Array.isArray(data)) {
    return data;
  }

  for (const key of keys) {
    if (data && Array.isArray(data[key])) {
      return data[key];
    }
  }

  return [];
}

function unwrapObject(data, keys = []) {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return {};
  }

  for (const key of keys) {
    if (
      data[key] &&
      typeof data[key] === "object" &&
      !Array.isArray(data[key])
    ) {
      return data[key];
    }
  }

  return data;
}

function setStatus(message, isError = false) {
  const ids = [
    "system-status",
    "api-status",
    "dashboard-status",
    "market-status",
  ];

  ids.forEach((id) => {
    const element = document.getElementById(id);

    if (element) {
      element.textContent = message;
      element.dataset.status = isError ? "error" : "ok";
    }
  });
}

function safeErrorMessage(error) {
  if (!error) {
    return "Unknown error";
  }

  return error.message || String(error);
}

/* ============================================================= API ============================================================= */

async function fetchJSON(endpoint, options = {}) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(`${endpoint} returned HTTP ${response.status}`);
  }

  return response.json();
}

/* ============================================================= MARKET PRICES ============================================================= */

async function loadMarketPrices() {
  try {
    const data = await fetchJSON("/prices");

    console.log("MARKET PRICES:", data);

    const rows = unwrapArray(data, ["prices", "data", "results"]);

    const latest = {};

    rows.forEach((row) => {
      if (!row || typeof row !== "object") {
        return;
      }

      const contract = upper(firstDefined(row.contract, row.symbol, row.name));

      if (!contract) {
        return;
      }

      const timestamp = firstDefined(
        row.timestamp,
        row.trade_date,
        row.date,
        row.updated_at
      );

      if (
        !latest[contract] ||
        (timestamp &&
          new Date(timestamp) >
            new Date(
              firstDefined(
                latest[contract].timestamp,
                latest[contract].trade_date,
                latest[contract].date,
                latest[contract].updated_at
              )
            ))
      ) {
        latest[contract] = {
          ...row,
          timestamp,
        };
      }
    });

    /* London */
    const london = latest["LONDON-FUTURES"];

    if (london) {
      setText(
        "london-price",
        formatNumber(firstDefined(london.price, london.value, london.last))
      );

      setText(
        "london-change",
        london.timestamp
          ? `Updated ${formatDate(london.timestamp)}`
          : "Live market data"
      );
    } else {
      setText("london-price", "Unavailable");
      setText("london-change", "No London futures observation");
    }

    /* New York */
    const newYork = latest["NEW-YORK-FUTURES"];

    if (newYork) {
      setText(
        "new-york-price",
        formatNumber(firstDefined(newYork.price, newYork.value, newYork.last))
      );

      setText(
        "new-york-change",
        newYork.timestamp
          ? `Updated ${formatDate(newYork.timestamp)}`
          : "Live market data"
      );
    } else {
      setText("new-york-price", "Unavailable");
      setText("new-york-change", "No New York futures observation");
    }

    /* ICCO USD */
    const icco = latest["ICCO-DAILY-USD"];

    if (icco) {
      setText(
        "icco-usd-price",
        formatNumber(firstDefined(icco.price, icco.value, icco.last))
      );

      setText(
        "icco-change",
        icco.timestamp
          ? `Updated ${formatDate(icco.timestamp)}`
          : "ICCO benchmark"
      );
    } else {
      setText("icco-usd-price", "Unavailable");
      setText("icco-change", "No ICCO USD observation");
    }

    setStatus("Market prices loaded");

    return rows;
  } catch (error) {
    console.error("Market price loading failed:", error);

    setText("london-price", "Unavailable");
    setText("new-york-price", "Unavailable");
    setText("icco-usd-price", "Unavailable");

    setStatus(`Market prices unavailable: ${safeErrorMessage(error)}`, true);

    return [];
  }
}

/* ============================================================= FX ============================================================= */

async function loadFX() {
  try {
    const data = await fetchJSON("/fx");

    console.log("FX:", data);

    const rows = unwrapArray(data, ["fx", "data", "results", "rates"]);

    const usdNgnRows = rows.filter((row) => {
      const base = upper(
        firstDefined(row.base_currency, row.base, row.from_currency, row.from)
      );

      const quote = upper(
        firstDefined(row.quote_currency, row.quote, row.to_currency, row.to)
      );

      return base === "USD" && quote === "NGN";
    });

    if (usdNgnRows.length > 0) {
      usdNgnRows.sort((a, b) => {
        const dateA = new Date(firstDefined(a.rate_date, a.date, a.timestamp));
        const dateB = new Date(firstDefined(b.rate_date, b.date, b.timestamp));

        return dateB - dateA;
      });

      const latest = usdNgnRows[0];

      setText(
        "usd-ngn",
        formatNumber(firstDefined(latest.rate, latest.value, latest.price))
      );

      setText(
        "fx-change",
        latest.rate_date ? `As of ${formatDate(latest.rate_date)}` : "USD/NGN"
      );
    } else {
      setText("usd-ngn", "Unavailable");
      setText("fx-change", "No USD/NGN observation");
    }

    return rows;
  } catch (error) {
    console.error("FX loading failed:", error);

    setText("usd-ngn", "Unavailable");
    setText("fx-change", "FX data unavailable");

    return [];
  }
}

/* ============================================================= MARKET SNAPSHOT ============================================================= */

async function loadMarketSnapshot() {
  try {
    const data = await fetchJSON("/market-snapshot");

    console.log("MARKET SNAPSHOT:", data);

    const snapshot = unwrapObject(data, [
      "snapshot",
      "market_snapshot",
      "data",
    ]);

    setText(
      "market-direction",
      firstDefined(
        snapshot.direction,
        snapshot.market_direction,
        snapshot.trend
      )
    );

    setText(
      "market-signal",
      firstDefined(snapshot.signal, snapshot.market_signal)
    );

    setText("market-risk", firstDefined(snapshot.risk_level, snapshot.risk));

    setText(
      "market-confidence",
      snapshot.confidence_index !== undefined
        ? formatNumber(snapshot.confidence_index, 0)
        : firstDefined(snapshot.confidence, snapshot.confidence_level)
    );

    setText(
      "market-price",
      snapshot.latest_price !== undefined
        ? formatNumber(snapshot.latest_price)
        : snapshot.price !== undefined
        ? formatNumber(snapshot.price)
        : "—"
    );

    return data;
  } catch (error) {
    console.error("Market snapshot loading failed:", error);
    return null;
  }
}

/* ============================================================= WEATHER ============================================================= */

async function loadWeather() {
  try {
    const data = await fetchJSON("/weather");

    console.log("WEATHER:", data);

    const weather = unwrapObject(data, ["weather", "data", "summary"]);

    setText(
      "rainfall",
      firstDefined(weather.rainfall_mm, weather.average_rainfall_mm) !== null
        ? `${formatNumber( firstDefined(weather.rainfall_mm, weather.average_rainfall_mm) )} mm`
        : "—"
    );

    setText(
      "temperature",
      firstDefined(weather.temperature_c, weather.average_temperature_c) !==
        null
        ? `${formatNumber( firstDefined(weather.temperature_c, weather.average_temperature_c) )} °C`
        : "—"
    );

    setText(
      "humidity",
      firstDefined(weather.humidity_pct, weather.average_humidity_pct) !== null
        ? `${formatNumber( firstDefined(weather.humidity_pct, weather.average_humidity_pct) )}%`
        : "—"
    );

    setText(
      "crop-risk",
      firstDefined(weather.crop_risk_score, weather.average_crop_risk_score)
    );

    return data;
  } catch (error) {
    console.error("Weather loading failed:", error);
    return null;
  }
}

/* ============================================================= SIGNALS ============================================================= */

async function loadSignals() {
  try {
    const data = await fetchJSON("/signals");

    console.log("SIGNALS:", data);

    const signal = unwrapObject(data, ["signal", "signals", "data"]);

    setText(
      "signal",
      firstDefined(signal.signal, signal.market_signal, signal.value)
    );

    setText(
      "direction",
      firstDefined(signal.direction, signal.market_direction, signal.trend)
    );

    setText("risk", firstDefined(signal.risk_level, signal.risk));

    setText(
      "confidence",
      signal.confidence_index !== undefined
        ? `${formatNumber(signal.confidence_index, 0)}/100`
        : firstDefined(signal.confidence, signal.confidence_level)
    );

    return data;
  } catch (error) {
    console.error("Signals loading failed:", error);
    return null;
  }
}

/* ============================================================= MARKET INTELLIGENCE ============================================================= */

async function loadMarketIntelligence() {
  try {
    const response = await fetchJSON("/market-intelligence");
    const intel = unwrapObject(response, [
      "intelligence",
      "market_intelligence",
      "data",
    ]);
    const root = response && typeof response === "object" ? response : {};
    const ens = intel.ensemble || root.ensemble || {};
    const e7 =
      intel.ensemble_7 || root.ensemble_7 || ens["7"] || ens["7d"] || {};
    const e30 =
      intel.ensemble_30 || root.ensemble_30 || ens["30"] || ens["30d"] || {};
    const pick = (...v) => firstDefined(...v);

    const f7 = pick(
      intel.forecast_7_price,
      intel.forecast_7,
      e7.ensemble_forecast,
      e7.forecast
    );
    const c7 = pick(
      intel.expected_change_7_pct,
      intel.expected_change_7,
      e7.ensemble_expected_change_pct,
      e7.expected_change_pct
    );
    const f30 = pick(
      intel.forecast_price,
      intel.forecast_30_price,
      intel.forecast_30,
      e30.ensemble_forecast,
      e30.forecast
    );
    const c30 = pick(
      intel.expected_change_pct,
      intel.expected_change_30_pct,
      intel.expected_change_30,
      e30.ensemble_expected_change_pct,
      e30.expected_change_pct
    );
    const direction = pick(
      e30.ensemble_direction,
      e30.direction,
      intel.direction,
      intel.market_direction
    );

    setText("intelligence-state", pick(intel.intelligence_state, intel.state));
    setText("market-state", pick(intel.market_state, intel.market));
    setText("intelligence-signal", pick(intel.signal, intel.market_signal));
    setText("intelligence-direction", direction);
    setText(
      "intelligence-price",
      formatNumber(
        pick(intel.latest_price, root.latest_price, intel.current_price)
      )
    );

    // Show both forecast horizons, as in Streamlit's executive view.
    setText("forecast-7-price", f7 == null ? "—" : formatNumber(f7));
    setText("forecast-7-change", c7 == null ? "—" : formatPercent(c7));
    setText("forecast-30-price", f30 == null ? "—" : formatNumber(f30));
    setText("forecast-30-change", c30 == null ? "—" : formatPercent(c30));

    // Streamlit's main forecast is the 30-day ensemble.
    setText("ensemble-forecast", f30 == null ? "—" : formatNumber(f30));
    setText("expected-change", c30 == null ? "—" : formatPercent(c30));
    setText("forecast-direction", direction || "—");
    const low = pick(intel.forecast_low, e30.range_low, e30.forecast_low);
    const high = pick(intel.forecast_high, e30.range_high, e30.forecast_high);
    setText(
      "forecast-range",
      low != null && high != null
        ? `${formatNumber(low)} – ${formatNumber(high)}`
        : pick(intel.forecast_range, e30.forecast_range)
    );
    const conf = pick(intel.confidence_index, intel.confidence, e30.confidence);
    setText(
      "forecast-confidence",
      conf == null
        ? "—"
        : `${formatNumber(Number(conf) <= 1 ? Number(conf) * 100 : conf, 0)}%`
    );
    setText("intelligence-risk", pick(intel.risk_level, intel.risk, e30.risk));
    setText(
      "model-agreement",
      pick(
        intel.model_agreement,
        intel.agreement,
        e30.agreement,
        e30.ensemble_agreement
      )
    );

    const models = Array.isArray(intel.models)
      ? intel.models
      : Array.isArray(root.models)
      ? root.models
      : [];
    const modelValue = (...aliases) => {
      const norm = (x) =>
        String(x ?? "")
          .toLowerCase()
          .replace(/[^a-z0-9]/g, "");
      const wanted = aliases.map(norm);
      const m = models.find((x) =>
        wanted.includes(norm(x?.model ?? x?.name ?? x?.model_name))
      );
      return pick(m?.forecast, m?.forecast_price, m?.prediction);
    };
    setText(
      "xgb-forecast",
      modelValue("xgboost", "xgb") == null
        ? "—"
        : formatNumber(modelValue("xgboost", "xgb"))
    );
    setText(
      "rf-forecast",
      modelValue("random forest", "randomforest", "rf") == null
        ? "—"
        : formatNumber(modelValue("random forest", "randomforest", "rf"))
    );
    setText(
      "ts-forecast",
      modelValue("time-series", "timeseries", "arima") == null
        ? "—"
        : formatNumber(modelValue("time-series", "timeseries", "arima"))
    );
    setText("model-ensemble", f30 == null ? "—" : formatNumber(f30));
    renderList("drivers", pick(intel.drivers, intel.key_drivers, []));
    renderList("cautions", pick(intel.cautions, intel.risk_factors, []));
    return response;
  } catch (error) {
    console.error("Market intelligence loading failed:", error);
    return null;
  }
}

/* ============================================================= LIST RENDERER ============================================================= */

function renderList(id, items) {
  const element = document.getElementById(id);

  if (!element) {
    return;
  }

  element.innerHTML = "";

  if (!Array.isArray(items) || items.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No information available.";
    element.appendChild(li);
    return;
  }

  items.forEach((item) => {
    const li = document.createElement("li");

    if (typeof item === "object") {
      li.textContent = JSON.stringify(item);
    } else {
      li.textContent = String(item);
    }

    element.appendChild(li);
  });
}

/* ============================================================= NAVIGATION ============================================================= */

/* The old navigation used: <a href="#" class="nav-item"> That changes nothing when clicked. This handler gives each navigation item a real destination based on its existing href, data-section, data-target, aria-controls, or visible text. It does not require changes to the existing HTML. */

function normaliseSectionName(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function findNavigationTarget(navItem) {
  const explicitTarget =
    navItem.dataset.target ||
    navItem.dataset.section ||
    navItem.getAttribute("aria-controls");

  if (explicitTarget) {
    const cleaned = explicitTarget.replace(/^#/, "");
    const target = document.getElementById(cleaned);

    if (target) {
      return target;
    }
  }

  const href = navItem.getAttribute("href");

  if (href && href !== "#") {
    try {
      if (href.startsWith("#")) {
        const target = document.getElementById(href.substring(1));

        if (target) {
          return target;
        }
      }
    } catch (_) {
      /* Ignore malformed selectors. */
    }
  }

  const text = normaliseSectionName(navItem.textContent);

  if (!text) {
    return null;
  }

  const candidates = [
    text,
    `${text}-section`,
    `${text}-page`,
    `section-${text}`,
  ];

  const aliases = {
    "market-prices": [
      "market-prices",
      "market-prices-section",
      "prices",
      "prices-section",
      "market",
      "market-section",
    ],
    "market-pulse": [
      "market-pulse",
      "market-pulse-section",
      "dashboard",
      "dashboard-section",
    ],
    "market-intelligence": [
      "market-intelligence",
      "market-intelligence-section",
      "intelligence",
      "intelligence-section",
    ],
    weather: ["weather", "weather-section"],
    signals: ["signals", "signals-section"],
    news: ["news", "news-section"],
    calculator: ["calculator", "calculator-section", "cocoa-calculator"],
  };

  const allCandidates = [...(aliases[text] || []), ...candidates];

  for (const id of allCandidates) {
    const target = document.getElementById(id);

    if (target) {
      return target;
    }
  }

  /* Last fallback: search sections by heading text. */
  const sections = document.querySelectorAll("section, [data-section]");

  for (const section of sections
