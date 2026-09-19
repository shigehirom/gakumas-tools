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


def find_latest_season(season: int | None = None, source: str = "human") -> tuple[int, Path] | None:
    prefix = "auto_advisory_" if source == "ai" else "fried_aji3_advisory_"
    all_found_seasons = []
    for d in INSTRUCTIONS_DIRS:
        if not safe_exists(d):
            continue
        if season is not None:
            f = d / f"{prefix}{season}.md"
            if safe_exists(f):
                return season, f
        else:
            try:
                files = list(d.glob(f"{prefix}*.md"))
                for f in files:
                    m = re.search(rf"{prefix}(\d+)\.md", f.name)
                    if m:
                        all_found_seasons.append((int(m.group(1)), f))
            except Exception:
                continue

    if all_found_seasons:
        all_found_seasons.sort(key=lambda x: x[0], reverse=True)
        return all_found_seasons[0]
    return None


def normalize_card_name(name: str) -> str:
    if not name:
        return ""
    # 波ダッシュ (U+301C) と 全角チルダ (U+FF5E) の統一、全角半角記号・空白の正規化
    return (name.replace("\uff5e", "\u301c")
            .replace("!", "！")
            .replace("?", "？")
            .replace(" ", "")
            .replace("　", "")
            .strip()
            .lower())


def is_support_card_owned(card_name: str | None, owned_cards: set[str] | None) -> bool:
    """カード名（サポートカード名）が所持セットに含まれているか、表記揺れを吸収して判定する"""
    if not card_name or not owned_cards:
        return True
    if card_name in owned_cards:
        return True
    norm_target = normalize_card_name(card_name)
    for c in owned_cards:
        if normalize_card_name(c) == norm_target:
            return True
    return False


def get_owned_support_card_names(mongo_uri: str = "mongodb://192.168.100.4:27017") -> set[str]:
    """MongoDB (gakumas-tools.owned_support_cards) から所持サポートカード名を取得する"""
    try:
        from pymongo import MongoClient
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
        db = client["gakumas-tools"]
        docs = list(db["owned_support_cards"].find({}, {"card_name": 1}))
        owned = set()
        for d in docs:
            cname = d.get("card_name", "").strip()
            if cname:
                owned.add(cname)
        return owned
    except Exception as e:
        log.warning(f"Failed to fetch owned_support_cards from mongo: {e}")
        return set()


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


def get_stage_recommended_pidols(stage: int, season: int | None = None, source: str = "human") -> list[dict[str, Any]]:
    """指定ステージに記載されている全おすすめPアイドル一覧を取得する"""
    season_info = find_latest_season(season, source=source)
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
        eff = matched_entry.get("effect") or matched_entry.get("recommended_effect") or _get_idol_recommended_effect(target_name, target_title)
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


def parse_advisory_for_entry(stage: int, matched_entry: dict[str, Any], season: int | None = None, source: str = "human") -> dict[str, Any] | None:
    """単一のPアイドルエントリに対する推奨構成データをパースする"""
    season_info = find_latest_season(season, source=source)
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
    common_blocks = {}
    idol_items = []
    curr_common_eff = ""
    curr_target = None
    
    for line in pitem_lines:
        line_s = line.strip()
        if line_s.startswith("- common:"):
            curr_target = "common"
            m_eff = re.search(r"recommend:\s*([^\s]+)", line_s)
            curr_common_eff = m_eff.group(1).strip() if m_eff else ""
            if curr_common_eff not in common_blocks:
                common_blocks[curr_common_eff] = []
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
                    if curr_common_eff not in common_blocks:
                        common_blocks[curr_common_eff] = []
                    common_blocks[curr_common_eff].append(item_name)
                elif curr_target == "idol":
                    idol_items.append(item_name)

    target_eff = matched_entry.get("effect") or matched_entry.get("recommended_effect") or _get_idol_recommended_effect(matched_entry.get("idol_name", ""), matched_entry.get("title", ""))
    selected_common_items = []
    if target_eff and target_eff in common_blocks:
        selected_common_items = common_blocks[target_eff]
    elif "" in common_blocks:
        selected_common_items = common_blocks[""]
    elif common_blocks:
        selected_common_items = list(common_blocks.values())[0]

    pitems = idol_items if idol_items else selected_common_items
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


