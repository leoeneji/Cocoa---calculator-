-- Cocoa Intelligence Layer
-- PostgreSQL schema for cocoa news, market data, weather and AI signals.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =========================
-- Reference data
-- =========================

CREATE TABLE IF NOT EXISTS countries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(3) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL UNIQUE,
    is_cocoa_origin BOOLEAN NOT NULL DEFAULT TRUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL UNIQUE,
    website_url TEXT NOT NULL,
    feed_url TEXT,
    source_type VARCHAR(30) NOT NULL CHECK (
        source_type IN ('rss', 'api', 'public_page', 'licensed_data', 'manual')
    ),
    permission_status VARCHAR(30) NOT NULL DEFAULT 'unknown' CHECK (
        permission_status IN ('unknown', 'permitted', 'licensed', 'restricted')
    ),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS fx_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    base_currency VARCHAR(10) NOT NULL,
    quote_currency VARCHAR(10) NOT NULL,
    rate NUMERIC(20,8) NOT NULL,
    rate_date DATE NOT NULL,
    source VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (base_currency, quote_currency, rate_date)
);
-- =========================
-- News / intelligence
-- =========================

CREATE TABLE IF NOT EXISTS articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    country_id UUID REFERENCES countries(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    author TEXT,
    published_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content TEXT,
    summary TEXT,
    content_hash VARCHAR(128),
    language VARCHAR(20) DEFAULT 'en',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (url)
);

CREATE TABLE IF NOT EXISTS article_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    topic VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (article_id, topic)
);

CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES articles(id) ON DELETE SET NULL,
    country_id UUID REFERENCES countries(id) ON DELETE SET NULL,
    category VARCHAR(50) NOT NULL CHECK (
        category IN (
            'supply', 'demand', 'weather', 'market', 'currency',
            'shipping', 'policy', 'geopolitics', 'production', 'other'
        )
    ),
    event TEXT NOT NULL,
    summary TEXT NOT NULL,
    market_direction VARCHAR(20) NOT NULL CHECK (
        market_direction IN ('bullish', 'bearish', 'neutral', 'mixed')
    ),
    impact_score NUMERIC(5,2) CHECK (impact_score BETWEEN 0 AND 100),
    confidence_score NUMERIC(5,2) CHECK (confidence_score BETWEEN 0 AND 100),
    severity VARCHAR(20) CHECK (
        severity IN ('low', 'medium', 'high', 'critical')
    ),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================
-- Market data
-- =========================

CREATE TABLE IF NOT EXISTS market_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market VARCHAR(50) NOT NULL,
    contract VARCHAR(100),
    price NUMERIC(14,4) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    unit VARCHAR(30) NOT NULL DEFAULT 'MT',
    price_change NUMERIC(14,4),
    price_change_pct NUMERIC(10,4),
    timestamp TIMESTAMPTZ NOT NULL,
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weather_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country_id UUID REFERENCES countries(id) ON DELETE SET NULL,
    location VARCHAR(200) NOT NULL,
    observation_date DATE NOT NULL,
    rainfall_mm NUMERIC(10,2),
    temperature_c NUMERIC(6,2),
    humidity_pct NUMERIC(6,2) CHECK (humidity_pct BETWEEN 0 AND 100),
    weather_anomaly TEXT,
    crop_risk_score NUMERIC(5,2) CHECK (crop_risk_score BETWEEN 0 AND 100),
    source VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================
-- Macro / composite indicators
-- =========================

CREATE TABLE IF NOT EXISTS market_indicators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_date DATE NOT NULL UNIQUE,
    usd_ngn NUMERIC(14,6),
    fuel_price_ngn NUMERIC(14,4),
    shipping_cost NUMERIC(14,4),
    supply_score NUMERIC(5,2) CHECK (supply_score BETWEEN 0 AND 100),
    demand_score NUMERIC(5,2) CHECK (demand_score BETWEEN 0 AND 100),
    weather_score NUMERIC(5,2) CHECK (weather_score BETWEEN 0 AND 100),
    geopolitical_score NUMERIC(5,2) CHECK (geopolitical_score BETWEEN 0 AND 100),
    overall_market_score NUMERIC(6,2),
    market_bias VARCHAR(20) CHECK (
        market_bias IN ('bullish', 'bearish', 'neutral', 'mixed')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================
-- Indexes
-- =========================

CREATE INDEX IF NOT EXISTS idx_articles_published_at
    ON articles (published_at DESC);

CREATE INDEX IF NOT EXISTS idx_articles_country
    ON articles (country_id);

CREATE INDEX IF NOT EXISTS idx_articles_source
    ON articles (source_id);

CREATE INDEX IF NOT EXISTS idx_articles_hash
    ON articles (content_hash);

CREATE INDEX IF NOT EXISTS idx_signals_detected_at
    ON signals (detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_country_category
    ON signals (country_id, category);

CREATE INDEX IF NOT EXISTS idx_signals_direction
    ON signals (market_direction);

CREATE INDEX IF NOT EXISTS idx_market_prices_market_time
    ON market_prices (market, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_weather_country_date
    ON weather_observations (country_id, observation_date DESC);

-- =========================
-- Initial cocoa markets
-- =========================

INSERT INTO countries (code, name, is_cocoa_origin)
VALUES
    ('NGA', 'Nigeria', TRUE),
    ('GHA', 'Ghana', TRUE),
    ('CIV', 'Côte d’Ivoire', TRUE),
    ('CMR', 'Cameroon', TRUE),
    ('ECU', 'Ecuador', TRUE),
    ('BRA', 'Brazil', TRUE),
    ('IDN', 'Indonesia', TRUE),
    ('GLB', 'Global', FALSE)
ON CONFLICT (code) DO NOTHING;
