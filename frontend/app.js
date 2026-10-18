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
    const raw = await fetchJSON("/market-intelligence");
    const intel = unwrapObject(raw, [
      "intelligence",
      "market_intelligence",
      "data",
    ]);
    const root = raw && typeof raw === "object" ? raw : {};
    const ensemble = intel.ensemble || root.ensemble || {};
    const h7 =
      intel.ensemble_7 ||
      root.ensemble_7 ||
      ensemble["7"] ||
      ensemble["7d"] ||
      {};
    const h30 =
      intel.ensemble_30 ||
      root.ensemble_30 ||
      ensemble["30"] ||
      ensemble["30d"] ||
      {};
    const first = (...vals) =>
      vals.find((v) => v !== undefined && v !== null && v !== "");
    const f7 = first(
      intel.forecast_7_price,
      intel.forecast_7,
      h7.ensemble_forecast,
      h7.forecast
    );
    const c7 = first(
      intel.expected_change_7_pct,
      intel.expected_change_7,
      h7.ensemble_expected_change_pct,
      h7.expected_change_pct
    );
    const f30 = first(
      intel.forecast_price,
      intel.forecast_30_price,
      intel.forecast_30,
      h30.ensemble_forecast,
      h30.forecast
    );
    const c30 = first(
      intel.expected_change_pct,
      intel.expected_change_30_pct,
      intel.expected_change_30,
      h30.ensemble_expected_change_pct,
      h30.expected_change_pct
    );
    const direction = first(
      h30.ensemble_direction,
      h30.direction,
      intel.ensemble_direction,
      intel.direction,
      intel.market_direction
    );

    // Populate the existing forecast card; 7-day values are surfaced in its secondary details when present.
    setText("intelligence-state", first(intel.intelligence_state, intel.state));
    setText("market-state", first(intel.market_state, intel.market));
    setText("intelligence-signal", first(intel.signal, intel.market_signal));
    setText("intelligence-direction", direction);
    const latest = first(
      intel.latest_price,
      root.latest_price,
      intel.current_price
    );
    if (latest !== undefined)
      setText("intelligence-price", formatNumber(latest));
    if (f7 !== undefined) setText("forecast-7-price", formatNumber(f7));
    if (c7 !== undefined) setText("forecast-7-change", formatPercent(c7));
    if (f30 !== undefined) {
      setText("ensemble-forecast", formatNumber(f30));
      setText("forecast-price", formatNumber(f30));
    }
    if (c30 !== undefined) {
      setText("expected-change", formatPercent(c30));
      setText("forecast-change", formatPercent(c30));
    }
    if (direction !== undefined) setText("forecast-direction", direction);
    const low = first(intel.forecast_low, h30.range_low, h30.forecast_low);
    const high = first(intel.forecast_high, h30.range_high, h30.forecast_high);
    if (low !== undefined && high !== undefined) {
      setText("forecast-range", `${formatNumber(low)} – ${formatNumber(high)}`);
      setText("forecast-low", formatNumber(low));
      setText("forecast-high", formatNumber(high));
    }
    const confidence = first(
      intel.confidence_index,
      intel.confidence,
      h30.confidence
    );
    if (confidence !== undefined)
      setText(
        "forecast-confidence",
        `${formatNumber(confidence, 0)}${ Number(confidence) <= 1 ? "%" : "/100" }`
      );
    setText(
      "intelligence-confidence",
      confidence === undefined ? null : `${formatNumber(confidence, 0)}/100`
    );
    setText("intelligence-risk", first(intel.risk_level, intel.risk));
    setText(
      "model-agreement",
      first(intel.model_agreement, intel.agreement, h30.model_agreement)
    );

    // Model forecasts plus model metrics are rendered in the page's existing breakdown/table if present.
    const models = Array.isArray(intel.models)
      ? intel.models
      : Array.isArray(root.models)
      ? root.models
      : [];
    const norm = (x) =>
      String(x ?? "")
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "");
    const model = (...aliases) =>
      models.find((m) =>
        aliases.map(norm).includes(norm(m.model ?? m.name ?? m.model_name))
      );
    const val = (m) =>
      m &&
      first(m.forecast, m.forecast_price, m.prediction, m.ensemble_forecast);
    const xgb = val(model("xgboost", "xgb")),
      rf = val(model("random forest", "randomforest", "rf")),
      ts = val(model("time-series", "timeseries", "arima"));
    if (xgb !== undefined) setText("xgb-forecast", formatNumber(xgb));
    if (rf !== undefined) setText("rf-forecast", formatNumber(rf));
    if (ts !== undefined) setText("ts-forecast", formatNumber(ts));
    if (f30 !== undefined) setText("model-ensemble", formatNumber(f30));
    renderList("drivers", first(intel.drivers, intel.key_drivers, []));
    renderList(
      "cautions",
      first(intel.cautions, intel.risks, intel.risk_factors, [])
    );
    return raw;
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

  const allCandidates = [...(aliases[text] || []), ...candida
