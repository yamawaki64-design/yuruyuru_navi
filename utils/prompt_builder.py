"""Groq へ渡すプロンプトの組み立て"""


def _turn_label(instruction: str) -> str:
    """ORS が生成した instruction テキストから方向ラベルを返す。
    ORS は言語設定（ja）に基づいて instruction を生成するため、
    型番号マッピングよりも信頼性が高い。"""
    if "左" in instruction:
        return "左折"
    if "右" in instruction:
        return "右折"
    return "直進"


def prioritize_steps(steps: list[dict]) -> list[dict]:
    """ステップに優先度・突き当たりタグを付与して返す

    - type 10（ゴール到着）/ 11（スタート）は除外済みを想定するが、念のためフィルタ
    - 優先度: 省略可（15m以下）/ 重要（前セグメント40m以上）/ 普通
    - 突き当たり: 前セグメント100m以上 かつ 左右折（instruction テキストで判定）
    """
    turn_steps = [s for s in steps if s.get("type") not in (10, 11)]
    result = []
    for i, s in enumerate(turn_steps):
        prev_dist = turn_steps[i - 1]["distance"] if i > 0 else 0
        instr = s.get("instruction", "")
        is_turn = "左" in instr or "右" in instr
        is_tsukiatari = prev_dist >= 100 and is_turn
        if s["distance"] <= 15:
            priority = "省略可"
        elif prev_dist >= 40:
            priority = "重要"
        else:
            priority = "普通"
        name = s.get("name", "")
        crossing = name if name and name not in ("-", "") else None
        result.append(
            {**s, "isTsukiatari": is_tsukiatari, "priority": priority, "crossingName": crossing}
        )
    return result


def _build_steps_text(steps_with_landmarks: list[dict]) -> str:
    """曲がり角リストをプロンプト用テキストに変換"""
    prioritized = prioritize_steps(steps_with_landmarks)
    if not prioritized:
        return ""
    lines = []
    for i, s in enumerate(prioritized):
        tsukiatari_tag = "【どん突き当たり】" if s["isTsukiatari"] else ""
        turn_label = _turn_label(s["instruction"])
        line = (
            f"{i + 1}. 【{s['priority']}】{tsukiatari_tag}"
            f"【{turn_label}】{s['instruction']}（約{s['distance']}m）"
        )
        if s.get("crossingName"):
            line += f" ／ 交差点名：{s['crossingName']}"
        landmarks = s.get("landmarks", [])
        if landmarks:
            lm_str = "、".join(f"{l['type']}「{l['name']}」" for l in landmarks)
            line += f" ／ 近く：{lm_str}"
        lines.append(line)
    return "\n\n【実際の曲がり角情報（これをもとに案内して）】\n" + "\n".join(lines)


def build_guide_prompt(
    start_name: str, goal_name: str, steps_with_landmarks: list[dict]
) -> str:
    """道案内セリフ用 Groq プロンプト"""
    steps_text = _build_steps_text(steps_with_landmarks)
    return f"""あなたは「犬のおまわりさん」というキャラクターです。一生懸命でおせっかい、でもゆるくて優しい犬のおまわりさんです。
スタート地点「{start_name}」からゴール地点「{goal_name}」への道案内をしてください。

【キャラクター設定】
・語尾は必ず「〜ワン」をつける（例：「右に曲がるワン」「もうすぐだワン！」）
・距離は「ちょっと」「けっこう」「すぐそこ」など感覚的に
・4〜5文のゆるいしゃべり言葉でまとめる

【ランドマーク情報の使い方】
曲がり角情報に「近く：〇〇」という情報がある場合、それをゆるく使って案内すること。
・曲がり角の目印として：「〇〇っぽいとこの角を右に曲がるワン」
・確認ポイントとして：「〇〇みたいなとこが見えたら行き過ぎたワン」
・横を通る描写として：「〇〇っぽいとこの横を通るワン」
ランドマーク情報がない曲がり角は「なんかそこらへん」でごまかしてOKワン。

【交差点名の使い方】
曲がり角情報に「交差点名：〇〇」という情報がある場合、ゆるく盛り込むこと。
・「〇〇っていう交差点を右に曲がるワン」「〇〇交差点あたりで左に曲がるワン」のように使う
・正式名称をそのまま言っていいが、「〜交差点」「〜の角」のように自然に言い換えてもOKワン

【優先度の扱い方】
・【重要】の曲がり角は必ず案内に含めること
・【普通】の曲がり角は自然に盛り込む
・【省略可】の曲がり角は省略してよい（細かすぎる動きなので）
・【どん突き当たり】がある場合は「どん突き当たりを〜ワン」と表現すること

【重要】曲がり角情報に【右折】【左折】と書いてある場合は、必ず「右に曲がるワン」「左に曲がるワン」と正確な方向で案内すること。
{steps_text}"""


def build_weather_context(weather_data: dict | None, route_summary: dict) -> str:
    """天気・距離情報をプロンプト用テキストに変換"""
    if not weather_data:
        return "（天気情報は取得できませんでした）"
    dist_m = route_summary.get("distanceM", 0)
    dur_min = route_summary.get("durationMin", 0)
    if dist_m < 300:
        dist_comment = "すぐそこ（300m以内）"
    elif dist_m < 800:
        dist_comment = "ちょっと歩く（800m以内）"
    elif dist_m < 1500:
        dist_comment = "けっこう歩く（1.5km以内）"
    else:
        dist_comment = "かなり遠い（1.5km超）"
    w = weather_data
    rain = "あり（傘が必要）" if w["weatherMain"] in ("Rain", "Drizzle") else "なし"
    pollen = "あり（春・気温高め）" if w["pollenRisk"] else "なし"
    return "\n".join([
        f"・季節：{w['season']}",
        f"・天気：{w['weatherDesc']}",
        f"・気温：{w['temp']}℃",
        f"・雨：{rain}",
        f"・風：{w['windComment']}（{w['windSpeed']}m/s）",
        f"・花粉リスク：{pollen}",
        f"・距離感：{dist_comment}（徒歩約{dur_min}分、約{dist_m}m）",
    ])


def build_osekkai_prompt(weather_data: dict | None, route_summary: dict) -> str:
    """おせっかいセリフ用 Groq プロンプト"""
    weather_context = build_weather_context(weather_data, route_summary)
    return f"""あなたは「犬のおまわりさん」というキャラクターです。一生懸命でおせっかい、でもゆるくて優しい犬のおまわりさんです。
以下の情報をもとに、出発前の「おせっかいアドバイス」を2〜3文でしてください。道案内は不要です。

【現地の状況】
{weather_context}

【おせっかいセリフのルール】
・語尾は必ず「〜ワン」をつける
・天気・気温・花粉・距離のうち気になるものをピックアップしてアドバイス
・「傘持ってくワン！」「マスクしたほうがいいワン」「けっこう歩くから水分補給してワン」など具体的に
・でも押しつけがましくなく、やさしくおせっかいな感じで
・2〜3文におさめる"""