def parse_advisory(stage: int, idol_query: str | None = None, season: int | None = None, source: str = "human") -> dict[str, Any] | None:
    pidol_entries = get_stage_recommended_pidols(stage, season, source=source)
    if not pidol_entries:
        return None

    if not idol_query:
        return parse_advisory_for_entry(stage, pidol_entries[0], season, source=source)

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
                    return parse_advisory_for_entry(stage, e, season, source=source)
        # タイトルのみ一致
        for e in pidol_entries:
            if clean(e['title']) == clean_ext or clean_ext in clean(e['title']) or clean(e['title']) in clean_ext:
                return parse_advisory_for_entry(stage, e, season, source=source)

    # 2. クエリ内に e['title'] が含まれている（例: 'china 空と約束' -> '空と約束' in q）
    for e in pidol_entries:
        e_title_clean = clean(e['title'])
        if len(e_title_clean) >= 2 and e_title_clean in q_clean:
            return parse_advisory_for_entry(stage, e, season, source=source)

    # 3. 完全一致 / アイドル名一致
    for e in pidol_entries:
        e_key = clean(e['idol_key'])
        e_name = clean(e['idol_name'])
        e_title = clean(e['title'])
        if target_key == e_key or q_clean == e_name or q_clean == e_title:
            return parse_advisory_for_entry(stage, e, season, source=source)

    # 4. 双方向部分一致
    for e in pidol_entries:
        e_key = clean(e['idol_key'])
        e_name = clean(e['idol_name'])
        e_title = clean(e['title'])
        if q_clean in e_key or e_key in q_clean or q_clean in e_name or e_name in q_clean or q_clean in e_title or e_title in q_clean:
            return parse_advisory_for_entry(stage, e, season, source=source)

    # 5. フォールバック: マスターデータ (ImageResolver) から該当アイドルを探索して動的にエントリを生成
    try:
        from image_resolver import ImageResolver
        resolver = ImageResolver()
        for p in resolver.p_idols:
            p_name_clean = clean(p.get("idol_name", ""))
            p_title_clean = clean(p.get("title", ""))
            c_name = p.get("idol_name", "").replace(" ", "")
            p_key = IDOL_NAME_TO_KEY.get(c_name, "")

            if extracted_title and (clean(extracted_title) == p_title_clean or p_title_clean in clean(extracted_title) or clean(extracted_title) in p_title_clean):
                if target_key == p_key or p_name_clean in q_clean or q_clean in p_name_clean:
                    dyn_entry = {
                        "idol_key": p_key,
                        "idol_name": c_name,
                        "title": p.get("title", ""),
                        "extra": "with_asari" if (stage == 3 or "asari" in q_clean) else "",
                        "subs": []
                    }
                    return parse_advisory_for_entry(stage, dyn_entry, season, source=source)

        stage_plan = "sense" if stage == 1 else ("logic" if stage == 2 else "anomaly")
        try:
            reg = get_stage_regulation(cur_season, stage)
            stage_plan = reg.get("plan", stage_plan)
        except Exception:
            pass

        # 1. ステージプラン一致 かつ SSR
        for p in resolver.p_idols:
            p_name_clean = clean(p.get("idol_name", ""))
            c_name = p.get("idol_name", "").replace(" ", "")
            p_key = IDOL_NAME_TO_KEY.get(c_name, "")
            if target_key == p_key or q_clean == p_name_clean or (len(q_clean) >= 2 and (q_clean in p_name_clean or p_name_clean in q_clean)):
                if p.get("plan") == stage_plan and p.get("rarity") == "SSR":
                    dyn_entry = {
                        "idol_key": p_key,
                        "idol_name": c_name,
                        "title": p.get("title", ""),
                        "extra": "with_asari" if (stage == 3 or "asari" in q_clean) else "",
                        "subs": []
                    }
                    return parse_advisory_for_entry(stage, dyn_entry, season, source=source)

        # 2. 任意のSSR
        for p in resolver.p_idols:
            p_name_clean = clean(p.get("idol_name", ""))
            c_name = p.get("idol_name", "").replace(" ", "")
            p_key = IDOL_NAME_TO_KEY.get(c_name, "")
            if target_key == p_key or q_clean == p_name_clean or (len(q_clean) >= 2 and (q_clean in p_name_clean or p_name_clean in q_clean)):
                if p.get("rarity") == "SSR":
                    dyn_entry = {
                        "idol_key": p_key,
                        "idol_name": c_name,
                        "title": p.get("title", ""),
                        "extra": "with_asari" if (stage == 3 or "asari" in q_clean) else "",
                        "subs": []
                    }
                    return parse_advisory_for_entry(stage, dyn_entry, season, source=source)
    except Exception:
        pass

    return None


