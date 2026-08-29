"""
gakumas_data_searcher.py — 学園アイドルマスター マスタデータ & 対戦履歴 & MongoDB所持データ統合検索モジュール
"""

import csv
import os
import re
from pathlib import Path
from typing import Any

import pymongo

WORKSPACE_DIR = Path("/root/gakumas-workspace")
DATA_DIR = WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-data" / "csv"
INSTRUCTIONS_DIR = WORKSPACE_DIR / "shared" / "agent-instructions"
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://192.168.100.4:27017")
MONGODB_DB = os.environ.get("MONGODB_DB", "gakumas-tools")

# 絵文字マッピング（標準Unicode）
PLAN_EMOJIS = {
    "free": "⚪",
    "sense": "🔴",
    "logic": "🔵",
    "anomaly": "🟣"
}

TYPE_EMOJIS = {
    "active": "⬢ active",
    "mental": "🔵 mental",
    "trouble": "⚠️ trouble"
}

def format_dsl_to_jp(dsl: str) -> str:
    """DSL文字列をゲーム内の自然な日本語テキスト（絵文字付き）に完全に変換する"""
    if not dsl:
        return ""
    text = dsl

    text = re.sub(r"if:isPreservation\b", "🛡️【温存】状態の時:", text)
    text = re.sub(r"if:isStrength\b", "🔥【強気】状態の時:", text)
    text = re.sub(r"if:isFullPower\b", "⚡【全力】状態の時:", text)
    text = re.sub(r"if:fullPowerCharge>=(\d+)", r"⚡全力値\1以上の場合:", text)
    text = re.sub(r"if:turnsRemaining<=(\d+)", r"残り\1ターン以下の場合:", text)

    text = re.sub(r"fullPowerCharge\+=(\d+)", r"⚡全力値+\1", text)
    text = re.sub(r"score\+=(\d+)", r"スコア+\1", text)
    text = re.sub(r"genki\+=(\d+)", r"💚元気+\1", text)
    text = re.sub(r"motivation\+=(\d+)", r"やる気+\1", text)
    text = re.sub(r"goodImpressionTurns\+=(\d+)", r"好印象+\1", text)
    text = re.sub(r"concentration\+=(\d+)", r"集中+\1", text)
    text = re.sub(r"goodConditionTurns\+=(\d+)", r"好調+\1ターン", text)

    text = text.replace("setStance(strength2)", "🔥【強気2】にする")
    text = text.replace("setStance(strength)", "🔥【強気】にする")
    text = text.replace("setStance(preservation2)", "🛡️【温存2】にする")
    text = text.replace("setStance(preservation)", "🛡️【温存】にする")

    text = text.replace("holdThisCard", "このカードを手札温存(ホールド)")
    text = text.replace("holdSelected[hand]", "手札1枚を温存")
    text = text.replace("drawCard(2)", "カードを2枚引く")
    text = text.replace("drawCard", "カードを1枚引く")
    text = text.replace("cardUsesRemaining+=1", "カード使用数+1")

    text = text.replace("{", " [ ").replace("}", " ] ")
    text = text.replace(";", " / ").replace("  ", " ").strip(" / ")
    return text

