"""OpenRouteService API でルートを取得する"""
import requests
import streamlit as st

_ORS_URL = "https://api.openrouteservice.org/v2/directions/foot-hiking"

_STEP_TYPES = {
    0: "直進",
    1: "右方向に進む",
    2: "右折",
    3: "急な右折",
    4: "Uターン",
    5: "左方向に進む",
    6: "左折",
    7: "急な左折",
    8: "直進",
    9: "右折(環状)",
    10: "ゴール到着",
    11: "スタート",
    12: "斜め右",
    13: "斜め左",
}


def _decode_polyline(encoded: str) -> list[list[float]]:
    """Google Encoded Polyline → [[lat, lng], ...] に変換"""
    coords: list[list[float]] = []
    index = 0
    lat = 0
    lng = 0
    while index < len(encoded):
        # latitude
        shift, result = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else (result >> 1)
        # longitude
        shift, result = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else (result >> 1)
        coords.append([lat / 1e5, lng / 1e5])
    return coords


def _parse_steps(raw_steps: list[dict]) -> list[dict]:
    return [
        {
            "instruction": s.get("instruction", ""),
            "distance": round(s.get("distance", 0)),
            "name": s.get("name") or "",
            "type": s.get("type", 0),
            "typeName": _STEP_TYPES.get(s.get("type", 0), "直進"),
            "wayPoints": s.get("way_points") or [],
        }
        for s in raw_steps
    ]


def get_route(
    start_lat: float, start_lng: float, goal_lat: float, goal_lng: float
) -> dict:
    """ルート取得。

    Returns:
        成功: {"polyline": [[lat,lng],...], "steps": [...], "summary": {...}}
        失敗: {"error": "エラーメッセージ"}
    """
    key = st.secrets.get("ORS_KEY", "")
    if not key or key.startswith("your_"):
        return {
            "error": (
                "ORS_KEY が未設定です。"
                ".streamlit/secrets.toml に OpenRouteService のAPIキーを設定してください。"
                "（https://openrouteservice.org/ で無料取得できます）"
            )
        }
    try:
        res = requests.post(
            _ORS_URL,
            headers={"Content-Type": "application/json", "Authorization": key},
            json={
                "coordinates": [[start_lng, start_lat], [goal_lng, goal_lat]],
                "instructions": True,
                "language": "ja",
            },
            timeout=15,
        )
        data = res.json()

        # v2 POST 形式
        if data.get("routes") and data["routes"][0]:
            route = data["routes"][0]
            polyline = _decode_polyline(route["geometry"])
            summary = route["summary"]
            steps = []
            segs = route.get("segments") or []
            if segs and segs[0].get("steps"):
                steps = _parse_steps(segs[0]["steps"])
            return {
                "polyline": polyline,
                "steps": steps,
                "summary": {
                    "distanceM": round(summary.get("distance", 0)),
                    "durationMin": round(summary.get("duration", 0) / 60),
                },
            }

        # GeoJSON フォールバック
        if data.get("features") and data["features"][0]:
            feature = data["features"][0]
            polyline = [[c[1], c[0]] for c in feature["geometry"]["coordinates"]]
            summary = feature["properties"]["summary"]
            steps = []
            segs = feature["properties"].get("segments") or []
            if segs and segs[0].get("steps"):
                steps = _parse_steps(segs[0]["steps"])
            return {
                "polyline": polyline,
                "steps": steps,
                "summary": {
                    "distanceM": round(summary.get("distance", 0)),
                    "durationMin": round(summary.get("duration", 0) / 60),
                },
            }

        error_val = data.get("error")
        if isinstance(error_val, dict):
            err = error_val.get("message") or str(error_val)
        else:
            err = str(error_val) if error_val else str(data)[:200]
        return {"error": err}

    except Exception as e:
        return {"error": str(e)}
