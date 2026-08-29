import json
import re
from typing import List, Dict, Any, Optional

# ==========================================
# 1. マッピング用辞書の厳密な定義
# ==========================================

# トリガーマッピング
TRIGGER_MAP: Dict[str, str] = {
    "初期": "@init",
    "授業・営業終了時": "@class_end",
    "お出かけ終了時": "@rest_end",
    "休む選択時": "@rest_select",
    "相談選択時": "@shop_select",
    "相談でPドリンク交換後": "@shop_buy_drink",
    "活動支給・差し入れ選択時": "@gift_select",
    "通常レッスン終了時": "@lesson_end",
    "SPレッスン終了時": "@sp_lesson_end",
    "試験・オーディション終了時": "@exam_end",
    "アクティブスキルカード強化時": "@card_upgrade(type=active)",
    "メンタルスキルカード獲得時": "@card_get(type=mental)",
    "スキルカード削除時": "@card_delete",
    "スキルカードカスタマイズ時": "@card_custom"
}

# 無視またはプレースホルダーとするキーワード
SKIP_KEYWORDS = [
    "サポート発生率増加",
    "お休み時体力回復量増加",
    "お出かけ時体力回復量増加",
    "トラブル発生率ダウン"
]

def parse_modifiers(text: str) -> str:
    """修飾子（回数制限、確率など）を抽出してDSL化する"""
    modifiers = []
    
    # プロデュース中X回
    limit_match = re.search(r"（プロデュース中(\d+)回）", text)
    if limit_match:
        modifiers.append(f"limit={limit_match.group(1)}")
        
    # 確率X%
    prob_match = re.search(r"（?確率(\d+)%）?", text)
    if prob_match:
        modifiers.append(f"prob={prob_match.group(1)}")
        
    if modifiers:
        return "(" + ",".join(modifiers) + ")"
    return ""

def parse_effect(effect_str: str) -> str:
    """効果文字列（ボーカル上昇+65など）をDSLの対象・演算子に変換する"""
    # プレースホルダーの処理
    for skip_kw in SKIP_KEYWORDS:
        if skip_kw in effect_str:
            return skip_kw

    # 効果の正規表現マッチング
    vo_match = re.search(r"ボーカル上昇\+?(\d+)", effect_str)
    if vo_match: return f"vo+{vo_match.group(1)}"
    
    da_match = re.search(r"ダンス上昇\+?(\d+)", effect_str)
    if da_match: return f"da+{da_match.group(1)}"
    
    vi_match = re.search(r"ビジュアル上昇\+?(\d+)", effect_str)
    if vi_match: return f"vi+{vi_match.group(1)}"
    
    hp_max_match = re.search(r"最大体力上昇\+?(\d+)", effect_str)
    if hp_max_match: return f"hp_max+{hp_max_match.group(1)}"
    
    hp_match = re.search(r"体力回復\+?(\d+)", effect_str)
    if hp_match: return f"hp+{hp_match.group(1)}"
    
    coin_match = re.search(r"Pポイント\+?(\d+)", effect_str)
    if coin_match: return f"coin+{coin_match.group(1)}"
    
    bonus_match = re.search(r"([A-Za-z]+|ボーカル|ダンス|ビジュアル)パラメータボーナス\+?(\d+)%", effect_str)
    if bonus_match:
        param_type = bonus_match.group(1)
        val = bonus_match.group(2)
        if param_type == "ボーカル": param_type = "vo"
        elif param_type == "ダンス": param_type = "da"
        elif param_type == "ビジュアル": param_type = "vi"
        return f"{param_type}_bonus+{val}"

    # マッチしない場合は元の文字列を返すかフォールバック
    return "unknown_effect"

