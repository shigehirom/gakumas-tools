import json
import os
import glob
import re
import urllib.request
import urllib.parse

# Config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GAKUMAS_TOOLS_PATH = SCRIPT_DIR
SUPPORT_CARDS_PATH = os.path.abspath(os.path.join(SCRIPT_DIR, "../gakumas-support_cards/support_cards"))
OUTPUT_DIR = "/Users/shigehiro/Library/CloudStorage/GoogleDrive-shigehiro.miyashita@gmail.com/マイドライブ/Documents/学園アイドルマスター/notebookLM"

# Load .env.local
ENV_LOCAL_PATH = os.path.join(GAKUMAS_TOOLS_PATH, ".env.local")
ENV_VARS = {}
if os.path.exists(ENV_LOCAL_PATH):
    with open(ENV_LOCAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                ENV_VARS[k.strip()] = v.strip().strip('"\'')

GOOGLE_CLIENT_ID = ENV_VARS.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = ENV_VARS.get("GOOGLE_CLIENT_SECRET")
GOOGLE_DRIVE_FOLDER_ID = ENV_VARS.get("GOOGLE_DRIVE_RAG_FOLDER_ID") or ENV_VARS.get("GOOGLE_DRIVE_FOLDER_ID")

os.makedirs(OUTPUT_DIR, exist_ok=True)

def refresh_access_token(client_id, client_secret, refresh_token):
    url = "https://oauth2.googleapis.com/token"
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        return res_data.get("access_token")

def get_drive_access_token():
    token_path = os.path.expanduser("~/.config/gakumas-tools/tokens.json")
    if not os.path.exists(token_path):
        print(f"[Warning] Token file not found at {token_path}. Please authenticate via CLI.")
        return None
        
    with open(token_path, "r", encoding="utf-8") as f:
        tokens = json.load(f)
        
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    
    if refresh_token and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        try:
            new_access_token = refresh_access_token(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, refresh_token)
            if new_access_token:
                tokens["access_token"] = new_access_token
                with open(token_path, "w", encoding="utf-8") as f:
                    json.dump(tokens, f, indent=2)
                return new_access_token
        except Exception as e:
            print(f"[Warning] Failed to refresh token: {e}")
            
    return access_token

def upload_to_drive(filename, content):
    if not GOOGLE_DRIVE_FOLDER_ID:
        print("[Warning] GOOGLE_DRIVE_FOLDER_ID not set. Skipping Drive upload.")
        return
        
    access_token = get_drive_access_token()
    if not access_token:
        print("[Warning] Could not get Google Drive access token. Skipping Drive upload.")
        return

    # Search for existing file
    query = f"name = '{filename}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false"
    url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(query)}&fields=files(id)"
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            files = res.get("files", [])
    except Exception as e:
        print(f"Error searching file on Drive: {e}")
        return

    if files:
        file_id = files[0]["id"]
        # Update content (PATCH)
        upload_url = f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media"
        headers["Content-Type"] = "text/markdown; charset=utf-8"
        data = content.encode("utf-8")
        req = urllib.request.Request(upload_url, data=data, headers=headers, method="PATCH")
        print(f"Updating existing file on Google Drive: {filename} (ID: {file_id})")
    else:
        # Create new file (POST multipart)
        upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
        boundary = "foo_bar_baz"
        headers["Content-Type"] = f"multipart/related; boundary={boundary}"
        
        metadata = {
            "name": filename,
            "parents": [GOOGLE_DRIVE_FOLDER_ID]
        }
        
        body = []
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(b"Content-Type: application/json; charset=UTF-8")
        body.append(b"")
        body.append(json.dumps(metadata).encode("utf-8"))
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(b"Content-Type: text/markdown; charset=utf-8")
        body.append(b"")
        body.append(content.encode("utf-8"))
        body.append(f"--{boundary}--".encode("utf-8"))
        
        data = b"\r\n".join(body)
        req = urllib.request.Request(upload_url, data=data, headers=headers, method="POST")
        print(f"Creating new file on Google Drive: {filename}")

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Successfully uploaded {filename} to Google Drive (ID: {result.get('id')})")
    except Exception as e:
        print(f"Error uploading file to Drive: {e}")
        if hasattr(e, "read"):
            print(e.read().decode("utf-8"))

def save_doc(filename_base, content):
    md_path = os.path.join(OUTPUT_DIR, f"{filename_base}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Generated {md_path}")

    
    # Also upload to Google Drive
    upload_to_drive(f"{filename_base}.md", content)

# Helper: Load JSON
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

# Global Card Map for ID resolution
try:
    _cards = load_json(os.path.join(GAKUMAS_TOOLS_PATH, "packages/gakumas-data/json/skill_cards.json"))
    CARD_MAP = {str(c["id"]): c["name"] for c in _cards}
