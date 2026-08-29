"""
advisory_parser.py — あじふらい氏アドバイスMarkdownおよびレギュレーション解析モジュール
"""

import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("advisory_parser")

def _find_dir(candidates: list[Path]) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]

WORKSPACE_DIR = _find_dir([
    Path("/app"),
    Path("/root/gakumas-workspace"),
    Path(__file__).resolve().parent.parent,
])

INSTRUCTIONS_DIRS = [
    WORKSPACE_DIR / "shared" / "agent-instructions",
    WORKSPACE_DIR / "gakumas-tools" / "agent-instructions",
    Path("/app/agent-instructions"),
]

IDOL_KEY_MAP = {
    "saki": "花海咲季",
    "temari": "月村手毬",
    "kotone": "藤田ことね",
    "tsubame": "雨夜燕",
    "mao": "有村麻央",
    "lilja": "葛城リーリヤ",
    "china": "倉本千奈",
    "sumika": "紫雲清夏",
    "hiro": "篠澤広",
    "sena": "十王星南",
    "misuzu": "秦谷美鈴",
    "ume": "花海佑芽",
    "rinami": "姫崎莉波",
}

IDOL_NAME_TO_KEY = {
    "花海咲季": "saki", "咲季": "saki", "さき": "saki", "saki": "saki",
    "月村手毬": "temari", "手毬": "temari", "てまり": "temari", "temari": "temari",
    "藤田ことね": "kotone", "ことね": "kotone", "kotone": "kotone",
    "雨夜燕": "tsubame", "燕": "tsubame", "つばめ": "tsubame", "tsubame": "tsubame",
    "有村麻央": "mao", "麻央": "mao", "まお": "mao", "mao": "mao",
    "葛城リーリヤ": "lilja", "リーリヤ": "lilja", "りーりや": "lilja", "lilja": "lilja",
    "倉本千奈": "china", "千奈": "china", "ちな": "china", "china": "china",
    "紫雲清夏": "sumika", "清夏": "sumika", "すみか": "sumika", "sumika": "sumika",
    "篠澤広": "hiro", "広": "hiro", "ひろ": "hiro", "hiro": "hiro",
    "十王星南": "sena", "星南": "sena", "せな": "sena", "sena": "sena",
    "秦谷美鈴": "misuzu", "美鈴": "misuzu", "みすず": "misuzu", "misuzu": "misuzu",
    "花海佑芽": "ume", "佑芽": "ume", "ゆめ": "ume", "ume": "ume",
    "姫崎莉波": "rinami", "莉波": "rinami", "りなみ": "rinami", "rinami": "rinami",
}


def find_latest_season(season: int | None = None) -> tuple[int, Path] | None:
    for d in INSTRUCTIONS_DIRS:
        if not d.exists():
            continue
        if season is not None:
            f = d / f"fried_aji3_advisory_{season}.md"
            if f.exists():
                return season, f
        else:
            files = list(d.glob("fried_aji3_advisory_*.md"))
            seasons = []
            for f in files:
                m = re.search(r"fried_aji3_advisory_(\d+)\.md", f.name)
                if m:
                    seasons.append((int(m.group(1)), f))
            if seasons:
                seasons.sort(key=lambda x: x[0], reverse=True)
                return seasons[0]
    return None


def get_stage_regulation(season: int, stage_num: int) -> dict[str, Any]:
    default_info = {
        "criteria": "Vo 45 / Da 35 / Vi 20",
        "plan": "sense" if stage_num == 1 else ("logic" if stage_num == 2 else "anomaly"),
        "plan_jp": "センス" if stage_num == 1 else ("ロジック" if stage_num == 2 else "アノマリー"),
        "turns": 12,
    }
    
    for d in INSTRUCTIONS_DIRS:
        if not d.exists():
            continue
        reg_file = d / f"regulation_{season}.md"
        if reg_file.exists():
            try:
                text = reg_file.read_text(encoding="utf-8")
                stages = re.split(r"(?m)^#\s*Stage:\s*", text)
                for s in stages:
                    lines = s.strip().splitlines()
                    if lines and lines[0].strip().startswith(str(stage_num)):
                        for line in lines:
                            if "criteria:" in line:
                                default_info["criteria"] = line.split("criteria:", 1)[1].strip()
                            elif "plan:" in line:
                                p = line.split("plan:", 1)[1].strip().lower()
                                default_info["plan"] = p
                                default_info["plan_jp"] = "センス" if p == "sense" else ("ロジック" if p == "logic" else "アノマリー")
                            elif "turn:" in line:
                                try:
                                    default_info["turns"] = int(re.search(r"\d+", line).group(0))
                                except Exception:
                                    pass
                        return default_info
            except Exception as e:
                log.warning(f"Error parsing regulation_{season}.md: {e}")
                
    return default_info


