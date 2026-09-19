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
        "timezone": TIMEZONE,
    }

    response = httpx.get(
        OPEN_METEO_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def calculate_crop_risk_score(
    temperature,
    humidity,
    rainfall,
):
    score = 0

    if humidity >= 90:
        score += 35
    elif humidity >= 80:
        score += 25
    elif humidity >= 70:
        score += 15

    if rainfall >= 10:
        score += 35
    elif rainfall >= 5:
        score += 25
    elif rainfall >= 1:
        score += 10

    if temperature >= 32:
        score += 20
    elif temperature <= 18:
        score += 15

    return min(score, 100)


def save_weather(data):
    conn = connect(settings.database_url)

    try:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id
                FROM countries
                WHERE code = 'NGA'
                LIMIT 1
            """)

            country = cur.fetchone()

            if not country:
                raise RuntimeError(
                    "Nigeria country record not found."
                )

            country_id = country[0]

            for location, weather in zip(LOCATIONS, data):

                current = weather["current"]

                observation_time = datetime.fromisoformat(
                    current["time"]
                )

                observation_date = observation_time.date()

                crop_risk_score = calculate_crop_risk_score(
                    current["temperature_2m"],
                    current["relative_humidity_2m"],
                    current["precipitation"],
                )

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
                    ON CONFLICT (location, observation_date)
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
                        current["precipitation"],
                        current["temperature_2m"],
                        current["relative_humidity_2m"],
                        crop_risk_score,
                        "Open-Meteo",
                    ),
                )

        conn.commit()

    finally:
        conn.close()


if __name__ == "__main__":

    data = fetch_weather()

    print("OPEN-METEO CONNECTION: OK")
    print(f"LOCATIONS RECEIVED: {len(data)}")

    for location, weather in zip(LOCATIONS, data):

        current = weather["current"]

        crop_risk_score = calculate_crop_risk_score(
            current["temperature_2m"],
            current["relative_humidity_2m"],
            current["precipitation"],
        )

        print()
        print(f"{location['name']} WEATHER:")
        print(current)
        print(
            f"CROP RISK SCORE: "
            f"{crop_risk_score}/100"
        )

    save_weather(data)

    print()
    print("WEATHER SAVED TO DATABASE")