except Exception:
    CARD_MAP = {}

# Global P-Items Map
try:
    P_ITEMS_DATA = load_json(os.path.join(GAKUMAS_TOOLS_PATH, "packages/gakumas-data/json/p_items.json"))
    P_ITEMS_MAP = {c["name"]: c for c in P_ITEMS_DATA if not c.get("upgraded")}
except Exception:
    P_ITEMS_DATA = []
    P_ITEMS_MAP = {}

# Helper: Translate DSL terms to Japanese
DSL_DICT = {
    "goodConditionTurns": "好調",
    "concentration": "集中",
    "goodImpressionTurns": "好印象",
    "motivation": "やる気",
    "score": "スコア",
    "genki": "元気",
    "stamina": "体力",
    "cost": "消費体力",
    "fullPowerCharge": "全力ゲージ",
    "cumulativeFullPowerCharge": "累積全力ゲージ",
    "fullPower": "全力",
    "setEnthusiasmBuff": "好調（ターン数）バフ付与",
    "setEnthusiasmBonus": "好調（値）ボーナス付与",
    "prideTurns": "プライド（ターン数）",
    "leisure": "余裕",
    "strength2": "絶好調",
    "strength": "絶好調",
    "preservation2": "温存",
    "preservation": "温存",
    "perfectConditionTurns": "絶好調",
    "drawCard": "カードを引く",
    "cardUsesRemaining": "使用回数",
    "setStance(strength)": "絶好調状態になる",
    "consumedGenki": "消費した元気",
    "fixedStamina": "固定体力",
    "maxStamina": "最大体力",
    "cardsUsed": "使用したカード枚数",
    "isPreservation": "温存状態",
    "isStrength": "絶好調状態",
    "isFullPower": "全力状態",
    "at:startOfTurn": "ターン開始時",
    "at:endOfTurn": "ターン終了時",
    "at:turn": "毎ターン",
    "limit:": "制限回数:",
    "ttl:": "継続ターン:",
    "if:": "条件:",
    "target:": "対象:",
    "this": "このカード",
    "held": "手札",
    "sense": "センス",
    "logic": "ロジック",
    "anomaly": "アノマリー",
    "free": "フリー",
    "setStance": "スタンス変更",
    "effect": "効果",
    "active": "アクティブ",
    "mental": "メンタル",
    "hand": "手札",
    "deck": "山札",
    "discarded": "捨て札",
    "removed": "除外",
    "holdCard": "カードをキープ",
    "countCards": "カード枚数",
    "consumedStamina": "消費した体力",
    "turnCardsUsed": "ターン中使用カード枚数",
    "activeCardsUsed": "使用したアクティブカード枚数",
    "doubleCardEffectCards": "カード効果2倍（回数）",
    "nullifyCostActiveCards": "アクティブカード消費体力無効（回数）",
    "stanceChangedTimes": "スタンス変更回数",
    "setFullPowerChargeBuff": "全力ゲージ増加量バフ付与",
    "setScoreBuff": "スコア増加量バフ付与",
    "setScoreDebuff": "スコア減少量デバフ付与",
    "setConcentrationBuff": "集中増加量バフ付与",
    "setGoodConditionTurnsBuff": "好調ターン数増加量バフ付与",
    "setMotivationBuff": "やる気増加量バフ付与",
    "setGoodImpressionTurnsBuff": "好印象ターン数増加量バフ付与",
    "setGoodImpressionTurnsEffectBuff": "好印象効果バフ付与",
    "moveRandomToHand": "ランダムに手札へ移動",
    "moveRandomToTopOfDeck": "ランダムに山札の一番上へ移動",
    "moveCardToHandFromRemoved": "除外から手札へ移動",
    "addCardToTopOfDeck": "山札の一番上へ追加",
    "upgradeRandomCardInHand": "手札のランダムなカードを強化",
    "upgradeHand": "手札のカードをすべて強化",
    "nullifyGenkiTurns": "元気増加無効（ターン数）",
    "fixedGenki": "固定元気",
    "delay": "遅延",
    "halfCostTurns": "消費体力半減（ターン数）",
    "group": "グループ",
    "uneaseTurns": "不調",
    "nullifyDebuff": "デバフ無効",
    "addCardToHand": "手札に追加"
}

