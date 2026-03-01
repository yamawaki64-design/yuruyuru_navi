"""Nominatim API を使った地名検索・逆ジオコーディング"""
import requests

_BASE = "https://nominatim.openstreetmap.org"
_HEADERS = {"User-Agent": "yuruyuru-navi/1.0 (contact: local-dev)"}

# 入力キーワード → 優先すべき OSM class / type の対応表
# Nominatim レスポンスの class・type フィールドを参照してソートに使う
_FACILITY_HINTS: dict[str, dict[str, set[str]]] = {
    "駅":       {"class": {"railway", "public_transport"},
                 "type":  {"station", "halt", "subway_entrance", "tram_stop", "stop_area"}},
    "バス停":   {"class": {"highway", "public_transport"},
                 "type":  {"bus_stop", "bus_station"}},
    "公園":     {"class": {"leisure"},
                 "type":  {"park", "garden", "playground", "nature_reserve"}},
    "病院":     {"class": {"amenity"},
                 "type":  {"hospital", "clinic"}},
    "学校":     {"class": {"amenity"},
                 "type":  {"school", "university", "college", "kindergarten"}},
    "大学":     {"class": {"amenity"},
                 "type":  {"university", "college"}},
    "神社":     {"class": {"amenity"},
                 "type":  {"place_of_worship"}},
    "寺":       {"class": {"amenity"},
                 "type":  {"place_of_worship"}},
    "コンビニ": {"class": {"shop"}, "type": {"convenience"}},
    "スーパー": {"class": {"shop"}, "type": {"supermarket"}},
    "図書館":   {"class": {"amenity"}, "type": {"library"}},
    "市役所":   {"class": {"amenity"}, "type": {"townhall"}},
    "警察":     {"class": {"amenity"}, "type": {"police"}},
    "郵便局":   {"class": {"amenity"}, "type": {"post_office"}},
    "銀行":     {"class": {"amenity"}, "type": {"bank"}},
}


def _get_facility_hint(query: str) -> dict[str, set[str]] | None:
    """クエリに含まれる施設種別キーワードを検出して OSM ヒントを返す"""
    for kw, hint in _FACILITY_HINTS.items():
        if kw in query:
            return hint
    return None


def _sort_by_facility(items: list[dict], hint: dict[str, set[str]]) -> list[dict]:
    """施設ヒントに一致する class/type を先頭に、次に importance 降順でソート"""
    def key(item: dict) -> tuple[int, float]:
        cl = item.get("class", "")
        tp = item.get("type", "")
        matched = cl in hint["class"] or tp in hint["type"]
        return (0 if matched else 1, -float(item.get("importance", 0)))
    return sorted(items, key=key)


def reverse_geocode(lat: float, lng: float) -> str:
    """緯度経度 → 短い地名文字列"""
    try:
        r = requests.get(
            f"{_BASE}/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "accept-language": "ja"},
            headers=_HEADERS,
            timeout=5,
        )
        data = r.json()
        addr = data.get("address", {})
        return (
            addr.get("road")
            or addr.get("suburb")
            or addr.get("city_district")
            or addr.get("city")
            or f"({lat:.4f}, {lng:.4f})"
        )
    except Exception:
        return f"({lat:.4f}, {lng:.4f})"


def _short_label(item: dict) -> tuple[str, str]:
    """Nominatim レスポンスから (短縮名, 選択肢用ラベル) を生成する"""
    display = item.get("display_name", "")
    addr = item.get("address", {})

    # 施設・駅名など（先頭要素）
    parts = [p.strip() for p in display.split(",")]
    name = parts[0] if parts else display[:40]

    # 選択肢ラベル = 名前 ＋ 市区町村 ＋ 都道府県 で文脈を付与
    context_parts = []
    for key in ("city", "town", "village", "city_district", "suburb", "county"):
        v = addr.get(key)
        if v and v != name:
            context_parts.append(v)
            break
    for key in ("state", "province"):
        v = addr.get(key)
        if v:
            context_parts.append(v)
            break
    context = "　".join(context_parts)
    label = f"{name}（{context}）" if context else name

    return name, label


def _fetch_nominatim(query: str) -> list[dict]:
    """Nominatim API から生の検索結果リストを返す（内部ヘルパー）"""
    try:
        r = requests.get(
            f"{_BASE}/search",
            params={
                "q": query,
                "format": "json",
                "accept-language": "ja",
                "countrycodes": "jp",
                "limit": 10,
                "addressdetails": 1,
            },
            headers=_HEADERS,
            timeout=5,
        )
        return r.json()
    except Exception as e:
        print(f"[Nominatim] ERROR query={query!r}  {type(e).__name__}: {e}")
        return []


def search_location(query: str) -> list[dict]:
    """テキスト検索 → 候補地リスト

    Returns:
        [{"name": str, "label": str, "lat": float, "lng": float}, ...]
    """
    items = _fetch_nominatim(query)
    print(f"[Nominatim] query={query!r}  hits={len(items)}"
          + (f"  first={items[0].get('display_name','')[:60]}" if items else ""))

    # 施設種別キーワードが含まれる場合は対応する class/type を優先ソート
    hint = _get_facility_hint(query)
    if hint:
        items = _sort_by_facility(items, hint)

    # 駅名検索でヒットが少ない場合、「駅」を除いた基本名で再検索して同名異駅を補完
    # 例: "京橋駅"(東京1件) → "京橋" でも検索 → JR京橋駅(大阪) を追加
    if query.endswith("駅") and len(items) < 3:
        base = query[:-1].strip()
        extra = _fetch_nominatim(base)
        station_hint = _FACILITY_HINTS["駅"]
        # 鉄道・駅タイプのみ残す
        station_extra = [
            i for i in extra
            if i.get("class") in station_hint["class"] or i.get("type") in station_hint["type"]
        ]
        # 重複排除（0.002度≒約200m以内は同じ場所とみなす）
        existing = [(float(i["lat"]), float(i["lon"])) for i in items]
        for i in station_extra:
            ilat, ilng = float(i["lat"]), float(i["lon"])
            if not any(abs(ilat - e[0]) < 0.002 and abs(ilng - e[1]) < 0.002 for e in existing):
                items.append(i)
                existing.append((ilat, ilng))
        if station_extra:
            print(f"[Nominatim] supplemented {len(station_extra)} station(s) for base={base!r}")

    results = []
    for item in items[:5]:
        name, label = _short_label(item)
        results.append(
            {
                "name": name,
                "label": label,
                "lat": float(item["lat"]),
                "lng": float(item["lon"]),
            }
        )
    return results
