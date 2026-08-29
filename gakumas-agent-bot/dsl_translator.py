"""
dsl_translator.py — 学園アイドルマスター DSL 決定論的トランスレーター

in-game DSL（スキルカード / Pアイテム）および
out-game DSL（サポカアビリティ）の両方に対応。

設計方針:
  LLM に生 DSL を渡さず、Python 側で 100% 確実に日本語変換してから LLM に渡す。
"""

import re


class DslTranslator:
    """DSL 文字列をゲーム内テキスト（絵文字付き日本語）に変換する。"""

    def translate(self, dsl: str) -> str:
        if not dsl:
            return ""
        text = dsl.strip().strip(";").strip()

        # ── 特殊トリガー・ターゲット (at:prestage, target:this, target:all 等) ──────
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.fullPowerCharge\+=(\d+)\s*[\}\]]\s*[\}\]]", r"レッスン開始時: ⚡全力値+\1", text)
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.genki\+=(\d+)\s*[\}\]]\s*[\}\]]", r"レッスン開始時: 💚元気+\1", text)
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.stanceLevel\+=(\d+)\s*[\}\]]\s*[\}\]]", r"レッスン開始時: スタンスLv+\1", text)
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.cost\+=(\d+)\s*[\}\]]\s*[\}\]]", r"体力消費-\1", text)
        text = re.sub(r"at:prestage\s*[\{\[]\s*target:this\s*[\{\[]\s*g\.score\+=(\d+)\s*[\}\]]\s*[\}\]]", r"レッスン開始時: スコア+\1", text)
        text = re.sub(r"target:all\s*[\{\[]\s*g\.score\+=(\d+)\s*[\}\]]", r"すべてのカード効果: スコア+\1", text)
        text = re.sub(r"target:hand\s*[\{\[]\s*g\.score\+=(\d+)\s*[\}\]]", r"手札のカード効果: スコア+\1", text)
        text = re.sub(r"target:this\s*[\{\[]\s*g\.([a-zA-Z]+)\+=(\d+)\s*[\}\]]", r"\1+\2", text)
        text = re.sub(r"at:cardUsed\s*[\{\[]\s*if:cardHasEffect\(fullPowerCharge\)\s*[\{\[]\s*(.*?)\s*[\}\]]\s*[\}\]]", r"全力効果カード使用時: \1", text)
        text = re.sub(r"at:afterStartOfTurn\s*[\{\[]\s*if:isPreservation\s*[\{\[]\s*setStance\(leisure\)\s*[\}\]]\s*[\}\]]", "ターン開始後【温存】時: 【温存解除】", text)
        text = re.sub(r"setFullPowerChargeBuff\(([\d.]+),(\d+)\)", r"全力値増加量+\1倍(\2ターン)", text)
        text = re.sub(r"addCardToDeck\(\d+\)", "山札にトラブルカードを追加", text)

        # ── レベル別構文 (level:1 { ... } level:2 { ... } または level:1 [ ... ]) ──
        def _fmt_levels(match: re.Match) -> str:
            raw = match.group(0)
            parts = re.findall(r"level:(\d+)\s*[\{\[]([^}\]]+)[\}\]]", raw)
            if parts:
                formatted = [f"Lv.{lv}: {self.translate(content)}" for lv, content in parts]
                return " ｜ ".join(formatted)
            return raw

        text = re.sub(r"(?:level:\d+\s*[\{\[][^}\]]+[\}\]]\s*)+", _fmt_levels, text)

        # 残った単発の at:prestage や target:this 等のクリーンアップ
        text = re.sub(r"at:prestage\b", "レッスン開始時:", text)
        text = re.sub(r"target:this\b", "", text)
        text = re.sub(r"target:all\b", "すべてのカード:", text)

        # ── 特殊効果・バフ・乗数 ──────────────────────────────────────────
        text = re.sub(r"concentrationMultiplier\s*=\s*([\d.]+)", r"集中効果×\1倍", text)
        text = re.sub(r"goodConditionMultiplier\s*=\s*([\d.]+)", r"好調効果×\1倍", text)
        text = re.sub(r"perfectConditionMultiplier\s*=\s*([\d.]+)", r"絶好調効果×\1倍", text)
        text = re.sub(r"setConcentrationEffectBuff\(([\d.]+),(\d+)\)", lambda m: f"集中効果+{int(float(m.group(1))*100)}%({m.group(2)}ターン)", text)
        text = re.sub(r"setGoodConditionBuff\(([\d.]+),(\d+)\)", lambda m: f"好調効果+{int(float(m.group(1))*100)}%({m.group(2)}ターン)", text)
        text = re.sub(r"delay:(\d+)", r"\1ターン後発動", text)
        text = re.sub(r"addCardToDeck\(\d+\)", "山札にトラブルカードを追加", text)

        # ── 条件節 (if:xxx) ─────────────────────────────────────────────────
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
        text = re.sub(r"if:fullPowerCharge>=(\d+)",      r"⚡全力値\1以上の場合:", text)
        text = re.sub(r"if:fullPowerCharge<=(\d+)",      r"⚡全力値\1以下の場合:", text)
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

        # ── アクション系 ─────────────────────────────────────────────────────
        text = re.sub(r"fullPowerCharge\+=(\d+)",        r"⚡全力値+\1", text)
        text = re.sub(r"fullPowerCharge-=(\d+)",         r"⚡全力値-\1", text)
        text = re.sub(r"fullPowerCharge\+(\d+)",         r"⚡全力値+\1", text)
        text = re.sub(r"score\+=([\d.]+)",               r"スコア+\1", text)
        text = re.sub(r"score\+([\d.]+)",                r"スコア+\1", text)
        text = re.sub(r"score\+=cumulativeFullPowerCharge\*1\.5", "スコア+（累計全力値×1.5）", text)
        text = re.sub(r"score\+=cumulativeFullPowerCharge\b",     "スコア+（累計全力値）", text)
        text = re.sub(r"genki\+=(\d+)",                  r"💚元気+\1", text)
        text = re.sub(r"genki-=(\d+)",                   r"💚元気-\1", text)
        text = re.sub(r"genki\+(\d+)",                   r"💚元気+\1", text)
        text = re.sub(r"motivation\+=(\d+)",             r"やる気+\1", text)
        text = re.sub(r"motivation\+(\d+)",              r"やる気+\1", text)
        text = re.sub(r"goodImpressionTurns\+=(\d+)",    r"好印象+\1", text)
        text = re.sub(r"goodImpressionTurns\+(\d+)",     r"好印象+\1", text)
        text = re.sub(r"concentration\+=(\d+)",          r"集中+\1", text)
        text = re.sub(r"concentration\+(\d+)",           r"集中+\1", text)
        text = re.sub(r"goodConditionTurns\+=(\d+)",     r"好調+\1ターン", text)
        text = re.sub(r"goodConditionTurns\+(\d+)",      r"好調+\1ターン", text)
        text = re.sub(r"perfectConditionTurns\+=(\d+)",  r"絶好調+\1ターン", text)
        text = re.sub(r"perfectConditionTurns\+(\d+)",   r"絶好調+\1ターン", text)
        text = re.sub(r"nullifyGenkiTurns\+=(\d+)",      r"元気無効+\1ターン", text)
        text = re.sub(r"halfCostTurns\+=(\d+)",          r"消費半減+\1ターン", text)
        text = re.sub(r"cardUsesRemaining\+=(\d+)",      r"カード使用数+\1", text)
        text = re.sub(r"enthusiasmMultiplier=(\d+)",     r"熱意倍率×\1", text)
        text = re.sub(r"setEnthusiasmBonus\((\d+)\)",    r"熱意ボーナス+\1", text)

        # ── スタンス ─────────────────────────────────────────────────────────
        text = text.replace("setStance(strength2)",      "🔥【強気2】にする")
        text = text.replace("setStance(strength)",       "🔥【強気】にする")
        text = text.replace("setStance(preservation2)",  "🛡️【温存2】にする")
        text = text.replace("setStance(preservation)",   "🛡️【温存】にする")
        text = text.replace("setStance(leisure)",        "【温存解除】")

        # ── カード操作・保留 ──────────────────────────────────────────────────
        text = text.replace("holdSelected[deck | discarded]", "山札または捨て札から任意のカードを保留")
        text = text.replace("holdSelected[deck]",        "山札から任意のカードを保留")
        text = text.replace("holdSelected[hand]",        "手札から任意のカードを保留")
        text = text.replace("holdSelected",              "任意のカードを保留")
        text = text.replace("holdThisCard",              "このカードを保留")
        text = text.replace("drawCard(2)",               "カードを2枚引く")
        text = text.replace("drawCard(3)",               "カードを3枚引く")
        text = text.replace("drawCard",                  "カードを1枚引く")
        text = text.replace("upgradeCard[hand]",         "手札1枚を強化")
        text = text.replace("upgradeCard",               "このカードを強化")
        text = text.replace("upgradeHand",               "手札のカードを強化")
        text = text.replace("forceInitialHand",          "開始時手札に入る")

        # ── コスト ──────────────────────────────────────────────────────────
        text = re.sub(r"cost-=(\d+)",                    r"体力消費\1", text)
        text = re.sub(r"stamina-=(\d+)",                 r"固定体力消費\1", text)

        # ── at: トリガー ─────────────────────────────────────────────────────
        text = text.replace("at:cardUsed[mental]",       "精神カード使用時:")
        text = text.replace("at:cardUsed[active]",       "アクティブカード使用時:")
        text = text.replace("at:cardUsed",               "カード使用時:")
        text = text.replace("at:turn",                   "ターン中:")
        text = text.replace("at:stanceChanged",          "スタンス変化時:")
        text = text.replace("at:startOfTurn",            "ターン開始時:")
        text = text.replace("at:afterStartOfTurn",       "ターン開始後:")
        text = text.replace("at:endOfTurn",              "ターン終了時:")

        # ── target: ─────────────────────────────────────────────────────────
        text = re.sub(r"target:mental\s*\{",             "精神カード対象: [", text)
        text = re.sub(r"target:active\s*\{",             "アクティブカード対象: [", text)
        text = re.sub(r"target:effect\(fullPowerCharge\)", "全力効果カード対象:", text)

        # ── limit ───────────────────────────────────────────────────────────
        text = re.sub(r"\blimit:(\d+)\b",                r"（最大\1回）", text)

        # ── out-game DSL（サポカアビリティ）────────────────────────────────
        text = re.sub(r"@passive:\s*vi_lesson_bonus\+\{v\}",  "常時: Viレッスンボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*da_lesson_bonus\+\{v\}",  "常時: Daレッスンボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*vo_lesson_bonus\+\{v\}",  "常時: Voレッスンボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*vo_bonus\+\{v\}",         "常時: Voボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*da_bonus\+\{v\}",         "常時: Daボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*vi_bonus\+\{v\}",         "常時: Viボーナス+{v}%", text)
        text = re.sub(r"@passive:\s*self_lesson_support_rate\+\{v\}", "常時: サポート発生率+{v}%", text)
        text = re.sub(r"@passive:\s*self_event_param_bonus\+\{v\}",   "常時: イベント効果アップ+{v}%", text)
        text = re.sub(r"@passive:\s*coin\+\{v\}",             "常時: Pポイント+{v}", text)
        text = re.sub(r"@passive:\s*hp\+\{v\}",               "常時: 体力+{v}", text)
        text = re.sub(r"@init:\s*coin\+\{v\}",                "プロデュース開始時: Pポイント+{v}", text)
        text = re.sub(r"@init:\s*hp\+\{v\}",                 "プロデュース開始時: 体力+{v}", text)
        text = re.sub(r"@sp_lesson_end\(type=vocal\):\s*hp\+\{v\}",   "VoのSPレッスン終了時: 体力+{v}", text)
        text = re.sub(r"@sp_lesson_end\(type=dance\):\s*hp\+\{v\}",   "DaのSPレッスン終了時: 体力+{v}", text)
        text = re.sub(r"@sp_lesson_end\(type=visual\):\s*hp\+\{v\}",  "ViのSPレッスン終了時: 体力+{v}", text)
        text = re.sub(r"@lesson_end\(type=vocal\):\s*vo\+\{v\}",      "Voレッスン終了時: Vo+{v}", text)
        text = re.sub(r"@lesson_end\(type=dance\):\s*da\+\{v\}",      "Daレッスン終了時: Da+{v}", text)
        text = re.sub(r"@lesson_end\(type=visual\):\s*vi\+\{v\}",     "Viレッスン終了時: Vi+{v}", text)
        text = re.sub(r"@rest_end:\s*vo\+\{v\}",              "お休み終了時: Vo+{v}", text)
        text = re.sub(r"@rest_end:\s*da\+\{v\}",              "お休み終了時: Da+{v}", text)
        text = re.sub(r"@rest_end:\s*vi\+\{v\}",              "お休み終了時: Vi+{v}", text)
        text = re.sub(r"@event:\s*([a-zA-Z]+)\+(\d+)",        r"イベント: \1+\2", text)

        # ── 残留 DSL プレフィックスのクリーンアップ ──────────────────────────
        text = re.sub(r"\bg\.([a-zA-Z]+)", r"\1", text)
        text = re.sub(r"\bmental\b", "メンタル", text, flags=re.IGNORECASE)
        text = re.sub(r"\bactive\b", "アクティブ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bdelay\b", "遅延", text, flags=re.IGNORECASE)

        # ── 括弧・区切り文字の整形 ──────────────────────────────────────────
        text = text.replace("{", "").replace("}", "")
        text = text.replace(";", " / ")
        text = re.sub(r"\[\s*\]", "", text)
        text = re.sub(r"\s{2,}", " ", text)
        text = text.strip().strip("/ ").strip()

        return text


# 後方互換性のためモジュールレベル関数も提供
_translator = DslTranslator()


def format_dsl_to_jp(dsl: str) -> str:
    """DSL文字列をゲーム内の自然な日本語テキスト（絵文字付き）に変換する（後方互換）"""
    return _translator.translate(dsl)
