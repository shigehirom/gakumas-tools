import csv
import os
import re

# パス設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "packages", "gakumas-data", "csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "export", "md")
EFFECTS_DOC = os.path.join(os.path.dirname(BASE_DIR), "packages", "gakumas-data", "Effects.md")

class EffectTranslator:
    """内部コードを日本語に翻訳するクラス"""
    def __init__(self):
        # Effects.md から主要な単語の対応表を定義（簡易版）
        self.dict = {
            "startOfStage": "ステージ開始時",
            "afterStartOfStage": "ステージ開始後",
            "startOfTurn": "ターン開始時",
            "afterStartOfTurn": "ターン開始後",
            "endOfTurn": "ターン終了時",
            "cardUsed": "スキルカード使用時",
            "activeCardUsed": "アクティブスキルカード使用時",
            "mentalCardUsed": "メンタルスキルカード使用時",
            "afterCardUsed": "スキルカード使用後",
            "afterActiveCardUsed": "アクティブスキルカード使用後",
            "afterMentalCardUsed": "メンタルスキルカード使用後",
            "goodConditionTurns": "好調",
            "perfectConditionTurns": "絶好調",
            "concentration": "集中",
            "goodImpressionTurns": "好印象",
            "motivation": "やる気",
            "score": "スコア",
            "genki": "元気",
            "fixedGenki": "固定元気",
            "stamina": "体力",
            "fixedStamina": "固定体力",
            "cost": "体力消費",
            "fullPowerCharge": "全力値",
            "turnsRemaining": "残りターン数",
            "drawCard": "カードを引く",
            "upgradeHand": "手札を強化する",
            "limit": "ステージ内回数制限",
            "isVisualTurn": "ビジュアルターンの場合",
            "isDanceTurn": "ダンスターンの場合",
            "isVocalTurn": "ボーカルターンの場合",
            "isFullPower": "指針が全力の場合",
            "isStrength": "指針が強気の場合",
            "isPreservation": "指針が温存の場合",
            "stance": "指針",
            "halfCostTurns": "消費体力減少",
            "doubleCostTurns": "消費体力増加",
            "nullifyGenkiTurns": "元気無効",
            "cardUsesRemaining": "使用回数追加",
            "concentrationMultiplier": "集中適用倍率",
            "motivationMultiplier": "やる気適用倍率",
        }

    def translate(self, effect_str):
        if not effect_str: return "（なし）"
        
        results = []
        # セミコロンで区切られた複数の効果をループ
        for effect in effect_str.split(';'):
            parts = effect.split(',')
            jap_parts = []
            for part in parts:
                if ':' in part:
                    prefix, value = part.split(':', 1)
                    # 接頭辞に応じた翻訳
                    if prefix == "at":
                        jap_parts.append(f"【{self.dict.get(value, value)}】")
                    elif prefix == "if":
                        # 数式などを含む条件の処理
                        cond = value
                        for k, v in self.dict.items():
                            cond = cond.replace(k, v)
                        jap_parts.append(f"条件: {cond}")
                    elif prefix == "do":
                        # アクションの処理
                        action = value
                        for k, v in self.dict.items():
                            action = action.replace(k, v)
                        # +=, -=, *= 等の記号を日本語に
                        action = action.replace("+=", "を ").replace("-=", "を ").replace("*=", "を ")
                        if "を" in action:
                            if value.startswith("set"): # 特殊関数
                                pass 
                            else:
                                action += " 増減/変更"
                        jap_parts.append(action)
                    elif prefix == "limit":
                        jap_parts.append(f"制限: {value}回")
                    else:
                        jap_parts.append(f"{prefix}: {value}")
                else:
                    jap_parts.append(part)
            results.append(" ".join(jap_parts))
        
        return " / ".join(results)

