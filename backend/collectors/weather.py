import httpx
from datetime import datetime

from psycopg import connect

from backend.database.config import settings


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

LOCATIONS = [
    {
        "name": "Ikom",
        "latitude": 5.6927,
        "longitude": 8.7027,
    },
    {
        "name": "Boki",
        "latitude": 6.25,
        "longitude": 9.0333,
    },
    {
        "name": "Etung",
        "latitude": 5.8589,
        "longitude": 8.7916,
    },
    {
        "name": "Akamkpa",
        "latitude": 5.4273,
        "longitude": 8.5186,
    },
]

TIMEZONE = "Africa/Lagos"
FORECAST_DAYS = 7


def fetch_weather():
    latitudes = ",".join(
        str(location["latitude"])
        for location in LOCATIONS
    )

    longitudes = ",".join(
        str(location["longitude"])
        for location in LOCATIONS
    )

    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation"
        ),
        "daily": (
            "precipitation_sum,"
            "temperature_2m_max,"
            "temperature_2m_min,"
            "precipitation_probability_max,"
            "precipitation_hours,"
            "relative_humidity_2m_mean"
        ),
        "forecast_days": FORECAST_DAYS,
        "timezone": TIMEZONE,
    }

    response = httpx.get(
        OPEN_METEO_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):
        data = [data]

    if len(data) != len(LOCATIONS):
        raise RuntimeError(
            f"Expected {len(LOCATIONS)} weather responses, "
            f"got {len(data)}."
        )

    return data


def calculate_crop_risk_score(
    temperature,
    humidity,
    rainfall,
):
    score = 0.0

    if humidity is not None:
        if humidity >= 90:
            score += 35
        elif humidity >= 80:
            score += 25
        elif humidity >= 70:
            score += 15

    if rainfall is not None:
        if rainfall >= 10:
            score += 35
        elif rainfall >= 5:
            score += 25
        elif rainfall >= 1:
            score += 10

    if temperature is not None:
        if temperature >= 32:
            score += 20
        elif temperature <= 18:
            score += 15

    return min(score, 100.0)


