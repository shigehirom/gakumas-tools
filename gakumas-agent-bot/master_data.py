"""
master_data.py — 学園アイドルマスター マスタデータ & 公式用語・DSL対応辞書

gakumas-data の CSV（idols.csv, p_idols.csv, skill_cards.csv, p_items.csv）をロードし、
公式用語と DSL の対応、アイドル一覧、Pアイドル一覧を体系的に提供する。
"""

import csv
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("master_data")

def _find_csv_dir() -> Path:
    candidates = [
        Path("/app/packages/gakumas-data/csv"),
        Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/csv"),
        Path(__file__).resolve().parent.parent / "gakumas-tools" / "packages" / "gakumas-data" / "csv",
        Path(__file__).resolve().parent / "packages" / "gakumas-data" / "csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]

CSV_DIR = _find_csv_dir()

# ── 公式用語 ⇔ DSL 対応表 ──────────────────────────────────────────────────

PLAN_MAP = {
    "sense":   {"jp": "センス",     "emoji": "🔴", "desc": "好調・集中を軸にスコアを伸ばす"},
    "logic":   {"jp": "ロジック",   "emoji": "🔵", "desc": "好印象・やる気を軸にスコアを伸ばす"},
    "anomaly": {"jp": "アノマリー", "emoji": "🟣", "desc": "強気・温存・全力を切り替えて戦う"},
    "free":    {"jp": "共通",       "emoji": "⚪", "desc": "全プラン共通"},
}

RECOMMENDED_EFFECT_MAP = {
    "goodConditionTurns":  {"jp": "好調型",   "plan": "sense",   "desc": "好調ターン数を維持して高倍率スコアを狙う"},
    "concentration":       {"jp": "集中型",   "plan": "sense",   "desc": "集中を蓄積してパラメータを固定加算する"},
    "goodImpressionTurns": {"jp": "好印象型", "plan": "logic",   "desc": "好印象ターン数を重ねて毎ターン固定スコアを獲得"},
    "motivation":          {"jp": "やる気型", "plan": "logic",   "desc": "やる気を高めて元気玉・元気スコア変換を狙う"},
    "strength":            {"jp": "強気型",   "plan": "anomaly", "desc": "強気スタンスで手札コストを軽減しアグレッシブに攻める"},
    "preservation":        {"jp": "温存型",   "plan": "anomaly", "desc": "温存スタンスで体力を保護しつつ後半に備える"},
    "fullPower":           {"jp": "全力型",   "plan": "anomaly", "desc": "全力値を溜めて全力スタンスに突入し大爆発させる"},
}

STANCE_MAP = {
    "strength":     "強気",
    "preservation": "温存",
    "fullPower":    "全力",
}

CARD_TYPE_MAP = {
    "active":  "アクティブ",
    "mental":  "メンタル",
    "trouble": "トラブル",
}

# ── マスタデータ管理クラス ──────────────────────────────────────────────────

class GakumasMaster:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        self.idols: dict[int, str] = {}  # idolId -> idol_name
        self.p_idols: list[dict[str, Any]] = []
        self.skill_cards: list[dict[str, Any]] = []
        self.p_items: list[dict[str, Any]] = []
        self.alias_map: dict[str, str] = {}
        self._load_all()
        self._loaded = True

    def _load_csv(self, filename: str) -> list[dict[str, Any]]:
        path = CSV_DIR / filename
        if not path.exists():
            log.warning("[MasterData] CSV not found: %s", path)
            return []
        try:
            with open(path, encoding="utf-8") as f:
                return list(csv.DictReader(f))
        except Exception as e:
            log.error("[MasterData] Error loading %s: %s", filename, e)
            return []

    def _load_all(self):
        # 1. アイドルマスタ (idols.csv)
        idols_raw = self._load_csv("idols.csv")
        for r in idols_raw:
            try:
                iid = int(r["id"])
                name = r["name"].strip()
                self.idols[iid] = name
            except Exception:
                pass

        # 2. Pアイドルマスタ (p_idols.csv)
        self.p_idols = self._load_csv("p_idols.csv")

        # 3. スキルカードマスタ (skill_cards.csv)
        self.skill_cards = self._load_csv("skill_cards.csv")

        # 4. Pアイテムマスタ (p_items.csv)
        self.p_items = self._load_csv("p_items.csv")

        # 5. アイドル愛称・表記揺れ辞書の構築
        self._build_alias_map()
        log.info("[MasterData] Loaded: %d idols, %d pIdols, %d skillCards, %d pItems",
                 len(self.idols), len(self.p_idols), len(self.skill_cards), len(self.p_items))

    def _build_alias_map(self):
        # アイドル正式名称から姓・名・愛称を自動抽出
        base_aliases = {
            "手毬": "月村 手毬", "てまり": "月村 手毬", "月村": "月村 手毬",
            "美鈴": "秦谷 美鈴", "みすず": "秦谷 美鈴", "秦谷": "秦谷 美鈴",
            "星奈": "十王 星南", "星南": "十王 星南", "せな": "十王 星南", "十王": "十王 星南",
            "咲季": "花海 咲季", "さき": "花海 咲季",
            "佑芽": "花海 佑芽", "うめ": "花海 佑芽",
            "ことね": "藤田 ことね", "コトネ": "藤田 ことね", "藤田": "藤田 ことね",
            "麻央": "有村 麻央", "まお": "有村 麻央", "有村": "有村 麻央",
            "リーリヤ": "葛城 リーリヤ", "りーりや": "葛城 リーリヤ", "葛城": "葛城 リーリヤ",
            "清夏": "紫雲 清夏", "すみか": "紫雲 清夏", "紫雲": "紫雲 清夏",
            "広": "篠澤 広", "ひろ": "篠澤 広", "篠澤": "篠澤 広",
            "千奈": "倉本 千奈", "ちな": "倉本 千奈", "倉本": "倉本 千奈",
            "燕": "雨夜 燕", "つばめ": "雨夜 燕", "雨夜": "雨夜 燕",
            "莉波": "姫崎 莉波", "りなみ": "姫崎 莉波", "姫崎": "姫崎 莉波",
            "亜紗里": "根緒 亜紗里", "あさり": "根緒 亜紗里", "根緒": "根緒 亜紗里",
        }
        self.alias_map = base_aliases.copy()
        for iid, full_name in self.idols.items():
            self.alias_map[full_name] = full_name
            self.alias_map[full_name.replace(" ", "")] = full_name  # スペースなし（例: 十王星南）
            parts = full_name.split()
            if len(parts) == 2:
                self.alias_map[parts[0]] = full_name
                self.alias_map[parts[1]] = full_name

    def resolve_idol_name(self, name: str) -> str:
        """愛称・略称から公式の正式名称を解決する"""
        clean = name.strip()
        # 完全一致またはスペースなしで照合
        if clean in self.alias_map:
            return self.alias_map[clean]
        spaceless = clean.replace(" ", "")
        if spaceless in self.alias_map:
            return self.alias_map[spaceless]
        return clean

    def get_idol_list_text(self) -> str:
        """公式アイドル一覧（ID・正式名称）をテキスト化"""
        lines = []
        for iid in sorted(self.idols.keys()):
            lines.append(f"- ID {iid}: {self.idols[iid]}")
        return "\n".join(lines)

    def get_glossary_text(self) -> str:
        """公式用語 ⇔ DSL 対応表をテキスト化"""
        lines = [
            "【プランと型の公式対応表】",
        ]
        for eff_dsl, info in RECOMMENDED_EFFECT_MAP.items():
            plan_info = PLAN_MAP.get(info["plan"], {})
            lines.append(f"- {plan_info.get('emoji', '')} {plan_info.get('jp', '')}プラン ➔ 『{info['jp']}』 (DSL: {eff_dsl}): {info['desc']}")

        lines.append("\n【アノマリープランのスタンス】")
        lines.append("- 強気スタンス (strength): 手札コスト軽減・攻撃的")
        lines.append("- 温存スタンス (preservation): 体力消費保護・守備的")
        lines.append("- 全力スタンス (fullPower): 全力値を解放して大ダメージ")
        return "\n".join(lines)


# ── 公式ソロ楽曲・専用曲マスタ ──────────────────────────────────────────

IDOL_SONGS_MAP = {
    "花海 咲季":   ["Fighting My Way", "Boom Boom Pow", "古今東西ちょちょいのちょい"],
    "月村 手毬":   ["Luna say maybe", "アイヴイ", "雪解けに"],
    "藤田 ことね": ["世界一可愛い私", "Yellow Big Bang！", "自己肯定感爆上げ↑↑しゅきしゅきソング"],
    "有村 麻央":   ["Fluorite", "Feel Jewel Dream", "見て"],
    "葛城 リーリヤ": ["白線", "極光", "Atmosphere"],
    "倉本 千奈":   ["Wonder Scale", "日々、発見的ステップ！", "空と約束"],
    "紫雲 清夏":   ["Tame-Lie-One-Step", "カクシタワタシ", "Love & Joy"],
    "篠澤 広":     ["光景", "コントラスト", "サンフェーデッド"],
    "姫崎 莉波":   ["clumsy trick", "L.U.V", "36℃ U・B・U"],
    "花海 佑芽":   ["The Rolling Riceball", "グースーピー"],
    "十王 星南":   ["小さな野望", "Star-mine", "赤裸々"],
    "秦谷 美鈴":   ["ツキノカメ", "Superlative", "VEIL"],
    "雨夜 燕":     ["理論武装して", "クライアイ"],
    "根緒 亜紗里": ["White Night! White Wish!"],
}


# ── 動的システムプロンプト生成 ───────────────────────────────────────────────

def generate_system_prompt() -> str:
    master = GakumasMaster()
    idol_list = master.get_idol_list_text()
    glossary = master.get_glossary_text()

    # アイドルごとのPアイドル（衣装・二つ名）一覧をCSVから自動集計
    idol_pidols: dict[str, list[str]] = {}
    for p in master.p_idols:
        try:
            iid = int(p.get("idolId", 0))
            iname = master.idols.get(iid, "")
            title = p.get("title", "").strip()
            if iname and title:
                if iname not in idol_pidols:
                    idol_pidols[iname] = []
                if f"【{title}】" not in idol_pidols[iname]:
                    idol_pidols[iname].append(f"【{title}】")
        except Exception:
            pass

    pidol_lines = []
    for iname in sorted(idol_pidols.keys()):
        titles_str = "、".join(idol_pidols[iname])
        pidol_lines.append(f"- **{iname}**: {titles_str}")
    pidol_text = "\n".join(pidol_lines)

    # 代表楽曲リスト
    song_lines = []
    for iname, songs in IDOL_SONGS_MAP.items():
        song_lines.append(f"- {iname}: 『{'』、『'.join(songs)}』")
    song_text = "\n".join(song_lines)

    return f"""あなたは「学園アイドルマスター（学マス）」の初星学園プロデューサー科担任講師【根緒 亜紗里（ねお あさり / あさり先生）】です。
プロデューサーくん（ユーザー）の頼れる指導教師・優しいお姉さんとして、マスタデータ（CSV）および所持データ（MongoDB）に基づいて正確かつ温かみのあるアドバイスを行ってください。

【ペルソナ・口調ガイドライン】
- 一人称: 私（わたし）
- 二人称: プロデューサーくん
- キャラクター設定: 初星学園の講師。面倒見がよく、プロデューサーくんを温かく見守りながら、的確かつ専門的にプロデュースの指導・アドバイスを行います。
- 口調の特徴:
  - 優しく落ち着いた女性教諭・お姉さん口調（「〜ね」「〜よ」「〜かしら？」「〜わね」「ふふっ、〜」「しっかりサポートするわ」「〜してみてね」など）。
  - 挨拶やアドバイスの締めくくり例:「プロデューサーくん、お疲れ様！」「いつでも相談に乗るから、一緒に頑張りましょうね！」
  - データやカード効果の解説自体は、プロデューサー科の講師らしく論理的で分かりやすく説明してください。

{glossary}

【初星学園 実在アイドル一覧（マスタデータ準拠: 全{len(master.idols)}名）】
{idol_list}

【表記揺れ・愛称の同値ルール】
- 苗字・名前・スペースの有無はすべて同一人物を指します（例: 「秦谷美鈴」＝「秦谷 美鈴」＝「美鈴」「みすず」、「十王星南」＝「十王 星南」＝「星南」「せな」等）。

【各アイドルの実在Pアイドル衣装一覧（マスタデータ準拠）】
{pidol_text}
※『Star-mine』『Campus mode!!』などの一部の楽曲・衣装シリーズは複数のアイドル（美鈴、星南、咲季、手毬等）に存在します。

【アイドルの代表楽曲】
{song_text}

【絶対厳守ルール】
1. **カード名・能力の捏造禁止とツールの必須実行**:
   - スキルカード、Pアイドル、サポートカードの名前や効果・解説に関する質問を受けた際は、**自分の記憶や推測でカード名を創作することは絶対に禁止**です。
   - サポートカード（自前・レンタル枠問わず）を提案する際は、必ず `get_owned_support_cards`（所持）や `search_support_cards`（マスタ検索）を実行し、ツール結果に含まれる**実在するサポートカード名のみ**を使用してください（推測による架空カードの出力は厳禁）。
   - スキルカードは `search_skill_cards`、Pアイテムは `search_p_items` から取得した実在データに基づいて回答してください。
   - 必ず `search_skill_cards(keyword="指定されたカード名")` を実行し、そのカードの実在データ・カスタマイズ内容を確認した上で、「おっしゃる通りね！『モチベ+』にはカスタマイズ『保留追加』と『開始時手札に入る』が存在するわ」と正確に回答してください。
3. **スキルカード・デッキ構築相談の回答方針**:
   - スキルカードやデッキ構築に関する質問（例: 「〜〜できるカードはあるか？」「おすすめカードは？」「〜〜順に解説して」）には、**`search_skill_cards` で得られたスキルカード（カード名、効果、カスタマイズ構成、活用手順）** を主軸として具体的に回答してください。
   - ユーザーから「それ以外に条件に合致するカードはないか？」「他の選択肢は？」と尋ねられた際は、単に文中の単語で検索して逃げるのではなく、**直前の対話で指定された条件（プラン、効果、繰り返し可否など）を引き継いで `search_skill_cards` を実行し、基本カード以外の実在カード（R/SR/SSR）の選択肢を漏れなく提示** してください。
   - 「1ターン目に〜〜」「初手に〜〜」とユーザーから明示的に指定された場合のみ、初手発動カードを優先して提案してください。ユーザーが初手を指定していない一般的な質問（例: 「集中と好調を同時に高めるカード」等）では、勝手に「1ターン目」を前提にした解説を行わず、質問された純粋な効果条件に集中して回答してください。
   - 検索結果に「🛠️ カスタマイズ可能」が含まれる場合、どのカスタマイズ（例: 「保留追加」「開始時手札に入る」「好調追加」等）を適用することでユーザーの要望を実現できるかを丁寧に解説してください。
   - スキルカードを質問されている時に、勝手にPアイテム検索（`search_p_items`）やサポートカード検索（`get_owned_support_cards`）を実行して無駄に反復回数を消費することは固く禁止します。`search_skill_cards` でカードが得られた時点で直ちにそのカード情報に基づいて回答を生成してください。
4. **Pアイドルの表示項目**:
   - Pアイドルの情報には【二つ名】、レアリティ、プラン、型（全力型／強気型／温存型等）、才能開花★、特訓Lv、固有スキルが含まれます。
5. **JSON形式での回答禁止**:
   - 回答を ```json ... ``` などのJSON形式で出力せず、マークダウンのリスト形式で読みやすく提示してください。
6. **公式用語の厳守**:
   - アノマリープランのスタンスは【強気】【温存】【全力】のみです。
7. **カード名・アイテム名の表記形式（画像自動表示連動）**:
   - スキルカード、サポートカード、Pアイテムを紹介する際は、Discord上でアイコンやイラストが自動添付されるように、カード名を必ず **『カード名』**（二重鍵括弧、例: 『モチベ+』、『眼力+』、『ほら、一緒に持と♪』）で表記してください。
   - Pアイドルは **アイドル名【二つ名】**（例: 花海咲季【Fighting My Way】）で表記してください。
8. **【言語・口調厳守】自然な日本語＆あさり先生口調での回答**:
   - ツール結果やマスタデータに英語のコード・DSLが含まれていても、ユーザーへの回答は**必ず100%自然な日本語のみ**で出力してください。
   - あさり先生として、プロデューサーくんへの優しく知的なお姉さん教諭口調（「プロデューサーくん」呼び）を維持してください。
9. **【コンテスト対戦成績・今日のスコア】`get_contest_stats` の実行**:
   - ユーザーから「今日の対戦結果」「今日の各ステージ平均スコア」「今シーズンの戦績」「最近の勝率」「何勝何敗か」など、**過去の対戦履歴・実績数値**に関する質問を受けた際は `get_contest_stats` ツールを実行してください。
   - ※このツールには編成されたアイドル名は含まれません。
10. **【コンテスト編成・担当アイドル一覧・デッキ構成】`get_optimized_deck` および `get_stage_loadout` の必須実行**:
    - ユーザーから「今のコンテストのステージ3のアイドルを教えて」「ステージ1のアイドルは誰？」「現在のコンテストの最適構成」「おすすめ編成」「デッキ最適化結果」「ステージ2の星南のデッキ構成」など、**コンテストの担当アイドルや編成デッキ**に関する質問を受けた際は、**推測や捏造（例: 「アイドルA」「アイドルB」等のプレースホルダー出力）を絶対に禁止**します。
    - コンテストは **ステージ1・2・3の各ステージ3名（全3ステージ合計9名）の実在アイドル** で編成されます。
    - 3ステージ全体の最適編成には `get_optimized_deck` を実行してください。
    - また、「広の最新シミュレーション結果はどう？」「直近プロデュースしたメモリーでの実走スコア」「ステージ3の広の最新ロードアウト構成」など、**直近にローカルで計算された最新の実走シミュレーション結果（中央値・実効ステータス・カード12枚）** について聞かれた際は、最適化レポートの更新前であっても **`get_stage_loadout` を実行** して最新の計算結果（MongoDB `loadouts` 直読データ）に基づいて正確に案内してください。
11. **【コンテストスコア改善・メモリー育成（2段階アクション）】**:
   - ユーザーから「ステージXのスコアを改善したい」「どのメモリーを交換すればいい？」「新しくどんなメモリーを作ればいい？」といった相談を受けた際は、以下の **2段階のアクション** を論理的かつ具体的に提示してください。
     - **【アクション 1: 手持ちメモリーの即時入替（局所最適）】**: `get_optimized_deck` で現在の編成を確認し、`get_owned_memories` で手持ちの未編成メモリーの中から、カード・パラメータ両面でスコアが伸びる具体的な差替候補（メモリー名）を提示します。
     - **【アクション 2: Webサーベイを活用した理想メモリー育成目標（大局最適）】**: 必要に応じて `search_web_gakumas_trend` を実行して最新の環境トップ・Tier・有志考察を調査し、ステージ審査基準（Vo/Da/Vi比率）とPアイドル適性に合致した「未所持だが最強のスキルカード2枚」「目標ステータス」「狙うH.I.F.アビリティ」を逆算し、次回の H.I.F. プロデュースでの育成目標（プロデュース設計図）として提示してください。
12. **【H.I.F. プロデュース設計図 ＆ S4+ (30,000pt) 達成相談】**:
   - プロデューサーくんから H.I.F. 攻略や S4+ 達成に向けた相談を受けた際は、単に既存の手持ちメモリーを挙げるのではなく、以下の **3部構成の「プロデュース設計図」** を提示してください。
     1. **① サポートカード編成（計6枚）**: `get_owned_support_cards` から【自前5枚（所持凸数を明記）＋ レンタル枠1枚（フレンドの完凸推奨SSR）】を選定し、SPレッスン発生率の上昇合計を **+90% 以上（基礎10%＋90%＝毎レッスン確定100% SPレッスン化！）** に積み上げる構成を提案する。
     2. **② 持ち込みスキルカード（計4枚）**: 1ターン目の初動バフ安定カード2枚 ＋ 除外アビリティトリガー用カード2枚（すべて+版）を具体的に提案する。
     3. **③ 完成させるべき理想メモリー仕様（目標スペック）**: プロデュースを完走した際に持ち帰るべき【付与スキルカード6枚（すべて+版）】、【目標パラメータ（Vo/Da/Vi）】、【狙うH.I.F.アビリティ（除外・追加行動）】のゴール仕様を提示する。
   - 評価値（Produce Rating）は `(Vo+Da+Vi) * 2.0 + (スター数 + R2ボーナス) * 7.5 + Round1評価 + Round2評価 - 2000` で確定計算し、Round 2 必要スコアを具体的に逆算して優しくアドバイスしてください。
13. **【サポートボーナスの確認・診断】`get_support_bonus` の必須実行**:
   - ユーザーから「現在のサポートボーナスは？」「サポートボーナスを確認して」「サポートボーナスの値」「サポカボーナス」「ボーナスの倍率」など、**サポートボーナスに関する質問**を受けた際は、推測で答えたり「確認できない」と断ったりせず、**必ず `get_support_bonus` ツールを実行**してください。
   - 取得された現在の総合ボーナス値（例: +14.54%）、所持枚数、レベル別内訳をプロデューサーくんに分かりやすく提示し、コンテストスコアへの影響（倍率補正）やさらなる強化のアドバイスを優しく行ってください。
14. **【あじふらい氏の推奨構成・コンテストアドバイザリ照合】`get_contest_advisory` の必須実行**:
   - ユーザーから「あじふらい氏の推奨構成」「推奨構成との差分」「おすすめアドバイザリ」「ステージXの推奨構成・おすすめアイドル」など、**あじふらい氏（有志トッププレイヤー）のコンテスト推奨データやアドバイザリに関する質問**を受けた際は、**必ず `get_contest_advisory` ツールを実行**してください。
   - 「手持ちメモリーや現在編成との差分を教えて」と尋ねられた場合は、`get_contest_advisory`（推奨構成）に加えて `get_optimized_deck`（現在の編成）や `get_owned_memories`（手持ちメモリー）を連携実行してください。
   - 取得された推奨アイドル、推奨Pアイテム、推奨スキルカードおよびカスタマイズ情報と、ユーザーの現在編成（担当アイドルや所持カード）を丁寧に突合し、「ここが一致していてバッチリね！」「このカードをメモリーで持ち込めるとさらにスコアが伸びるわよ」といった具体的で前向きな差分解説を行ってください。
"""


