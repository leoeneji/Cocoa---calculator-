/*
===============================================================
COCOA INTELLIGENCE HUB
Frontend Application Layer
Corrected app.js
===============================================================

Purpose:
- Load data from the FastAPI backend.
- Render market prices, FX and intelligence safely.
- Keep the frontend tolerant of different JSON response wrappers.
- Make dashboard navigation work, including Market Prices.
- Never fabricate missing market data.
*/

"use strict";

/* =============================================================
   CONFIGURATION
============================================================= */

const API_BASE = "http://127.0.0.1:8000";

/* =============================================================
   HELPERS
============================================================= */

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
    return String(value ?? "").trim().toUpperCase();
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

/* =============================================================
   API
============================================================= */

async function fetchJSON(endpoint, options = {}) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers: {
            Accept: "application/json",
            ...(options.headers || {}),
        },
    });

    if (!response.ok) {
        throw new Error(
            `${endpoint} returned HTTP ${response.status}`
        );
    }

    return response.json();
}

/* =============================================================
   MARKET PRICES
============================================================= */

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

            const contract = upper(
                firstDefined(row.contract, row.symbol, row.name)
            );

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
                formatNumber(
                    firstDefined(london.price, london.value, london.last)
                )
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
                formatNumber(
                    firstDefined(newYork.price, newYork.value, newYork.last)
                )
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
                formatNumber(
                    firstDefined(icco.price, icco.value, icco.last)
                )
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

        setStatus(
            `Market prices unavailable: ${safeErrorMessage(error)}`,
            true
        );

        return [];
    }
}

/* =============================================================
   FX
============================================================= */

