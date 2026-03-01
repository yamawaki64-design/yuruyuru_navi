"""ランドマーク距離フィルタ・POI分類"""
import math

# 大型施設（距離35m以内まで許容）
LARGE_POI_TYPES = {"駅", "大きな病院", "学校", "公園", "警察署", "郵便局"}

# 小型店舗は15m以内
SMALL_MAX_DIST = 15
LARGE_MAX_DIST = 35


def calc_dist_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2点間の距離をメートルで返す（簡易Haversine）"""
    R = 6_371_000
    d_lat = (lat2 - lat1) * math.pi / 180
    d_lng = (lng2 - lng1) * math.pi / 180
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1 * math.pi / 180)
        * math.cos(lat2 * math.pi / 180)
        * math.sin(d_lng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def classify_poi(tags: dict) -> str:
    """Overpass タグ辞書 → カテゴリ名"""
    if not tags:
        return "スポット"
    shop = tags.get("shop", "")
    amenity = tags.get("amenity", "")
    if shop == "convenience":
        return "コンビニ"
    if shop == "supermarket":
        return "スーパー"
    if shop in ("chemist", "drugstore"):
        return "ドラッグストア"
    if shop == "mobile_phone":
        return "携帯ショップ"
    if shop == "variety_store":
        return "100円ショップ"
    if amenity == "fast_food":
        return "ファストフード"
    if amenity == "bank":
        return "銀行"
    if tags.get("railway") == "station":
        return "駅"
    if tags.get("highway") == "bus_stop":
        return "バス停"
    if amenity == "school":
        return "学校"
    if amenity == "hospital":
        return "大きな病院"
    if amenity == "post_office":
        return "郵便局"
    if amenity == "police":
        return "警察署"
    if tags.get("leisure") in ("park", "playground"):
        return "公園"
    return "スポット"


def filter_landmarks(
    route_steps: list[dict],
    pois: list[dict],
    route_polyline: list[list[float]],
) -> list[dict]:
    """各曲がり角にランドマークを紐付けて返す（type 10/11 を除外済み）

    Returns: route_steps (type 10/11 除外) に landmarks フィールドを追加したリスト
    """
    turn_steps = [s for s in route_steps if s.get("type") not in (10, 11)]
    result = []
    for step in turn_steps:
        wp_list = step.get("wayPoints") or [0]
        wp_idx = min(wp_list[0], len(route_polyline) - 1)
        coord = route_polyline[wp_idx]

        nearby = []
        for p in pois:
            dist = calc_dist_m(coord[0], coord[1], p["lat"], p["lng"])
            is_large = p["type"] in LARGE_POI_TYPES
            if dist <= (LARGE_MAX_DIST if is_large else SMALL_MAX_DIST):
                nearby.append({**p, "dist": dist})

        # 大型施設を優先（距離が遠くても先）、同種は距離順
        nearby.sort(
            key=lambda p: (0 if p["type"] in LARGE_POI_TYPES else 1, p["dist"])
        )
        result.append({**step, "landmarks": nearby[:2]})

    return result
