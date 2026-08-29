"""
contest_parser.py — コンテスト結果の3枚のスクリーンショットからGemini APIを用いて結果を構造化抽出するモジュール
"""
import asyncio
import os
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types

CONTEST_PROMPT = """
You are analyzing 3 sequential screenshots from the mobile game "Gakuen Idolmaster (学園アイドルマスター)" contest mode.

Image 1 (First image): Opponent selection screen before the match.
Image 2 (Second image): Match result screen showing 3 stages.
Image 3 (Third image): Final points and rewards screen after the match.

Please extract the following information accurately:

1. From Image 1:
   - Remaining match count text on top-right (e.g., "5/5", "4/5", "3/5", "2/5", "1/5").
   - 3 opponent candidate cards (Top = position 1, Middle = position 2, Bottom = position 3):
     - position (1, 2, or 3)
     - name (the player name string under the total power)
     - totalPower (the integer of 総合力合計, e.g. 208791)
     - expectedPt (the integer of +XXXPt on the card, e.g. 142)

2. From Image 2:
   - Stage 1: myScore (left side integer, ignore comma), enemyScore (right side integer, ignore comma), result ("WIN" or "LOSE")
   - Stage 2: myScore (left side integer, ignore comma), enemyScore (right side integer, ignore comma), result ("WIN" or "LOSE")
   - Stage 3: myScore (left side integer, ignore comma), enemyScore (right side integer, ignore comma), result ("WIN" or "LOSE")

3. From Image 3:
   - overallResult ("WIN" or "LOSE" at the top)
   - earnedPt (the integer in +XX next to Pt, e.g. 90)
   - coins (the integer in +XX next to the coin/medal icon, e.g. 10)
   - fans (the integer in +XXX next to ファン数, e.g. 989)
   - currentPt (the integer of total Pt, e.g. 4649)
   - currentRank (the integer next to the crown icon, e.g. 203)

Respond strictly with valid JSON matching this schema:
{
  "remainingAttemptsStr": "5/5",
  "candidates": [
    { "position": 1, "name": "...", "totalPower": 0, "expectedPt": 0 },
    { "position": 2, "name": "...", "totalPower": 0, "expectedPt": 0 },
    { "position": 3, "name": "...", "totalPower": 0, "expectedPt": 0 }
  ],
  "stage1": { "myScore": 0, "enemyScore": 0, "result": "WIN" },
  "stage2": { "myScore": 0, "enemyScore": 0, "result": "WIN" },
  "stage3": { "myScore": 0, "enemyScore": 0, "result": "WIN" },
  "overallResult": "WIN",
  "earnedPt": 0,
  "coins": 0,
  "fans": 0,
  "currentPt": 0,
  "currentRank": 0
}
"""

def _detect_mime_type(b: bytes) -> str:
    """バイト列から MIME タイプを判定する"""
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif b.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif b.startswith(b"RIFF") and b[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"

def _load_env_if_needed() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        workspace = Path("/root/gakumas-workspace")
        for env_path in [workspace / "gakumas-agent-bot" / ".env", workspace / ".env"]:
            if env_path.exists():
                with open(env_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v


async def _parse_with_antigravity(image_bytes_list: List[bytes], key: Optional[str] = None) -> Dict[str, Any]:
    from google.antigravity import Agent, LocalAgentConfig
    from google.antigravity.hooks import policy
    from google.antigravity import types as agy_types

    prompt_items: list[Any] = [CONTEST_PROMPT + "\n\n必ず上記指定のJSON形式のみを出力してください。"]
    for b in image_bytes_list:
        mime = _detect_mime_type(b)
        prompt_items.append(agy_types.Image(data=b, mime_type=mime))

    config = LocalAgentConfig(
        api_key=key if key else None,
        app_data_dir=str(Path.home() / ".gemini/antigravity-ide"),
        workspaces=["/root/gakumas-workspace"],
        model="gemini-3.6-flash",
        policies=[policy.allow_all()],
        capabilities=agy_types.CapabilitiesConfig(enabled_tools=[]),
    )

    agent = Agent(config)
    async with agent:
        resp = await agent.chat(prompt_items)
        raw_text = resp.text or "{}"
        clean_json = _clean_json_string(raw_text)
        return json.loads(clean_json)


def _clean_json_string(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def parse_contest_images(
    image_bytes_list: List[bytes],
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    3枚の画像バイト列からGemini APIで構造化データを抽出する
    """
    _load_env_if_needed()
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY が設定されていません。")

    data = None
    last_error = None

    # 1. google-genai SDK (gemini-3.6-flash) での直接解析
    try:
        client = genai.Client(api_key=key)
        contents = [CONTEST_PROMPT]
        for b in image_bytes_list:
            mime = _detect_mime_type(b)
            contents.append(types.Part.from_bytes(data=b, mime_type=mime))

        candidate_models = [
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
        ]
        for m_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=m_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                raw_text = response.text or "{}"
                data = json.loads(_clean_json_string(raw_text))
                break
            except Exception as e:
                last_error = e
                continue
    except Exception as e:
        last_error = e

    # 2. Antigravity SDK でのフォールバック解析
    if data is None:
        try:
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    data = pool.submit(lambda: asyncio.run(_parse_with_antigravity(image_bytes_list, key))).result()
            except RuntimeError:
                data = asyncio.run(_parse_with_antigravity(image_bytes_list, key))
        except Exception as e:
            last_error = e

    if data is None:
        raise RuntimeError(f"Gemini による画像解析に失敗しました: {last_error}")

    # 残り回数から matchIndex (1〜5) を算出
    # 5/5 -> 1回目, 4/5 -> 2回目, 3/5 -> 3回目, 2/5 -> 4回目, 1/5 -> 5回目
    rem_str = data.get("remainingAttemptsStr", "5/5")
    rem_matches = 5
    m = re.search(r"(\d+)/5", rem_str)
    if m:
        rem_matches = int(m.group(1))
    match_index = max(1, min(5, 6 - rem_matches))

    # 対戦相手の特定（Image 3 の earnedPt と Image 1 の expectedPt を突合）
    earned_pt = data.get("earnedPt", 0)
    candidates = data.get("candidates", [])
    opponent_name = "Unknown"
    opponent_grade = 1

    matched_cand = next((c for c in candidates if c.get("expectedPt") == earned_pt), None)
    if matched_cand:
        opponent_name = matched_cand.get("name", "Unknown")
        opponent_grade = matched_cand.get("position", 1)
    elif candidates:
        opponent_name = candidates[0].get("name", "Unknown")
        opponent_grade = candidates[0].get("position", 1)

    return {
        "remainingMatches": rem_matches,
        "matchIndex": match_index,
        "opponent": {
            "name": opponent_name,
            "grade": opponent_grade,
        },
        "overallResult": data.get("overallResult", "WIN"),
        "earnedPt": earned_pt,
        "stages": {
            "stage1": data.get("stage1", {"myScore": 0, "enemyScore": 0, "result": "WIN"}),
            "stage2": data.get("stage2", {"myScore": 0, "enemyScore": 0, "result": "WIN"}),
            "stage3": data.get("stage3", {"myScore": 0, "enemyScore": 0, "result": "WIN"}),
        },
        "extra": {
            "fans": data.get("fans", 0),
            "coins": data.get("coins", 0),
            "currentPt": data.get("currentPt", 0),
            "currentRank": data.get("currentRank", 0),
        }
    }
