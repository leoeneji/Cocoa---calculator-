from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import date, datetime
from pydantic import BaseModel

from backend.database.connection import get_connection
from backend.market_intelligence_engine import build_intelligence

class FXRate(BaseModel):
    base_currency: str
    quote_currency: str
    rate: float
    rate_date: date
    source: str

class CocoaPrice(BaseModel):
    contract: str
    price: float
    currency: str
    unit: str
    timestamp: datetime
    source: str

class MarketSnapshot(BaseModel):
    fx: list[FXRate]
    cocoa_prices: list[CocoaPrice]



app = FastAPI(
    title="Cocoa Intelligence API",
    description="Backend API for the Cocoa Intelligence Hub and Cocoa Calculator",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "Cocoa Intelligence API",
        "status": "online",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/db-health")
def db_health():
    conn = get_connection()

    try:
        return {
            "database": "cocoa_intelligence",
            "status": "connected",
        }

    finally:
        conn.close()


@app.get("/countries")
def countries():
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT code, name, is_cocoa_origin
                FROM countries
                ORDER BY name
            """)

            rows = cur.fetchall()

        return [
            {
                "code": row[0],
                "name": row[1],
                "is_cocoa_origin": row[2],
            }
            for row in rows
        ]

    finally:
        conn.close()


@app.get("/prices")
def prices():
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (contract)
                    market,
                    contract,
                    price,
                    currency,
                    unit,
                    timestamp
                FROM market_prices
                WHERE market = 'ICCO'
                ORDER BY contract, timestamp DESC
            """)

            rows = cur.fetchall()

        return [
            {
                "market": row[0],
                "contract": row[1],
                "price": float(row[2]),
                "currency": row[3],
                "unit": row[4],
                "timestamp": row[5],
                "source": row[0],
            }
            for row in rows
        ]

    finally:
        conn.close()
@app.get("/fx", response_model=list[FXRate])
def fx():
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (base_currency, quote_currency)
                    base_currency,
                    quote_currency,
                    rate,
                    rate_date,
                    source
                FROM fx_rates
                ORDER BY
                    base_currency,
                    quote_currency,
                    rate_date DESC
            """)

            rows = cur.fetchall()

        return [
            {
                "base_currency": row[0],
                "quote_currency": row[1],
                "rate": float(row[2]),
                "rate_date": row[3],
                "source": row[4],
            }
            for row in rows
        ]

    finally:
        conn.close()

@app.get("/market-snapshot", response_model=MarketSnapshot)
def market_snapshot():
    return {
        "fx": fx(),
        "cocoa_prices": prices()
    }

@app.get("/weather")
def weather():
    conn = get_connection()

    try:
        with conn.cursor() as cur:

            # Current weather observations
            cur.execute("""
                SELECT
                    location,
                    observation_date,
                    rainfall_mm,
                    temperature_c,
                    humidity_pct,
                    crop_risk_score,
                    source
                FROM weather_observations
                ORDER BY observation_date DESC, location
            """)

            observation_rows = cur.fetchall()

            # 7-day forecasts
            cur.execute("""
                SELECT
                    location,
                    forecast_date,
                    precipitation_sum_mm,
                    temperature_max_c,
                    temperature_min_c,
                    precipitation_probability_pct,
                    precipitation_hours,
                    crop_risk_score,
                    source
                FROM weather_forecasts
                ORDER BY forecast_date ASC, location
            """)

            forecast_rows = cur.fetchall()

        return {
            "observations": [
                {
                    "location": row[0],
                    "date": row[1],
                    "rainfall_mm": float(row[2]) if row[2] is not None else None,
                    "temperature_c": float(row[3]) if row[3] is not None else None,
                    "humidity_pct": float(row[4]) if row[4] is not None else None,
                    "crop_risk_score": float(row[5]) if row[5] is not None else None,
                    "source": row[6],
                }
                for row in observation_rows
            ],

            "forecasts": [
                {
                    "location": row[0],
                    "date": row[1],
                    "rainfall_mm": float(row[2]) if row[2] is not None else None,
                    "temperature_max_c": float(row[3]) if row[3] is not None else None,
                    "temperature_min_c": float(row[4]) if row[4] is not None else None,
                    "rain_probability_pct": float(row[5]) if row[5] is not None else None,
                    "rain_hours": float(row[6]) if row[6] is not None else None,
                    "crop_risk_score": float(row[7]) if row[7] is not None else None,
                    "source": row[8],
                }
                for row in forecast_rows
            ],
        }

    finally:
        conn.close()

@app.get("/signals")
def signals():
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    article_id,
                    country_id,
                    category,
                    event,
                    summary,
                    market_direction,
                    impact_score,
                    confidence_score,
                    severity,
                    detected_at,
                    created_at
                FROM signals
                ORDER BY created_at DESC
                LIMIT 20
                """
            )

            rows = cur.fetchall()

        signals_data = []

        for row in rows:
            signals_data.append(
                {
                    "id": str(row[0]),
                    "article_id": str(row[1]) if row[1] else None,
                    "country_id": str(row[2]) if row[2] else None,
                    "category": row[3],
                    "event": row[4],
                    "summary": row[5],
                    "market_direction": row[6],
                    "impact_score": float(row[7]) if row[7] is not None else None,
                    "confidence_score": float(row[8]) if row[8] is not None else None,
                    "severity": row[9],
                    "detected_at": row[10],
                    "created_at": row[11],
                }
            )

        return {
            "count": len(signals_data),
            "signals": signals_data,
        }

    finally:
        conn.close()



@app.get("/market-intelligence")
def market_intelligence():
    """
    Return the complete Cocoa Intelligence Hub decision-intelligence context.
    """
    try:
        return build_intelligence()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Market intelligence engine failed: {exc}",
        )   
@app.get("/news")
def news():
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    a.title,
                    a.url,
                    a.published_at
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE s.name = 'Nigeria CRIN'
                ORDER BY a.published_at DESC NULLS LAST
                LIMIT 20
            """)

            rows = cur.fetchall()

        return [
            {
                "title": row[0],
                "url": row[1],
                "published_at": row[2],
            }
            for row in rows
        ]

    finally:
        conn.close()

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