def translate_dsl(text):
    if not isinstance(text, str):
        return str(text)
    
    # 1. Replace exact DSL_DICT matches
    for k, v in DSL_DICT.items():
        text = text.replace(k, v)
        
    # 2. Regex replace numeric IDs with Names e.g. addCardToDeck(23) -> addCardToDeck(23: 眠気)
    # Match patterns like (ID) or [baseId(ID)] or target:ID
    
    def replacer(match):
        prefix = match.group(1) # e.g. "addCardToDeck(" or "id(" or "target:" or "baseId("
        card_id = match.group(2)
        suffix = match.group(3) # e.g. ")" or ""
        card_name = CARD_MAP.get(card_id, "不明なカード")
        return f"{prefix}{card_id}: {card_name}{suffix}"
        
    # Replace function-like syntax: id(382), addCardToDeck(23), baseId(809)
    text = re.sub(r'(id\(|addCardToDeck\(|baseId\()(\d+)(\))', replacer, text)
    
    # Replace target:382 syntax (target: is translated to 対象: in step 1)
    text = re.sub(r'(対象:)(\d+)()', replacer, text)
    
    return text

# 1. Game Mechanics
def generate_game_mechanics():
    content = """# 学園アイドルマスター (学マス) ゲームシステム・ルール定義

## 1. アイドルのプラン (Plan)
アイドル（Pアイドル）には主に3つのプランがあり、得意とする戦術（バフ・効果）が異なります。
*   **センス (Sense):** 「好調」「集中」を駆使してスコアを稼ぐプラン。
    *   **好調:** アピール時のスコアが増加する（%加算）。
    *   **集中:** アピール時のスコアが固定値で増加する。
*   **ロジック (Logic):** 「好印象」「やる気」を駆使してスコアを稼ぐプラン。
    *   **好印象:** ターン終了時に好印象の値だけスコアを獲得する。
    *   **やる気:** 元気増加系のスキルを使用した際、増加する元気の量にやる気の値が加算される。
*   **アノマリー (Anomaly):** 「毒」や「温存」、「体力低下時」など特殊なギミックを用いるプラン。

## 2. 主要なステータス効果
*   **元気 (Shield/Health):** アピール（スキル）を使用する際の体力消費を肩代わりするバリアのようなもの。
*   **体力 (HP):** 0になるとスキルが使用できなくなる（またはペナルティを受ける）。
*   **絶好調:** スキルの効果が大きく上がるが、特定の条件下でのみ発動。

## 3. コンテスト (Contest)
*   コンテストは、育てたPアイドル3人1組（またはそれ以上）で編成を組み、他プレイヤーのデータやNPCとスコアを競うモードです。
*   ステージごとに有利なプラン（センスやロジック）や流行（ボーカル、ダンス、ビジュアル）が設定されています。
*   **最適化のルール:**
    *   同一のアイドルは、同じ衣装（カード）でなければ別のステージに出場可能（例：ステージ1に「姫崎莉波【ガラクタロード】」、ステージ2に「姫崎莉波【clumsy trick】」を配置するのは可能）。
    *   重複配置を避けつつ、総合期待値（中央値）が最も高くなる組み合わせが「最適編成」となります。

## 4. 凡例・用語対応表 (Glossary)
本ドキュメント群のデータ上で使用される略称・変数名やターゲット指定タグの意味は以下の通りです。

* **target:mental** : メンタル属性のカードを対象とする
* **target:active** : アクティブ属性のカードを対象とする
* **T** : トラブルカード (Trouble) を指す
* **R** : レアリティ R のカードを指す
* **held / hand** : 手札のカードを指す
* **deck** : 山札を指す
* **discarded** : 捨て札を指す
* **removed** : 除外されたカードを指す
"""
    save_doc("01_Game_Mechanics", content)

# 2. P-Idols
def generate_pidols():
    idols_data = load_json(os.path.join(GAKUMAS_TOOLS_PATH, "packages/gakumas-data/json/idols.json"))
    p_idols_data = load_json(os.path.join(GAKUMAS_TOOLS_PATH, "packages/gakumas-data/json/p_idols.json"))
    
    # Map idolId -> name
    idol_map = {idol["id"]: idol["name"] for idol in idols_data}
    
    content = "# プロデュースアイドル (Pアイドル) 一覧\n\n"
    
    # Group by Idol Name
    grouped = {}
    for p in p_idols_data:
        idol_name = idol_map.get(p["idolId"], "Unknown")
        if idol_name not in grouped:
            grouped[idol_name] = []
        grouped[idol_name].append(p)
        
    for name, p_list in grouped.items():
        content += f"## {name}\n"
        for p in p_list:
            title = p.get("title", "")
            rarity = p.get("rarity", "")
            plan = translate_dsl(p.get("plan", ""))
            rec_effect = translate_dsl(p.get("recommendedEffect", ""))
            content += f"- **【{title}】** (レアリティ: {rarity} / プラン: {plan} / 推奨効果: {rec_effect})\n"
        content += "\n"
        
    save_doc("02_P_Idols", content)