class GakumasDataSearcher:
    def __init__(self):
        self.skill_cards: list[dict[str, Any]] = []
        self.p_items: list[dict[str, Any]] = []
        self.stages: list[dict[str, Any]] = []
        self.match_histories: dict[str, list[dict[str, Any]]] = {}
        self._mongo_client: pymongo.MongoClient | None = None
        self._db: Any = None
        self._load_csv_data()
        self._init_mongo()

    def _init_mongo(self):
        try:
            self._mongo_client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
            self._db = self._mongo_client[MONGODB_DB]
        except Exception:
            self._mongo_client = None
            self._db = None

    def _load_csv_data(self):
        cards_path = DATA_DIR / "skill_cards.csv"
        if cards_path.exists():
            with open(cards_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.skill_cards.append(row)

        items_path = DATA_DIR / "p_items.csv"
        if items_path.exists():
            with open(items_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.p_items.append(row)

        stages_path = DATA_DIR / "stages.csv"
        if stages_path.exists():
            with open(stages_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.stages.append(row)

        if INSTRUCTIONS_DIR.exists():
            for p in INSTRUCTIONS_DIR.glob("match_history_*.csv"):
                m = re.search(r"match_history_(\d+)\.csv", p.name)
                if m:
                    season = m.group(1)
                    rows = []
                    with open(p, encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for r in reader:
                            rows.append(r)
                    self.match_histories[season] = rows

    # ────────────────────────── MongoDB 所持データ照会 ──────────────────────────

    def search_owned_p_idols(self, query: str) -> str:
        if self._db is None:
            return "※MongoDB に接続できませんでした。"
        try:
            col = self._db["owned_p_idols"]
            docs = list(col.find({}))
            if not docs:
                return "※所持Pアイドルの登録データがありません。"

            q = query.lower()

            # フィルタ判定
            plan_filter = None
            if "アノマリー" in query or "anomaly" in q:
                plan_filter = "anomaly"
            elif "センス" in query or "sense" in q:
                plan_filter = "sense"
            elif "ロジック" in query or "logic" in q:
                plan_filter = "logic"

            # アイドル名ごとにグルーピング
            idols_dict: dict[str, list[dict[str, Any]]] = {}

            rarity_weight = {"SSR": 3, "SR": 2, "R": 1}

            for doc in docs:
                idol_name = doc.get("idol_name", "").strip() or "その他"
                title = doc.get("title", "").strip()
                plan = (doc.get("plan") or "").lower()
                rarity = doc.get("rarity", "")

                if plan_filter and plan != plan_filter:
                    continue

                keywords = [k.strip() for k in re.split(r"[\s,、。]+", query) if len(k.strip()) >= 2]
                match = True
                if keywords and not plan_filter:
                    match = any(kw in idol_name or kw in title or kw in rarity for kw in keywords)

                if match:
                    if idol_name not in idols_dict:
                        idols_dict[idol_name] = []
                    idols_dict[idol_name].append(doc)

            if not idols_dict:
                return "※条件に一致する所持Pアイドルは見つかりませんでした。"

            total_count = sum(len(v) for v in idols_dict.values())
            plan_name = f"（{plan_filter.upper()}プラン）" if plan_filter else ""
            lines = [
                f"【所持 P アイドル一覧{plan_name}（該当: 全 {total_count} 件）】\n"
            ]

            for idol_name, card_list in idols_dict.items():
                # レアリティ順にソート (SSR -> SR -> R)
                card_list.sort(key=lambda x: rarity_weight.get(x.get("rarity", ""), 0), reverse=True)
                lines.append(f"■ **{idol_name}**（{len(card_list)}着）:")
                for doc in card_list:
                    title = doc.get("title", "")
                    plan = (doc.get("plan") or "").lower()
                    rarity = doc.get("rarity", "")
                    talent = doc.get("talent_level", 1)
                    awaken = doc.get("awaken_level", 1)
                    p_emoji = PLAN_EMOJIS.get(plan, "")

                    lines.append(
                        f"- ◆ {p_emoji} **【{title}】** `[{rarity} / {plan.upper()}]` ｜ 才能開花: **★{talent}** ｜ 特訓レベル: **Lv.{awaken}**"
                    )
                lines.append("")  # 空行

            return "\n".join(lines).strip()
        except Exception as e:
            return f"※所持Pアイドル照会エラー: {e}"


    def search_owned_support_cards(self, query: str) -> str:
        if self._db is None:
            return "※MongoDB に接続できませんでした。"
        try:
            col = self._db["owned_support_cards"]
            docs = list(col.find({}))
            if not docs:
                return "※所持サポートカードの登録データがありません。"

            q = query.lower()
            matched = []

            # 凸数フィルタ
            uncap_filter = None
            if "完凸" in query or "4凸" in query:
                uncap_filter = 4
            elif "3凸" in query:
                uncap_filter = 3
            elif "2凸" in query:
                uncap_filter = 2
            elif "1凸" in query:
                uncap_filter = 1
            elif "無凸" in query or "0凸" in query:
                uncap_filter = 0

            # レアリティフィルタ
            rarity_filter = None
            if "ssr" in q:
                rarity_filter = "SSR"
            elif "sr" in q and "ssr" not in q:
                rarity_filter = "SR"
            elif "r" in q and "ssr" not in q and "sr" not in q:
                rarity_filter = "R"

            for doc in docs:
                name = doc.get("card_name", "")
                rarity = doc.get("rarity", "")
                uncap = doc.get("uncap", 0)
                lv = doc.get("lv", 1)
                obtained_card = doc.get("obtained_skill_card")
                ctype = doc.get("type", "")

                if uncap_filter is not None and uncap != uncap_filter:
                    continue
                if rarity_filter and rarity != rarity_filter:
                    continue

                keywords = [k.strip() for k in re.split(r"[\s,、。]+", query) if len(k.strip()) >= 2]
                match = True
                if keywords and uncap_filter is None and not rarity_filter:
                    match = any(kw in name or (obtained_card and kw in obtained_card) for kw in keywords)

                if match:
                    skill_str = f" ｜ 習得スキル: 『{obtained_card}』" if obtained_card else ""
                    matched.append(
                        f"- ◆ **{name}** `[{rarity} / {ctype}]`\n"
                        f"  ・上限解放: **{uncap} 凸** ｜ レベル: **Lv.{lv}**{skill_str}"
                    )

            if not matched:
                return "※条件に一致する所持サポートカードは見つかりませんでした。"

            lines = [
                f"【所持サポートカード一覧（該当: 全 {len(matched)} 件中、上位 {min(len(matched), 20)} 件を表示）】\n"
            ]
            lines.extend(matched[:20])
            if len(matched) > 20:
                lines.append(f"\n※他 {len(matched) - 20} 件（特定のカード名やタイプで絞り込み可能です）")
            return "\n".join(lines)

        except Exception as e:
            return f"※所持サポカ照会エラー: {e}"

    # ────────────────────────── 対戦履歴照会 ──────────────────────────

    def get_match_history_summary(self, query: str) -> str:
        range_match = re.search(r"(\d+)\s*(?:から|〜|~|-)\s*(\d+)", query)
        is_multi = range_match or any(k in query for k in ["各シーズン", "全シーズン", "すべて", "一覧", "推移"])

        all_seasons = sorted(self.match_histories.keys(), key=lambda x: int(x))
        if not all_seasons:
            return "※対戦履歴データが見つかりませんでした。"

        if range_match:
            s_start = int(range_match.group(1))
            s_end = int(range_match.group(2))
            target_seasons = [s for s in all_seasons if s_start <= int(s) <= s_end]
        elif is_multi:
            target_seasons = all_seasons
        else:
            season_match = re.search(r"(?:シーズン|season|s)\s*(\d+)", query, re.IGNORECASE)
            if season_match:
                target_seasons = [season_match.group(1)]
            else:
                target_seasons = [all_seasons[-1]]

        if len(target_seasons) > 1:
            lines = ["【コンテスト 各シーズン別 対戦成績・勝率まとめ】\n"]
            total_all_matches = 0
            total_all_wins = 0
            total_all_pt = 0

            for s in target_seasons:
                rows = self.match_histories.get(s, [])
                valid_matches = []
                for r in rows:
                    res_val = (r.get("結果") or r.get("対戦結果") or "").strip().upper()
                    pt_val = (r.get("獲得Pt") or "").strip()
                    if res_val in ["WIN", "LOSE"] or (pt_val and pt_val.isdigit()):
                        valid_matches.append(r)

                if not valid_matches:
                    continue

                total = len(valid_matches)
                wins = sum(1 for r in valid_matches if (r.get("結果") or r.get("対戦結果") or "").strip().upper() == "WIN" or (r.get("獲得Pt", "").isdigit() and int(r.get("獲得Pt")) > 50))
                losses = total - wins
                win_rate = (wins / total * 100) if total > 0 else 0

                pts = [int(r.get("獲得Pt")) for r in valid_matches if r.get("獲得Pt", "").isdigit()]
                avg_pt = sum(pts) / len(pts) if pts else 0
                total_pt = sum(pts)

                total_all_matches += total
                total_all_wins += wins
                total_all_pt += total_pt

                lines.append(
                    f"◆ **シーズン {s}**\n"
                    f"・戦績: **{total}戦 {wins}勝 {losses}敗**（勝率: **{win_rate:.1f}%**）\n"
                    f"・獲得Pt: **{total_pt:,} Pt**（平均: **{avg_pt:.1f} Pt/戦**）\n"
                )

            if total_all_matches > 0:
                overall_rate = (total_all_wins / total_all_matches * 100)
                lines.append(
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 **通算（シーズン {target_seasons[0]} 〜 {target_seasons[-1]}）**\n"
                    f"- 総対戦数: **{total_all_matches} 戦**\n"
                    f"- 通算勝敗: **{total_all_wins} 勝 {total_all_matches - total_all_wins} 敗**（通算勝率: **{overall_rate:.1f}%**）\n"
                    f"- 獲得Pt総計: **{total_all_pt:,} Pt**"
                )
            return "\n".join(lines)

        season = target_seasons[0]
        rows = self.match_histories.get(season, [])
        if not rows:
            return f"※シーズン {season} の対戦履歴データが見つかりませんでした。"

        valid_matches = []
        for r in rows:
            res_val = (r.get("結果") or r.get("対戦結果") or "").strip().upper()
            pt_val = (r.get("獲得Pt") or "").strip()
            if res_val in ["WIN", "LOSE"] or (pt_val and pt_val.isdigit()):
                valid_matches.append(r)

        if not valid_matches:
            return f"※シーズン {season} の対戦履歴にはまだ記録された対戦がありません。"

        total = len(valid_matches)
        wins = sum(1 for r in valid_matches if (r.get("結果") or r.get("対戦結果") or "").strip().upper() == "WIN" or (r.get("獲得Pt", "").isdigit() and int(r.get("獲得Pt")) > 50))
        losses = total - wins
        win_rate = (wins / total * 100) if total > 0 else 0

        pts = [int(r.get("獲得Pt")) for r in valid_matches if r.get("獲得Pt", "").isdigit()]
        avg_pt = sum(pts) / len(pts) if pts else 0
        total_pt = sum(pts)

        lines = [
            f"【コンテスト シーズン {season} 公式対戦成績集計】",
            f"- 総対戦数: **{total} 戦**",
            f"- 勝敗: **{wins} 勝 {losses} 敗**（勝率: **{win_rate:.1f}%**）",
            f"- 獲得Pt合計: **{total_pt:,} Pt**（平均: **{avg_pt:.1f} Pt / 戦**）",
            "\n■ 直近の対戦履歴（最新5戦）:"
        ]

        for idx, r in enumerate(valid_matches[-5:], start=1):
            date = r.get("日付", "")
            res_val = (r.get("結果") or r.get("対戦結果") or "").strip().upper()
            res_str = "🏆 勝利 (WIN)" if res_val == "WIN" or (r.get("獲得Pt", "").isdigit() and int(r.get("獲得Pt")) > 50) else "❌ 敗北 (LOSE)"
            pt = r.get("獲得Pt", "-")
            opp = r.get("相手名") or r.get("対戦相手") or "-"
            s1_my, s1_en = r.get("自S1", "-"), r.get("敵S1", "-")
            s2_my, s2_en = r.get("自S2", "-"), r.get("敵S2", "-")
            s3_my, s3_en = r.get("自S3", "-"), r.get("敵S3", "-")
            
            lines.append(
                f"- **{date}** | {res_str} | 獲得: **{pt} Pt** | 対戦相手: `{opp}`\n"
                f"  └ ステージ1: {s1_my} vs {s1_en} ｜ ステージ2: {s2_my} vs {s2_en} ｜ ステージ3: {s3_my} vs {s3_en}"
            )

        return "\n".join(lines)

    # ────────────────────────── マスタデータ & 統合検索 ──────────────────────────

    def search_context_for_query(self, query: str, max_results: int = 40) -> str:
        """ユーザーの質問内容に基づいて関連するスキルカード、アイテム、対戦成績、所持データを完全条件抽出する"""
        q = query.lower()

        # 0. 所持データの判定 (MongoDB)
        is_owned_query = any(k in query for k in ["所持", "持っている", "手持ち", "持ちアイドル", "持ちサポカ", "自分の", "才能開花", "特訓レベル", "完凸", "凸数", "上限解放"])
        if is_owned_query and any(k in q for k in ["pアイドル", "アイドル", "キャラ", "星", "才能"]):
            return self.search_owned_p_idols(query)
        if is_owned_query and any(k in q for k in ["サポカ", "サポート", "カード", "完凸", "凸数", "上限解放"]):
            return self.search_owned_support_cards(query)


        # 1. 対戦成績・戦績・コンテスト履歴の判定
        if any(k in query for k in ["対戦成績", "戦績", "勝率", "対戦結果", "コンテスト結果", "マッチ履歴", "何勝", "各シーズン", "シーズンごとの"]):
            return self.get_match_history_summary(query)

        # 2. スキルカード・マスタデータ検索
        target_plan = None
        if "アノマリー" in query or "anomaly" in q:
            target_plan = "anomaly"
        elif "センス" in query or "sense" in q:
            target_plan = "sense"
        elif "ロジック" in query or "logic" in q:
            target_plan = "logic"

        is_full_power = "全力" in query or "fullpower" in q
        is_genki = "元気" in query or "genki" in q
        is_score = "スコア" in query or "アピール" in query
        is_draw = "ドロー" in query or "引く" in query
        is_repeat_only = "繰り返し" in query or "再使用" in query or "何度も" in query

        matched_cards = []

        for card in self.skill_cards:
            name = card.get("name", "")
            plan = (card.get("plan") or "").lower()
            actions = card.get("actions", "")
            effects = card.get("effects", "")
            all_effects = f"{actions}; {effects}".strip("; ")
            unique = card.get("unique", "")
            limit_val = card.get("limit", "").strip()

            if target_plan and plan != target_plan and plan != "free":
                continue

            is_one_time = (unique == "TRUE") or (limit_val == "1") or ("limit:1" in all_effects)
            if is_repeat_only and is_one_time:
                continue

            match = False
            if is_full_power and ("fullpowercharge" in all_effects.lower() or "全力" in name):
                match = True
            elif is_genki and ("genki+=" in all_effects.lower() or "元気" in name):
                match = True
            elif is_score and ("score+=" in all_effects.lower() or "スコア" in name):
                match = True
            elif is_draw and ("drawcard" in all_effects.lower()):
                match = True
            elif not (is_full_power or is_genki or is_score or is_draw):
                keywords = [k.strip() for k in re.split(r"[\s,、。]+", query) if len(k.strip()) >= 2]
                if any(kw in name or kw in all_effects for kw in keywords):
                    match = True

            if match:
                matched_cards.append((card, all_effects, is_one_time))

        if not matched_cards:
            return ""

        context_lines = [
            f"【学園アイドルマスター 公式マスタデータ検索結果（条件該当: 全 {len(matched_cards)} 件）】",
            "※絶対厳守ルール:",
            "1. 以下の該当カードを省略せず、すべてリスト形式で出力してください。",
            "2. カード名は以下の正式名称を1文字も変えずにそのまま出力してください。",
            "3. スタンス公式用語は【強気】【温存】【全力】です。",
            "4. 効果はわかりやすい日本語で簡潔に記載してください。"
        ]

        context_lines.append("\n■ 該当スキルカード一覧（全件）:")
        for c, all_eff, is_one_time in matched_cards[:max_results]:
            repeat_label = "1回限り" if is_one_time else "繰り返し使用可能"
            cost_raw = c.get("cost", "0").replace("cost-=", "体力消費:").replace("stamina-=", "固定体力:").replace("fullPowerCharge-=", "全力値消費:")
            jp_eff = format_dsl_to_jp(all_eff)
            
            p_emoji = PLAN_EMOJIS.get((c.get("plan") or "").lower(), "")
            t_emoji = TYPE_EMOJIS.get((c.get("type") or "").lower(), c.get("type", ""))

            context_lines.append(
                f"- ◆ {p_emoji} **{c.get('name')}** `[{c.get('rarity')} / {t_emoji} / {repeat_label}]`\n"
                f"  ・コスト: {cost_raw} ｜ 効果: {jp_eff}"
            )

        return "\n".join(context_lines)
