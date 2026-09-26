"""
dsl_translator.py — 学園アイドルマスター DSL 決定論的トランスレーター

in-game DSL（スキルカード / Pアイテム）および
out-game DSL（サポカアビリティ）の両方に対応。

設計方針:
  LLM に生 DSL や内部ID（holdCard(638) 等）を渡さず、
  マスタデータ辞書と突合してカード名解決およびゲーム内テキスト準拠の自然な日本語に
  100% 確実に変換してから渡す。
"""

import csv
from pathlib import Path
import re

_CUSTOMIZATIONS: dict[str, dict] | None = None
_SKILL_CARDS_MAP: dict[str, str] | None = None
_P_ITEMS_MAP: dict[str, str] | None = None


def _get_customizations() -> dict[str, dict]:
    global _CUSTOMIZATIONS
    if _CUSTOMIZATIONS is not None:
        return _CUSTOMIZATIONS
    _CUSTOMIZATIONS = {}
    candidates = [
        Path("/home/pi/gakumas-mcp-server/data/csv/customizations.csv"),
        Path("/app/packages/gakumas-data/csv/customizations.csv"),
        Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/csv/customizations.csv"),
        Path(__file__).resolve().parent.parent / "data" / "csv" / "customizations.csv",
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    _CUSTOMIZATIONS = {row["id"]: row for row in csv.DictReader(f)}
                break
            except Exception:
                continue
    return _CUSTOMIZATIONS


def _get_skill_cards_map() -> dict[str, str]:
    global _SKILL_CARDS_MAP
    if _SKILL_CARDS_MAP is not None:
        return _SKILL_CARDS_MAP
    _SKILL_CARDS_MAP = {}
    candidates = [
        Path("/home/pi/gakumas-mcp-server/data/csv/skill_cards.csv"),
        Path("/app/packages/gakumas-data/csv/skill_cards.csv"),
        Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/csv/skill_cards.csv"),
        Path(__file__).resolve().parent.parent / "data" / "csv" / "skill_cards.csv",
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        cid = row.get("id")
                        cname = row.get("name")
                        if cid and cname:
                            _SKILL_CARDS_MAP[cid] = cname
                break
            except Exception:
                continue
    return _SKILL_CARDS_MAP


def _get_p_items_map() -> dict[str, str]:
    global _P_ITEMS_MAP
    if _P_ITEMS_MAP is not None:
        return _P_ITEMS_MAP
    _P_ITEMS_MAP = {}
    candidates = [
        Path("/home/pi/gakumas-mcp-server/data/csv/p_items.csv"),
        Path("/app/packages/gakumas-data/csv/p_items.csv"),
        Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/csv/p_items.csv"),
        Path(__file__).resolve().parent.parent / "data" / "csv" / "p_items.csv",
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        iid = row.get("id")
                        iname = row.get("name")
                        if iid and iname:
                            _P_ITEMS_MAP[iid] = iname
                break
            except Exception:
                continue
    return _P_ITEMS_MAP


def _card_name(cid: str | int) -> str:
    cmap = _get_skill_cards_map()
    return cmap.get(str(cid), f"カードID:{cid}")


def _item_name(iid: str | int) -> str:
    imap = _get_p_items_map()
    return imap.get(str(iid), f"アイテムID:{iid}")


class DslTranslator:
    """DSL 文字列をゲーム内テキスト（絵文字付き日本語）に変換する。"""

    def translate(self, dsl: str) -> str:
        if not dsl:
            return ""
        text = dsl.strip().strip(";").strip()

        # ── 0. カードID / アイテムIDの動的解決 (Resolver) ─────────────────────
        text = re.sub(r"holdCard\((\d+)\)", lambda m: f"『{_card_name(m.group(1))}』を保留", text)
        text = re.sub(r"moveRandomToTopOfDeck\[baseId\((\d+)\)\]", lambda m: f"『{_card_name(m.group(1))}』を山札の一番上に移動", text)
        text = re.sub(r"moveRandomToHand\[removed\s*&\s*(\d+)\]", lambda m: f"除外ゾーンの『{_card_name(m.group(1))}』を手札に加える", text)
        text = re.sub(r"moveRandomToHand\[.*?baseId\((\d+)\).*?\]", lambda m: f"『{_card_name(m.group(1))}』を手札に加える", text)
        text = re.sub(r"countCards\[removed\s*&\s*(\d+)\]>=(\d+)", lambda m: f"除外ゾーンの『{_card_name(m.group(1))}』が{m.group(2)}枚以上の場合", text)
        text = re.sub(r"countCards\[removed\s*&\s*(\d+)\]", lambda m: f"除外ゾーンの『{_card_name(m.group(1))}』の枚数", text)

        # 複合使用後効果
        text = re.sub(
            r"if:usedCardBaseId==(\d+)\s*&\s*isFullPower",
            lambda m: f"『{_card_name(m.group(1))}』を⚡【全力】状態で使用時:",
            text,
        )
        text = re.sub(r"if:usedCardBaseId==(\d+)", lambda m: f"『{_card_name(m.group(1))}』使用時:", text)
        text = re.sub(r"usedCardBaseId==(\d+)", lambda m: f"直前に使用したカードが『{_card_name(m.group(1))}』", text)

        # ターン中限定効果 (at:turn { ... ; limit:1 })
        text = re.sub(r"at:turn\s*[\{\[]\s*(.*?)(?:;\s*limit:(\d+))\s*[\}\]]", r"ターン中(\2回のみ): \1", text)

        # ── 1. 特殊トリガー・ターゲット (at:prestage, target:this, target:all 等) ──
        text = re.sub(r"target:mental\s*[\{\[]\s*g\.genki\+=(\d+)\s*[\}\]]", r"メンタルスキルカードの元気値増加+\1", text)
        text = re.sub(r"target:mental\s*[\{\[]\s*g\.score\+=(\d+)\s*[\}\]]", r"メンタルスキルカードのスコア増加+\1", text)
        text = re.sub(r"target:mental\s*[\{\[]\s*g\.cost-=(\d+)\s*[\}\]]", r"メンタルスキルカードの体力消費-\1", text)
        text = re.sub(r"target:active\s*[\{\[]\s*g\.score\+=(\d+)\s*[\}\]]", r"アクティブスキルカードのスコア増加+\1", text)
        text = re.sub(r"target:active\s*[\{\[]\s*g\.genki\+=(\d+)\s*[\}\]]", r"アクティブスキルカードの元気値増加+\1", text)
        text = re.sub(r"target:active\s*[\{\[]\s*g\.cost-=(\d+)\s*[\}\]]", r"アクティブスキルカードの体力消費-\1", text)

        # 保留カード対象ターゲット (target:held)
        text = re.sub(r"target:held\s*[\{\[]\s*g\.scoreTimes\+=(\d+)\s*;\s*g\.cost-=(\d+)\s*[\}\]]", r"保留したカードのパラメータ上昇回数+\1、体力消費-\2", text)
        text = re.sub(r"target:held\s*[\{\[]\s*g\.scoreTimes\+=(\d+)\s*[\}\]]", r"保留したカードのパラメータ上昇回数+\1", text)
        text = re.sub(r"target:held\s*[\{\[]\s*g\.cost-=(\d+)\s*[\}\]]", r"保留したカードの体力消費-\1", text)

        # 自身対象ターゲット (target:this)
        text = re.sub(r"target:this\s*[\{\[]\s*g\.score\+=(\d+)\s*[\}\]]", r"このカードのスコア+\1", text)
        text = re.sub(r"target:this\s*[\{\[]\s*g\.cost-=(\d+)\s*[\}\]]", r"このカードの体力消費-\1", text)
        text = re.sub(r"target:this\s*[\{\[]\s*g\.typedCost-=(\d+)\s*[\}\]]", r"このカードの消費コスト-\1", text)

        # 特定カードID対象 (target:ID)
        text = re.sub(
            r"target:(\d+)\s*[\{\[]\s*g\.scoreTimes\+=(\d+)\s*;\s*g\.score\+=(\d+)\s*;\s*g\.cost-=(\d+)\s*[\}\]]",
            lambda m: f"『{_card_name(m.group(1))}』のパラメータ上昇回数+{m.group(2)}、スコア+{m.group(3)}、体力消費-{m.group(4)}",
            text,
        )
        text = re.sub(r"target:(\d+)\s*[\{\[]\s*(.*?)\s*[\}\]]", lambda m: f"『{_card_name(m.group(1))}』の効果: {m.group(2)}", text)

        # score+=genki*X; genki=0 ➔ 元気の{rate}%分パラメータ上昇させ、元気を0にする
        def _fmt_genki_score_reset(m: re.Match) -> str:
            rate = int(round(float(m.group(1)) * 100))
            return f"元気の{rate}%分パラメータ上昇させ、元気を0にする"
        text = re.sub(r"score\+=genki\*([\d.]+)\s*;\s*genki=0", _fmt_genki_score_reset, text)
        text = re.sub(r"score\+=genki\s*;\s*genki=0", "元気の100%分パラメータ上昇させ、元気を0にする", text)

        text = re.sub(
            r"at:stanceChanged\s*[\{\[]\s*if:isDirectEffect\s*&\s*isStrength\s*&\s*genki>=(\d+)\s*[\{\[]\s*(.*?)\s*[\}\]]\s*(?:;\s*limit:(\d+))?\s*[\}\]]",
            lambda m: f"直接効果で 強気 になった時、元気が{m.group(1)}以上の場合、\n{m.group(2)}" + (f" ; limit:{m.group(3)}" if m.group(3) else ""),
            text,
        )
        text = re.sub(
            r"at:stanceChanged\s*[\{\[]\s*if:isDirectEffect\s*&\s*isStrength\s*[\{\[]\s*(.*?)\s*[\}\]]\s*(?:;\s*limit:(\d+))?\s*[\}\]]",
            lambda m: f"直接効果で 強気 になった時:\n{m.group(1)}" + (f" ; limit:{m.group(2)}" if m.group(2) else ""),
            text,
        )
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.fullPowerCharge\+=(\d+)\s*[\}\]]\s*[\}\]]", r"レッスン開始時: ⚡全力値+\1", text)
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.genki\+=(\d+)\s*[\}\]]\s*[\}\]]", r"レッスン開始時: 💚元気+\1", text)
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.stanceLevel\+=(\d+)\s*[\}\]]\s*[\}\]]", r"レッスン開始時: スタンスLv+\1", text)
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.typedCost\+=(\d+)\s*[\}\]]\s*[\}\]]", r"消費コスト-\1", text)
        text = re.sub(r"target:this\s*[\{\[]\s*g\.typedCost\+=(\d+)\s*[\}\]]", r"消費コスト-\1", text)
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.cost\+=(\d+)\s*[\}\]]\s*[\}\]]", r"体力消費-\1", text)
        text = re.sub(r"target:this\s*[\{\[]\s*g\.cost\+=(\d+)\s*[\}\]]", r"体力消費-\1", text)
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.score\+=(\d+)\s*[\}\]]\s*[\}\]]", r"レッスン開始時: スコア+\1", text)
        text = re.sub(r"target:all\s*[\{\[]\s*g\.score\+=(\d+)\s*[\}\]]", r"すべてのカード効果: スコア+\1", text)
        text = re.sub(r"target:hand\s*[\{\[]\s*g\.score\+=(\d+)\s*[\}\]]", r"手札のカード効果: スコア+\1", text)
        text = re.sub(r"target:this\s*[\{\[]\s*g\.([a-zA-Z]+)\+=(\d+)\s*[\}\]]", r"\1+\2", text)
        text = re.sub(r"at:cardUsed\s*[\{\[]\s*if:cardHasEffect\(fullPowerCharge\)\s*[\{\[]\s*(.*?)\s*[\}\]]\s*[\}\]]", r"全力効果カード使用時: \1", text)

        # ── 2. バフ・デバフ（カンマ後スペース対応） ─────────────────────────
        def _fmt_buff(stat_name: str):
            def _inner(m: re.Match) -> str:
                rate = int(round(float(m.group(1)) * 100))
                turns = f"({m.group(2)}ターン)" if m.group(2) else ""
                return f"{stat_name}増加量+{rate}%{turns}"
            return _inner

        text = re.sub(r"setGoodImpressionTurnsBuff\(([\d.]+)(?:,\s*(\d+))?\)", _fmt_buff("好印象"), text)
        text = re.sub(r"setGoodImpressionTurnsEffectBuff\(([\d.]+)(?:,\s*(\d+))?\)", _fmt_buff("好印象効果"), text)
        text = re.sub(r"setGoodConditionTurnsBuff\(([\d.]+)(?:,\s*(\d+))?\)", _fmt_buff("好調"), text)
        text = re.sub(r"setGoodConditionBuff\(([\d.]+)(?:,\s*(\d+))?\)", lambda m: f"好調効果+{int(round(float(m.group(1))*100))}%" + (f"({m.group(2)}ターン)" if m.group(2) else ""), text)
        text = re.sub(r"setConcentrationBuff\(([\d.]+)(?:,\s*(\d+))?\)", _fmt_buff("集中"), text)
        text = re.sub(r"setConcentrationEffectBuff\(([\d.]+)(?:,\s*(\d+))?\)", lambda m: f"集中効果+{int(round(float(m.group(1))*100))}%" + (f"({m.group(2)}ターン)" if m.group(2) else ""), text)
        text = re.sub(r"setMotivationBuff\(([\d.]+)(?:,\s*(\d+))?\)", _fmt_buff("やる気"), text)
        text = re.sub(r"setEnthusiasmBuff\(([\d.]+)(?:,\s*(\d+))?\)", _fmt_buff("熱意"), text)
        text = re.sub(r"setFullPowerChargeBuff\(([\d.]+)(?:,\s*(\d+))?\)", _fmt_buff("⚡全力値"), text)
        text = re.sub(r"setFullPowerEffectBuff\(([\d.]+)(?:,\s*(\d+))?\)", _fmt_buff("⚡全力効果"), text)
        text = re.sub(r"setScoreBuff\(([\d.]+)(?:,\s*(\d+))?\)", lambda m: f"スコア上昇量+{int(round(float(m.group(1))*100))}%" + (f"({m.group(2)}ターン)" if m.group(2) else ""), text)
        text = re.sub(r"doubleCardEffectCards\+=1\b", "次回使用カードの効果が2倍", text)
        text = re.sub(r"doubleCardEffectCards\+=(\d+)", r"次回使用カードの効果が2倍(\1回)", text)
        text = re.sub(r"doubleCardEffectCards\+1\b", "次回使用カードの効果が2倍", text)

        # ── 3. レベル別構文 (level:1 { ... } level:2 { ... }) ────────────────
        def _fmt_levels(match: re.Match) -> str:
            raw = match.group(0)
            parts = re.findall(r"level:(\d+)\s*[\{\[]([^}\]]+)[\}\]]", raw)
            if parts:
                formatted = [f"Lv.{lv}: {self.translate(content)}" for lv, content in parts]
                return " ｜ ".join(formatted)
            return raw

        text = re.sub(r"(?:level:\d+\s*[\{\[][^}\]]+[\}\]]\s*)+", _fmt_levels, text)

        # ── 4. 条件節 (if:xxx) ───────────────────────────────────────────────
        text = re.sub(r"if:isDanceTurn\b",               "Daターンの時:", text)
        text = re.sub(r"if:isVocalTurn\b",               "Voターンの時:", text)
        text = re.sub(r"if:isVisualTurn\b",              "Viターンの時:", text)
        text = re.sub(r"if:isPreservation\b",            "🛡️【温存】状態の時:", text)
        text = re.sub(r"if:isPreservation2\b",           "🛡️【温存2】状態の時:", text)
        text = re.sub(r"if:isStrength\b",                "🔥【強気】状態の時:", text)
        text = re.sub(r"if:isStrength2\b",               "🔥【強気2】状態の時:", text)
        text = re.sub(r"if:isFullPower\b",               "⚡【全力】状態の時:", text)
        text = re.sub(r"if:isGoodCondition\b",           "好調状態の時:", text)
        text = re.sub(r"if:isPerfectCondition\b",        "絶好調状態の時:", text)
        text = re.sub(r"if:cumulativeFullPowerCharge>=(\d+)", r"累計全力値\1以上の場合:", text)
        text = re.sub(r"if:cumulativeFullPowerCharge<=(\d+)", r"累計全力値\1以下の場合:", text)
        text = re.sub(r"if:fullPowerCharge>=(\d+)",      r"⚡全力値\1以上の場合:", text)
        text = re.sub(r"if:fullPowerCharge<=(\d+)",      r"⚡全力値\1以下の場合:", text)
        text = re.sub(r"if:stanceChangedTimes>=(\d+)",   r"スタンス変更回数が\1回以上の場合:", text)
        text = re.sub(r"if:lockStanceTurns==0\b",        "スタンス固定なしの場合:", text)
        text = re.sub(r"if:stamina>=maxStamina\*0\.5",  r"体力が最大値の50%以上の時:", text)
        text = re.sub(r"if:stamina>=(\d+)",             r"体力\1以上の時:", text)
        text = re.sub(r"if:stamina<=(\d+)",             r"体力\1以下の時:", text)
        text = re.sub(r"if:turnsElapsed>=(\d+)",        r"\1ターン目以降:", text)
        text = re.sub(r"if:turnsElapsed%(\d+)==(\d+)",  r"(\1ターン周期の\2ターン目):", text)
        text = re.sub(r"if:score<=(\d+)",               r"スコアが\1以下の時:", text)
        text = re.sub(r"if:genki==0",                   r"元気が0の時:", text)
        text = re.sub(r"if:turnsRemaining<=(\d+)",       r"残り\1ターン以下の場合:", text)
        text = re.sub(r"if:turnsRemaining==(\d+)",       r"残り\1ターンの場合:", text)
        text = re.sub(r"if:cardUsed>=(\d+)",             r"カード\1枚以上使用済みの時:", text)
        text = re.sub(r"if:genki>=(\d+)",                r"💚元気\1以上の時:", text)
        text = re.sub(r"if:genki<=(\d+)",                r"💚元気\1以下の時:", text)
        text = re.sub(r"if:motivation>=(\d+)",           r"やる気\1以上の時:", text)
        text = re.sub(r"if:motivation<=(\d+)",           r"やる気\1以下の時:", text)
        text = re.sub(r"if:concentration>=(\d+)",        r"集中\1以上の時:", text)
        text = re.sub(r"if:concentration<=(\d+)",        r"集中\1以下の時:", text)
        text = re.sub(r"if:goodConditionTurns>=(\d+)",   r"好調\1ターン以上の時:", text)
        text = re.sub(r"if:goodConditionTurns<=(\d+)",   r"好調\1ターン以下の時:", text)
        text = re.sub(r"if:goodImpressionTurns>=(\d+)",  r"好印象\1以上の時:", text)
        text = re.sub(r"if:goodImpressionTurns<=(\d+)",  r"好印象\1以下の時:", text)
        text = re.sub(r"if:isDirectEffect\b",            "（カード本来の効果）", text)

        # ── 5. カード操作・保留・使用 ─────────────────────────────────────────
        text = re.sub(r"holdSelectedUpto\[deck\s*\|\s*discarded\]\((\d+)\)", r"山札または捨て札からカードを最大\1枚選んで保留", text)
        text = re.sub(r"holdSelectedUpto\[deck\]\((\d+)\)", r"山札からカードを最大\1枚選んで保留", text)
        text = re.sub(r"holdSelectedUpto\[discarded\]\((\d+)\)", r"捨て札からカードを最大\1枚選んで保留", text)
        text = re.sub(r"holdSelected\[deck\s*\|\s*discarded\]", "山札または捨て札から任意のカードを保留", text)
        text = re.sub(r"holdSelected\[deck\]", "山札から任意のカードを保留", text)
        text = re.sub(r"holdSelected\[hand\]", "手札から任意のカードを保留", text)
        text = text.replace("holdSelected", "任意のカードを保留")
        text = text.replace("holdThisCard", "このカードを保留")

        text = re.sub(r"useSelectedFree\[deck\s*\|\s*discarded\]", "山札または捨て札から選んだカードを体力消費0で使用", text)
        text = re.sub(r"useSelectedFree\[deck\]", "山札から選んだカードを体力消費0で使用", text)
        text = re.sub(r"useSelectedFree\[discarded\]", "捨て札から選んだカードを体力消費0で使用", text)
        text = text.replace("useSelectedFree", "選んだカードを体力消費0で使用")

        text = text.replace("drawCard(2)", "カードを2枚引く")
        text = text.replace("drawCard(3)", "カードを3枚引く")
        text = text.replace("drawCard", "カードを1枚引く")
        text = text.replace("upgradeCard[hand]", "手札1枚を強化")
        text = text.replace("upgradeRandomCardInHand", "手札のランダムなカード1枚を強化")
        text = text.replace("upgradeCard", "このカードを強化")
        text = text.replace("upgradeHand", "手札のカードを強化")
        text = text.replace("forceInitialHand", "レッスン開始時手札に入る")
        text = re.sub(r"addCardToDeck\(\d+\)", "山札にトラブルカードを追加", text)

        # ── 6. スコア計算式 ──────────────────────────────────────────────────
        text = re.sub(r"score\+=([\d.]+)\+cumulativeFullPowerCharge\*([\d.]+)", r"スコア+\1 ＋ 累計全力値×\2のスコア獲得", text)
        text = re.sub(r"score\+=([\d.]+)\+cumulativeFullPowerCharge\b", r"スコア+\1 ＋ 累計全力値分のスコア獲得", text)
        text = re.sub(r"score\+=cumulativeFullPowerCharge\*([\d.]+)", r"累計全力値×\1のスコア獲得", text)
        text = re.sub(r"score\+=cumulativeFullPowerCharge\b", "累計全力値分のスコア獲得", text)
        text = re.sub(r"score\+=goodImpressionTurns\*([\d.]+)", lambda m: f"好印象の{int(round(float(m.group(1))*100))}%分パラメータ上昇", text)
        text = re.sub(r"score\+=motivation\*([\d.]+)", lambda m: f"やる気の{int(round(float(m.group(1))*100))}%分パラメータ上昇", text)
        text = re.sub(r"score\+=genki\*([\d.]+)", lambda m: f"元気の{int(round(float(m.group(1))*100))}%分パラメータ上昇", text)
        text = re.sub(r"score\+=concentration\*([\d.]+)", lambda m: f"集中の{int(round(float(m.group(1))*100))}%分パラメータ上昇", text)
        text = re.sub(r"score\+=([\d.]+)", r"スコア+\1", text)
        text = re.sub(r"score\+([\d.]+)", r"スコア+\1", text)

        # ── 7. アクション・リソース増減 ──────────────────────────────────────
        text = re.sub(r"fullPowerCharge\+=(\d+)", r"⚡全力値+\1", text)
        text = re.sub(r"fullPowerCharge-=(\d+)", r"⚡全力値-\1", text)
        text = re.sub(r"fullPowerCharge\+(\d+)", r"⚡全力値+\1", text)
        text = re.sub(r"genki\+=(\d+)", r"💚元気+\1", text)
        text = re.sub(r"genki-=(\d+)", r"💚元気-\1", text)
        text = re.sub(r"genki\+(\d+)", r"💚元気+\1", text)
        text = text.replace("genki=0", "元気を0に変更")
        text = re.sub(r"motivation\+=(\d+)", r"やる気+\1", text)
        text = re.sub(r"motivation\+(\d+)", r"やる気+\1", text)
        text = re.sub(r"goodImpressionTurns\+=(\d+)", r"好印象+\1", text)
        text = re.sub(r"goodImpressionTurns\+(\d+)", r"好印象+\1", text)
        text = re.sub(r"concentration\+=(\d+)", r"集中+\1", text)
        text = re.sub(r"concentration\+(\d+)", r"集中+\1", text)
        text = re.sub(r"goodConditionTurns\+=(\d+)", r"好調+\1ターン", text)
        text = re.sub(r"goodConditionTurns\+(\d+)", r"好調+\1ターン", text)
        text = re.sub(r"perfectConditionTurns\+=(\d+)", r"絶好調+\1ターン", text)
        text = re.sub(r"perfectConditionTurns\+(\d+)", r"絶好調+\1ターン", text)
        text = re.sub(r"nullifyGenkiTurns\+=(\d+)", r"元気無効+\1ターン", text)
        text = re.sub(r"halfCostTurns\+=(\d+)", r"消費半減+\1ターン", text)
        text = re.sub(r"cardUsesRemaining\+=(\d+)", r"カード使用数+\1", text)
        text = re.sub(r"enthusiasmMultiplier=(\d+)", r"熱意倍率×\1", text)
        text = re.sub(r"setEnthusiasmBonus\((\d+)\)", r"熱意ボーナス+\1", text)
        text = re.sub(r"fixedStamina-=(\d+)", r"体力消費\1", text)

        # ── 8. スタンス変更 ──────────────────────────────────────────────────
        text = text.replace("setStance(strength2)", "強気2に変更")
        text = text.replace("setStance(strength)", "強気に変更")
        text = text.replace("setStance(preservation2)", "温存2に変更")
        text = text.replace("setStance(preservation)", "温存に変更")
        text = text.replace("setStance(fullPower)", "全力に変更")
        text = text.replace("setStance(leisure)", "温存解除")

        # ── 9. コスト ────────────────────────────────────────────────────────
        text = re.sub(r"cost-=(\d+)", r"体力消費\1", text)
        text = re.sub(r"stamina-=(\d+)", r"固定体力消費\1", text)
        text = re.sub(r"typedCost-=(\d+)", r"消費コスト-\1", text)
        text = re.sub(r"motivation-=(\d+)", r"やる気消費\1", text)
        text = re.sub(r"goodImpressionTurns-=(\d+)", r"好印象消費\1", text)
        text = re.sub(r"goodConditionTurns-=(\d+)", r"好調消費\1", text)
        text = re.sub(r"genki-=(\d+)", r"元気消費\1", text)

        # ── 10. at: トリガー ─────────────────────────────────────────────────
        text = text.replace("at:afterCardUsed", "カード使用後:")
        text = text.replace("at:beforeCardUsed", "カード使用前:")
        text = text.replace("at:cardUsed[mental]", "メンタルスキルカード使用時:")
        text = text.replace("at:cardUsed[active]", "アクティブスキルカード使用時:")
        text = text.replace("at:cardUsed", "カード使用時:")
        text = text.replace("at:turn", "ターン中:")
        text = text.replace("at:stanceChanged", "スタンス変更時:")
        text = text.replace("at:startOfTurn", "ターン開始時:")
        text = text.replace("at:afterStartOfTurn", "ターン開始後:")
        text = text.replace("at:endOfTurn", "ターン終了時:")
        text = text.replace("at:everyTurn", "毎ターン:")
        text = text.replace("at:prestage", "レッスン開始時:")

        # ── 11. グロース・残存プレフィックス整理 ─────────────────────────────
        text = re.sub(r"\b(?:g\.)?scoreByGoodImpressionTurns\+=([\d.]+)", lambda m: f"好印象分パラメータ+{int(round(float(m.group(1))*100))}%", text)
        text = re.sub(r"\b(?:g\.)?scoreByMotivation\+=([\d.]+)", lambda m: f"やる気分パラメータ+{int(round(float(m.group(1))*100))}%", text)
        text = re.sub(r"\b(?:g\.)?scoreByGenki\+=([\d.]+)", lambda m: f"元気分パラメータ+{int(round(float(m.group(1))*100))}%", text)
        text = re.sub(r"\b(?:g\.)?scoreByConcentration\+=([\d.]+)", lambda m: f"集中分パラメータ+{int(round(float(m.group(1))*100))}%", text)
        text = re.sub(r"\b(?:g\.)?halfCostTurns\+=(\d+)", r"消費体力削減+\1ターン", text)
        text = re.sub(r"\b(?:g\.)?typedCost\+=(\d+)", r"消費コスト-\1", text)
        text = re.sub(r"\b(?:g\.)?cost\+=(\d+)", r"体力消費-\1", text)
        text = re.sub(r"\bg\.([a-zA-Z]+)\+=(\d+)", r"\1+\2", text)
        text = re.sub(r"\bg\.([a-zA-Z]+)", r"\1", text)

        # ── 12. limit ────────────────────────────────────────────────────────
        text = re.sub(r"\blimit:(\d+)\b", r"［レッスン中\1回］", text)

        # ── 13. クリーンアップ ───────────────────────────────────────────────
        text = text.replace("target:this", "")
        text = text.replace("target:all", "すべてのカード:")
        text = re.sub(r"[\{\}\[\]]", "", text)
        text = re.sub(r"\s*;\s*", " / ", text)

        # ── 14. out-game DSL（サポカアビリティ）───────────────────────────────
        text = re.sub(r"@passive:\s*vi_lesson_bonus\+\{v\}", "常時: Viレッスンボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*da_lesson_bonus\+\{v\}", "常時: Daレッスンボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*vo_lesson_bonus\+\{v\}", "常時: Voレッスンボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*vo_bonus\+\{v\}", "常時: Voボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*da_bonus\+\{v\}", "常時: Daボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*vi_bonus\+\{v\}", "常時: Viボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*self_lesson_support_rate\+\{v\}", "常時: サポート発生率+{v}%", text)
        text = re.sub(r"@passive:\s*self_event_param_bonus\+\{v\}", "常時: イベント効果アップ+{v}%", text)
        text = re.sub(r"@passive:\s*coin\+\{v\}", "常時: Pポイント+{v}", text)
        text = re.sub(r"@passive:\s*hp\+\{v\}", "常時: 体力+{v}", text)
        text = re.sub(r"@init:\s*coin\+\{v\}", "プロデュース開始時: Pポイント+{v}", text)
        text = re.sub(r"@init:\s*hp\+\{v\}", "プロデュース開始時: 体力+{v}", text)
        text = re.sub(r"@sp_lesson_end\(type=vocal\):\s*hp\+\{v\}", "VoのSPレッスン終了時: 体力+{v}", text)
        text = re.sub(r"@sp_lesson_end\(type=dance\):\s*hp\+\{v\}", "DaのSPレッスン終了時: 体力+{v}", text)
        text = re.sub(r"@sp_lesson_end\(type=visual\):\s*hp\+\{v\}", "ViのSPレッスン終了時: 体力+{v}", text)
        text = re.sub(r"@lesson_end\(type=vocal\):\s*vo\+\{v\}", "Voレッスン終了時: Vo+{v}", text)
        text = re.sub(r"@lesson_end\(type=dance\):\s*da\+\{v\}", "Daレッスン終了時: Da+{v}", text)
        text = re.sub(r"@lesson_end\(type=visual\):\s*vi\+\{v\}", "Viレッスン終了時: Vi+{v}", text)
        text = re.sub(r"@rest_end:\s*vo\+\{v\}", "お休み終了時: Vo+{v}", text)
        text = re.sub(r"@rest_end:\s*da\+\{v\}", "お休み終了時: Da+{v}", text)
        text = re.sub(r"@rest_end:\s*vi\+\{v\}", "お休み終了時: Vi+{v}", text)
        text = re.sub(r"@event:\s*([a-zA-Z]+)\+(\d+)", r"イベント: \1+\2", text)

        # ── 15. 整形仕上げ ───────────────────────────────────────────────────
        text = re.sub(r"\bmental\b", "メンタル", text, flags=re.IGNORECASE)
        text = re.sub(r"\bactive\b", "アクティブ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bdelay\b", "遅延", text, flags=re.IGNORECASE)
        text = re.sub(r"\s{2,}", " ", text)
        text = text.strip().strip("/ ").strip()

        return text


