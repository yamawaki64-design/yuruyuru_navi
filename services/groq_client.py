"""Groq API でセリフを生成する（道案内・おせっかいを並行実行）"""
import requests
import streamlit as st
from concurrent.futures import ThreadPoolExecutor

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.3-70b-versatile"


def _call_groq(prompt: str, max_tokens: int = 500) -> str | None:
    """Groq API を呼び出してセリフテキストを返す"""
    key = st.secrets.get("GROQ_KEY", "")
    try:
        res = requests.post(
            _GROQ_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            json={
                "model": _MODEL,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        data = res.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content")
    except Exception:
        return None


def generate_speeches(
    guide_prompt: str, osekkai_prompt: str
) -> tuple[str, str]:
    """道案内セリフとおせっかいセリフを並行生成して返す"""
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_guide = executor.submit(_call_groq, guide_prompt, 500)
        f_osekkai = executor.submit(_call_groq, osekkai_prompt, 200)
        guide = f_guide.result()
        osekkai = f_osekkai.result()

    guide = guide or "うまく生成できなかったワン...もう一回試してみてワン！"
    osekkai = osekkai or "（おせっかいセリフが出てこなかったワン）"
    return guide, osekkai