def read_csv(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def main():
    translator = EffectTranslator()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # データ読み込み
    skill_cards = read_csv("skill_cards.csv")
    p_items = read_csv("p_items.csv")
    p_drinks = read_csv("p_drinks.csv")
    p_idols = read_csv("p_idols.csv")
    idols = read_csv("idols.csv")
    customizations = {row['id']: row for row in read_csv("customizations.csv")}

    # アイドルIDから名前へのマッピング
    idol_map = {row['id']: row['name'] for row in idols}

    # 1. スキルカード
    print("Exporting skill_cards.md...")
    with open(os.path.join(OUTPUT_DIR, "skill_cards.md"), "w", encoding='utf-8') as f:
        f.write("# 学園アイドルマスター スキルカード一覧\n\n")
        f.write("スキルカードの基本性能と、コンテストで使用可能なカスタマイズ情報の一覧です。\n\n")
        for card in skill_cards:
            name = card['name']
            f.write(f"### {name} ({card['rarity']})\n")
            f.write(f"- **ID**: {card['id']}\n")
            f.write(f"- **プラン**: {card['plan']}\n")
            f.write(f"- **タイプ**: {card['type']}\n")
            if card.get('pIdolId') and card['pIdolId'] in idol_map:
                f.write(f"- **専用アイドル**: {idol_map[card['pIdolId']]}\n")
            
            f.write("\n#### 効果説明\n")
            f.write(f"- **内容**: {translator.translate(card['effects'])}\n")
            f.write(f"- **コスト**: {card['cost']}\n")
            if card['conditions']:
                f.write(f"- **発動条件**: {translator.translate('if:' + card['conditions'])}\n")
            
            # カスタマイズ情報の紐付け
            cust_ids = card['availableCustomizations'].split(',') if card['availableCustomizations'] else []
            if cust_ids:
                f.write("\n#### 可能なカスタマイズ (コンテスト用)\n")
                for cid in cust_ids:
                    if cid in customizations:
                        c = customizations[cid]
                        f.write(f"- **{c['name']}**: {translator.translate(c['effects'] or c['growth'])}\n")
            
            f.write("\n---\n\n")

    # 2. Pアイテム
    print("Exporting p_items.md...")
    with open(os.path.join(OUTPUT_DIR, "p_items.md"), "w", encoding='utf-8') as f:
        f.write("# 学園アイドルマスター プロデュースアイテム一覧\n\n")
        for item in p_items:
            f.write(f"### {item['name']} ({item['rarity']})\n")
            f.write(f"- **タイプ**: {item['sourceType']}\n")
            f.write(f"- **プラン**: {item['plan']}\n")
            if item.get('pIdolId') and item['pIdolId'] in idol_map:
                f.write(f"- **専用アイドル**: {idol_map[item['pIdolId']]}\n")
            f.write(f"\n#### 効果説明\n")
            f.write(f"- **内容**: {translator.translate(item['effects'])}\n")
            f.write("\n---\n\n")

    # 3. Pドリンク
    print("Exporting p_drinks.md...")
    with open(os.path.join(OUTPUT_DIR, "p_drinks.md"), "w", encoding='utf-8') as f:
        f.write("# 学園アイドルマスター プロデュースドリンク一覧\n\n")
        for drink in p_drinks:
            f.write(f"### {drink['name']} ({drink['rarity']})\n")
            f.write(f"\n#### 効果説明\n")
            f.write(f"- **内容**: {translator.translate(drink['effects'])}\n")
            f.write("\n---\n\n")

    # 4. ステージ
    print("Exporting stages.md...")
    stages = read_csv("stages.csv")
    with open(os.path.join(OUTPUT_DIR, "stages.md"), "w", encoding='utf-8') as f:
        f.write("# 学園アイドルマスター ステージ一覧 (コンテスト・イベント)\n\n")
        for stage in stages:
            f.write(f"### {stage['name']}\n")
            f.write(f"- **シーズン**: {stage['season']}\n")
            f.write(f"- **プラン制限**: {stage['plan']}\n")
            f.write(f"- **ターン構成**: {stage['turnCounts']}\n")
            f.write(f"\n#### 特殊効果 (ギミック)\n")
            f.write(f"- **内容**: {translator.translate(stage['effects'])}\n")
            f.write("\n---\n\n")

    # 5. プロデュースアイドル
    print("Exporting p_idols.md...")
    with open(os.path.join(OUTPUT_DIR, "p_idols.md"), "w", encoding='utf-8') as f:
        f.write("# 学園アイドルマスター プロデュースアイドル一覧\n\n")
        for pi in p_idols:
            idol_name = idol_map.get(pi['idolId'], "不明")
            f.write(f"### 【{pi['title']}】{idol_name} ({pi['rarity']})\n")
            f.write(f"- **プラン**: {pi['plan']}\n")
            f.write(f"- **推奨効果**: {pi['recommendedEffect']}\n")
            f.write("\n---\n\n")

    print(f"Done! Markdown files are in {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
