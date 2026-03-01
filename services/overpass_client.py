"""Overpass API からランドマークを取得する（フォールバック付き）"""
import requests
from utils.landmark_filter import classify_poi, filter_landmarks

_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
_TIMEOUT = 10  # 各サーバーのタイムアウト秒数


def _overpass_fetch(query: str) -> dict | None:
    """3サーバーを順番に試してレスポンスを返す。全滅時は None"""
    for server in _SERVERS:
        try:
            res = requests.post(
                server,
                data={"data": query},
                timeout=_TIMEOUT,
            )
            if not res.ok:
                continue
            return res.json()
        except Exception:
            continue
    return None


def fetch_landmarks(
    route_polyline: list[list[float]],
    route_steps: list[dict],
) -> list[dict]:
    """ランドマーク取得 → 曲がり角ステップに紐付けて返す

    失敗時は route_steps をそのまま返す（ランドマークなし）。
    """
    if len(route_polyline) < 2 or not route_steps:
        return route_steps

    lats = [c[0] for c in route_polyline]
    lngs = [c[1] for c in route_polyline]
    south = min(lats) - 0.001
    north = max(lats) + 0.001
    west = min(lngs) - 0.001
    east = max(lngs) + 0.001

    query = f"""[out:json][timeout:10];
(
  node["shop"~"convenience|supermarket|chemist|drugstore|mobile_phone|variety_store"]({south},{west},{north},{east});
  node["amenity"~"fast_food|bank|school|hospital|post_office|police"]({south},{west},{north},{east});
  node["railway"="station"]({south},{west},{north},{east});
  node["highway"="bus_stop"]({south},{west},{north},{east});
  node["leisure"~"park|playground"]({south},{west},{north},{east});
  way["leisure"="park"]({south},{west},{north},{east});
);
out center;
"""

    data = _overpass_fetch(query)
    if not data:
        return route_steps

    pois = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:ja")
        if not name:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if not lat or not lng:
            continue
        pois.append(
            {"name": name, "lat": float(lat), "lng": float(lng), "type": classify_poi(tags)}
        )

    return filter_landmarks(route_steps, pois, route_polyline)