def ensure_weather_forecasts_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_forecasts (
                id BIGSERIAL PRIMARY KEY,
                country_id INTEGER NOT NULL,
                location TEXT NOT NULL,
                forecast_date DATE NOT NULL,
                precipitation_sum_mm DOUBLE PRECISION,
                temperature_max_c DOUBLE PRECISION,
                temperature_min_c DOUBLE PRECISION,
                precipitation_probability_pct DOUBLE PRECISION,
                precipitation_hours DOUBLE PRECISION,
                crop_risk_score DOUBLE PRECISION,
                source TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (location, forecast_date)
            )
            """
        )

    conn.commit()


def save_weather(data):
    conn = connect(settings.database_url)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM countries
                WHERE code = 'NGA'
                LIMIT 1
                """
            )

            country = cur.fetchone()

            if not country:
                raise RuntimeError(
                    "Nigeria country record not found."
                )

            country_id = country[0]

        ensure_weather_forecasts_table(conn)

        with conn.cursor() as cur:
            for location, weather in zip(
                LOCATIONS,
                data,
            ):
                current = weather["current"]

                observation_time = datetime.fromisoformat(
                    current["time"]
                )

                observation_date = observation_time.date()

                current_risk = calculate_crop_risk_score(
                    current.get("temperature_2m"),
                    current.get("relative_humidity_2m"),
                    current.get("precipitation"),
                )

                # --------------------------------------------
                # CURRENT WEATHER OBSERVATION
                # --------------------------------------------

                cur.execute(
                    """
                    INSERT INTO weather_observations (
                        country_id,
                        location,
                        observation_date,
                        rainfall_mm,
                        temperature_c,
                        humidity_pct,
                        crop_risk_score,
                        source
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    ON CONFLICT (
                        location,
                        observation_date
                    )
                    DO UPDATE SET
                        rainfall_mm = EXCLUDED.rainfall_mm,
                        temperature_c = EXCLUDED.temperature_c,
                        humidity_pct = EXCLUDED.humidity_pct,
                        crop_risk_score = EXCLUDED.crop_risk_score,
                        source = EXCLUDED.source
                    """,
                    (
                        country_id,
                        location["name"],
                        observation_date,
                        current.get("precipitation"),
                        current.get("temperature_2m"),
                        current.get("relative_humidity_2m"),
                        current_risk,
                        "Open-Meteo",
                    ),
                )

                # --------------------------------------------
                # 7-DAY FORECAST
                # --------------------------------------------

                daily = weather.get("daily", {})

                dates = daily.get("time", [])
                rainfall = daily.get("precipitation_sum", [])
                temp_max = daily.get("temperature_2m_max", [])
                temp_min = daily.get("temperature_2m_min", [])
                rain_probability = daily.get(
                    "precipitation_probability_max",
                    [],
                )
                rain_hours = daily.get(
                    "precipitation_hours",
                    [],
                )
                humidity = daily.get(
                    "relative_humidity_2m_mean",
                    [],
                )

                for index, forecast_date in enumerate(dates):
                    rainfall_value = (
                        rainfall[index]
                        if index < len(rainfall)
                        else None
                    )

                    temp_max_value = (
                        temp_max[index]
                        if index < len(temp_max)
                        else None
                    )

                    temp_min_value = (
                        temp_min[index]
                        if index < len(temp_min)
                        else None
                    )

                    probability_value = (
                        rain_probability[index]
                        if index < len(rain_probability)
                        else None
                    )

                    hours_value = (
                        rain_hours[index]
                        if index < len(rain_hours)
                        else None
                    )

                    humidity_value = (
                        humidity[index]
                        if index < len(humidity)
                        else None
                    )

                    forecast_risk = calculate_crop_risk_score(
                        temp_max_value,
                        humidity_value,
                        rainfall_value,
                    )

                    cur.execute(
                        """
                        INSERT INTO weather_forecasts (
                            country_id,
                            location,
                            forecast_date,
                            precipitation_sum_mm,
                            temperature_max_c,
                            temperature_min_c,
                            precipitation_probability_pct,
                            precipitation_hours,
                            crop_risk_score,
                            source
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        ON CONFLICT (
                            location,
                            forecast_date
                        )
                        DO UPDATE SET
                            country_id = EXCLUDED.country_id,
                            precipitation_sum_mm =
                                EXCLUDED.precipitation_sum_mm,
                            temperature_max_c =
                                EXCLUDED.temperature_max_c,
                            temperature_min_c =
                                EXCLUDED.temperature_min_c,
                            precipitation_probability_pct =
                                EXCLUDED.precipitation_probability_pct,
                            precipitation_hours =
                                EXCLUDED.precipitation_hours,
                            crop_risk_score =
                                EXCLUDED.crop_risk_score,
                            source =
                                EXCLUDED.source
                        """,
                        (
                            country_id,
                            location["name"],
                            forecast_date,
                            rainfall_value,
                            temp_max_value,
                            temp_min_value,
                            probability_value,
                            hours_value,
                            forecast_risk,
                            "Open-Meteo",
                        ),
                    )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    data = fetch_weather()

    print("OPEN-METEO CONNECTION: OK")
    print(f"LOCATIONS RECEIVED: {len(data)}")

    total_forecast_rows = 0

    for location, weather in zip(
        LOCATIONS,
        data,
    ):
        current = weather["current"]

        current_risk = calculate_crop_risk_score(
            current.get("temperature_2m"),
            current.get("relative_humidity_2m"),
            current.get("precipitation"),
        )

        daily = weather.get("daily", {})
        forecast_dates = daily.get("time", [])

        print()
        print(f"{location['name']} WEATHER:")
        print(current)
        print(f"CROP RISK SCORE: {current_risk}/100")
        print(f"FORECAST DAYS: {len(forecast_dates)}")

        total_forecast_rows += len(forecast_dates)

    save_weather(data)

    print()
    print(
        f"FORECAST ROWS SAVED/UPDATED: "
        f"{total_forecast_rows}"
    )
    print(
        "WEATHER OBSERVATIONS AND "
        "FORECASTS SAVED TO DATABASE"
    )