# 3. Skill Cards
def generate_skill_cards():
    cards = load_json(os.path.join(GAKUMAS_TOOLS_PATH, "packages/gakumas-data/json/skill_cards.json"))
    content = "# スキルカード一覧\n\n"
    content += "ゲーム内で使用するスキルカードの一覧です。レアリティや対象プランごとに分類されています。\n\n"
    
    grouped = {}
    for c in cards:
        plan = translate_dsl(c.get("plan", "free"))
        rarity = c.get("rarity", "N")
        key = f"{plan} / {rarity}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(c)
        
    # Sort keys: plan then rarity
    for key in sorted(grouped.keys()):
        content += f"## プラン・レアリティ: {key}\n"
        for c in grouped[key]:
            name = c.get("name", "")
            cost = translate_dsl(c.get("cost", "なし"))
            actions = translate_dsl(c.get("actions", ""))
            conditions = translate_dsl(c.get("conditions", ""))
            limit = c.get("limit", "")
            
            # Format conditions/actions for better readability (very simple replace)
            if conditions:
                conditions = f" (条件: {conditions})"
                
            content += f"- **{name}**\n"
            content += f"  - コスト: {cost}\n"
            content += f"  - 効果: {actions}{conditions}\n"
            if limit:
                content += f"  - 使用回数制限: {limit}回のみ\n"
        content += "\n"

    save_doc("03_Skill_Cards", content)

# 4. Support Cards
def generate_support_cards():
    content = "# サポートカード一覧\n\n"
    content += "サポートカードの効果（サポートアビリティ・サポートイベント）をまとめたリストです。\n\n"
    
    files = glob.glob(os.path.join(SUPPORT_CARDS_PATH, "*.json"))
    cards_list = []
    
    for file in files:
        data = load_json(file)
        if isinstance(data, list) and len(data) > 0:
            cards_list.append(data[0])
            
    # Group by Rarity -> Type
    grouped = {}
    for c in cards_list:
        rarity = c.get("rarity", "R")
        type_ = c.get("type", "Unknown")
        key = f"{rarity} / {type_}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(c)
        
    for key in sorted(grouped.keys(), reverse=True): # SSR first
        content += f"## レアリティ・タイプ: {key}\n"
        for c in grouped[key]:
            name = c.get("card_name", "")
            wiki_id = os.path.basename(file).replace(".json", "")
            content += f"### {name}\n"
            
            # Abilities
            abilities = c.get("support_abilities", [])
            if abilities:
                content += "#### サポートアビリティ\n"
                for ab in abilities:
                    cond = ab.get("unlock_condition", "")
                    eff = ab.get("ability", "").replace("*", "") # remove markdown bold if any
                    content += f"- [{cond}] {eff}\n"
            
            # Events
            events = c.get("support_events", [])
            if events:
                content += "#### サポートイベント\n"
                for ev in events:
                    cond = ev.get("unlock_condition", "")
                    eff = ev.get("effect", "")
                    content += f"- [{cond}] {eff}\n"
            
            # Obtained Item
            item_name = c.get("obtained_item")
            if item_name:
                content += "#### 取得Pアイテム\n"
                content += f"- **{item_name}**\n"
                item_data = P_ITEMS_MAP.get(item_name)
                if item_data:
                    effects = translate_dsl(item_data.get("effects", ""))
                    content += f"  - 効果: {effects}\n"
            
            content += "\n"
            
    save_doc("04_Support_Cards", content)

# 5. P-Items
def generate_p_items():
    content = "# Pアイテム一覧\n\n"
    content += "ゲーム内で使用するPアイテムの一覧です。取得元やプランごとに分類されています。\n\n"
    
    grouped = {}
    for item in P_ITEMS_DATA:
        name = item.get("name", "")
        plan = translate_dsl(item.get("plan", "free"))
        rarity = item.get("rarity", "N")
        source = item.get("sourceType", "unknown")
        
        # Translate source
        if source == "produce": source_ja = "プロデュース共通"
        elif source == "pIdol": source_ja = "Pアイドル"
        elif source == "support": source_ja = "サポートカード"
        else: source_ja = source
        
        key = f"{source_ja} / {plan} / {rarity}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(item)
        
    for key in sorted(grouped.keys()):
        content += f"## {key}\n"
        for item in grouped[key]:
            name = item.get("name", "")
            effects = translate_dsl(item.get("effects", ""))
            content += f"- **{name}**: {effects}\n"
        content += "\n"
        
    save_doc("05_P_Items", content)


if __name__ == "__main__":
    generate_game_mechanics()
    generate_pidols()
    generate_skill_cards()
    generate_support_cards()
    generate_p_items()