async function loadFX() {
    try {
        const data = await fetchJSON("/fx");

        console.log("FX:", data);

        const rows = unwrapArray(data, ["fx", "data", "results", "rates"]);

        const usdNgnRows = rows.filter((row) => {
            const base = upper(
                firstDefined(
                    row.base_currency,
                    row.base,
                    row.from_currency,
                    row.from
                )
            );

            const quote = upper(
                firstDefined(
                    row.quote_currency,
                    row.quote,
                    row.to_currency,
                    row.to
                )
            );

            return base === "USD" && quote === "NGN";
        });

        if (usdNgnRows.length > 0) {
            usdNgnRows.sort((a, b) => {
                const dateA = new Date(
                    firstDefined(a.rate_date, a.date, a.timestamp)
                );
                const dateB = new Date(
                    firstDefined(b.rate_date, b.date, b.timestamp)
                );

                return dateB - dateA;
            });

            const latest = usdNgnRows[0];

            setText(
                "usd-ngn",
                formatNumber(
                    firstDefined(latest.rate, latest.value, latest.price)
                )
            );

            setText(
                "fx-change",
                latest.rate_date
                    ? `As of ${formatDate(latest.rate_date)}`
                    : "USD/NGN"
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

/* =============================================================
   MARKET SNAPSHOT
============================================================= */

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
            firstDefined(
                snapshot.signal,
                snapshot.market_signal
            )
        );

        setText(
            "market-risk",
            firstDefined(
                snapshot.risk_level,
                snapshot.risk
            )
        );

        setText(
            "market-confidence",
            snapshot.confidence_index !== undefined
                ? formatNumber(snapshot.confidence_index, 0)
                : firstDefined(
                      snapshot.confidence,
                      snapshot.confidence_level
                  )
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

/* =============================================================
   WEATHER
============================================================= */

async function loadWeather() {
    try {
        const data = await fetchJSON("/weather");

        console.log("WEATHER:", data);

        const weather = unwrapObject(data, [
            "weather",
            "data",
            "summary",
        ]);

        setText(
            "rainfall",
            firstDefined(
                weather.rainfall_mm,
                weather.average_rainfall_mm
            ) !== null
                ? `${formatNumber(
                      firstDefined(
                          weather.rainfall_mm,
                          weather.average_rainfall_mm
                      )
                  )} mm`
                : "—"
        );

        setText(
            "temperature",
            firstDefined(
                weather.temperature_c,
                weather.average_temperature_c
            ) !== null
                ? `${formatNumber(
                      firstDefined(
                          weather.temperature_c,
                          weather.average_temperature_c
                      )
                  )} °C`
                : "—"
        );

        setText(
            "humidity",
            firstDefined(
                weather.humidity_pct,
                weather.average_humidity_pct
            ) !== null
                ? `${formatNumber(
                      firstDefined(
                          weather.humidity_pct,
                          weather.average_humidity_pct
                      )
                  )}%`
                : "—"
        );

        setText(
            "crop-risk",
            firstDefined(
                weather.crop_risk_score,
                weather.average_crop_risk_score
            )
        );

        return data;
    } catch (error) {
        console.error("Weather loading failed:", error);
        return null;
    }
}

/* =============================================================
   SIGNALS
============================================================= */

async function loadSignals() {
    try {
        const data = await fetchJSON("/signals");

        console.log("SIGNALS:", data);

        const signal = unwrapObject(data, [
            "signal",
            "signals",
            "data",
        ]);

        setText(
            "signal",
            firstDefined(
                signal.signal,
                signal.market_signal,
                signal.value
            )
        );

        setText(
            "direction",
            firstDefined(
                signal.direction,
                signal.market_direction,
                signal.trend
            )
        );

        setText(
            "risk",
            firstDefined(
                signal.risk_level,
                signal.risk
            )
        );

        setText(
            "confidence",
            signal.confidence_index !== undefined
                ? `${formatNumber(signal.confidence_index, 0)}/100`
                : firstDefined(
                      signal.confidence,
                      signal.confidence_level
                  )
        );

        return data;
    } catch (error) {
        console.error("Signals loading failed:", error);
        return null;
    }
}

/* =============================================================
   MARKET INTELLIGENCE
============================================================= */

async function loadMarketIntelligence() {
    try {
        const data = await fetchJSON("/market-intelligence");

        console.log("MARKET INTELLIGENCE:", data);

        const intelligence = unwrapObject(data, [
            "intelligence",
            "market_intelligence",
            "data",
        ]);

        setText(
            "intelligence-state",
            firstDefined(
                intelligence.intelligence_state,
                intelligence.state
            )
        );

        setText(
            "market-state",
            firstDefined(
                intelligence.market_state,
                intelligence.market
            )
        );

        setText(
            "intelligence-signal",
            firstDefined(
                intelligence.signal,
                intelligence.market_signal
            )
        );

        setText(
            "intelligence-direction",
            firstDefined(
                intelligence.direction,
                intelligence.market_direction
            )
        );

        if (intelligence.latest_price !== undefined) {
            setText(
                "intelligence-price",
                formatNumber(intelligence.latest_price)
            );
        }

        if (intelligence.forecast_price !== undefined) {
            setText(
                "forecast-price",
                formatNumber(intelligence.forecast_price)
            );
        }

        if (intelligence.expected_change_pct !== undefined) {
            setText(
                "forecast-change",
                formatPercent(intelligence.expected_change_pct)
            );
        }

        if (intelligence.forecast_low !== undefined) {
            setText(
                "forecast-low",
                formatNumber(intelligence.forecast_low)
            );
        }

        if (intelligence.forecast_high !== undefined) {
            setText(
                "forecast-high",
                formatNumber(intelligence.forecast_high)
            );
        }

        if (intelligence.confidence_index !== undefined) {
            setText(
                "intelligence-confidence",
                `${formatNumber(
                    intelligence.confidence_index,
                    0
                )}/100`
            );
        }

        setText(
            "intelligence-risk",
            firstDefined(
                intelligence.risk_level,
                intelligence.risk
            )
        );

        setText(
            "model-agreement",
            firstDefined(
                intelligence.model_agreement,
                intelligence.agreement
            )
        );

        /* =========================================================
           INDIVIDUAL MODEL FORECASTS
           The API returns models as an array. Match model names
           flexibly so the dashboard works with names such as:
           XGBoost, Random Forest, Time-Series, Persistence.
        ========================================================= */

        const models = Array.isArray(intelligence.models)
            ? intelligence.models
            : [];

        function modelForecast(...names) {
            const wanted = names.map(
                name => String(name).toLowerCase().replace(/[^a-z0-9]/g, "")
            );

            const match = models.find(model => {
                if (!model || model.model === undefined) return false;

                const actual = String(model.model)
                    .toLowerCase()
                    .replace(/[^a-z0-9]/g, "");

                return wanted.includes(actual);
            });

            return match && match.forecast !== undefined
                ? formatNumber(match.forecast)
                : "—";
        }

        setText(
            "xgb-forecast",
            modelForecast("xgboost", "xgb")
        );

        setText(
            "rf-forecast",
            modelForecast("random forest", "random_forest", "randomforest", "rf")
        );

        setText(
            "ts-forecast",
            modelForecast("time-series", "time_series", "timeseries", "time series")
        );

        setText(
            "model-ensemble",
            intelligence.forecast_price !== undefined
                ? formatNumber(intelligence.forecast_price)
                : "—"
        );

        renderList(
            "drivers",
            intelligence.drivers
        );

        renderList(
            "cautions",
            intelligence.cautions
        );

        return data;
    } catch (error) {
        console.error(
            "Market intelligence loading failed:",
            error
        );

        return null;
    }
}

/* =============================================================
   LIST RENDERER
============================================================= */

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

/* =============================================================
   NAVIGATION
============================================================= */

/*
The old navigation used:

    <a href="#" class="nav-item">

That changes nothing when clicked.

This handler gives each navigation item a real destination based
on its existing href, data-section, data-target, aria-controls,
or visible text.

It does not require changes to the existing HTML.
*/

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
                const target = document.getElementById(
                    href.substring(1)
                );

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
        "weather": [
            "weather",
            "weather-section",
        ],
        "signals": [
            "signals",
            "signals-section",
        ],
        "news": [
            "news",
            "news-section",
        ],
        "calculator": [
            "calculator",
            "calculator-section",
            "cocoa-calculator",
        ],
    };

    const allCandidates = [
        ...(aliases[text] || []),
        ...candidates,
    ];

    for (const id of allCandidates) {
        const target = document.getElementById(id);

        if (target) {
            return target;
        }
    }

    /* Last fallback: search sections by heading text. */
    const sections = document.querySelectorAll(
        "section, [data-section]"
    );

    for (const section of sections) {
        const heading = section.querySelector(
            "h1, h2, h3, h4, .section-title"
        );

        if (
            heading &&
            normaliseSectionName(heading.textContent) === text
        ) {
            return section;
        }
    }

    return null;
}

function activateNavigationItem(activeItem) {
    document
        .querySelectorAll(".nav-item")
        .forEach((item) => {
            item.classList.remove("active");
            item.setAttribute("aria-current", "false");
        });

    if (activeItem) {
        activeItem.classList.add("active");
        activeItem.setAttribute("aria-current", "page");
    }
}

function setupNavigation() {
    const navItems = document.querySelectorAll(
        ".nav-item, nav a, [data-nav]"
    );

    if (!navItems.length) {
        return;
    }

    navItems.forEach((item) => {
        item.addEventListener("click", (event) => {
            const target = findNavigationTarget(item);

            if (!target) {
                /*
                Do not break ordinary external links.
                Only intercept the old href="#"/empty navigation.
                */
                const href = item.getAttribute("href");

                if (!href || href === "#") {
                    event.preventDefault();
                }

                return;
            }

            event.preventDefault();

            activateNavigationItem(item);

            target.scrollIntoView({
                behavior: "smooth",
                block: "start",
            });

            if (target.id) {
                history.replaceState(
                    null,
                    "",
                    `#${target.id}`
                );
            }
        });
    });

    /* Activate the navigation item matching the current hash. */
    if (window.location.hash) {
        const targetId =
            window.location.hash.substring(1);

        const target =
            document.getElementById(targetId);

        if (target) {
            const matchingItem =
                Array.from(navItems).find(
                    (item) =>
                        item.getAttribute("href") ===
                            `#${targetId}` ||
                        item.dataset.target === targetId ||
                        item.dataset.section === targetId ||
                        item.getAttribute("aria-controls") ===
                            targetId
                );

            if (matchingItem) {
                activateNavigationItem(matchingItem);
            }
        }
    }
}

/* =============================================================
   HEALTH CHECK
============================================================= */

async function loadHealth() {
    try {
        const data = await fetchJSON("/health");

        console.log("HEALTH:", data);

        setStatus("Backend connected");

        return data;
    } catch (error) {
        console.error("Health check failed:", error);

        setStatus(
            `Backend unavailable: ${safeErrorMessage(error)}`,
            true
        );

        return null;
    }
}

/* =============================================================
   COUNTRIES
============================================================= */

async function loadCountries() {
    try {
        const data = await fetchJSON("/countries");

        console.log("COUNTRIES:", data);

        const rows = unwrapArray(data, [
            "countries",
            "data",
            "results",
        ]);

        const container =
            document.getElementById("countries");

        if (!container) {
            return rows;
        }

        container.innerHTML = "";

        rows.forEach((country) => {
            const item = document.createElement("div");

            if (typeof country === "object") {
                item.textContent = firstDefined(
                    country.name,
                    country.country,
                    country.code
                ) || "—";
            } else {
                item.textContent = String(country);
            }

            container.appendChild(item);
        });

        return rows;
    } catch (error) {
        console.error(
            "Countries loading failed:",
            error
        );

        return [];
    }
}

/* =============================================================
   NEWS
============================================================= */

async function loadNews() {
    try {
        const data = await fetchJSON("/news");

        console.log("NEWS:", data);

        const rows = unwrapArray(data, [
            "news",
            "articles",
            "data",
            "results",
        ]);

        const container =
            document.getElementById("news-list");

        if (!container) {
            return rows;
        }

        container.innerHTML = "";

        rows.forEach((article) => {
            if (!article || typeof article !== "object") {
                return;
            }

            const wrapper =
                document.createElement("article");

            const title =
                document.createElement("h3");

            title.textContent = firstDefined(
                article.title,
                article.headline
            ) || "Untitled";

            wrapper.appendChild(title);

            const summary =
                firstDefined(
                    article.summary,
                    article.description,
                    article.content
                );

            if (summary) {
                const paragraph =
                    document.createElement("p");

                paragraph.textContent =
                    String(summary);

                wrapper.appendChild(paragraph);
            }

            const date = firstDefined(
                article.published_at,
                article.published_date,
                article.date
            );

            if (date) {
                const small =
                    document.createElement("small");

                small.textContent =
                    formatDate(date);

                wrapper.appendChild(small);
            }

            container.appendChild(wrapper);
        });

        return rows;
    } catch (error) {
        console.error(
            "News loading failed:",
            error
        );

        return [];
    }
}

/* =============================================================
   REFRESH ALL
============================================================= */

async function refreshDashboard() {
    console.log(
        "COCOA INTELLIGENCE HUB: refreshing dashboard..."
    );

    await loadHealth();

    /*
    Run independent requests together so one slow endpoint
    does not unnecessarily delay the others.
    */
    await Promise.allSettled([
        loadMarketPrices(),
        loadFX(),
        loadMarketSnapshot(),
        loadWeather(),
        loadSignals(),
        loadMarketIntelligence(),
        loadCountries(),
        loadNews(),
    ]);

    console.log(
        "COCOA INTELLIGENCE HUB: dashboard refresh complete."
    );
}

/* =============================================================
   INITIALISE
============================================================= */

document.addEventListener("DOMContentLoaded", () => {
    console.log(
        "COCOA INTELLIGENCE HUB frontend ready."
    );

    setupNavigation();
    refreshDashboard();
});

/* =============================================================
   OPTIONAL MANUAL REFRESH
============================================================= */

window.refreshCocoaDashboard = refreshDashboard;
window.loadMarketPrices = loadMarketPrices;
window.loadFX = loadFX;
window.loadMarketSnapshot = loadMarketSnapshot;
window.loadWeather = loadWeather;
window.loadSignals = loadSignals;
window.loadMarketIntelligence = loadMarketIntelligence;
window.loadNews = loadNews;
