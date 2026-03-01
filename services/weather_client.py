"""OpenWeatherMap から天気情報を取得する"""
import requests
import streamlit as st
from datetime import datetime

_OWM_URL = "https://api.openweathermap.org/data/2.5/weather"


def fetch_weather(lat: float, lng: float) -> dict | None:
    """天気取得。

    Returns:
        {"season", "temp", "weatherMain", "weatherDesc",
         "pollenRisk", "windSpeed", "windComment"}
        or None on failure.
    """
    key = st.secrets.get("OWM_KEY", "")
    try:
        res = requests.get(
            _OWM_URL,
            params={"lat": lat, "lon": lng, "appid": key, "units": "metric", "lang": "ja"},
            timeout=8,
        )
        data = res.json()
        if data.get("cod") != 200:
            return None

        month = datetime.now().month
        if 3 <= month <= 5:
            season = "春"
        elif 6 <= month <= 8:
            season = "夏"
        elif 9 <= month <= 11:
            season = "秋"
        else:
            season = "冬"

        temp = round(data["main"]["temp"])
        weather_main = data["weather"][0]["main"]
        weather_desc = data["weather"][0]["description"]
        pollen_risk = season == "春" and temp >= 12
        wind_speed = data.get("wind", {}).get("speed", 0)

        if wind_speed >= 10:
            wind_comment = "かなり強い（10m/s以上）"
        elif wind_speed >= 6:
            wind_comment = "そこそこ強い（6〜10m/s）"
        elif wind_speed >= 3:
            wind_comment = "少し風あり（3〜6m/s）"
        else:
            wind_comment = "おだやか"

        return {
            "season": season,
            "temp": temp,
            "weatherMain": weather_main,
            "weatherDesc": weather_desc,
            "pollenRisk": pollen_risk,
            "windSpeed": wind_speed,
            "windComment": wind_comment,
        }
    except Exception:
        return None
