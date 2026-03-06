# 🐾 ゆるゆる道案内

## このファイルについて
Claude Code がプロジェクトを理解するための引継ぎ資料。
実装済みコードをもとに更新（2026年3月5日）。

---

## アプリ概要
童謡「犬のおまわりさん」をモチーフにした、ゆるい徒歩道案内アプリ。
一生懸命だけどちょっとおせっかいな犬のおまわりさんが、ゆるく道案内してくれる。

---

## 技術スタック

| 項目 | 内容 |
|------|------|
| フレームワーク | Streamlit |
| 地図 | streamlit-folium（Leaflet相当・クリックで座標取得可） |
| ルート取得 | OpenRouteService（ORS）API |
| ランドマーク取得 | Overpass API（3サーバーフォールバック） |
| 天気取得 | OpenWeatherMap API |
| AI セリフ生成 | Groq API（llama-3.3-70b-versatile） |
| GPS | streamlit-js-eval（`get_geolocation()`） |
| APIキー管理 | `.streamlit/secrets.toml`（gitignore済み） |
| ホスティング | Streamlit Community Cloud |

---

## ファイル構成

```
app.py                    # メイン（2ページ: page=1/2）
services/
  ors_client.py           # ORS ルート取得
  overpass_client.py      # ランドマーク（3サーバーフォールバック）
  weather_client.py       # OpenWeatherMap 天気
  groq_client.py          # セリフ生成（ThreadPoolExecutor 並行）
utils/
  nominatim.py            # テキスト検索・逆ジオコーディング
  landmark_filter.py      # 距離フィルタ・POI分類
  prompt_builder.py       # Groq プロンプト組み立て
assets/
  navi_background_1600x900.jpg  # 背景画像（base64でCSS埋め込み）
.streamlit/
  secrets.toml            # APIキー（gitignore済み）
  config.toml             # テーマ設定（primaryColor=#2d6a4f, bg=#fdf6e3）
requirements.txt
CLAUDE.md
```

---

## キャラクター設定（犬のおまわりさん）

- 語尾に「〜ワン」をつける
- お店・建物名はうろ覚えで、ぼんやりした表現のみ（正式名称は使わない）
- ランドマーク情報は「〇〇っぽいとこの角」「〇〇みたいなとこの横」のように使う
- 交差点名はそのまま使ってよい（「〇〇交差点あたりで左に曲がるワン」）
- 距離感は「ちょっと」「けっこう」「すぐそこ」など感覚的に
- 一生懸命・おせっかい・寄り添い型のキャラクター

---

## セリフ構成（2種類）

### ① 道案内セリフ（ラベル：「🗣️ 道案内するワン」）
ORS の曲がり角情報 ＋ Overpass のランドマーク情報をもとに Groq が生成

### ② おせっかいセリフ（ラベル：「🐾 おせっかいするワン」）
天気・気温・風・花粉・距離をもとに Groq が別途生成

※ 2つの Groq 呼び出しは ThreadPoolExecutor で並行実行

---

## 画面構成（実装済み）

### ページ1：スタート・ゴール入力

- **タグラインパネル**：3行の小テキスト（0.75rem）+ 「🐾 犬のおまわりさんが、道案内するワン！」
- **スタート地点**：
  - 「📡 今いる場所をスタートにする」GPS ボタン（streamlit-js-eval）
  - テキスト検索フォーム → Nominatim 検索 → 候補 selectbox（placeholder：`-- 選択するワン`）
  - 地図クリックでもピン設定可
- **ゴール地点**：
  - テキスト検索フォーム → Nominatim 検索 → 候補 selectbox（placeholder：`-- 選択するワン`）
  - 地図クリックでもピン設定可
- **✕ボタン**：各地点を個別クリア
- **「🔀 入れ替え」ボタン**：両方確定時のみ活性
- **「🔍 ルートを検索する」ボタン**（primary）：両方確定時のみ活性 → ORS完了後にページ2へ
- ORS エラー時はページ1にエラー表示して遷移しない
- **「🔄 最初からやり直す」ボタン**
- 地図：`zoom_start=13`（固定）・`returned_objects=["last_clicked"]`

### ページ2：ルート確認・道案内

- スタート・ゴール地点名パネル表示
- ルート情報バー（徒歩○分 ／ 約○m）
- ルート付き地図（fit_bounds で自動ズーム、初回のみ）
- Overpass・天気取得中はスピナー ＋「ちょっと待つワン。今説明の順番を考えてるワン…」
- 取得完了後に「案内してもらうワン🐾」ボタンが出現（primary）
- セリフ表示：道案内 → おせっかい の順
- **「🐾 もう一回道案内するワン」**：セリフリセット → ページ1に戻る
- **「🗺️ Google Map先生に引き継ぐワン」**：link_button で Google Maps（徒歩）を開く
- **「🔄 最初からやり直す」ボタン**

---

## API 呼び出しタイミング

| タイミング | 処理 |
|-----------|------|
| 「ルートを検索する」押下 | ORS 実行 → 完了後ページ2へ遷移 |
| ページ2 初回表示 | ThreadPoolExecutor で Overpass・天気を並行取得（blocking spinner） |
| 「案内してもらうワン🐾」押下 | Groq（道案内＋おせっかい）を ThreadPoolExecutor で並行呼び出し |

