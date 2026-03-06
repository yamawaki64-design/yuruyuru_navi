"""ゆるゆる道案内 - メインアプリ"""
import base64
from html import escape
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

from streamlit_js_eval import get_geolocation

from services.groq_client import generate_speeches
from services.ors_client import get_route
from services.overpass_client import fetch_landmarks
from services.weather_client import fetch_weather
from utils.nominatim import reverse_geocode, search_location
from utils.prompt_builder import build_guide_prompt, build_osekkai_prompt

# ===========================
# ページ設定
# ===========================
st.set_page_config(
    page_title="ゆるゆる道案内",
    page_icon="🐾",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;700&family=M+PLUS+Rounded+1c:wght@400;800&display=swap');
html, body, [class*="css"] { font-family: 'Zen Maru Gothic', sans-serif !important; }
/* Streamlit デフォルトヘッダー・ツールバーを非表示 */
header[data-testid="stHeader"],
[data-testid="stToolbar"] { display: none !important; }
/* 固定ヘッダー分の余白 */
.block-container { padding-top: 2rem !important; }
/* 固定タイトルバー */
.app-header {
    position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
    background: #2d6a4f; color: #fdf6e3;
    padding: 2px 16px;
    display: flex; align-items: center; gap: 8px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.25);
}
.app-header h1 {
    font-family: 'M PLUS Rounded 1c', sans-serif;
    font-weight: 800; font-size: 0.9rem; margin: 0;
}
/* タグラインパネル */
.tagline-panel {
    background: #d8f3dc; border: 2px solid #52b788;
    border-radius: 12px; padding: 9px 16px;
    font-size: 0.85rem; color: #1b4332; font-weight: 700;
    text-align: center; margin-bottom: 12px;
}
.instr-bar {
    background: #d8f3dc; border-left: 4px solid #52b788;
    padding: 10px 16px; border-radius: 6px;
    font-size: 0.85rem; color: #1b4332; margin-bottom: 10px;
}
.route-bar {
    background: #fff; border: 1px solid #ddd; border-radius: 8px;
    padding: 8px 14px; font-size: 0.8rem; color: #555;
    text-align: center; margin: 8px 0;
}
.point-panel {
    border-radius: 10px; padding: 10px 14px;
    font-size: 0.85rem; margin-bottom: 6px;
}
.point-start { background: #fff9e6; border: 1.5px solid #ffc107; }
.point-goal  { background: #e8f8fb; border: 1.5px solid #17a2b8; }
.speech-box  { border-radius: 14px; padding: 16px; margin: 10px 0; line-height: 1.85; }
.speech-guide   { background: #f0fff4; border: 2px solid #52b788; }
.speech-osekkai { background: #fff8e1; border: 2px solid #f9a825; }
/* セカンダリボタン：非ホバー時を温かい黄色に */
.stButton > button {
    background-color: #fff8e1 !important;
    border: 1.5px solid #f9a825 !important;
    color: #1b4332 !important;
}
.stButton > button:hover {
    background-color: #2d6a4f !important;
    border-color: #2d6a4f !important;
    color: #fdf6e3 !important;
}
/* プライマリボタン（ルート検索）は緑を維持 */
.stButton > button[kind="primary"] {
    background-color: #2d6a4f !important;
    border-color: #2d6a4f !important;
    color: #fdf6e3 !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: #1b4332 !important;
    border-color: #1b4332 !important;
}
/* iOS タッチ操作改善 */
* { -webkit-tap-highlight-color: rgba(0,0,0,0) !important; }
.stSelectbox > div { cursor: pointer !important; touch-action: manipulation; }
.stSelectbox input { pointer-events: none; }
[data-testid="stCustomComponentV1"] iframe {
    pointer-events: all !important;
    touch-action: pan-x pan-y !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# 背景画像（base64 で CSS に埋め込み）
_bg_path = Path(__file__).parent / "assets" / "navi_background_1600x900.jpg"
if _bg_path.exists():
    _bg_b64 = base64.b64encode(_bg_path.read_bytes()).decode()
    st.markdown(
        f'<style>'
        f'.stApp {{'
        f'  background-image: url("data:image/jpeg;base64,{_bg_b64}");'
        f'  background-size: cover;'
        f'  background-position: center top;'
        f'  background-repeat: no-repeat;'
        f'}}'
        f'.main .block-container {{'
        f'  background: rgba(253, 246, 227, 0.90);'
        f'  border-radius: 12px;'
        f'}}'
        f'</style>',
        unsafe_allow_html=True,
    )

# ===========================
# セッション初期化
# ===========================
_DEFAULTS: dict = {
    "page": 1,
    "start": None,            # {"lat", "lng", "name"}
    "goal": None,             # {"lat", "lng", "name"}
    "input_phase": "start",   # "start" | "goal" | "both"
    "last_click": None,       # 処理済みのクリック座標タプル
    "route": None,            # ORS result dict
    "ors_error": None,
    "overpass_done": False,
    "overpass_steps": [],
    "weather_data": None,
    "guide_speech": None,
    "osekkai_speech": None,
    "start_results": [],      # Nominatim 検索結果
    "goal_results": [],
    "map_center": [35.6895, 139.6917],  # デフォルト：東京
    "gps_requested": False,  # GPS 取得リクエスト中フラグ
    "fitted_bounds": None,   # (s_lat, s_lng, g_lat, g_lng) fit_bounds 適用済みのピン組
    "p2_map_fitted": False,  # 2画面目 fit_bounds 適用済みフラグ
}

for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

ss = st.session_state  # 短縮エイリアス

# 施設種別キーワード一覧（これらを含むクエリは結果1件でも自動採用しない）
_FACILITY_WORDS = frozenset([
    "駅", "バス停", "公園", "病院", "学校", "大学", "神社", "寺",
    "コンビニ", "スーパー", "図書館", "市役所", "警察", "郵便局", "銀行",
])


def _is_facility_query(query: str) -> bool:
    """施設種別キーワードが含まれるクエリは候補リストを必ず表示する"""
    return any(w in query for w in _FACILITY_WORDS)


def _reset_all() -> None:
    for k in list(_DEFAULTS.keys()):
        if k in ss:
            del ss[k]
    # テキスト入力ウィジェットもクリア
    for wk in ("sq_input", "gq_input"):
        if wk in ss:
            del ss[wk]


# ===========================
# ヘッダー（全ページ共通）
# ===========================
st.markdown(
    """
<div class="app-header">
  <h1>🗺️ ゆるゆる道案内</h1>
</div>
<div class="tagline-panel">
  <div style="font-size:0.75rem;color:#2d6a4f;line-height:1.85;margin-bottom:8px;">
    「今いるとこからお店までの道がわからないよ」<br>
    「最寄り駅まで来たけど、ここからがわからん」<br>
    そんな歩き道迷子になりかけ子猫ちゃんも大丈夫。
  </div>
  🐾 犬のおまわりさんが、道案内するワン！
</div>
""",
    unsafe_allow_html=True,
)


# ===========================
# ページ 1：スタート・ゴール入力
# ===========================
def page1() -> None:
    _active_badge = (
        '<span style="background:#52b788;color:#fff;'
        'padding:2px 8px;border-radius:10px;font-size:0.7rem;font-weight:700;">'
        "← 今ここ入力中</span>"
    )
    _done_badge = (
        '<span style="background:#aaa;color:#fff;'
        'padding:2px 8px;border-radius:10px;font-size:0.7rem;">設定済み ✓</span>'
    )

    # ── スタート地点 ────────────────────────────────
    if ss.start:
        # 設定済み：1行コンパクト表示
        c1, c2 = st.columns([6, 1])
        with c1:
            st.markdown(
                f'<div class="point-panel point-start" style="margin-bottom:4px">'
                f'📍 <b>スタート</b>&ensp;{escape(ss.start["name"])}&ensp;{_done_badge}'
                f'</div>',
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("✕", key="btn_clr_s", use_container_width=True):
                ss.start = None
                ss.input_phase = "start"
                st.rerun()
    else:
        # 入力フォーム（Enter キーで検索）
        badge = _active_badge if ss.input_phase == "start" else ""
        st.markdown(f"**📍 スタート地点** {badge}", unsafe_allow_html=True)

        # --- GPS ボタン ---
        if not ss.gps_requested:
            if st.button("📡 今いる場所をスタートにする", key="btn_gps", use_container_width=True):
                ss.gps_requested = True
                st.rerun()
        else:
            st.info("📡 ブラウザの位置情報許可を確認してワン🐾")
            loc = get_geolocation()
            if loc and isinstance(loc, dict) and "coords" in loc:
                try:
                    lat = loc["coords"]["latitude"]
                    lng = loc["coords"]["longitude"]
                except (KeyError, TypeError):
                    st.error("位置情報の取得に失敗したワン😢 テキスト入力で場所を入力してワン")
                    ss.gps_requested = False
                    st.rerun()
                else:
                    with st.spinner("住所を確認中..."):
                        name = reverse_geocode(lat, lng)
                    ss.start = {"lat": lat, "lng": lng, "name": name}
                    ss.map_center = [lat, lng]
                    ss.input_phase = "both" if ss.goal else "goal"
                    ss.gps_requested = False
                    st.rerun()
            elif loc:
                # coords キーがない（エラーレスポンスなど想定外の構造）
                st.error("位置情報を取得できなかったワン😢 テキスト入力で場所を入力してワン")
                ss.gps_requested = False
                st.rerun()
            if st.button("キャンセル", key="btn_gps_cancel"):
                ss.gps_requested = False
                st.rerun()

        # --- テキスト検索フォーム ---
        with st.form("form_start", clear_on_submit=False):
            sq = st.text_input(
                "スタート検索", key="sq_input",
                label_visibility="collapsed",
                placeholder="駅名・施設名・住所など（Enterでも検索できるワン）",
            )
            s_sub = st.form_submit_button("🔍 検索", use_container_width=True)
        if s_sub and sq.strip():
            with st.spinner("検索中..."):
                s_res = search_location(sq.strip())
            if len(s_res) == 1 and not _is_facility_query(sq.strip()):
                chosen = s_res[0]
                ss.start = {"lat": chosen["lat"], "lng": chosen["lng"], "name": chosen["name"]}
                ss.map_center = [chosen["lat"], chosen["lng"]]
                ss.input_phase = "both" if ss.goal else "goal"
                ss.start_results = []
                st.rerun()
            elif s_res:
                ss.start_results = s_res
            else:
                ss.start_results = []
                st.warning("場所が見つからなかったワン。別のキーワードで試してみてワン！")
        if ss.start_results:
            opts = [r["label"] for r in ss.start_results]
            idx = st.selectbox(
                "スタート候補", range(len(opts)),
                format_func=lambda i: opts[i], key="s_sel",
                label_visibility="collapsed",
                index=None,
                placeholder="-- 選択するワン",
            )
            if idx is not None:
                if st.button("📍 ここをスタートに設定", key="btn_s_set", use_container_width=True):
                    chosen = ss.start_results[idx]
                    ss.start = {"lat": chosen["lat"], "lng": chosen["lng"], "name": chosen["name"]}
                    ss.map_center = [chosen["lat"], chosen["lng"]]
                    ss.input_phase = "both" if ss.goal else "goal"
                    ss.start_results = []
                    st.rerun()
        if ss.input_phase == "start":
            st.caption("📌 地図をタップして設定することもできるワン")

    # ── ゴール地点 ────────────────────────────────
    if ss.goal:
        # 設定済み：1行コンパクト表示
        c1, c2 = st.columns([6, 1])
        with c1:
            st.markdown(
                f'<div class="point-panel point-goal" style="margin-bottom:4px">'
                f'🏁 <b>ゴール</b>&ensp;{escape(ss.goal["name"])}&ensp;{_done_badge}'
                f'</div>',
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("✕", key="btn_clr_g", use_container_width=True):
                ss.goal = None
                ss.input_phase = "goal" if ss.start else "start"
                st.rerun()
    else:
        # 入力フォーム（Enter キーで検索）
        badge = _active_badge if ss.input_phase == "goal" else ""
        st.markdown(f"**🏁 ゴール地点** {badge}", unsafe_allow_html=True)
        with st.form("form_goal", clear_on_submit=False):
            gq = st.text_input(
                "ゴール検索", key="gq_input",
                label_visibility="collapsed",
                placeholder="駅名・施設名・住所など（Enterでも検索できるワン）",
            )
            g_sub = st.form_submit_button("🔍 検索", use_container_width=True)
        if g_sub and gq.strip():
            with st.spinner("検索中..."):
                g_res = search_location(gq.strip())
            if len(g_res) == 1 and not _is_facility_query(gq.strip()):
                chosen = g_res[0]
                ss.goal = {"lat": chosen["lat"], "lng": chosen["lng"], "name": chosen["name"]}
                ss.map_center = [chosen["lat"], chosen["lng"]]
                ss.input_phase = "both" if ss.start else "goal"
                ss.goal_results = []
                st.rerun()
            elif g_res:
                ss.goal_results = g_res
            else:
                ss.goal_results = []
                st.warning("場所が見つからなかったワン。別のキーワードで試してみてワン！")
        if ss.goal_results:
            opts = [r["label"] for r in ss.goal_results]
            idx = st.selectbox(
                "ゴール候補", range(len(opts)),
                format_func=lambda i: opts[i], key="g_sel",
                label_visibility="collapsed",
                index=None,
                placeholder="-- 選択するワン",
            )
            if idx is not None:
                if st.button("🏁 ここをゴールに設定", key="btn_g_set", use_container_width=True):
                    chosen = ss.goal_results[idx]
                    ss.goal = {"lat": chosen["lat"], "lng": chosen["lng"], "name": chosen["name"]}
                    ss.map_center = [chosen["lat"], chosen["lng"]]
                    ss.input_phase = "both" if ss.start else "goal"
                    ss.goal_results = []
                    st.rerun()
        if ss.input_phase == "goal":
            st.caption("📌 地図をタップして設定することもできるワン")

    # --- 入れ替え / ルート検索ボタン ---
    can_search = ss.start is not None and ss.goal is not None
    btn_swap, btn_search = st.columns([1, 2])
    with btn_swap:
        if st.button("🔀 入れ替え", disabled=not can_search, use_container_width=True):
            ss.start, ss.goal = ss.goal, ss.start
            st.rerun()
    with btn_search:
        if st.button(
            "🔍 ルートを検索する",
            disabled=not can_search,
            use_container_width=True,
            type="primary",
        ):
            with st.spinner("🔍 ルートを計算中だワン..."):
                result = get_route(
                    ss.start["lat"], ss.start["lng"],
                    ss.goal["lat"], ss.goal["lng"],
                )
            if "error" in result:
                ss.ors_error = f"ルートが見つからなかったワン😢（{result['error']}）"
            else:
                ss.route = result
                ss.ors_error = None
                ss.overpass_done = False
                ss.overpass_steps = []
                ss.weather_data = None
                ss.guide_speech = None
                ss.osekkai_speech = None
                ss.p2_map_fitted = False
                ss.page = 2
                st.rerun()

    if ss.ors_error:
        st.error(ss.ors_error)

    # --- 地図 ---
    # zoom_start は固定値（毎 rerun で変化させると st_folium が再初期化してユーザーのズームが失われる）
    m = folium.Map(location=ss.map_center, zoom_start=13, tiles="OpenStreetMap")
    # 両地点確定時: ピン組が変わった最初の1回だけ fit_bounds を適用
    if ss.start and ss.goal:
        _cur = (ss.start["lat"], ss.start["lng"], ss.goal["lat"], ss.goal["lng"])
        if ss.fitted_bounds != _cur:
            m.fit_bounds(
                [
                    [min(ss.start["lat"], ss.goal["lat"]),
                     min(ss.start["lng"], ss.goal["lng"])],
                    [max(ss.start["lat"], ss.goal["lat"]),
                     max(ss.start["lng"], ss.goal["lng"])],
                ],
                padding_top_left=[50, 30],
                padding_bottom_right=[20, 30],
            )
            ss.fitted_bounds = _cur

    if ss.start:
        folium.Marker(
            [ss.start["lat"], ss.start["lng"]],
            popup=f"📍 スタート<br>{escape(ss.start['name'])}",
            icon=folium.DivIcon(
                html='<div style="font-size:26px;line-height:1;filter:drop-shadow(1px 1px 1px #0006)">📍</div>',
                icon_size=(26, 26), icon_anchor=(13, 24),
            ),
        ).add_to(m)

    if ss.goal:
        folium.Marker(
            [ss.goal["lat"], ss.goal["lng"]],
            popup=f"🏁 ゴール<br>{escape(ss.goal['name'])}",
            icon=folium.DivIcon(
                html='<div style="font-size:26px;line-height:1;filter:drop-shadow(1px 1px 1px #0006)">🏁</div>',
                icon_size=(26, 26), icon_anchor=(13, 24),
            ),
        ).add_to(m)

    map_data = st_folium(
        m,
        use_container_width=True,
        height=360,
        returned_objects=["last_clicked"],
        key="page1_map",
    )

    # --- クリック処理 ---
    if map_data and map_data.get("last_clicked"):
        clicked = map_data["last_clicked"]
        click_key = (round(clicked["lat"], 5), round(clicked["lng"], 5))
        if ss.last_click != click_key:
            ss.last_click = click_key
            lat, lng = clicked["lat"], clicked["lng"]
            if ss.input_phase == "start":
                with st.spinner("場所を確認中..."):
                    name = reverse_geocode(lat, lng)
                ss.start = {"lat": lat, "lng": lng, "name": name}
                ss.map_center = [lat, lng]
                ss.input_phase = "goal"
                st.rerun()
            elif ss.input_phase == "goal":
                with st.spinner("場所を確認中..."):
                    name = reverse_geocode(lat, lng)
                ss.goal = {"lat": lat, "lng": lng, "name": name}
                ss.map_center = [lat, lng]
                ss.input_phase = "both"
                st.rerun()

    # --- リセット ---
    st.markdown("---")
    if st.button("🔄 最初からやり直す", key="btn_reset1"):
        _reset_all()
        st.rerun()


# ===========================
# ページ 2：ルート確認・道案内
# ===========================
def page2() -> None:
    route = ss.route
    summary = route["summary"]

    # --- スタート・ゴール表示 ---
    sn = escape(ss.start["name"])
    gn = escape(ss.goal["name"])
    st.markdown(
        f'<div style="display:flex;gap:10px;margin-bottom:8px;">'
        f'<div class="point-panel point-start" style="flex:1"><b>📍 スタート</b><br><small>{sn}</small></div>'
        f'<div class="point-panel point-goal"  style="flex:1"><b>🏁 ゴール</b><br><small>{gn}</small></div>'
        f"</div>",
        unsafe_allow_html=True,
    )

    # --- ルート情報バー ---
    st.markdown(
        f'<div class="route-bar">🚶 徒歩約{summary["durationMin"]}分 ／ 約{summary["distanceM"]}m</div>',
        unsafe_allow_html=True,
    )

    # --- ルート地図 ---
    polyline = route["polyline"]
    lats = [c[0] for c in polyline]
    lngs = [c[1] for c in polyline]
    m = folium.Map(
        location=[(min(lats) + max(lats)) / 2, (min(lngs) + max(lngs)) / 2],
        zoom_start=14,
        tiles="OpenStreetMap",
    )
    folium.PolyLine(polyline, color="#2d6a4f", weight=5, opacity=0.8).add_to(m)
    folium.Marker(
        [ss.start["lat"], ss.start["lng"]],
        popup=f"📍 スタート<br>{sn}",
        icon=folium.DivIcon(
            html='<div style="font-size:26px;line-height:1;filter:drop-shadow(1px 1px 1px #0006)">📍</div>',
            icon_size=(26, 26), icon_anchor=(13, 24),
        ),
    ).add_to(m)
    folium.Marker(
        [ss.goal["lat"], ss.goal["lng"]],
        popup=f"🏁 ゴール<br>{gn}",
        icon=folium.DivIcon(
            html='<div style="font-size:26px;line-height:1;filter:drop-shadow(1px 1px 1px #0006)">🏁</div>',
            icon_size=(26, 26), icon_anchor=(13, 24),
        ),
    ).add_to(m)
    if not ss.p2_map_fitted:
        m.fit_bounds(
            [[min(lats), min(lngs)], [max(lats), max(lngs)]],
            padding_top_left=[40, 30],
            padding_bottom_right=[30, 30],
        )
        ss.p2_map_fitted = True
    st_folium(m, use_container_width=True, height=340, returned_objects=[], key="page2_map")

    # --- Overpass・天気バックグラウンド取得 ---
    if not ss.overpass_done:
        with st.spinner("ちょっと待つワン。今説明の順番を考えてるワン…"):
            with ThreadPoolExecutor(max_workers=2) as executor:
                f_land = executor.submit(fetch_landmarks, route["polyline"], route["steps"])
                f_weat = executor.submit(fetch_weather, ss.goal["lat"], ss.goal["lng"])
                ss.overpass_steps = f_land.result()
                ss.weather_data = f_weat.result()
        ss.overpass_done = True
        st.rerun()

    # --- 「案内してもらうワン🐾」ボタン ---
    if not ss.guide_speech:
        if st.button("案内してもらうワン🐾", use_container_width=True, type="primary"):
            steps_src = ss.overpass_steps if ss.overpass_steps else route["steps"]
            guide_prompt = build_guide_prompt(ss.start["name"], ss.goal["name"], steps_src)
            osekkai_prompt = build_osekkai_prompt(ss.weather_data, summary)
            with st.spinner("犬のおまわりさんが考えてるワン...🐾"):
                guide_text, osekkai_text = generate_speeches(guide_prompt, osekkai_prompt)
            ss.guide_speech = guide_text
            ss.osekkai_speech = osekkai_text
            st.rerun()

    # --- セリフ表示 ---
    if ss.guide_speech:
        guide_html = escape(ss.guide_speech).replace("\n", "<br>")
        st.markdown(
            f'<div class="speech-box speech-guide">'
            f"<b style='color:#2d6a4f;'>🗣️ 道案内するワン</b>"
            f"<p style='margin-top:8px;font-size:0.92rem;'>{guide_html}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # ④ おせっかいセリフ（迷ったら？より先に表示）
        if ss.osekkai_speech:
            osekkai_html = escape(ss.osekkai_speech).replace("\n", "<br>")
            st.markdown(
                f'<div class="speech-box speech-osekkai">'
                f"<b style='color:#e65100;'>🐾 おせっかいするワン</b>"
                f"<p style='margin-top:8px;font-size:0.92rem;'>{osekkai_html}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ② ボタン行
        gmap_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={ss.start['lat']},{ss.start['lng']}"
            f"&destination={ss.goal['lat']},{ss.goal['lng']}"
            "&travelmode=walking"
        )
        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button("🐾 もう一回道案内するワン", use_container_width=True):
                ss.guide_speech = None
                ss.osekkai_speech = None
                ss.page = 1
                st.rerun()
        with rc2:
            st.link_button("🗺️ Google Map先生に引き継ぐワン", gmap_url, use_container_width=True)

    # --- リセット ---
    st.markdown("---")
    if st.button("🔄 最初からやり直す", key="btn_reset2"):
        _reset_all()
        st.rerun()


# ===========================
# ページルーティング
# ===========================
if ss.page == 1:
    page1()
else:
    page2()