def get_stage_recommended_pidols(stage: int, season: int | None = None) -> list[dict[str, Any]]:
    """指定ステージに記載されている全おすすめPアイドル一覧を取得する"""
    season_info = find_latest_season(season)
    if not season_info:
        return []
    cur_season, adv_path = season_info
    text = adv_path.read_text(encoding="utf-8")

    stages = re.split(r"(?m)^#\s*Stage:\s*", text)
    stage_text = None
    for s in stages:
        if not s.strip():
            continue
        lines = s.splitlines()
        if lines[0].strip().startswith(str(stage)):
            stage_text = s
            break
    if not stage_text:
        return []

    sections = re.split(r"(?m)^##\s+", stage_text)
    pidol_sec = ""
    for sec in sections:
        if sec.strip().startswith("p_idol:"):
            pidol_sec = sec.strip()
            break

    pidol_entries = []
    current_entry = None
    for line in pidol_sec.splitlines():
        line_str = line.strip()
        if line_str.startswith("- ") and not line_str.startswith("- sub:"):
            m = re.match(r"^-\s*([a-zA-Z0-9_]+):\s*(【[^】]+】)(.*)", line_str)
            if m:
                k = m.group(1)
                current_entry = {
                    "idol_key": k,
                    "idol_name": IDOL_KEY_MAP.get(k, k),
                    "title": m.group(2).strip("【】"),
                    "extra": m.group(3).strip(),
                    "subs": []
                }
                pidol_entries.append(current_entry)
        elif line_str.startswith("- sub:") and current_entry:
            m_sub = re.match(r"^-\s*sub:\s*(【[^】]+】)(.*)", line_str)
            if m_sub:
                current_entry["subs"].append({
                    "title": m_sub.group(1).strip("【】"),
                    "extra": m_sub.group(2).strip()
                })

    return pidol_entries


def parse_advisory_for_entry(stage: int, matched_entry: dict[str, Any], season: int | None = None) -> dict[str, Any] | None:
    """単一のPアイドルエントリに対する推奨構成データをパースする"""
    season_info = find_latest_season(season)
    if not season_info:
        return None
    cur_season, adv_path = season_info
    reg_info = get_stage_regulation(cur_season, stage)
    text = adv_path.read_text(encoding="utf-8")

    stages = re.split(r"(?m)^#\s*Stage:\s*", text)
    stage_text = None
    for s in stages:
        if not s.strip():
            continue
        lines = s.splitlines()
        if lines[0].strip().startswith(str(stage)):
            stage_text = s
            break
    if not stage_text:
        return None

    sections = re.split(r"(?m)^##\s+", stage_text)
    pitem_sec = ""
    skill_sec = ""
    for sec in sections:
        sec_clean = sec.strip()
        if sec_clean.startswith("p_item:"):
            pitem_sec = sec_clean
        elif sec_clean.startswith("skill_card:"):
            skill_sec = sec_clean

    # Pアイテムパース
    pitem_lines = pitem_sec.splitlines()
    common_items = []
    idol_items = []
    curr_target = None
    
    for line in pitem_lines:
        line_s = line.strip()
        if line_s.startswith("- common:"):
            curr_target = "common"
        elif line_s.startswith("- ") and "【" in line_s:
            if matched_entry["idol_key"] in line_s and matched_entry["title"] in line_s:
                curr_target = "idol"
            else:
                curr_target = "other"
        elif line_s.startswith("- ") and curr_target in ("common", "idol"):
            item_name = line_s[2:].strip()
            if item_name and not item_name.startswith("common:") and "【" not in item_name:
                if curr_target == "common":
                    common_items.append(item_name)
                elif curr_target == "idol":
                    idol_items.append(item_name)

    pitems = idol_items if idol_items else common_items
    pitems = pitems[:2]

    # スキルカードパース
    common_cards = []
    curr_c = None
    curr_sec_name = None
    idol_cards_raw = []
    
    for line in skill_sec.splitlines():
        line_s = line.strip()
        if line_s.startswith("- common:"):
            curr_sec_name = "common"
            continue
        elif line_s.startswith("- ") and "【" in line_s:
            if matched_entry["idol_key"] in line_s and matched_entry["title"] in line_s:
                curr_sec_name = "idol"
            else:
                curr_sec_name = "other"
            continue

        if curr_sec_name == "common":
            if line_s.startswith("- customize:") and curr_c:
                cust_val = line_s.split(":", 1)[1].strip()
                curr_c["customizations"].append(cust_val)
            elif line_s.startswith("- ") and not line_s.startswith("- customize:"):
                card_name = line_s[2:].strip()
                if card_name:
                    curr_c = {"name": card_name, "customizations": []}
                    common_cards.append(curr_c)
        elif curr_sec_name == "idol":
            if line_s.startswith("- customize:") and idol_cards_raw:
                cust_val = line_s.split(":", 1)[1].strip()
                if isinstance(idol_cards_raw[-1], dict):
                    idol_cards_raw[-1]["customizations"].append(cust_val)
                elif isinstance(idol_cards_raw[-1], tuple):
                    idol_cards_raw[-1][1]["customizations"].append(cust_val)
            elif line_s.startswith("- /"):
                m_rep = re.match(r"^-\s*/([^/]+)/([^/]+)/", line_s)
                if m_rep:
                    target_c = m_rep.group(1).strip()
                    new_c = m_rep.group(2).strip()
                    new_card_obj = {"name": new_c, "customizations": []}
                    idol_cards_raw.append((target_c, new_card_obj))
            elif line_s.startswith("- ") and not line_s.startswith("- customize:"):
                c_name = line_s[2:].strip()
                if c_name:
                    idol_cards_raw.append({"name": c_name, "customizations": []})

    # スキルカードの合成・置換
    final_cards = []
    if idol_cards_raw and all(isinstance(c, dict) for c in idol_cards_raw):
        final_cards = idol_cards_raw
    else:
        for c in common_cards:
            replaced = False
            for raw in idol_cards_raw:
                if isinstance(raw, tuple):
                    orig, repl = raw
                    if c["name"] == orig:
                        final_cards.append(repl)
                        replaced = True
                        break
            if not replaced:
                final_cards.append(c)

    return {
        "season": cur_season,
        "stage": stage,
        "regulation": reg_info,
        "p_idol": matched_entry,
        "p_items": pitems,
        "skill_cards": final_cards[:10]
    }