# 後方互換性のためモジュールレベル関数も提供
_translator = DslTranslator()


def format_dsl_to_jp(dsl: str) -> str:
    """DSL文字列をゲーム内の自然な日本語テキスト（絵文字付き）に変換する（後方互換）"""
    return _translator.translate(dsl)


def format_skill_card_specs(sc: dict, indent: str = "", dsl: DslTranslator | None = None) -> str:
    """スキルカードの公式諸元（カード名、レアリティ、タイプ、プラン、コスト、手札指定、効果、制限）を省略なくフォーマットする。"""
    if dsl is None:
        dsl = _translator

    name = sc.get("name", "")
    rarity = sc.get("rarity", "")
    card_type = (sc.get("type") or "").lower()
    type_jp = {"active": "アクティブ", "mental": "メンタル", "trouble": "トラブル"}.get(card_type, card_type)
    plan = (sc.get("plan") or "").lower()
    plan_jp = {"sense": "センス", "logic": "ロジック", "anomaly": "アノマリー", "free": "フリー"}.get(plan, plan.upper())

    # コスト
    cost_raw = (sc.get("cost") or "").strip()
    cost_str = "体力消費なし"
    if "fullPowerCharge-=" in cost_raw:
        val = cost_raw.replace("fullPowerCharge-=", "").strip()
        cost_str = f"⚡全力値消費{val}"
    elif "stamina-=" in cost_raw:
        val = cost_raw.replace("stamina-=", "").strip()
        cost_str = f"♥体力消費{val} (固定体力)"
    elif "typedCost-=" in cost_raw:
        val = cost_raw.replace("typedCost-=", "").strip()
        cost_str = f"消費コスト{val}"
    elif "cost-=" in cost_raw:
        val = cost_raw.replace("cost-=", "").strip()
        cost_str = f"♥体力消費{val}"
    elif "genki-=" in cost_raw:
        val = cost_raw.replace("genki-=", "").strip()
        cost_str = f"元気消費{val}"
    elif "motivation-=" in cost_raw:
        val = cost_raw.replace("motivation-=", "").strip()
        cost_str = f"やる気消費{val}"
    elif "goodImpressionTurns-=" in cost_raw:
        val = cost_raw.replace("goodImpressionTurns-=", "").strip()
        cost_str = f"好印象消費{val}"
    elif "goodConditionTurns-=" in cost_raw:
        val = cost_raw.replace("goodConditionTurns-=", "").strip()
        cost_str = f"好調消費{val}"
    elif cost_raw and cost_raw != "0":
        cost_str = f"コスト: {cost_raw}"

    # 手札指定
    force_hand = sc.get("forceInitialHand", "").upper() == "TRUE"
    hand_str = "レッスン開始時手札に入る" if force_hand else ""

    # 使用条件 (conditions)
    cond_raw = (sc.get("conditions") or "").strip()
    cond_str = ""
    if cond_raw:
        cond_trans = dsl.translate(cond_raw).rstrip(":")
        cond_str = f"使用条件: {cond_trans}"

    # 効果 (actions, effects)
    acts = (sc.get("actions") or "").strip()
    effs = (sc.get("effects") or "").strip()
    dsl_full = "; ".join([x for x in [acts, effs] if x])
    limit_match = re.search(r"(?:^|;|\s)limit:(\d+)", dsl_full)
    dsl_for_trans = re.sub(r";?\s*limit:\d+", "", dsl_full).strip("; ")
    translated = dsl.translate(dsl_for_trans) if dsl_for_trans else ""

    # 多段スコアのまとめ表示（例: スコア+5 / スコア+5 / スコア+5 ... ➔ スコア+5 (5回)）
    score_multi_match = re.search(r"((?:スコア\+\d+\s*/\s*)+スコア\+\d+)", translated)
    if score_multi_match:
        full_match = score_multi_match.group(1)
        items = [x.strip() for x in full_match.split("/") if x.strip()]
        if len(items) >= 2 and all(x == items[0] for x in items):
            compact_score = f"{items[0]}（{len(items)}回）"
            translated = translated.replace(full_match, compact_score)

    eff_items = [item.strip() for item in translated.split(" / ") if item.strip()]

    # 制限 (unique, limit)
    limits = []
    if sc.get("unique", "").upper() == "TRUE":
        limits.append("重複不可")
    limit_val = (sc.get("limit") or "").strip()
    if not limit_val and limit_match:
        limit_val = limit_match.group(1)
    if limit_val:
        limits.append(f"レッスン中{limit_val}回")

    lim_str = " ｜ ".join(limits)

    lines = [
        f"{indent}■ **【{name}】** `[{rarity} / {plan_jp} / {type_jp}]`",
        f"{indent}  - コスト: {cost_str}",
    ]
    if hand_str:
        lines.append(f"{indent}  - 手札指定: {hand_str}")
    if cond_str:
        lines.append(f"{indent}  - 条件: {cond_str}")
    if eff_items:
        lines.append(f"{indent}  - 効果:")
        for item in eff_items:
            lines.append(f"{indent}    ✦ {item}")
    else:
        lines.append(f"{indent}  - 効果: （記載なし）")
    if limits:
        lines.append(f"{indent}  - 制限: {lim_str}")

    # カスタマイズ解放効果
    custom_ids_raw = sc.get("availableCustomizations", "")
    if custom_ids_raw:
        cust_dict = _get_customizations()
        custom_items = []
        for cid in [x.strip() for x in custom_ids_raw.split(",") if x.strip()]:
            c_info = cust_dict.get(cid)
            if c_info:
                c_name = c_info.get("name", "")
                c_price = c_info.get("price", "")
                price_suffix = f" ({c_price}P)" if c_price else ""
                raw = "; ".join([x for x in [c_info.get("actions", ""), c_info.get("effects", ""), c_info.get("cost", ""), c_info.get("conditions", "")] if x])
                if not raw:
                    if c_name == "開始時手札に入る":
                        desc = "レッスン開始時手札に入る"
                    elif c_name == "レッスン中1回の制限削除":
                        desc = "レッスン中1回の制限を削除"
                    elif c_name == "条件変更":
                        desc = "使用条件の緩和・変更"
                    else:
                        desc = c_name
                else:
                    desc = dsl.translate(raw)
                custom_items.append((f"{c_name}{price_suffix}", desc))
        if custom_items:
            lines.append(f"{indent}  - カスタマイズ解放効果:")
            for c_label, c_desc in custom_items:
                lines.append(f"{indent}    ◆ {c_label}: {c_desc}")

    return "\n".join(lines)