def get_stage_support_combinations(stage: int, season: int | None = None, owned_cards: set[str] | None = None, source: str = "human") -> dict[str, Any]:
    """
    指定ステージにおける必須サポートカード構成の組合せ（共通構成・特定アイドル専用構成・方針別構成）を解析して返す。
    """
    from image_resolver import ImageResolver
    resolver = ImageResolver()

    if owned_cards is None:
        owned_cards = get_owned_support_card_names()

    season_info = find_latest_season(season, source=source)
    if not season_info:
        return {"season": season or 52, "stage": stage, "combinations": [], "asari_idols": []}
    cur_season, adv_path = season_info
    text = adv_path.read_text(encoding="utf-8")

    stages = re.split(r"(?m)^#\s*Stage:\s*", text)
    stage_text = next((s for s in stages if s.strip() and s.splitlines()[0].strip().startswith(str(stage))), "")
    if not stage_text:
        return {"season": cur_season, "stage": stage, "combinations": [], "asari_idols": []}

    sections = re.split(r"(?m)^##\s+", stage_text)
    pidol_sec = next((s for s in sections if s.strip().startswith("p_idol:")), "")
    pitem_sec = next((s for s in sections if s.strip().startswith("p_item")), "")
    skill_sec = next((s for s in sections if s.strip().startswith("skill_card")), "")

    all_pidols = get_stage_recommended_pidols(stage, season, source=source)
    asari_idols = [f"{p['idol_name']}【{p['title']}】" for p in all_pidols if "with_asari" in p.get("extra", "")]

    # 1. p_item ブロックの抽出
    pitem_blocks: dict[str, list[dict[str, Any]]] = {}
    curr_pi_key = None
    for l in pitem_sec.splitlines():
        line = l.rstrip()
        if not line or line.startswith("p_item"):
            continue
        if line.strip().startswith("- common: recommend:"):
            curr_pi_key = line.strip().replace("- ", "").strip()
            pitem_blocks[curr_pi_key] = []
        elif line.strip().startswith("- common:"):
            curr_pi_key = "common"
            pitem_blocks[curr_pi_key] = []
        elif line.strip().startswith("- ") and "【" in line:
            curr_pi_key = line.strip().replace("- ", "").strip()
            pitem_blocks[curr_pi_key] = []
        elif line.startswith("\t- ") or line.startswith("    - ") or (line.strip().startswith("- ") and curr_pi_key):
            it = line.strip().replace("- ", "").strip()
            if it and not it.startswith("common") and "【" not in it:
                lbl = resolver.get_p_item_card_label(it)
                sc_name = resolver.get_p_item_support_card_name(it)
                is_owned = is_support_card_owned(sc_name, owned_cards)
                pitem_blocks[curr_pi_key].append({
                    "item_name": it,
                    "card_label": lbl,
                    "support_card_name": sc_name,
                    "is_owned": is_owned
                })

    # 2. skill_card AST の構築
    class Node:
        def __init__(self, indent: int, text: str):
            self.indent = indent
            self.text = text
            self.children: list['Node'] = []
        def add_child(self, c: 'Node'):
            self.children.append(c)

    root = Node(-1, "root")
    stack = [root]
    for raw_line in skill_sec.splitlines():
        if not raw_line.strip() or raw_line.strip().startswith("##"):
            continue
        expanded = raw_line.replace("\t", "    ")
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

    skill_common_blocks: dict[str, dict[str, Any]] = {}
    skill_idol_blocks: dict[str, list[dict[str, Any]]] = {}

    for top in root.children:
        t_text = top.text
        if t_text.startswith("common: recommend:") or t_text.startswith("common:") or t_text == "common":
            s_key = "common" if t_text in ("common", "common:") else t_text
            base_cards = []
            replacements: dict[str, list[dict[str, Any]]] = {}
            for cnode in top.children:
                c_name = cnode.text.split(":")[0].strip()
                lbl = resolver.get_skill_card_support_label(c_name)
                sc_name = resolver.get_skill_card_support_card_name(c_name)
                is_owned = is_support_card_owned(sc_name, owned_cards)
                if lbl:
                    base_cards.append({
                        "card_name": c_name,
                        "card_label": lbl,
                        "support_card_name": sc_name,
                        "is_owned": is_owned
                    })
                for sub in cnode.children:
                    if "【" in sub.text:
                        idol_key = sub.text.strip()
                        if idol_key not in replacements:
                            replacements[idol_key] = []
                        for rnode in sub.children:
                            r_name = rnode.text.split(":")[0].strip()
                            r_lbl = resolver.get_skill_card_support_label(r_name)
                            r_sc_name = resolver.get_skill_card_support_card_name(r_name)
                            r_is_owned = is_support_card_owned(r_sc_name, owned_cards)
                            if r_lbl:
                                replacements[idol_key].append({
                                    "card_name": r_name,
                                    "card_label": r_lbl,
                                    "support_card_name": r_sc_name,
                                    "is_owned": r_is_owned,
                                    "replaces": c_name
                                })
            skill_common_blocks[s_key] = {"base_cards": base_cards, "replacements": replacements}
        elif "【" in t_text:
            cards = []
            for cnode in top.children:
                c_name = cnode.text.split(":")[0].strip()
                lbl = resolver.get_skill_card_support_label(c_name)
                sc_name = resolver.get_skill_card_support_card_name(c_name)
                is_owned = is_support_card_owned(sc_name, owned_cards)
                if lbl:
                    cards.append({
                        "card_name": c_name,
                        "card_label": lbl,
                        "support_card_name": sc_name,
                        "is_owned": is_owned
                    })
            skill_idol_blocks[t_text] = cards

    def get_idol_display(k: str) -> str:
        m = re.match(r"^([a-zA-Z0-9_]+):\s*(【[^】]+】)", k)
        if m:
            idol_key = m.group(1)
            title = m.group(2)
            name = IDOL_KEY_MAP.get(idol_key, idol_key)
            return f"{name}{title}"
        return k

    has_policies = any("recommend:" in k for k in pitem_blocks.keys()) or any("recommend:" in k for k in skill_common_blocks.keys())

    raw_combinations = []
    if not has_policies:
        com_pi = pitem_blocks.get("common", [])
        com_sc = skill_common_blocks.get("common", {}).get("base_cards", [])
        raw_combinations.append({
            "name": "共通（common）構成",
            "p_items": com_pi,
            "skill_cards": com_sc,
            "is_common": True,
            "special_idol": None
        })

        for k, items in pitem_blocks.items():
            if k == "common":
                continue
            sc = skill_idol_blocks.get(k, com_sc)
            raw_combinations.append({
                "name": f"{get_idol_display(k)} 専用構成",
                "p_items": items,
                "skill_cards": sc,
                "is_common": False,
                "special_idol": k
            })

        for k, cards in skill_idol_blocks.items():
            if any(c.get("special_idol") == k for c in raw_combinations):
                continue
            pi = pitem_blocks.get(k, com_pi)
            raw_combinations.append({
                "name": f"{get_idol_display(k)} 専用構成",
                "p_items": pi,
                "skill_cards": cards,
                "is_common": False,
                "special_idol": k
            })

        com_repls = skill_common_blocks.get("common", {}).get("replacements", {})
        for k, repl_cards in com_repls.items():
            if any(c.get("special_idol") == k for c in raw_combinations):
                continue
            replaces_names = {rc.get("replaces") for rc in repl_cards}
            final_sc = [c for c in com_sc if c["card_name"] not in replaces_names] + repl_cards
            pi = pitem_blocks.get(k, com_pi)
            raw_combinations.append({
                "name": f"{get_idol_display(k)} 専用構成",
                "p_items": pi,
                "skill_cards": final_sc,
                "is_common": False,
                "special_idol": k
            })
    else:
        policies = []
        for k in list(pitem_blocks.keys()) + list(skill_common_blocks.keys()):
            if "recommend:" in k:
                p_name = k.split("recommend:", 1)[1].strip()
                if p_name not in policies:
                    policies.append(p_name)

        for pol in policies:
            pol_key = f"common: recommend: {pol}"
            pol_pi = pitem_blocks.get(pol_key, [])
            pol_sc_info = skill_common_blocks.get(pol_key, {"base_cards": [], "replacements": {}})
            pol_sc = pol_sc_info["base_cards"]

            raw_combinations.append({
                "name": f"共通・{pol}型構成",
                "p_items": pol_pi,
                "skill_cards": pol_sc,
                "is_common": True,
                "policy": pol,
                "special_idol": None
            })

            for k, repl_cards in pol_sc_info.get("replacements", {}).items():
                replaces_names = {rc.get("replaces") for rc in repl_cards}
                final_sc = [c for c in pol_sc if c["card_name"] not in replaces_names] + repl_cards
                pi = pitem_blocks.get(k, pol_pi)
                raw_combinations.append({
                    "name": f"{get_idol_display(k)}（{pol}型）構成",
                    "p_items": pi,
                    "skill_cards": final_sc,
                    "is_common": False,
                    "policy": pol,
                    "special_idol": k
                })

        for k, items in pitem_blocks.items():
            if k.startswith("common"):
                continue
            if any(c.get("special_idol") == k for c in raw_combinations):
                continue
            sc = skill_idol_blocks.get(k, [])
            if not sc:
                sc = skill_common_blocks.get("common: recommend: 好印象", {}).get("base_cards", [])
            raw_combinations.append({
                "name": f"{get_idol_display(k)} 専用構成",
                "p_items": items,
                "skill_cards": sc,
                "is_common": False,
                "special_idol": k
            })

        for k, cards in skill_idol_blocks.items():
            if any(c.get("special_idol") == k for c in raw_combinations):
                continue
            pi = pitem_blocks.get(k, [])
            if not pi:
                pi = pitem_blocks.get("common: recommend: やる気", [])
            raw_combinations.append({
                "name": f"{get_idol_display(k)} 専用構成",
                "p_items": pi,
                "skill_cards": cards,
                "is_common": False,
                "special_idol": k
            })

    # 重複排除: 共通構成と全く同じサポカセットを持つ個別エントリは除外
    final_combinations = []
    common_card_sets = {}
    for comb in raw_combinations:
        pi_cards = tuple(sorted(it["card_label"] for it in comb["p_items"] if it.get("card_label") and it["card_label"] != "推奨Pアイテム"))
        sc_cards = tuple(sorted(sc["card_label"] for sc in comb["skill_cards"] if sc.get("card_label")))
        sig = (pi_cards, sc_cards)

        if comb["is_common"]:
            common_card_sets[comb.get("policy", "all")] = sig
            comb["signature"] = sig
            final_combinations.append(comb)
        else:
            if sig in common_card_sets.values():
                continue
            comb["signature"] = sig
            final_combinations.append(comb)

    for idx, comb in enumerate(final_combinations, 1):
        labels = set(comb["signature"][0] + comb["signature"][1])
        comb["total_required"] = len(labels)
        comb["index"] = idx
        # clean signature for serialization
        comb.pop("signature", None)

    return {
        "season": cur_season,
        "stage": stage,
        "combinations": final_combinations,
        "asari_idols": asari_idols
    }


