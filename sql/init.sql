CREATE TABLE IF NOT EXISTS weather_hourly (
    city             TEXT        NOT NULL,
    observed_at      TIMESTAMPTZ NOT NULL,
    temperature_c    REAL,
    precipitation_mm REAL,
    wind_speed_kmh   REAL,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (city, observed_at)
);