def parse_ability_line(line: str) -> Optional[Dict[str, Any]]:
    """アビリティ行（例: - 初期: ボーカル上昇+65）をパースする"""
    line = line.strip().lstrip("-").strip()
    if not line:
        return None

    # トリガーと効果を分離
    if ":" in line:
        parts = line.split(":", 1)
        trigger_jp = parts[0].strip()
        effect_part = parts[1].strip()
    else:
        # トリガー明記なし（サポート発生率増加など）の場合は「初期」扱いとするかそのまま
        trigger_jp = "初期"
        effect_part = line

    trigger_dsl = TRIGGER_MAP.get(trigger_jp, "@init")
    effect_dsl = parse_effect(effect_part)
    mod_dsl = parse_modifiers(effect_part)
    
    if effect_dsl in SKIP_KEYWORDS:
        # シミュレートに関係ない場合はプレースホルダー化
        final_dsl = f"{trigger_dsl}: {effect_dsl}{mod_dsl}"
    else:
        final_dsl = f"{trigger_dsl}: {effect_dsl}{mod_dsl}"

    return {
        "level": 0,
        "type": "ability",
        "dsl": final_dsl
    }

def parse_markdown_to_json(md_text: str) -> List[Dict[str, Any]]:
    cards = []
    current_card = None
    current_section = None
    
    lines = md_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # カードタイトルのパース (# [ID] NAME (RARITY / TYPE))
        title_match = re.match(r"^#\s+\[(.*?)\]\s+(.*?)\s+\((.*?)/(.*?)\)", line)
        if title_match:
            if current_card:
                cards.append(current_card)
            current_card = {
                "id": title_match.group(1).strip(),
                "name": title_match.group(2).strip(),
                "rarity": title_match.group(3).strip(),
                "type": title_match.group(4).strip(),
                "unlocked_effects": [],
                "support_events": [],
                "acquired_p_item": {}
            }
            continue
            
        if not current_card:
            continue
            
        # セクションの切り替え
        if line.startswith("## アビリティ"):
            current_section = "ability"
            continue
        elif line.startswith("## サポートイベント"):
            current_section = "event"
            continue
        elif line.startswith("## Pアイテム"):
            current_section = "p_item"
            continue
            
        # リスト項目のパース
        if line.startswith("-"):
            if current_section == "ability":
                ab = parse_ability_line(line)
                if ab:
                    current_card["unlocked_effects"].append(ab)
            elif current_section == "event":
                ab = parse_ability_line(line)
                if ab:
                    # サポートイベントは dsl キーをそのまま使用するか、event_triggerとして処理
                    current_card["support_events"].append({
                        "level": 0,
                        "dsl": ab["dsl"]
                    })
            elif current_section == "p_item":
                # Pアイテムは - 名前: と - 効果: に分かれている想定
                if line.startswith("- 名前:"):
                    current_card["acquired_p_item"]["name"] = line.replace("- 名前:", "").strip()
                elif line.startswith("- 効果:"):
                    current_card["acquired_p_item"]["in_game_effect"] = line.replace("- 効果:", "").strip()

    if current_card:
        cards.append(current_card)
        
    return cards

# ==========================================
# 実際の動作検証用ブロック
# ==========================================
if __name__ == '__main__':
    # 提供されたMarkdownのサンプル（ダミーデータ）
    SAMPLE_MARKDOWN = """
# [SP_SSR_0001] 何かのカード名 (SSR / vocal)

## アビリティ
- 初期: ボーカル上昇+65
- 授業・営業終了時: Pポイント+10
- 休む選択時: 体力回復+5
- サポート発生率増加（プロデュース中1回）
- SPレッスン終了時: ボーカル上昇+10（確率50%）

## サポートイベント
- 相談選択時: ボーカル上昇+10（確率50%）
- メンタルスキルカード獲得時: ビジュアルパラメータボーナス+10%

## Pアイテム
- 名前: 最高のお守り
- 効果: 相談でPドリンク交換後: 体力回復+1

# [SP_SR_0002] 別のサポートカード (SR / dance)

## アビリティ
- 初期: ダンス上昇+40
- アクティブスキルカード強化時: ダンス上昇+15（プロデュース中3回）
- お休み時体力回復量増加

## サポートイベント
- 通常レッスン終了時: ダンスパラメータボーナス+5%

## Pアイテム
- 名前: 練習用シューズ
- 効果: 授業・営業終了時: 最大体力上昇+2
"""

    print("パース開始...")
    parsed_json = parse_markdown_to_json(SAMPLE_MARKDOWN)
    
    output_path = "support_cards_master.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(parsed_json, f, indent=2, ensure_ascii=False)
    
    print(f"パース完了。結果を {output_path} に保存しました。")
    print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