def get_stage_configurations(stage: int, season: int | None = None, owned_cards: set[str] | None = None, source: str = "human") -> list[dict[str, Any]]:
    """
    ステージ内の「汎用 (common)」および「個別定義されたアイドル (それ以外)」の構成リストを取得する。
    """
    if owned_cards is None:
        owned_cards = get_owned_support_card_names()

    season_info = find_latest_season(season, source=source)
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
    pitem_sec = ""
    skill_sec = ""
    for sec in sections:
        sec_clean = sec.strip()
        if sec_clean.startswith("p_item:"):
            pitem_sec = sec_clean
        elif sec_clean.startswith("skill_card:"):
            skill_sec = sec_clean

    # 1. 個別指定されたアイドル (それ以外) の抽出を先に行う
    # p_item や skill_card のトップレベルで - <idol>: 【<title>】 と定義されているものを抽出
    specific_pairs = []
    for sec in [pitem_sec, skill_sec]:
        for line in sec.splitlines():
            if not line.startswith("- "):
                continue
            line_s = line.strip()
            if line_s.startswith("- common:"):
                continue
            if "【" in line_s:
                m = re.match(r"^-\s*([a-zA-Z0-9_]+):\s*(【[^】]+】)(.*)", line_s)
                if m:
                    k = m.group(1)
                    t = m.group(2).strip("【】")
                    if (k, t) not in specific_pairs:
                        specific_pairs.append((k, t))

    # ステージ推奨Pアイドル全リストから、個別指定のないアイドルを汎用対象とする
    all_pidols = get_stage_recommended_pidols(stage, season, source=source)
    specific_keys_titles = set(specific_pairs)
    target_common_pidols = [
        p for p in all_pidols
        if (p.get("idol_key"), p.get("title")) not in specific_keys_titles
    ]
    target_idol_names = [f"{p['idol_name']}【{p['title']}】" for p in target_common_pidols]
    target_idol_short = [p['idol_name'] for p in target_common_pidols]

    # 2. 汎用 (common) の抽出（Stage 2 などで やる気 / 好印象 が分かれているか確認）
    common_effects = []
    for sec in [pitem_sec, skill_sec]:
        for line in sec.splitlines():
            line_s = line.strip()
            if line_s.startswith("- common:"):
                m_eff = re.search(r"recommend:\s*([^\s]+)", line_s)
                eff = m_eff.group(1).strip() if m_eff else ""
                if eff and eff not in common_effects:
                    common_effects.append(eff)

    configs = []

    if common_effects:
        for eff in common_effects:
            entry = {
                "idol_key": "common",
                "idol_name": f"汎用 ({eff})",
                "title": f"{eff}型 ステージ共通推奨",
                "effect": eff,
                "is_common": True,
                "config_type": "common",
                "type_label": f"汎用 ({eff})",
                "target_idols": target_idol_names,
                "target_idols_short": target_idol_short
            }
            data = parse_advisory_for_entry(stage, entry, season, source=source)
            if data:
                data["owned_support_cards"] = list(owned_cards)
                configs.append({
                    "type": "common",
                    "label": f"汎用 ({eff})",
                    "entry": entry,
                    "data": data,
                    "target_idols": target_idol_names,
                    "target_idols_short": target_idol_short
                })
    else:
        entry = {
            "idol_key": "common",
            "idol_name": "汎用 (common)",
            "title": "ステージ共通推奨",
            "is_common": True,
            "config_type": "common",
            "type_label": "汎用 (common)",
            "target_idols": target_idol_names,
            "target_idols_short": target_idol_short
        }
        data = parse_advisory_for_entry(stage, entry, season, source=source)
        if data:
            data["owned_support_cards"] = list(owned_cards)
            configs.append({
                "type": "common",
                "label": "汎用 (common)",
                "entry": entry,
                "data": data,
                "target_idols": target_idol_names,
                "target_idols_short": target_idol_short
            })

    for k, t in specific_pairs:
        idol_name = IDOL_KEY_MAP.get(k, k)
        entry = {
            "idol_key": k,
            "idol_name": idol_name,
            "title": t,
            "is_common": False,
            "config_type": "specific",
            "type_label": f"{idol_name}【{t}】"
        }
        data = parse_advisory_for_entry(stage, entry, season, source=source)
        if data:
            data["owned_support_cards"] = list(owned_cards)
            configs.append({
                "type": "specific",
                "label": f"{idol_name}【{t}】",
                "entry": entry,
                "data": data
            })

    return configs


