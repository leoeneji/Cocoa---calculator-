// Netlify serverless function: /.netlify/functions/market-price
//
// Looks up (1) the latest international cocoa price and (2) the current
// USD -> NGN exchange rate, server-side, and returns a small JSON payload
// the calculator's front end can display. Runs on Netlify's servers, so
// any API key stays out of the browser.
//
// IMPORTANT — shared rate limit: Alpha Vantage's free tier allows only
// 25 requests/day TOTAL, shared across every user of this app, not
// per-user. To make a paid feature actually usable by more than a
// couple of people, this function caches its result in Netlify Blobs
// for CACHE_TTL_MS and serves that cached copy to everyone during that
// window, instead of calling Alpha Vantage on every single click.
//
// Requires one environment variable, set in Netlify:
//   ALPHA_VANTAGE_KEY  — free key from https://www.alphavantage.co/support/#api-key
//
// Data sources:
//   Cocoa price   -> Alpha Vantage "COCOA" endpoint (IMF Global Price of
//                    Cocoa, monthly, US cents per pound).
//   Exchange rate -> open.er-api.com (free, no key required).

const { getStore } = require("@netlify/blobs");

const CACHE_KEY = "latest";
const CACHE_TTL_MS = 45 * 60 * 1000; // 45 minutes

exports.handler = async function () {
  const headers = {
    "Content-Type": "application/json",
    "Cache-Control": "public, max-age=1800", // let Netlify's CDN cache this for 30 min too
  };

  const store = getStore("market-cache");

  // Serve the cached price if it's still fresh, without touching
  // Alpha Vantage at all — this is what keeps the free tier's 25
  // requests/day from being exhausted by normal usage.
  try {
    const cached = await store.get(CACHE_KEY, { type: "json" });
    if (cached && Date.now() - cached.cachedAt < CACHE_TTL_MS) {
      return { statusCode: 200, headers, body: JSON.stringify(cached.payload) };
    }
  } catch (err) {
    // Cache miss/error is non-fatal — fall through and fetch fresh.
  }

  const apiKey = process.env.ALPHA_VANTAGE_KEY;
  if (!apiKey) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({
        error: "Server is missing ALPHA_VANTAGE_KEY. Add it in Netlify: Site configuration → Environment variables.",
      }),
    };
  }

  try {
    const [cocoaRes, fxRes] = await Promise.all([
      fetch(`https://www.alphavantage.co/query?function=COCOA&interval=monthly&apikey=${apiKey}`),
      fetch("https://open.er-api.com/v6/latest/USD"),
    ]);

    if (!cocoaRes.ok) throw new Error("Cocoa price source unavailable");
    if (!fxRes.ok) throw new Error("Exchange rate source unavailable");

    const cocoaJson = await cocoaRes.json();
    const fxJson = await fxRes.json();

    const cocoaSeries = cocoaJson && cocoaJson.data;
    if (!Array.isArray(cocoaSeries) || cocoaSeries.length === 0) {
      throw new Error("Unexpected cocoa price response");
    }
    // Most recent entry with a numeric value.
    const latestCocoa = cocoaSeries.find((row) => row.value && !Number.isNaN(Number(row.value)));
    if (!latestCocoa) throw new Error("No usable cocoa price data point");

    const centsPerLb = Number(latestCocoa.value);
    const usdPerTonne = (centsPerLb / 100) * 2204.62; // cents/lb -> USD/tonne

    const ngnRate = fxJson && fxJson.rates && fxJson.rates.NGN;
    if (!ngnRate) throw new Error("Unexpected exchange rate response");

    const payload = {
      international_price_usd_per_tonne: Math.round(usdPerTonne * 100) / 100,
      price_reference_date: latestCocoa.date,
      usd_ngn_rate: Math.round(ngnRate * 100) / 100,
      rate_reference_date: fxJson.time_last_update_utc || new Date().toISOString(),
      note: "Cocoa price is monthly IMF global reference data (ICE-linked), not a live tick — treat as a directional benchmark.",
    };

    try {
      await store.setJSON(CACHE_KEY, { payload, cachedAt: Date.now() });
    } catch (err) {
      // Failing to write the cache shouldn't fail the request itself.
    }

    return { statusCode: 200, headers, body: JSON.stringify(payload) };
  } catch (err) {
    return {
      statusCode: 502,
      headers,
      body: JSON.stringify({ error: "Could not fetch current market data. Try again shortly." }),
    };
  }
};