---

## Streamlit 実装上の重要メモ

- ボタン押下のたびにスクリプト全体が再実行される
- ORS・Overpass・天気の取得結果は `session_state` にキャッシュして再呼び出しを防ぐ
- 画面遷移は `ss.page`（1 or 2）で管理
- **地図ズーム**：`zoom_start` を固定値にしないと毎 rerun でリセットされる。ページ1は `13`、ページ2は `14` で固定
- **fit_bounds のone-shot制御**：
  - ページ1：`ss.fitted_bounds`（ピン組のタプル）が変わった最初の1回のみ適用
  - ページ2：`ss.p2_map_fitted` フラグで初回のみ適用
- **クリック二重処理防止**：`ss.last_click` に処理済み座標を保存し、同一クリックを無視
- **GPS**：`ss.gps_requested` フラグで「ボタン押下 → get_geolocation() 待機 → 取得完了 → rerun」の流れを管理
- **施設クエリ判定**：「駅」「病院」等の種別ワードを含む検索は、結果1件でも候補リストを強制表示（`_is_facility_query()`）
- **selectbox 初期値**：`index=None, placeholder="-- 選択するワン"` で未選択状態をデフォルトに

---

## CSS・デザイン

- **フォント**：Zen Maru Gothic / M PLUS Rounded 1c（Google Fonts）
- **テーマ色**：緑系（primaryColor `#2d6a4f`）、クリーム系背景（`#fdf6e3`）
- **背景画像**：`assets/navi_background_1600x900.jpg` を base64 で CSS に埋め込み（`.stApp` background）
- **コンテンツ背景**：`rgba(253,246,227,0.90)` の半透明オーバーレイ
- **ボタン色**（非hover）：`#fff8e1`（おせっかいボックスと同色）、ボーダー `#f9a825`
- **ボタン色**（hover）：緑 `#2d6a4f`
- **プライマリボタン**：緑 `#2d6a4f`（Streamlit primaryColor に従う）
- **iOS タッチ対応**：`-webkit-tap-highlight-color: rgba(0,0,0,0)`、selectbox に `touch-action: manipulation`、地図 iframe に `pointer-events: all`

---

## Overpass API フォールバック順

1. overpass-api.de（メイン）
2. overpass.kumi.systems（バックアップ）
3. maps.mail.ru（バックアップ）

各サーバー10秒タイムアウト。全滅時はランドマークなしで続行。

---

## ランドマーク取得仕様

### 取得対象 POI
- コンビニ・スーパー（道沿い最優先）
- ファストフード（マクドナルド・吉野家等）
- ドラッグストア（マツキヨ・ウエルシア等）
- 携帯ショップ・100円ショップ
- 銀行
- 駅・バス停
- 学校・大きな病院・郵便局・警察署（大型施設）
- 公園・広場

### 距離フィルタ
- 小型店舗（コンビニ・ファストフード等）：曲がり角から **15m以内**
- 大型施設（駅・病院・学校・公園・警察署・郵便局）：**35m以内**
- 大型施設を優先してソート（距離が遠くても先に出す）
- 曲がり角1箇所につき最大 **2件**

---

## Groq プロンプト方針

### 道案内セリフ
- キャラクター設定：語尾〜ワン・距離感覚的・4〜5文
- ランドマークは「〇〇っぽいとこの角・横・確認ポイント」として使う
- 交差点名はそのまま使ってよい
- **右折・左折は ORS instruction テキストから判定**（`_turn_label()` 関数で "左"/"右" を検出。type 番号は使わない）
- 「重要」ステップは必須、「省略可」はスキップしてよい
- 「どん突き当たり」表現を使う（前セグメント100m以上かつ左右折）

### おせっかいセリフ
- 天気・気温・風・花粉リスク・距離感を渡す
- 2〜3文で出発前のアドバイス
- 押しつけがましくなく、やさしくおせっかいな感じで

### Groq へ渡す曲がり角情報の例
```
1. 【重要】【どん突き当たり】【左折】左方向に進む（約80m） ／ 交差点名：和泉橋交差点 ／ 近く：コンビニ「ローソン〇〇店」
2. 【省略可】【右折】右方向に進む（約14m）
3. 【重要】【左折】左方向に進む（約200m） ／ 近く：駅「秋葉原駅」
```

---

## 今後実装予定の機能（優先度低）

- テンションモード（通常・丁寧・慌て気味）
- 季節イベント対応（夏の熱中症注意、冬の滑り注意 等）
- 「言い直してワン」ボタン（セリフ再生成、回数制限あり）
- GPS連携・今ここ表示・エール＆到着セリフ
- 方向転換の実効判定

---

## 注意事項

- `yuru_guide.html` はAPIキー直書きのため `.gitignore` 済み。参考用のみ。
- APIキーは `secrets.toml` で管理すること（GitHub には上げない）
- `secrets.toml` に必要なキー：`ORS_KEY`、`GROQ_API_KEY`、`OWM_KEY`
