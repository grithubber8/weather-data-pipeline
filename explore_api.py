import requests
import pandas as pd

URL = "https://api.open-meteo.com/v1/forecast"
params = {
    "latitude": 47.2184,
    "longitude": -1.5536,
    "hourly": "temperature_2m,precipitation,wind_speed_10m",
    "past_days": 7,
    "timezone": "Europe/Paris",
}

response = requests.get(URL, params=params, timeout=30)
response.raise_for_status()
data = response.json()

df = pd.DataFrame(data["hourly"])
print(df.shape)
print(df.head())
print(df.dtypes)