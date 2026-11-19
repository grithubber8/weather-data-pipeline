"""Weather ETL: Open-Meteo API -> PostgreSQL."""
import logging
import math
import os

import pandas as pd
import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values

CITIES = {
    "Nantes": (47.2184, -1.5536),
    "Casablanca": (33.5731, -7.5898),
}
API_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = "temperature_2m,precipitation,wind_speed_10m"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")


def extract(latitude, longitude):
    """Call the API and return the raw JSON as a Python dictionary."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": HOURLY_VARIABLES,
        "past_days": 7,
        "timezone": "GMT",
    }
    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def transform(raw, city):
    """Turn raw JSON into a clean table that matches the database columns."""
    df = pd.DataFrame(raw["hourly"]).rename(
        columns={
            "time": "observed_at",
            "temperature_2m": "temperature_c",
            "precipitation": "precipitation_mm",
            "wind_speed_10m": "wind_speed_kmh",
        }
    )
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    df.insert(0, "city", city)

    # Keep only hours that have already happened (the API also returns forecasts).
    df = df[df["observed_at"] <= pd.Timestamp.now(tz="UTC")]

    # Quality checks: drop empty rows, then reject impossible values.
    measures = ["temperature_c", "precipitation_mm", "wind_speed_kmh"]
    df = df.dropna(subset=measures, how="all")
    bad = (
        (df["temperature_c"] < -60) | (df["temperature_c"] > 60)
        | (df["precipitation_mm"] < 0) | (df["wind_speed_kmh"] < 0)
    )
    if bad.any():
        log.warning("%s: dropping %d rows with impossible values", city, int(bad.sum()))
        df = df[~bad]
    return df.reset_index(drop=True)


def _none_if_nan(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


def load(df, connection):
    """Insert rows; if a (city, observed_at) already exists, update it instead."""
    rows = [
        (
            r.city,
            r.observed_at.to_pydatetime(),
            _none_if_nan(r.temperature_c),
            _none_if_nan(r.precipitation_mm),
            _none_if_nan(r.wind_speed_kmh),
        )
        for r in df.itertuples(index=False)
    ]
    sql = """
        INSERT INTO weather_hourly
            (city, observed_at, temperature_c, precipitation_mm, wind_speed_kmh)
        VALUES %s
        ON CONFLICT (city, observed_at) DO UPDATE SET
            temperature_c    = EXCLUDED.temperature_c,
            precipitation_mm = EXCLUDED.precipitation_mm,
            wind_speed_kmh   = EXCLUDED.wind_speed_kmh,
            loaded_at        = now()
    """
    with connection.cursor() as cursor:
        execute_values(cursor, sql, rows)
    return len(rows)


def get_connection():
    load_dotenv()
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def main():
    connection = get_connection()
    try:
        with connection:  # commits if everything succeeds, rolls back on error
            for city, (lat, lon) in CITIES.items():
                raw = extract(lat, lon)
                df = transform(raw, city)
                loaded = load(df, connection)
                log.info("%s: extracted %d, loaded %d rows", city, len(raw["hourly"]["time"]), loaded)
    finally:
        connection.close()


if __name__ == "__main__":
    main()