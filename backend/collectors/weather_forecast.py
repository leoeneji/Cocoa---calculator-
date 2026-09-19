import httpx
from datetime import date

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


def fetch_weather_forecast():

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
        "daily": (
            "precipitation_sum,"
            "temperature_2m_max,"
            "temperature_2m_min,"
            "precipitation_probability_max,"
            "precipitation_hours"
        ),
        "forecast_days": 7,
        "timezone": TIMEZONE,
    }

    response = httpx.get(
        OPEN_METEO_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def calculate_forecast_risk(
    precipitation,
    precipitation_probability,
    temperature_max,
    temperature_min,
):
    score = 0

    if precipitation >= 20:
        score += 35
    elif precipitation >= 10:
        score += 25
    elif precipitation >= 5:
        score += 15

    if precipitation_probability >= 80:
        score += 25
    elif precipitation_probability >= 60:
        score += 15
    elif precipitation_probability >= 40:
        score += 10

    if temperature_max >= 32:
        score += 20

    if temperature_min <= 18:
        score += 15

    return min(score, 100)


def save_forecasts(data):

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

                daily = weather["daily"]

                for i, forecast_date in enumerate(
                    daily["time"]
                ):

                    precipitation = (
                        daily["precipitation_sum"][i]
                    )

                    temperature_max = (
                        daily["temperature_2m_max"][i]
                    )

                    temperature_min = (
                        daily["temperature_2m_min"][i]
                    )

                    precipitation_probability = (
                        daily["precipitation_probability_max"][i]
                    )

                    precipitation_hours = (
                        daily["precipitation_hours"][i]
                    )

                    crop_risk_score = calculate_forecast_risk(
                        precipitation,
                        precipitation_probability,
                        temperature_max,
                        temperature_min,
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
                            precipitation,
                            temperature_max,
                            temperature_min,
                            precipitation_probability,
                            precipitation_hours,
                            crop_risk_score,
                            "Open-Meteo",
                        ),
                    )

        conn.commit()

    finally:
        conn.close()


if __name__ == "__main__":

    data = fetch_weather_forecast()

    print("OPEN-METEO FORECAST CONNECTION: OK")
    print(f"LOCATIONS RECEIVED: {len(data)}")

    for location, weather in zip(LOCATIONS, data):

        print()
        print(f"{location['name']} 7-DAY FORECAST:")

        daily = weather["daily"]

        for i, forecast_date in enumerate(
            daily["time"]
        ):

            risk = calculate_forecast_risk(
                daily["precipitation_sum"][i],
                daily["precipitation_probability_max"][i],
                daily["temperature_2m_max"][i],
                daily["temperature_2m_min"][i],
            )

            print(
                forecast_date,
                "| Rain:",
                daily["precipitation_sum"][i],
                "mm",
                "| Max:",
                daily["temperature_2m_max"][i],
                "°C",
                "| Min:",
                daily["temperature_2m_min"][i],
                "°C",
                "| Rain Prob:",
                daily["precipitation_probability_max"][i],
                "%",
                "| Risk:",
                risk,
            )

    save_forecasts(data)

    print()
    print("7-DAY FORECASTS SAVED TO DATABASE")