def parse_advisory(stage: int, idol_query: str | None = None, season: int | None = None) -> dict[str, Any] | None:
    pidol_entries = get_stage_recommended_pidols(stage, season)
    if not pidol_entries:
        return None

    if not idol_query:
        return parse_advisory_for_entry(stage, pidol_entries[0], season)

    raw_q = idol_query.strip()
    m_title = re.search(r'【([^】]+)】', raw_q)
    extracted_title = m_title.group(1).strip() if m_title else None

    def clean(s: str) -> str:
        return re.sub(r'[\s\(\)\[\]【】_]+', '', s).lower()

    q_clean = clean(raw_q)
    target_key = IDOL_NAME_TO_KEY.get(q_clean, q_clean)

    # 1. 【タイトル】が明示されている場合
    if extracted_title:
        clean_ext = clean(extracted_title)
        # アイドル名もクエリに含まれるエントリを最優先
        for e in pidol_entries:
            if clean(e['title']) == clean_ext or clean_ext in clean(e['title']) or clean(e['title']) in clean_ext:
                if clean(e['idol_name']) in q_clean or clean(e['idol_key']) in q_clean:
                    return parse_advisory_for_entry(stage, e, season)
        # タイトルのみ一致
        for e in pidol_entries:
            if clean(e['title']) == clean_ext or clean_ext in clean(e['title']) or clean(e['title']) in clean_ext:
                return parse_advisory_for_entry(stage, e, season)

    # 2. クエリ内に e['title'] が含まれている（例: 'china 空と約束' -> '空と約束' in q）
    for e in pidol_entries:
        e_title_clean = clean(e['title'])
        if len(e_title_clean) >= 2 and e_title_clean in q_clean:
            return parse_advisory_for_entry(stage, e, season)

    # 3. 完全一致 / アイドル名一致
    for e in pidol_entries:
        e_key = clean(e['idol_key'])
        e_name = clean(e['idol_name'])
        e_title = clean(e['title'])
        if target_key == e_key or q_clean == e_name or q_clean == e_title:
            return parse_advisory_for_entry(stage, e, season)

    # 4. 双方向部分一致
    for e in pidol_entries:
        e_key = clean(e['idol_key'])
        e_name = clean(e['idol_name'])
        e_title = clean(e['title'])
        if q_clean in e_key or e_key in q_clean or q_clean in e_name or e_name in q_clean or q_clean in e_title or e_title in q_clean:
            return parse_advisory_for_entry(stage, e, season)

    return None

