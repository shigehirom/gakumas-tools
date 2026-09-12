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
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return candidates[0]

WORKSPACE_DIR = _find_dir([
    Path("/app"),
    Path("/root/gakumas-workspace"),
    Path(__file__).resolve().parent.parent,
])

INSTRUCTIONS_DIRS = [
    Path("/root/gakumas-workspace/shared/agent-instructions"),
    Path("/root/gakumas-workspace/gakumas-tools/agent-instructions"),
    Path("/app/agent-instructions"),
    Path("/app/shared/agent-instructions"),
    Path(__file__).resolve().parent.parent / "shared" / "agent-instructions",
    Path(__file__).resolve().parent.parent / "gakumas-tools" / "agent-instructions",
    Path(__file__).resolve().parent.parent / "agent-instructions",
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


def safe_exists(p: Path) -> bool:
    try:
        return p.exists()
    except Exception:
        return False


def find_latest_season(season: int | None = None) -> tuple[int, Path] | None:
    all_found_seasons = []
    for d in INSTRUCTIONS_DIRS:
        if not safe_exists(d):
            continue
        if season is not None:
            f = d / f"fried_aji3_advisory_{season}.md"
            if safe_exists(f):
                return season, f
        else:
            try:
                files = list(d.glob("fried_aji3_advisory_*.md"))
                for f in files:
                    m = re.search(r"fried_aji3_advisory_(\d+)\.md", f.name)
                    if m:
                        all_found_seasons.append((int(m.group(1)), f))
            except Exception:
                continue

    if all_found_seasons:
        all_found_seasons.sort(key=lambda x: x[0], reverse=True)
        return all_found_seasons[0]
    return None


def get_stage_regulation(season: int, stage_num: int) -> dict[str, Any]:
    default_info = {
        "criteria": "Vo 45 / Da 35 / Vi 20",
        "plan": "sense" if stage_num == 1 else ("logic" if stage_num == 2 else "anomaly"),
        "plan_jp": "センス" if stage_num == 1 else ("ロジック" if stage_num == 2 else "アノマリー"),
        "turns": 12,
    }
    
    for d in INSTRUCTIONS_DIRS:
        if not safe_exists(d):
            continue
        reg_file = d / f"regulation_{season}.md"
        if safe_exists(reg_file):
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


IDOL_NAME_TO_ID = {
    "花海咲季": 1, "saki": 1,
    "月村手毬": 2, "temari": 2,
    "藤田ことね": 3, "kotone": 3,
    "有村麻央": 4, "mao": 4,
    "葛城リーリヤ": 5, "lilja": 5,
    "倉本千奈": 6, "china": 6,
    "紫雲清夏": 7, "sumika": 7,
    "篠澤広": 8, "hiro": 8,
    "姫崎莉波": 9, "rinami": 9,
    "花海佑芽": 10, "ume": 10,
    "十王星南": 11, "sena": 11,
    "秦谷美鈴": 12, "misuzu": 12,
    "雨夜燕": 13, "tsubame": 13,
    "根緒亜紗里": 14, "asari": 14,
}

def _get_idol_recommended_effect(idol_name: str, title: str) -> str:
    """p_idols.json からアイドルの得意効果（やる気、好印象等）を取得する"""
    effect_map = {
        "motivation": "やる気",
        "goodImpressionTurns": "好印象",
        "goodConditionTurns": "好調",
        "concentration": "集中",
        "strength": "強気",
        "fullPower": "全力",
        "preservation": "温存"
    }
    target_clean = idol_name.replace(" ", "").strip()
    target_id = IDOL_NAME_TO_ID.get(target_clean)

    json_candidates = [
        WORKSPACE_DIR / "packages" / "gakumas-data" / "json" / "p_idols.json",
        WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-data" / "json" / "p_idols.json",
        Path("/app/packages/gakumas-data/json/p_idols.json"),
    ]
    for p in json_candidates:
        if safe_exists(p):
            try:
                import json
                data = json.loads(p.read_text(encoding="utf-8"))
                for item in data:
                    if item.get("title") == title:
                        if target_id is not None and item.get("idolId") != target_id:
                            continue
                        eff = item.get("recommendedEffect")
                        return effect_map.get(eff, "")
            except Exception:
                pass
    return ""


def _parse_skill_cards_section(skill_sec: str, matched_entry: dict[str, Any]) -> list[dict[str, Any]]:
    """skill_card セクションを階層的に解析し、対象アイドル向けのカードリスト（最大10枚）を生成する"""
    lines = skill_sec.splitlines()

    class Node:
        def __init__(self, indent: int, text: str):
            self.indent = indent
            self.text = text
            self.children: list['Node'] = []

        def add_child(self, child: 'Node'):
            self.children.append(child)

    root = Node(-1, "root")
    stack = [root]

    for raw_line in lines:
        if not raw_line.strip() or raw_line.strip().startswith("##"):
            continue
        expanded = raw_line.replace('\t', '    ')
        indent = len(expanded) - len(expanded.lstrip())
        content = raw_line.strip()
        if content.startswith("- "):
            content = content[2:].strip()
        elif content.startswith("-"):
            content = content[1:].strip()
        else:
            continue

        node = Node(indent, content)
        while len(stack) > 1 and stack[-1].indent >= indent:
            stack.pop()
        stack[-1].add_child(node)
        stack.append(node)

    common_card_nodes = []
    idol_card_nodes = []

    target_key = matched_entry.get("idol_key", "")
    target_title = matched_entry.get("title", "")
    target_name = matched_entry.get("idol_name", "")

    for top in root.children:
        t_text = top.text
        if t_text.startswith("common:") or t_text == "common":
            common_card_nodes.append(top)
        elif "【" in t_text:
            if (target_key and target_key in t_text) or (target_name and target_name in t_text):
                if target_title in t_text:
                    idol_card_nodes.append(top)

    # 1. アイドル専用セットが定義されている場合
    if idol_card_nodes:
        # S51 旧記法（- /元/先/）か、S52 直接カード一覧か判定
        is_legacy_diff = any(cnode.text.startswith("/") for cnode in idol_card_nodes[0].children)
        if not is_legacy_diff:
            res_cards = []
            for cnode in idol_card_nodes[0].children:
                card_obj = {"name": cnode.text, "customizations": []}
                for sub in cnode.children:
                    if sub.text.startswith("customize:"):
                        card_obj["customizations"].append(sub.text.split("customize:", 1)[1].strip())
                res_cards.append(card_obj)
            if res_cards:
                return res_cards

    # 2. common ブロック選択
    selected_common = None
    if len(common_card_nodes) == 1:
        selected_common = common_card_nodes[0]
    elif len(common_card_nodes) > 1:
        eff = _get_idol_recommended_effect(target_name, target_title)
        for c in common_card_nodes:
            if eff and eff in c.text:
                selected_common = c
                break
        if not selected_common:
            selected_common = common_card_nodes[0]

    if not selected_common:
        return []

    # 共通カード構築
    final_cards = []
    for cnode in selected_common.children:
        orig_card_name = cnode.text
        customizations = []
        replaced_card = None

        for sub in cnode.children:
            s_text = sub.text
            if s_text.startswith("customize:"):
                customizations.append(s_text.split("customize:", 1)[1].strip())
            elif "【" in s_text:
                if (target_key and target_key in s_text) or (target_name and target_name in s_text):
                    if target_title in s_text:
                        for rnode in sub.children:
                            r_name = rnode.text
                            r_custs = []
                            for rsub in rnode.children:
                                if rsub.text.startswith("customize:"):
                                    r_custs.append(rsub.text.split("customize:", 1)[1].strip())
                            replaced_card = {"name": r_name, "customizations": r_custs}

        if replaced_card:
            final_cards.append(replaced_card)
        else:
            final_cards.append({"name": orig_card_name, "customizations": customizations})

    # 旧形式 diff 置換のサポート（idol_card_nodes に - /元/先/ がある場合）
    if idol_card_nodes:
        diff_replacements = {}
        for cnode in idol_card_nodes[0].children:
            if cnode.text.startswith("/"):
                m = re.match(r"^/([^/]+)/([^/]+)/", cnode.text)
                if m:
                    orig_c = m.group(1).strip()
                    new_c = m.group(2).strip()
                    diff_replacements[orig_c] = new_c
        if diff_replacements:
            for idx, c in enumerate(final_cards):
                if c["name"] in diff_replacements:
                    final_cards[idx] = {"name": diff_replacements[c["name"]], "customizations": c.get("customizations", [])}

    return final_cards


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
            if (matched_entry.get("idol_key") and matched_entry["idol_key"] in line_s) or (matched_entry.get("idol_name") and matched_entry["idol_name"] in line_s):
                if matched_entry.get("title") and matched_entry["title"] in line_s:
                    curr_target = "idol"
                else:
                    curr_target = "other"
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
    final_cards = _parse_skill_cards_section(skill_sec, matched_entry)

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

