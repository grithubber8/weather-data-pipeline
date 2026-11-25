"""Unit tests for the transform step. They need no database and no internet."""
import math

import pandas as pd
import pytest

import pipeline


def make_raw(temps, precips, winds, start_offset_hours=-5):
    """Build a fake API response with one reading per hour, starting relative to now."""
    now = pd.Timestamp.now(tz="UTC").floor("h")
    times = [
        (now + pd.Timedelta(hours=start_offset_hours + i)).strftime("%Y-%m-%dT%H:%M")
        for i in range(len(temps))
    ]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": temps,
            "precipitation": precips,
            "wind_speed_10m": winds,
        }
    }


def test_columns_and_city_match_the_database_table():
    raw = make_raw([10.0, 11.0], [0.0, 0.1], [5.0, 6.0])
    df = pipeline.transform(raw, "Nantes")
    assert list(df.columns) == [
        "city", "observed_at", "temperature_c", "precipitation_mm", "wind_speed_kmh",
    ]
    assert set(df["city"]) == {"Nantes"}


def test_timestamps_are_timezone_aware_utc():
    raw = make_raw([10.0], [0.0], [5.0], start_offset_hours=-1)
    df = pipeline.transform(raw, "Nantes")
    assert str(df["observed_at"].dt.tz) == "UTC"


def test_future_hours_are_dropped():
    # offsets -2, -1, 0 are past or current; +1, +2, +3 are forecasts
    n = 6
    raw = make_raw([10.0] * n, [0.0] * n, [5.0] * n, start_offset_hours=-2)
    df = pipeline.transform(raw, "Nantes")
    assert len(df) == 3
    assert df["observed_at"].max() <= pd.Timestamp.now(tz="UTC")


def test_rows_with_no_measurements_are_dropped():
    raw = make_raw([None, 10.0], [None, 0.0], [None, 5.0], start_offset_hours=-2)
    df = pipeline.transform(raw, "Nantes")
    assert len(df) == 1


def test_partial_missing_values_are_kept_as_missing():
    raw = make_raw([10.0], [None], [5.0], start_offset_hours=-1)
    df = pipeline.transform(raw, "Nantes")
    assert len(df) == 1
    assert math.isnan(df.loc[0, "precipitation_mm"])


@pytest.mark.parametrize(
    "temps, precips, winds",
    [
        ([200.0], [0.0], [5.0]),   # impossible temperature
        ([10.0], [-1.0], [5.0]),   # negative rain
        ([10.0], [0.0], [-3.0]),   # negative wind speed
    ],
)
def test_impossible_values_are_rejected_and_logged(temps, precips, winds, caplog):
    raw = make_raw(temps, precips, winds, start_offset_hours=-1)
    with caplog.at_level("WARNING"):
        df = pipeline.transform(raw, "Nantes")
    assert df.empty
    assert "impossible values" in caplog.text


def test_none_if_nan_converts_missing_values_for_the_database():
    assert pipeline._none_if_nan(float("nan")) is None
    assert pipeline._none_if_nan(None) is None
    assert pipeline._none_if_nan(3.5) == 3.5
