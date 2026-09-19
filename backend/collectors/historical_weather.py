"""
Cocoa Intelligence Hub
Historical Weather Backfill

Purpose:
    Collect historical weather observations for the four
    Cross River cocoa intelligence locations.

Locations:
    Ikom
    Boki
    Etung
    Akamkpa

Source:
    Open-Meteo Historical Weather API

Important:
    This collector is separate from the existing live
    weather and forecast collectors.

    Historical weather is used to improve the multi-factor
    cocoa forecasting engine without introducing future
    information into historical observations.
"""

from datetime import date, datetime, timedelta
from statistics import mean

import requests

from backend.database.connection import get_connection


# ============================================================
# CONFIGURATION
# ============================================================

OPEN_METEO_ARCHIVE_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
)

START_DATE = date(2024, 10, 1)
END_DATE = date.today()

TIMEZONE = "Africa/Lagos"

TIMEOUT = 60

USER_AGENT = "Cocoa-Intelligence-Hub/1.0"


# ============================================================
# EXISTING PROJECT LOCATIONS
# ============================================================

LOCATIONS = [
    {
        "name": "Ikom",
        "latitude": 5.6927,
        "longitude": 8.7027,
    },
    {
        "name": "Boki",
        "latitude": 6.2500,
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


# ============================================================
# WEATHER API
# ============================================================

DAILY_VARIABLES = ",".join(
    [
        "temperature_2m_mean",
        "temperature_2m_max",
        "temperature_2m_min",
        "relative_humidity_2m_mean",
        "precipitation_sum",
    ]
)


# ============================================================
# FETCH HISTORICAL WEATHER
# ============================================================

def fetch_historical_weather(
    location,
    start_date,
    end_date,
):
    """
    Fetch historical daily weather for one location.

    Returns a list of normalized observations.
    """

    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": DAILY_VARIABLES,
        "timezone": TIMEZONE,
    }

    response = requests.get(
        OPEN_METEO_ARCHIVE_URL,
        params=params,
        timeout=TIMEOUT,
        headers={
            "User-Agent": USER_AGENT,
        },
    )

    response.raise_for_status()

    payload = response.json()

    daily = payload.get("daily")

    if not daily:
        raise ValueError(
            f"No daily weather data returned for "
            f"{location['name']}"
        )

    dates = daily.get("time", [])

    temperatures = daily.get(
        "temperature_2m_mean",
        [],
    )

    humidity = daily.get(
        "relative_humidity_2m_mean",
        [],
    )

    rainfall = daily.get(
        "precipitation_sum",
        [],
    )

    if not dates:
        return []

    observations = []

    for index, observation_date in enumerate(dates):

        temperature = (
            temperatures[index]
            if index < len(temperatures)
            else None
        )

        humidity_value = (
            humidity[index]
            if index < len(humidity)
            else None
        )

        rainfall_value = (
            rainfall[index]
            if index < len(rainfall)
            else None
        )

        observations.append(
            {
                "location": location["name"],
                "observation_date": observation_date,
                "rainfall_mm": rainfall_value,
                "temperature_c": temperature,
                "humidity_pct": humidity_value,
                "source": "OPEN_METEO_HISTORICAL",
            }
        )

    return observations


# ============================================================
# WEATHER ANOMALY
# ============================================================

def calculate_weather_anomaly(observations):
    """
    Calculate rainfall anomaly relative to the historical
    average for the same calendar month.

    This prevents January from being compared directly with
    September, for example.

    Result:
        percentage difference from the month's historical mean.
    """

    monthly_values = {}

    for row in observations:

        rainfall = row["rainfall_mm"]

        if rainfall is None:
            continue

        observation_date = datetime.strptime(
            row["observation_date"],
            "%Y-%m-%d",
        ).date()

        month = observation_date.month

        monthly_values.setdefault(
            month,
            [],
        ).append(float(rainfall))

    monthly_average = {}

    for month, values in monthly_values.items():

        if values:
            monthly_average[month] = mean(values)

    for row in observations:

        rainfall = row["rainfall_mm"]

        if rainfall is None:
            row["weather_anomaly"] = None
            continue

        observation_date = datetime.strptime(
            row["observation_date"],
            "%Y-%m-%d",
        ).date()

        baseline = monthly_average.get(
            observation_date.month
        )

        if baseline is None or baseline == 0:
            row["weather_anomaly"] = 0.0
            continue

        anomaly = (
            (float(rainfall) - baseline)
            / baseline
        ) * 100.0

        row["weather_anomaly"] = round(
            anomaly,
            2,
        )

    return observations


# ============================================================
# CROP WEATHER RISK
# ============================================================

def calculate_crop_risk(observations):
    """
    Calculate a transparent heuristic cocoa-weather risk score.

    Score:
        0 = lower weather risk
        100 = higher weather risk

    This is an intelligence indicator, NOT a scientifically
    validated disease or yield prediction model.

    Risk components:
        - excessive rainfall
        - unusually low rainfall
        - excessive temperature
        - excessive humidity
    """

    for row in observations:

        rainfall = row["rainfall_mm"]
        temperature = row["temperature_c"]
        humidity = row["humidity_pct"]

        risk = 0.0

        # ----------------------------------------------------
        # Rainfall risk
        # ----------------------------------------------------

        if rainfall is not None:

            rainfall = float(rainfall)

            # Very dry day
            if rainfall < 1:
                risk += 20

            # Heavy rainfall
            elif rainfall > 50:
                risk += 25

            # Extreme rainfall
            if rainfall > 100:
                risk += 20

        # ----------------------------------------------------
        # Temperature risk
        # ----------------------------------------------------

        if temperature is not None:

            temperature = float(temperature)

            if temperature > 32:
                risk += 20

            elif temperature < 20:
                risk += 15

        # ----------------------------------------------------
        # Humidity risk
        # ----------------------------------------------------

        if humidity is not None:

            humidity = float(humidity)

            if humidity > 90:
                risk += 20

            elif humidity < 45:
                risk += 15

        # ----------------------------------------------------
        # Clamp score
        # ----------------------------------------------------

        risk = min(
            100.0,
            max(0.0, risk),
        )

        row["crop_risk_score"] = round(
            risk,
            2,
        )

    return observations


# ============================================================
# DATABASE SAVE
# ============================================================

def save_observations(observations):

    if not observations:
        return 0

    conn = get_connection()

    saved = 0

    try:

        with conn.cursor() as cur:

            for row in observations:

                cur.execute(
                    """
                    INSERT INTO weather_observations (
                        location,
                        observation_date,
                        rainfall_mm,
                        temperature_c,
                        humidity_pct,
                        weather_anomaly,
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
                        rainfall_mm =
                            EXCLUDED.rainfall_mm,
                        temperature_c =
                            EXCLUDED.temperature_c,
                        humidity_pct =
                            EXCLUDED.humidity_pct,
                        weather_anomaly =
                            EXCLUDED.weather_anomaly,
                        crop_risk_score =
                            EXCLUDED.crop_risk_score,
                        source =
                            EXCLUDED.source
                    """,
                    (
                        row["location"],
                        row["observation_date"],
                        row["rainfall_mm"],
                        row["temperature_c"],
                        row["humidity_pct"],
                        row["weather_anomaly"],
                        row["crop_risk_score"],
                        row["source"],
                    ),
                )

                saved += 1

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()

    return saved


# ============================================================
# COLLECT ONE LOCATION
# ============================================================

def collect_location(
    location,
    start_date,
    end_date,
):
    print()
    print(
        f"FETCHING {location['name']} "
        f"HISTORICAL WEATHER..."
    )

    observations = fetch_historical_weather(
        location,
        start_date,
        end_date,
    )

    print(
        f"{location['name']} RAW ROWS: "
        f"{len(observations)}"
    )

    observations = calculate_weather_anomaly(
        observations
    )

    observations = calculate_crop_risk(
        observations
    )

    print(
        f"{location['name']} PROCESSED ROWS: "
        f"{len(observations)}"
    )

    return observations


# ============================================================
# MAIN
# ============================================================

def run(
    start_date=START_DATE,
    end_date=END_DATE,
):
    print("=" * 70)
    print("COCOA INTELLIGENCE HUB")
    print("HISTORICAL WEATHER BACKFILL")
    print("=" * 70)

    print(
        f"DATE RANGE: "
        f"{start_date.isoformat()} -> "
        f"{end_date.isoformat()}"
    )

    all_observations = []

    for location in LOCATIONS:

        try:

            observations = collect_location(
                location,
                start_date,
                end_date,
            )

            all_observations.extend(
                observations
            )

        except Exception as exc:

            print()
            print(
                f"{location['name']} COLLECTION ERROR:"
            )

            print(
                f"{type(exc).__name__}: {exc}"
            )

    print()
    print(
        f"TOTAL WEATHER RECORDS: "
        f"{len(all_observations)}"
    )

    if all_observations:

        saved = save_observations(
            all_observations
        )

        print()
        print(
            f"WEATHER RECORDS SAVED/UPDATED: "
            f"{saved}"
        )

    else:

        print()
        print(
            "NO HISTORICAL WEATHER DATA "
            "WAS AVAILABLE."
        )

    print()
    print(
        "HISTORICAL WEATHER BACKFILL COMPLETE"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run()