def format_p_item_specs(item: dict, indent: str = "", dsl: DslTranslator | None = None) -> str:
    """Pアイテムの公式諸元（アイテム名、レアリティ、プラン、トリガー条件、効果、制限）を省略なくフォーマットする。"""
    if dsl is None:
        dsl = _translator

    name = item.get("name", "")
    rarity = item.get("rarity", "")
    plan = (item.get("plan") or "").lower()
    plan_jp = {"sense": "センス", "logic": "ロジック", "anomaly": "アノマリー", "free": "フリー"}.get(plan, plan.upper())

    acts = (item.get("actions") or "").strip()
    effs = (item.get("effects") or "").strip()
    dsl_full = "; ".join([x for x in [acts, effs] if x])

    # limit:X の抽出（一番外側の最後の limit をレッスン回数とする）
    limit_matches = re.findall(r"(?:^|;|\s)limit:(\d+)", dsl_full)
    limit_str = f"(レッスン中{limit_matches[-1]}回)" if limit_matches else ""

    # 文末のトップレベル limit:X を安全に除去して翻訳へ渡す
    dsl_no_limit = re.sub(r";?\s*limit:\d+\s*(\}*)\s*$", r"\1", dsl_full).strip("; ")
    translated = dsl.translate(dsl_no_limit) if dsl_no_limit else ""

    # トリガー文（「〜〜の場合、」「〜〜の時:」「〜〜時:」）の分離
    trigger = ""
    eff_body = translated
    if "\n" in translated:
        parts = translated.split("\n", 1)
        trigger = parts[0].strip()
        eff_body = parts[1].strip()

    eff_items = [item_str.strip() for item_str in eff_body.split(" / ") if item_str.strip()]
    if limit_str:
        eff_items.append(limit_str)

    lines = [
        f"{indent}■ **【{name}】** `[{rarity} / {plan_jp}]`",
    ]
    if trigger:
        lines.append(f"{indent}  {trigger}")
    if eff_items:
        lines.append(f"{indent}  - 効果:")
        for item_str in eff_items:
            lines.append(f"{indent}    ✦ {item_str}")
    else:
        lines.append(f"{indent}  - 効果: （記載なし）")

    return "\n".join(lines)
