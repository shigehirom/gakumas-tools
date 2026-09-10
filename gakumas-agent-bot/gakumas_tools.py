"""
gakumas_tools.py — 学園アイドルマスター エージェント用ツール層

LLM（Qwen / Gemini）の tool_calls に応じて呼び出される関数群を管理する。
各ツール関数は「日本語化済みの文字列」を返す（LLM に生 DSL を見せない）。

TOOLS_SCHEMA: Ollama / OpenAI 互換 JSON Schema 定義
GakumasToolExecutor: ツール名 → 実行のディスパッチャ
"""

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

import pymongo

from dsl_translator import DslTranslator

# ── .env 読み込み ────────────────────────────────────────────────────────────
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

DATA_DIR = _find_dir([
    Path("/app/packages/gakumas-data/csv"),
    Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/csv"),
    WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-data" / "csv",
    WORKSPACE_DIR / "packages" / "gakumas-data" / "csv",
])

INSTRUCTIONS_DIR = _find_dir([
    Path("/app/agent-instructions"),
    Path("/root/gakumas-workspace/shared/agent-instructions"),
    WORKSPACE_DIR / "shared" / "agent-instructions",
    WORKSPACE_DIR / "agent-instructions",
])

def _load_env() -> None:
    env_paths = [
        Path("/app/.env.local"),
        Path("/app/.env"),
        WORKSPACE_DIR / "gakumas-agent-bot" / ".env",
        WORKSPACE_DIR / "gakumas-tools" / ".env.local",
        WORKSPACE_DIR / ".env"
    ]
    for env_file in env_paths:
        if env_file.exists():
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    if "#" in line:
                        line = line.split("#", 1)[0].strip()
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v

_load_env()

# ── 定数 ────────────────────────────────────────────────────────────────────

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://192.168.100.4:27017")
MONGODB_DB  = os.environ.get("MONGODB_DB", "gakumas-tools")

PLAN_EMOJI = {"free": "⚪", "sense": "🔴", "logic": "🔵", "anomaly": "🟣"}
TYPE_LABEL = {"active": "⬢ Active", "mental": "🔵 Mental", "trouble": "⚠️ Trouble"}
RARITY_WEIGHT = {"SSR": 3, "SR": 2, "R": 1}

MAX_TOOL_RESULT_CHARS = 2000  # ツール結果のトークン制限（文字数上限）

# ── TOOLS_SCHEMA（Ollama / OpenAI 互換 JSON Schema）──────────────────────────

TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_skill_cards",
            "description": (
                "学マスのスキルカードをマスタデータから条件検索する。"
                "プラン（sense/logic/anomaly/free/any）、カード種類（active/mental/trouble/any）、"
                "効果種別（goodConditionTurns/concentration/perfectConditionTurns/goodImpressionTurns/motivation/enthusiasm/fullPower/genki/score/draw/strength/preservation/any）、"
                "繰り返し可否、キーワードを組み合わせて検索できる。"
                "結果にはカード名・レアリティ・コスト・効果（日本語）・カスタマイズ情報が含まれる。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "string",
                        "enum": ["sense", "logic", "anomaly", "free", "any"],
                        "description": "対象プラン（センス=sense、ロジック=logic、アノマリー=anomaly、指定なし=any）。「センスタイプ」等の質問には必ず 'sense' を指定してください。",
                    },
                    "card_type": {
                        "type": "string",
                        "enum": ["active", "mental", "trouble", "any"],
                        "description": "カード種類（アクティブ=active、メンタル=mental。ユーザーがアクティブ限定/メンタル限定と指定しない限り 'any' を指定してください）",
                    },
                    "effect_type": {
                        "type": "string",
                        "enum": [
                            "goodConditionTurns", "concentration", "perfectConditionTurns",
                            "goodImpressionTurns", "motivation", "enthusiasm",
                            "fullPower", "strength", "preservation", "genki", "score", "draw", "hold", "any",
                        ],
                        "description": "主な効果種別（好調=goodConditionTurns、集中=concentration、絶好調=perfectConditionTurns、好印象=goodImpressionTurns、やる気=motivation、元気=genki、スコア=score、全力=fullPower、強気=strength、温存=preservation、保留=hold）",
                    },
                    "is_repeatable": {
                        "type": "boolean",
                        "description": "true: 繰り返し使用可能カードのみ（ユーザーが「繰り返し使える」と指定した場合のみ true を渡してください。指定がない場合はこの引数は省略してください）",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "カード名や効果文への部分一致キーワード（任意）",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返す最大件数（1〜40、デフォルト20）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_p_items",
            "description": (
                "学マスのPアイテムをマスタデータから条件検索する。"
                "プラン・効果種別・キーワードでフィルタリングできる。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "string",
                        "enum": ["anomaly", "sense", "logic", "free", "any"],
                    },
                    "effect_type": {
                        "type": "string",
                        "enum": ["fullPower", "genki", "score", "draw", "any"],
                        "description": "主な効果種別",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "アイテム名・効果文への部分一致キーワード",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返す最大件数（デフォルト15）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_owned_p_idols",
            "description": (
                "ユーザーが所持しているPアイドル一覧をMongoDBから取得する。"
                "アイドル名ごとにグループ化・レアリティ降順でソートされた結果を返す。"
                "才能開花★・特訓レベル・プラン・レアリティを含む。"
                "コスト・効果などPアイドルに存在しない項目は含まない。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "string",
                        "enum": ["anomaly", "sense", "logic", "any"],
                        "description": "絞り込むプラン。全て対象なら 'any'",
                    },
                    "idol_name": {
                        "type": "string",
                        "description": "アイドル名で絞り込む（例: '花海 咲季'、愛称・複数名指定も可）",
                    },
                    "effect_type": {
                        "type": "string",
                        "description": "型・タイプで絞り込む（fullPower/全力型, strength/強気型, preservation/温存型, goodConditionTurns/好調型, concentration/集中型, goodImpressionTurns/好印象型, motivation/やる気型, any）",
                    },
                    "rarity": {
                        "type": "string",
                        "enum": ["SSR", "SR", "R", "any"],
                    },
                    "min_talent": {
                        "type": "integer",
                        "description": "才能開花の最低段階（★0〜4）でフィルタ",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_p_idol_details",
            "description": (
                "特定のPアイドルの詳細能力・固有スキル・型・所持育成状況を取得する。"
                "アイドル名（例: '十王 星南'）やタイトル・楽曲名・二つ名（例: 'ねえ、言っちゃうよ。', 'Star-mine'）で検索できる。"
                "Pアイドルの能力やスキル、特徴を聞かれた際はこちらを使用する。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "idol_name": {
                        "type": "string",
                        "description": "アイドル名（例: '十王 星南', '月村 手毬'、愛称も可）",
                    },
                    "title": {
                        "type": "string",
                        "description": "Pアイドルのタイトル・二つ名・楽曲名（例: '「ねえ、言っちゃうよ。」', '小さな野望' 等）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_owned_support_cards",
            "description": (
                "ユーザーが所持しているサポートカード一覧をMongoDBから取得する。"
                "凸数・レアリティ・習得可能スキルカード名でフィルタ可能。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rarity": {
                        "type": "string",
                        "enum": ["SSR", "SR", "R", "any"],
                    },
                    "min_uncap": {
                        "type": "integer",
                        "description": "最低上限解放数でフィルタ（4=完凸のみ）",
                    },
                    "target_skill": {
                        "type": "string",
                        "description": "習得可能スキルカード名でフィルタ（部分一致）",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "カード名への部分一致キーワード",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返す最大件数（デフォルト20）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_support_bonus",
            "description": (
                "現在ユーザーが所持しているサポートカード群から算出される最新のサポートボーナス値（%および倍率補正）と、"
                "所持枚数・レベル別内訳、コンテストでの効果、ボーナス底上げのアドバイスを取得する。"
                "「サポートボーナス」「サポカボーナス」「ボーナスの値」「サポートボーナスは確認できる？」などの質問には必ずこのツールを実行する。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_owned_memories",
            "description": (
                "ユーザーの所持メモリー一覧および枚数をMongoDBから取得する。"
                "「〇〇のメモリーは何枚ある？」「秦谷美鈴のメモリー一覧」「Star-mineのメモリー」などの質問には必ずこのツールを実行する。"
                "アイドル名、Pアイドル衣装名（二つ名）、プラン、付与スキルカード名で絞り込み可能。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "idol_name": {
                        "type": "string",
                        "description": "アイドル名で絞り込み（例: '秦谷 美鈴', '美鈴', '篠澤 広', '手毬'）",
                    },
                    "p_idol_name": {
                        "type": "string",
                        "description": "Pアイドル衣装名・二つ名で絞り込み（例: 'Star-mine', 'ツキノカメ', 'ガラクタロード', 'Campus mode!!'）",
                    },
                    "plan": {
                        "type": "string",
                        "enum": ["sense", "logic", "anomaly", "any"],
                        "description": "プラン（タイプ）で絞り込み",
                    },
                    "card_name": {
                        "type": "string",
                        "description": "付与スキルカード名でフィルタ（例: '国民的アイドル', '静かな意志'）",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "メモリー名や衣装名への部分一致キーワード",
                    },
                    "min_param": {
                        "type": "integer",
                        "description": "総パラメータ合計の下限",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返す最大件数（デフォルト15）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_contest_stats",
            "description": (
                "過去のコンテスト対戦履歴（勝敗、勝率、対戦相手名、獲得Pt、実際の対戦スコア実績・平均スコア）を集計して返す。"
                "「今日の対戦結果」「今日の各ステージ平均スコア」「最新の対戦」「シーズン50の戦績・勝率」などの対戦成績の質問にのみ使用する。"
                "【重要】このツールに対戦で使用したアイドル名や編成デッキは含まれません。編成されたアイドル名やデッキ構成を知りたい場合は絶対にこのツールではなく 'get_optimized_deck' を実行してください。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "season": {
                        "type": "integer",
                        "description": "対象シーズン番号（例: 50）。省略すると最新シーズン",
                    },
                    "date": {
                        "type": "string",
                        "description": "特定の日付で絞り込む場合（'today', '今日', '26/08/21', '8/21' など。今日の対戦を聞かれた場合は 'today' を指定）",
                    },
                    "season_start": {
                        "type": "integer",
                        "description": "複数シーズン比較の開始番号",
                    },
                    "season_end": {
                        "type": "integer",
                        "description": "複数シーズン比較の終了番号",
                    },
                    "recent_count": {
                        "type": "integer",
                        "description": "直近N戦を詳細表示する件数（デフォルト5）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_support_card_details",
            "description": (
                "サポートカードのアビリティや効果詳細（各上限解放ごとのボーナス値、サポート効果、イベント効果など）をマスタデータから取得する。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {
                        "type": "string",
                        "description": "サポートカード名（完全一致または部分一致、例: 'ほら、一緒に持と？'）",
                    },
                },
                "required": ["card_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_optimized_deck",
            "description": (
                "現在開催中のコンテスト向け編成・担当アイドル一覧・デッキ構成を取得する。"
                "「今のコンテストのステージ3のアイドルを教えて」「ステージ1のアイドルは誰？」「現在のコンテストの最適構成」「おすすめ編成」「デッキ最適化結果」などの質問には必ずこのツールを実行する。"
                "各ステージ3名（全3ステージ合計9名）のアイドル名、メイン/サブメモリー、期待中央値スコアを返す。"
                "特定のアイドル（例: '十王 星南'）を指定すると、そのアイドルが採用している全スキルカード12枚（カスタム付き）、Pアイテム、ステータス詳細も取得できる。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "integer",
                        "description": "特定のステージ番号（1, 2, 3）。ステージ3のアイドルを聞かれた場合は 3 を指定。全ステージ（9名）を見る場合は省略（null）",
                    },
                    "idol_name": {
                        "type": "string",
                        "description": "特定のアイドルの詳細デッキ構成（スキルカード12枚・Pアイテム）を取得したい場合のアイドル名（例: '十王 星南', '星南', '篠澤 広'）",
                    },
                },
                "required": [],
            },
        },
    },
]


# ── GakumasToolExecutor ───────────────────────────────────────────────────────

class GakumasToolExecutor:
    """
    LLM tool_calls のディスパッチャ。
    各ツール関数を同期で実行し、日本語化済みの文字列を返す。
    """

    def __init__(self) -> None:
        self._dsl = DslTranslator()
        self._skill_cards: list[dict[str, Any]] = []
        self._p_items: list[dict[str, Any]] = []
        self._customizations: dict[str, dict[str, Any]] = {}
        self._support_cards_master: list[dict[str, Any]] = []
        self._match_histories: dict[str, list[dict[str, Any]]] = {}
        self._db: Any = None
        self._load_csv_data()
        self._init_mongo()

    # ── 初期化 ───────────────────────────────────────────────────────────────

    def _load_csv_data(self) -> None:
        for fname, attr in [
            ("skill_cards.csv", "_skill_cards"),
            ("p_items.csv",     "_p_items"),
        ]:
            path = DATA_DIR / fname
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    setattr(self, attr, list(csv.DictReader(f)))

        # カスタマイズマスタの読み込み
        custom_csv = DATA_DIR / "customizations.csv"
        if custom_csv.exists():
            with open(custom_csv, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    cid = r.get("id", "").strip()
                    if cid:
                        self._customizations[cid] = r

        # サポートカード詳細マスタの読み込み
        sc_paths = [
            WORKSPACE_DIR / "gakumas-support_cards" / "support_cards_master.json",
            WORKSPACE_DIR / "gakumas-og-tools" / "support_cards_master.json",
        ]
        for sc_p in sc_paths:
            if sc_p.exists():
                try:
                    with open(sc_p, encoding="utf-8") as f:
                        self._support_cards_master = json.load(f)
                    break
                except Exception:
                    pass

        if INSTRUCTIONS_DIR.exists():
            for p in INSTRUCTIONS_DIR.glob("match_history_*.csv"):
                m = re.search(r"match_history_(\d+)\.csv", p.name)
                if m:
                    season = m.group(1)
                    with open(p, encoding="utf-8") as f:
                        self._match_histories[season] = list(csv.DictReader(f))

    def _init_mongo(self) -> None:
        try:
            self._client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=1500)
            self._db = self._client[MONGODB_DB]
        except Exception:
            self._db = None

    def reload_master_data(self) -> None:
        """同期実行後などにマスタデータとMongoDB接続を再読み込みする"""
        self._load_csv_data()
        self._init_mongo()

    # ── 公開ディスパッチャ ────────────────────────────────────────────────────

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        dispatch = {
            "search_skill_cards":       self.search_skill_cards,
            "search_p_items":           self.search_p_items,
            "get_owned_p_idols":        self.get_owned_p_idols,
            "get_p_idol_details":       self.get_p_idol_details,
            "get_owned_support_cards":  self.get_owned_support_cards,
            "get_owned_memories":       self.get_owned_memories,
            "get_contest_stats":        self.get_contest_stats,
            "get_support_card_details": self.get_support_card_details,
            "get_optimized_deck":       self.get_optimized_deck,
            "get_support_bonus":        self.get_support_bonus,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            return f"※ 未知のツール: {tool_name}"
        try:
            result = fn(**args)
            # トークン節約のため長すぎる結果は末尾を省略
            if len(result) > MAX_TOOL_RESULT_CHARS:
                result = result[:MAX_TOOL_RESULT_CHARS] + "\n…（結果が長いため省略しました）"
            return result
        except TypeError as e:
            return f"※ ツール引数エラー ({tool_name}): {e}"
        except Exception as e:
            return f"※ ツール実行エラー ({tool_name}): {e}"

    # ── ツール: search_skill_cards ───────────────────────────────────────────

    def search_skill_cards(
        self,
        plan: str = "any",
        card_type: str = "any",
        effect_type: str = "any",
        is_repeatable: bool | None = None,
        keyword: str = "",
        include_customizations: bool = True,
        max_results: int = 20,
        **kwargs: Any,
    ) -> str:
        max_results = min(max(1, max_results), 40)
        
        # 1. プラン名・カードタイプの自動補正・正規化
        plan_low = plan.lower().strip()
        card_type_low = card_type.lower().strip()

        # LLM が card_type にプラン名（sense, logic, anomaly）を渡してしまった場合のフェイルセーフ
        if card_type_low in ("sense", "logic", "anomaly", "free"):
            if plan_low == "any":
                plan_low = card_type_low
            card_type_low = "any"

        # 効果名からのプラン自動推定
        if plan_low in ("fullpower", "strength", "preservation"):
            plan_low = "anomaly"
        elif plan_low in ("goodconditionturns", "concentration", "perfectconditionturns"):
            plan_low = "sense"
        elif plan_low in ("goodimpressionturns", "motivation", "enthusiasm"):
            plan_low = "logic"

        # キーワードからのプラン自動推定
        kw_raw = keyword.strip()
        if plan_low == "any":
            if "センス" in kw_raw or "好調" in kw_raw or "絶好調" in kw_raw:
                plan_low = "sense"
            elif "ロジック" in kw_raw or "好印象" in kw_raw or "やる気" in kw_raw:
                plan_low = "logic"
            elif "アノマリー" in kw_raw or "全力" in kw_raw or "強気" in kw_raw or "温存" in kw_raw:
                plan_low = "anomaly"

        # card_type / type エイリアス
        extra_type = kwargs.get("type", "").lower().strip()
        if extra_type and card_type_low == "any":
            if extra_type in ("sense", "logic", "anomaly"):
                if plan_low == "any":
                    plan_low = extra_type
            else:
                card_type_low = extra_type

        # 2. キーワードのトークン化・重要語抽出
        kw_raw = keyword.strip()
        kw_tokens = []
        if kw_raw:
            known_terms = [
                "保留", "山札", "手札", "開始時", "初手", "1ターン目", "全力値", "全力",
                "ドロー", "引く", "元気", "スコア", "好調", "絶好調", "集中", "好印象",
                "やる気", "強気", "温存", "消費", "体力", "固定体力", "レッスン", "アピール"
            ]
            for term in known_terms:
                if term in kw_raw:
                    kw_tokens.append(term)
            for part in kw_raw.split():
                if len(part) >= 2 and part not in kw_tokens:
                    kw_tokens.append(part)
            if not kw_tokens:
                kw_tokens = [kw_raw]

        def _do_search(use_card_type: str) -> list[tuple[int, dict, list[str]]]:
            res: list[tuple[int, dict, list[str]]] = []
            for c in self._skill_cards:
                c_plan   = (c.get("plan") or "").lower()
                c_type   = (c.get("type") or "").lower()
                c_acts   = c.get("actions", "")
                c_effs   = c.get("effects", "")
                all_eff  = f"{c_acts}; {c_effs}".strip("; ")
                limit    = c.get("limit", "").strip()
                unique   = c.get("unique", "")
                # カード自体の使用制限判定（トリガー効果ブロック { ... } 内の limit:1 は除外する）
                acts_clean = re.sub(r'\{[^{}]*\}', '', c_acts)
                effs_clean = re.sub(r'\{[^{}]*\}', '', c_effs)
                has_card_level_limit = (
                    (unique == "TRUE")
                    or (limit == "1")
                    or bool(re.search(r'(?:^|;)\s*limit:1(?:\s*;|\s*$)', acts_clean))
                    or bool(re.search(r'(?:^|;)\s*limit:1(?:\s*;|\s*$)', effs_clean))
                )
                one_time = has_card_level_limit

                # プランフィルタ
                if plan_low != "any" and c_plan not in (plan_low, "free"):
                    continue
                # タイプフィルタ（キーワード検索時は厳密に除外せず、スコアで調整）
                # ※ユーザーが「アクティブ限定」「メンタル限定」と明示していない限り除外しない
                # (is_repeatable も同様)

                # カスタマイズ情報の解決
                custom_ids_str = c.get("availableCustomizations", "").strip()
                custom_labels = []
                custom_effs_text = ""
                if custom_ids_str and include_customizations:
                    cids = [x.strip() for x in custom_ids_str.split(",") if x.strip()]
                    for cid in cids:
                        cobj = self._customizations.get(cid)
                        if cobj:
                            c_name = cobj.get("name", "")
                            c_act = cobj.get("actions", "")
                            c_eff = cobj.get("effects", "")
                            c_fhand = cobj.get("forceInitialHand", "")
                            label = c_name
                            if c_act or c_eff or c_fhand:
                                translated_part = self._dsl.translate(f"{c_act}; {c_eff}".strip("; "))
                                if c_fhand == "TRUE" or "forceInitialHand" in cobj.get("alias", ""):
                                    translated_part = "開始時手札に入る" + (f", {translated_part}" if translated_part else "")
                                label = f"{c_name}（{translated_part}）" if translated_part else c_name
                            custom_labels.append(label)
                            custom_effs_text += f" {c_name} {c_act} {c_eff} {cobj.get('alias','')} {label}"

                combined_search_text = f"{c.get('name','')} {all_eff} {self._dsl.translate(all_eff)} {custom_effs_text}".lower()

                has_force_initial_hand = (
                    c.get("forceInitialHand") == "TRUE"
                    or "forceinitialhand" in custom_effs_text.lower()
                    or "開始時手札に入る" in custom_effs_text
                )

                # シノニム（同義語）マッピング
                synonym_groups = {
                    "first_turn": ("1ターン目", "1ターン", "初手", "開始時", "開幕", "forceinitialhand"),
                    "hold":       ("保留", "山札保留", "ホールド", "hold", "holdselected"),
                    "fullpower":  ("全力", "全力値", "全力型", "fullpower", "fullpowercharge"),
                    "genki":      ("元気", "genki"),
                    "draw":       ("ドロー", "引く", "drawcard"),
                    "deck":       ("山札", "デッキ", "deck"),
                }

                match_score = 0
                # 好調+元気の複合効果を持つカードへの特大ボーナス
                has_good_cond = "goodconditionturns+=" in all_eff.lower() or "goodconditionturns+" in all_eff.lower() or "好調追加" in custom_effs_text
                has_genki_eff = "genki+=" in all_eff.lower() or "genki+" in all_eff.lower() or "元気追加" in custom_effs_text or "元気+" in custom_effs_text
                if has_good_cond and has_genki_eff:
                    match_score += 40
                elif has_good_cond:
                    match_score += 20
                if kw_tokens:
                    matched_count = 0
                    for tok in kw_tokens:
                        tok_low = tok.lower()
                        # 1. 直接テキストマッチ
                        if tok_low in combined_search_text:
                            matched_count += 1
                            match_score += 10
                        # 2. 1ターン目・初手シノニムと開始時手札の連動
                        elif any(syn in tok_low for syn in synonym_groups["first_turn"]) and has_force_initial_hand:
                            matched_count += 1
                            match_score += 50
                        # 3. 保留シノニムと保留効果の連動
                        elif any(syn in tok_low for syn in synonym_groups["hold"]) and ("保留" in combined_search_text or "hold" in combined_search_text):
                            matched_count += 1
                            match_score += 25
                        # 4. 全力シノニムと全力効果の連動
                        elif any(syn in tok_low for syn in synonym_groups["fullpower"]) and ("全力" in combined_search_text or "fullpower" in combined_search_text):
                            matched_count += 1
                            match_score += 20

                    # 1ターン目/初手を求めている場合に forceInitialHand を持っていれば特大ボーナス
                    if any(t in kw_raw for t in synonym_groups["first_turn"]) and has_force_initial_hand:
                        match_score += 50
                        # さらに保留効果も併せ持つ場合は圧倒的ボーナス
                        if "保留" in combined_search_text or "hold" in combined_search_text:
                            match_score += 60

                    if matched_count == 0:
                        continue
                else:
                    match_score = 1

                # is_repeatable フィルタ（厳格な AND 条件）
                if is_repeatable is not None:
                    if is_repeatable and one_time:
                        continue
                    if not is_repeatable and not one_time:
                        continue

                # effect_type 判定（あらゆる区切り文字: | , / & + 、 空白 に対応）
                req_effects: list[str] = []
                if isinstance(effect_type, list):
                    for item in effect_type:
                        for part in re.split(r'[,|/&+、\s]+', str(item)):
                            p_clean = part.lower().strip()
                            if p_clean and p_clean != "any" and p_clean not in req_effects:
                                req_effects.append(p_clean)
                elif isinstance(effect_type, str) and effect_type.lower().strip() != "any":
                    for part in re.split(r'[,|/&+、\s]+', effect_type):
                        p_clean = part.lower().strip()
                        if p_clean and p_clean != "any" and p_clean not in req_effects:
                            req_effects.append(p_clean)

                translated_eff = self._dsl.translate(all_eff)

                def check_has_increase_effect(eff_key: str) -> bool:
                    eff_k = eff_key.lower().strip()
                    if eff_k in ("goodconditionturns", "goodcondition", "好調"):
                        return (
                            "goodconditionturns+=" in all_eff.lower()
                            or "goodconditionturns+" in all_eff.lower()
                            or "好調+" in translated_eff
                            or "好調追加" in custom_effs_text
                            or "好調+" in custom_effs_text
                        )
                    elif eff_k in ("concentration", "集中"):
                        return (
                            "concentration+=" in all_eff.lower()
                            or "concentration+" in all_eff.lower()
                            or "集中+" in translated_eff
                            or "集中追加" in custom_effs_text
                            or "集中+" in custom_effs_text
                        )
                    elif eff_k in ("perfectconditionturns", "perfectcondition", "絶好調"):
                        return (
                            "perfectconditionturns+=" in all_eff.lower()
                            or "perfectconditionturns+" in all_eff.lower()
                            or "絶好調+" in translated_eff
                            or "絶好調追加" in custom_effs_text
                        )
                    elif eff_k in ("goodimpressionturns", "goodimpression", "好印象"):
                        return (
                            "goodimpressionturns+=" in all_eff.lower()
                            or "goodimpressionturns+" in all_eff.lower()
                            or "好印象+" in translated_eff
                            or "好印象追加" in custom_effs_text
                        )
                    elif eff_k in ("motivation", "やる気"):
                        return (
                            "motivation+=" in all_eff.lower()
                            or "motivation+" in all_eff.lower()
                            or "やる気+" in translated_eff
                            or "やる気追加" in custom_effs_text
                        )
                    elif eff_k in ("enthusiasm", "熱意"):
                        return (
                            "enthusiasm+=" in all_eff.lower()
                            or "enthusiasm+" in all_eff.lower()
                            or "熱意+" in translated_eff
                            or "熱意追加" in custom_effs_text
                        )
                    elif eff_k in ("genki", "元気"):
                        return (
                            "genki+=" in all_eff.lower()
                            or "genki+" in all_eff.lower()
                            or "元気+" in translated_eff
                            or "元気追加" in custom_effs_text
                            or "元気+" in custom_effs_text
                        )
                    elif eff_k in ("fullpower", "fullpowercharge", "全力"):
                        return (
                            "fullpowercharge+=" in all_eff.lower()
                            or "fullpowercharge+" in all_eff.lower()
                            or "全力+" in translated_eff
                            or "全力値+" in custom_effs_text
                        )
                    elif eff_k in ("score", "スコア"):
                        return (
                            "score+=" in all_eff.lower()
                            or "スコア+" in translated_eff
                            or "パラメータ+" in custom_effs_text
                            or "パラメータ追加" in custom_effs_text
                        )
                    elif eff_k in ("draw", "ドロー"):
                        return "drawcard" in all_eff.lower() or "カードを引く" in translated_eff or "カードを1枚引く" in translated_eff
                    elif eff_k in ("hold", "保留"):
                        return "hold" in all_eff.lower() or "保留" in translated_eff or "保留追加" in custom_effs_text
                    elif eff_k in ("strength", "強気"):
                        return "setstance(strength)" in all_eff.lower() or "強気" in translated_eff
                    elif eff_k in ("preservation", "温存"):
                        return "setstance(preservation)" in all_eff.lower() or "温存" in translated_eff
                    return False

                if req_effects:
                    all_matched = True
                    for req in req_effects:
                        if req == "any":
                            continue
                        if not check_has_increase_effect(req):
                            all_matched = False
                            break
                    if not all_matched:
                        continue

                res.append((match_score, c, custom_labels, has_force_initial_hand))
            return res

        results_with_score = _do_search(card_type_low)
        fallback_notice = ""

        # もし 0 件だった場合、制約を緩和して自動フォールバック
        if not results_with_score and is_repeatable is not None:
            is_repeatable = None
            results_with_score = _do_search(card_type_low)
            if results_with_score:
                fallback_notice = "（※指定された使用回数制限を解除して全カードから検索しました）\n"

        if not results_with_score and card_type_low != "any":
            results_with_score = _do_search("any")
            if results_with_score:
                fallback_notice = f"（※指定されたタイプ '{card_type_low}' に該当がなかったため、全タイプから検索しました）\n"

        if not results_with_score:
            return "※ 条件に一致するスキルカードは見つかりませんでした。"

        # スコア降順ソート
        results_with_score.sort(key=lambda x: x[0], reverse=True)
        results = [(c, custom_labels, fhand) for _, c, custom_labels, fhand in results_with_score]

        limit_count = min(len(results), min(max_results, 8))
        lines = [
            f"【スキルカード検索結果（{len(results)} 件中 {limit_count} 件表示）】"
        ]
        if fallback_notice:
            lines.append(fallback_notice)

        for c, custom_labels, fhand in results[:limit_count]:
            c_plan   = (c.get("plan") or "").lower()
            c_type   = (c.get("type") or "").lower()
            type_lbl = TYPE_LABEL.get(c_type, c_type)
            emoji    = PLAN_EMOJI.get(c_plan, "")
            c_acts_item   = c.get("actions", "")
            c_effs_item   = c.get("effects", "")
            acts_clean_item = re.sub(r'\{[^{}]*\}', '', c_acts_item)
            effs_clean_item = re.sub(r'\{[^{}]*\}', '', c_effs_item)
            is_item_one_time = (
                (c.get("unique") == "TRUE")
                or (c.get("limit", "").strip() == "1")
                or bool(re.search(r'(?:^|;)\s*limit:1(?:\s*;|\s*$)', acts_clean_item))
                or bool(re.search(r'(?:^|;)\s*limit:1(?:\s*;|\s*$)', effs_clean_item))
            )
            repeat = "1回限り" if is_item_one_time else "繰り返し可"
            is_first_turn_query = any(w in kw_raw for w in ["1ターン目", "1ターン", "初手", "開幕", "開始時"])
            fhand_tag = " 🌟**【初手確定】**" if (fhand and is_first_turn_query) else ""
            cost_raw = (
                c.get("cost", "0")
                .replace("cost-=",        "体力消費:")
                .replace("stamina-=",     "固定体力:")
            )
            all_eff = f"{c.get('actions', '')}; {c.get('effects', '')}".strip("; ")
            jp_eff  = self._dsl.translate(all_eff)

            custom_line = f" 🛠️{'/'.join(custom_labels[:2])}" if custom_labels else ""

            lines.append(
                f"- {emoji} **{c.get('name', '')}** `[{c.get('rarity','')} / {type_lbl} / {repeat}]`{fhand_tag} (コスト:{cost_raw}) ➔ {jp_eff}{custom_line}"
            )
        if len(results) > limit_count:
            lines.append(f"\n※他 {len(results) - limit_count} 件（主要候補のみ抜粋）")
        return "\n".join(lines)
    # ── ツール: search_p_items ───────────────────────────────────────────────

    def search_p_items(
        self,
        plan: str = "any",
        effect_type: str = "any",
        max_results: int = 15,
        **kwargs: Any,
    ) -> str:

        for item in self._p_items:
            i_plan   = (item.get("plan") or "").lower()
            i_effs   = f"{item.get('actions','')}; {item.get('effects','')}".strip("; ")
            i_effs_low = i_effs.lower()

            if plan != "any" and i_plan not in (plan, "free"):
                continue
            if keyword:
                name = item.get("name", "")
                if keyword not in name and keyword not in i_effs:
                    continue
            effect_map = {
                "fullPower": "fullpowercharge" in i_effs_low,
                "genki":     "genki+=" in i_effs_low,
                "score":     "score+=" in i_effs_low,
                "draw":      "drawcard" in i_effs_low,
                "any":       True,
            }
            if not effect_map.get(effect_type, False):
                continue
            results.append(item)

        if not results:
            return "※ 条件に一致するPアイテムは見つかりませんでした。"

        lines = [f"【Pアイテム検索結果（{len(results)} 件）】\n"]
        for item in results[:max_results]:
            i_plan = (item.get("plan") or "").lower()
            emoji  = PLAN_EMOJI.get(i_plan, "")
            i_effs = f"{item.get('actions','')}; {item.get('effects','')}".strip("; ")
            jp_eff = self._dsl.translate(i_effs)
            lines.append(
                f"- {emoji} **{item.get('name','')}** `[{item.get('rarity','')} / {i_plan}]`\n"
                f"  効果: {jp_eff}"
            )
        return "\n".join(lines)

    # ── ツール: get_owned_p_idols ────────────────────────────────────────────

    def get_owned_p_idols(
        self,
        plan: str = "any",
        idol_name: str | list[str] = "",
        effect_type: str = "any",
        rarity: str = "any",
        min_talent: int = 0,
        **kwargs: Any,
    ) -> str:
        if self._db is None:
            return "※ MongoDB に接続できませんでした。"

        docs = list(self._db["owned_p_idols"].find({}))
        if not docs:
            return "※ 所持Pアイドルの登録データがありません。"

        # 複数アイドル名パラメータの吸収（p_ids, idols, idol_names, names 等）
        raw_targets: list[str] = []
        if isinstance(idol_name, list):
            raw_targets.extend(idol_name)
        elif isinstance(idol_name, str) and idol_name:
            raw_targets.append(idol_name)

        for alt_key in ["p_ids", "idols", "idol_names", "names"]:
            val = kwargs.get(alt_key)
            if isinstance(val, list):
                raw_targets.extend([str(x) for x in val])
            elif isinstance(val, str) and val:
                raw_targets.append(val)

        # master_data.py から愛称辞書・型辞書を取得
        from master_data import GakumasMaster, RECOMMENDED_EFFECT_MAP
        master = GakumasMaster()

        target_idols = set()
        for t in raw_targets:
            t_clean = t.strip()
            if not t_clean:
                continue
            matched_canonical = master.resolve_idol_name(t_clean)
            target_idols.add(matched_canonical)

        # 型（おすすめ効果）ラベル変換マップ
        EFFECT_LABEL_MAP = {k: v["jp"] for k, v in RECOMMENDED_EFFECT_MAP.items()}

        # effect_type 検索正規化
        effect_query = effect_type.strip()
        for dsl_k, meta in RECOMMENDED_EFFECT_MAP.items():
            if effect_query in (dsl_k, meta["jp"], meta["jp"].replace("型", "")):
                effect_query = dsl_k
                break

        grouped: dict[str, list] = {}
        for doc in docs:
            p = (doc.get("plan") or "").lower()
            if plan != "any" and p != plan:
                continue
            if rarity != "any" and doc.get("rarity") != rarity:
                continue
            if doc.get("talent_level", 0) < min_talent:
                continue

            eff_raw = doc.get("recommendedEffect") or doc.get("recommended_effect") or ""
            if effect_query != "any" and eff_raw != effect_query:
                continue

            doc_idol_name = doc.get("idol_name", "").strip() or "その他"

            # ターゲットアイドル指定がある場合
            if target_idols:
                match_any = False
                for target in target_idols:
                    if target in doc_idol_name or doc_idol_name in target:
                        match_any = True
                        break
                if not match_any:
                    continue

            grouped.setdefault(doc_idol_name, []).append(doc)

        if not grouped:
            return "※ 条件に一致する所持Pアイドルは見つかりませんでした。"

        total = sum(len(v) for v in grouped.values())
        filters = []
        if plan != "any":
            filters.append(f"{plan.upper()}プラン")
        if effect_query != "any":
            filters.append(EFFECT_LABEL_MAP.get(effect_query, effect_query))
        filter_str = f"（{' / '.join(filters)}）" if filters else ""

        lines = [f"【所持 P アイドル一覧{filter_str}（{total} 件）】\n"]

        for iname, cards in grouped.items():
            cards.sort(key=lambda x: RARITY_WEIGHT.get(x.get("rarity", ""), 0), reverse=True)
            lines.append(f"■ **{iname}**（{len(cards)} 着）:")
            for d in cards:
                p     = (d.get("plan") or "").lower()
                emoji = PLAN_EMOJI.get(p, "")
                eff_raw = d.get("recommendedEffect") or d.get("recommended_effect") or ""
                eff_lbl = EFFECT_LABEL_MAP.get(eff_raw, "")
                type_str = f" / {eff_lbl}" if eff_lbl else ""

                # 固有スキルカード
                skill_cards = d.get("skill_cards", [])
                sc_name = ""
                if skill_cards and isinstance(skill_cards, list):
                    base_cards = [c.get("name") for c in skill_cards if isinstance(c, dict) and not c.get("upgraded", False)]
                    if base_cards:
                        sc_name = base_cards[0]
                    elif skill_cards and isinstance(skill_cards[0], dict):
                        sc_name = skill_cards[0].get("name", "")
                sc_tag = f" ｜ 固有スキル: 『{sc_name}』" if sc_name else ""

                lines.append(
                    f"  - {emoji} **【{d.get('title', '')}】** "
                    f"`[{d.get('rarity', '')} / {p.upper()}{type_str}]` "
                    f"才能開花: ★{d.get('talent_level', 0)} ｜ 特訓: Lv.{d.get('awaken_level', 0)}{sc_tag}"
                )
            lines.append("")

        return "\n".join(lines).strip()

    # ── ツール: get_owned_support_cards ─────────────────────────────────────

    def get_owned_support_cards(
        self,
        rarity: str = "any",
        min_uncap: int = 0,
        target_skill: str = "",
        keyword: str = "",
        max_results: int = 20,
        **kwargs: Any,
    ) -> str:
        if self._db is None:
            return "※ MongoDB に接続できませんでした。"

        # 引数エイリアス（card_name, name, skill 等）
        extra_card = kwargs.get("card_name") or kwargs.get("name") or ""
        extra_skill = kwargs.get("skill") or kwargs.get("skill_name") or ""
        if extra_card and not keyword:
            keyword = str(extra_card).strip()
        if extra_skill and not target_skill:
            target_skill = str(extra_skill).strip()

        docs = list(self._db["owned_support_cards"].find({}))
        if not docs:
            return "※ 所持サポートカードの登録データがありません。"

        # カード名ごとに重複排除（uncap が高い方、または最新を優先）
        unique_docs: dict[str, dict] = {}
        for doc in docs:
            name = doc.get("card_name", "")
            if not name:
                continue
            if name not in unique_docs:
                unique_docs[name] = doc
            else:
                existing = unique_docs[name]
                if (doc.get("uncap", 0), doc.get("lv", 0)) > (existing.get("uncap", 0), existing.get("lv", 0)):
                    unique_docs[name] = doc

        # スキルカード名が keyword に渡された場合の逆引き候補サポカ名
        skill_matched_card_names = set()
        search_kw = keyword.strip()
        if search_kw:
            for sc in self._support_cards_master:
                sc_name = sc.get("name", "")
                events = sc.get("support_events", [])
                for ev in events:
                    if search_kw in ev.get("dsl", "") or search_kw in ev.get("name", ""):
                        skill_matched_card_names.add(sc_name)

        matched: list[str] = []
        for doc in unique_docs.values():
            d_rarity = doc.get("rarity", "")
            d_uncap  = doc.get("uncap", 0)
            d_name   = doc.get("card_name", "")
            d_skill  = doc.get("obtained_skill_card", "") or ""
            d_type   = doc.get("type", "")
            d_lv     = doc.get("lv", 1)

            if rarity != "any" and d_rarity != rarity:
                continue
            if d_uncap < min_uncap:
                continue
            if target_skill and target_skill not in d_skill:
                continue
            if search_kw:
                if search_kw not in d_name and search_kw not in d_skill and d_name not in skill_matched_card_names:
                    continue

            skill_str = f" ｜ 習得スキル: 『{d_skill}』" if d_skill else ""
            matched.append(
                f"- **{d_name}** `[{d_rarity} / {d_type}]`\n"
                f"  上限解放: **{d_uncap} 凸** ｜ Lv.**{d_lv}**{skill_str}"
            )

        if not matched:
            return f"※ 条件に一致する所持サポートカードは見つかりませんでした（条件: {search_kw or target_skill or '指定なし'}）。"

        limit_count = min(len(matched), min(max_results, 10))

        def _bonus_for_lv(lv: Any) -> float:
            try:
                l = int(lv)
            except (ValueError, TypeError):
                l = 1
            if l >= 60: return 0.10
            if l >= 50: return 0.08
            if l >= 40: return 0.06
            if l >= 30: return 0.04
            if l >= 20: return 0.02
            if l >= 10: return 0.01
            return 0.00

        total_bonus_pct = sum(_bonus_for_lv(d.get("lv", 1)) for d in unique_docs.values())
        lines = [f"【所持サポートカード一覧（{len(matched)} 件中 {limit_count} 件表示 / 現在の総合サポートボーナス: +{total_bonus_pct:.2f}%）】\n"]
        lines.extend(matched[:limit_count])
        if len(matched) > limit_count:
            lines.append(f"\n※他 {len(matched) - limit_count} 件（上位のみ抜粋）")
        return "\n".join(lines)

    # ── ツール: get_support_bonus ───────────────────────────────────────────

    def get_support_bonus(self, **kwargs: Any) -> str:
        if self._db is None:
            return "※ MongoDB に接続できませんでした。"

        docs = list(self._db["owned_support_cards"].find({}))
        if not docs:
            return "※ 所持サポートカードの登録データがありません（デフォルト値: +4.00%）。"

        # 重複排除（同じカード名ならレベル・上限解放が高い方を優先）
        unique_docs: dict[str, dict] = {}
        for doc in docs:
            name = doc.get("card_name", "")
            if not name:
                continue
            if name not in unique_docs:
                unique_docs[name] = doc
            else:
                existing = unique_docs[name]
                if (int(doc.get("lv", 1)), int(doc.get("uncap", 0))) > (int(existing.get("lv", 1)), int(existing.get("uncap", 0))):
                    unique_docs[name] = doc

        def _bonus_for_lv(lv: Any) -> float:
            try:
                l = int(lv)
            except (ValueError, TypeError):
                l = 1
            if l >= 60: return 0.10
            if l >= 50: return 0.08
            if l >= 40: return 0.06
            if l >= 30: return 0.04
            if l >= 20: return 0.02
            if l >= 10: return 0.01
            return 0.00

        total_bonus_pct = 0.0
        rarity_counts = {"SSR": 0, "SR": 0, "R": 0}
        lv_counts = {60: 0, 50: 0, 40: 0, 30: 0, 20: 0, 10: 0, 1: 0}

        for doc in unique_docs.values():
            lv = int(doc.get("lv", 1))
            total_bonus_pct += _bonus_for_lv(lv)

            rarity = doc.get("rarity", "R")
            rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1

            if lv >= 60:
                lv_counts[60] += 1
            elif lv >= 50:
                lv_counts[50] += 1
            elif lv >= 40:
                lv_counts[40] += 1
            elif lv >= 30:
                lv_counts[30] += 1
            elif lv >= 20:
                lv_counts[20] += 1
            elif lv >= 10:
                lv_counts[10] += 1
            else:
                lv_counts[1] += 1

        multiplier = 1.0 + (total_bonus_pct / 100.0)
        norm_factor = round(total_bonus_pct / 100.0, 4)

        lines = [
            f"### 📊 現在のサポートボーナス状況",
            f"- **総合サポートボーナス**: **+{total_bonus_pct:.2f}%**（倍率補正: **×{multiplier:.4f}** / 内部係数: `{norm_factor}`）",
            f"- **所持サポートカード総数**: **{len(unique_docs)} 枚**（SSR: {rarity_counts.get('SSR', 0)}枚, SR: {rarity_counts.get('SR', 0)}枚, R: {rarity_counts.get('R', 0)}枚）",
            f"- **レベル帯別の所持内訳**:",
            f"  - **Lv.60（最大ボーナス +0.10% 達成）**: **{lv_counts[60]} 枚**",
            f"  - Lv.50〜59（ボーナス +0.08%）: {lv_counts[50]} 枚",
            f"  - Lv.40〜49（ボーナス +0.06%）: {lv_counts[40]} 枚",
            f"  - Lv.30〜39（ボーナス +0.04%）: {lv_counts[30]} 枚",
            f"  - Lv.20〜29（ボーナス +0.02%）: {lv_counts[20]} 枚",
            f"  - Lv.10〜19（ボーナス +0.01%）: {lv_counts[10]} 枚",
            f"  - Lv.1〜9（ボーナスなし）: {lv_counts[1]} 枚",
            f"",
            f"**【サポートボーナスのゲーム仕様・影響】**",
            f"- サポートボーナスは、所持しているサポートカードのレベルに応じて加算される累積・永続ボーナスです（プロデュースやコンテストで未編成の所持カードも含め、所持する全サポートカードのレベルが反映されます）。",
            f"- コンテストの全ステージにおいて、最終スコア計算時に倍率補正（`× {multiplier:.4f}`）として乗算適用されます。",
            f"- シミュレータ（`gakumas-tools`）やコンテスト最適化探索時にもこの最新値（+{total_bonus_pct:.2f}%）が適用されています。",
            f"- 未育成（Lv.60未満）の所持カードを上限解放・強化することで、1枚あたり最大 +0.10% ずつボーナスを底上げ可能です。"
        ]
        return "\n".join(lines)

    # ── ツール: get_owned_memories ───────────────────────────────────────────

    def get_owned_memories(
        self,
        idol_name: str = "",
        p_idol_name: str = "",
        plan: str = "any",
        keyword: str = "",
        card_name: str = "",
        max_results: int = 20,
        **kwargs: Any,
    ) -> str:
        if self._db is None:
            return "※ MongoDB に接続できませんでした。"

        docs = list(self._db["memories"].find({}))
        if not docs:
            return "※ 所持メモリーの登録データがありません。"


        from master_data import GakumasMaster
        master = GakumasMaster()

        # パラメータの吸収（title, p_name, idol など）
        target_p_idol = p_idol_name or kwargs.get("title") or kwargs.get("p_name") or ""
        target_idol = idol_name or kwargs.get("idol") or ""

        # マスタデータからのPアイドル・アイドルマップ構築（int / str 両対応）
        idol_map = {}
        for iid, iname in master.idols.items():
            idol_map[str(iid)] = iname
            idol_map[int(iid)] = iname

        pidol_map = {}
        for p in master.p_idols:
            p_dict = dict(p)
            try:
                iid = int(p.get("idolId", 0))
                p_dict["idol_name"] = idol_map.get(iid, "")
            except Exception:
                p_dict["idol_name"] = ""

            pidol_map[p["id"]] = p_dict
            pidol_map[str(p["id"])] = p_dict
            try:
                pidol_map[int(p["id"])] = p_dict
            except Exception:
                pass

        card_map = {}
        for c in master.skill_cards:
            card_map[c["id"]] = c["name"]
            card_map[str(c["id"])] = c["name"]
            try:
                card_map[int(c["id"])] = c["name"]
            except Exception:
                pass

        # アイドル名正規化（空白完全除去）
        def _clean(s: str) -> str:
            return str(s).replace(" ", "").replace("　", "").replace("【", "").replace("】", "").strip().lower()

        norm_target_idol = _clean(master.resolve_idol_name(target_idol)) if target_idol else ""
        norm_target_p = _clean(target_p_idol) if target_p_idol else ""
        norm_kw = _clean(keyword) if keyword else ""

        matched: list[dict[str, Any]] = []

        for doc in docs:
            m_name = doc.get("name", "") or ""
            p_id = doc.get("pIdolId") or (doc.get("data", {}).get("pIdolId") if isinstance(doc.get("data"), dict) else None)
            
            p_meta = pidol_map.get(p_id) or pidol_map.get(str(p_id)) or {}
            doc_idol_name = p_meta.get("idol_name", "")
            doc_title = p_meta.get("title", "")
            doc_plan = (p_meta.get("plan", "") or "").lower()

            clean_doc_idol = _clean(doc_idol_name)
            clean_doc_title = _clean(doc_title)
            clean_m_name = _clean(m_name)

            # スキルカード名一覧の解決
            card_names: list[str] = []
            if "skill_cards" in doc and isinstance(doc["skill_cards"], list):
                card_names = [str(x) for x in doc["skill_cards"]]
            elif "skillCardIds" in doc and isinstance(doc["skillCardIds"], list):
                card_names = [card_map.get(cid, f"ID:{cid}") for cid in doc["skillCardIds"] if cid]
            elif isinstance(doc.get("data"), dict) and "skillCardIds" in doc["data"]:
                card_names = [card_map.get(cid, f"ID:{cid}") for cid in doc["data"]["skillCardIds"] if cid]

            # パラメータ合計の計算
            raw_params = doc.get("params") or (doc.get("data", {}).get("params") if isinstance(doc.get("data"), dict) else None) or {}
            total_p = 0
            param_str = ""

            if isinstance(raw_params, list) and len(raw_params) >= 3:
                vo, da, vi = raw_params[0], raw_params[1], raw_params[2]
                sta = raw_params[3] if len(raw_params) > 3 else 0
                total_p = vo + da + vi
                param_str = f"Vo: {vo} / Da: {da} / Vi: {vi}" + (f" / 体力: {sta}" if sta else "")
            elif isinstance(raw_params, dict):
                total_p = sum(v for v in raw_params.values() if isinstance(v, (int, float)))
                param_parts = [f"{k}: {v}" for k, v in raw_params.items() if isinstance(v, (int, float)) and v > 0]
                param_str = " / ".join(param_parts) if param_parts else "（パラメータ情報なし）"

            # ── フィルタリング判定（空白非依存） ──
            if norm_target_idol and norm_target_idol not in clean_doc_idol and norm_target_idol not in clean_m_name:
                continue

            if norm_target_p and norm_target_p not in clean_doc_title and norm_target_p not in clean_m_name:
                continue

            if plan != "any" and plan.lower() != doc_plan:
                continue

            if norm_kw and norm_kw not in clean_m_name and norm_kw not in clean_doc_title and norm_kw not in clean_doc_idol:
                continue

            if card_name and not any(card_name in c for c in card_names):
                continue

            if total_p < min_param:
                continue

            matched.append({
                "name": m_name,
                "idol": doc_idol_name,
                "title": doc_title,
                "cards": card_names,
                "param_str": param_str,
                "total_p": total_p
            })

        if not matched:
            return f"※ 条件に一致する所持メモリーは見つかりませんでした。（検索条件: アイドル='{target_idol}', 衣装='{target_p_idol}', キーワード='{keyword}'）"

        # スコアやパラメータ合計で降順ソート
        matched.sort(key=lambda x: x["total_p"], reverse=True)

        lines = [f"【所持メモリー検索結果：合計 {len(matched)} 枚（上位 {min(len(matched), max_results)} 枚を表示）】\n"]
        for m in matched[:max_results]:
            cards_str = "、".join(m["cards"][:6]) if m["cards"] else "なし"
            if len(m["cards"]) > 6:
                cards_str += f"（他 {len(m['cards'])-6} 枚）"

            header = f"- **{m['name']}**"
            if m["idol"] or m["title"]:
                header += f" 【{m['idol']} / {m['title']}】"

            lines.append(
                f"{header}\n"
                f"  付与カード: {cards_str}\n"
                f"  パラメータ: {m['param_str']}（合計: {m['total_p']}）"
            )

        if len(matched) > max_results:
            lines.append(f"\n※他 {len(matched) - max_results} 枚のメモリーが登録されています。")

        return "\n".join(lines)

    # ── ツール: get_contest_stats ────────────────────────────────────────────

    def get_contest_stats(
        self,
        season: int | None = None,
        date: str = "",
        season_start: int | None = None,
        season_end: int | None = None,
        recent_count: int = 5,
        **kwargs: Any,
    ) -> str:
        # 常に最新の match_history CSV をリロード
        self._load_csv_data()

        all_seasons = sorted(self._match_histories.keys(), key=lambda x: int(x))
        if not all_seasons:
            return "※ 対戦履歴データが見つかりませんでした。"

        # ターゲットシーズンの決定
        if season_start is not None and season_end is not None:
            target_seasons = [s for s in all_seasons if season_start <= int(s) <= season_end]
        elif season is not None:
            target_seasons = [str(season)] if str(season) in self._match_histories else []
        else:
            target_seasons = [all_seasons[-1]]

        if not target_seasons:
            return f"※ 指定されたシーズンのデータが見つかりませんでした。利用可能: {', '.join(all_seasons)}"

        # 複数シーズン比較（date 指定がない場合のみ）
        if len(target_seasons) > 1 and not date:
            return self._format_multi_season(target_seasons)

        # 単一シーズン詳細（または特定日付絞り込み）
        return self._format_single_season(target_seasons[0], date=date, recent_count=recent_count)

    def _valid_matches(self, rows: list[dict]) -> list[dict]:
        """対戦記録として有効な行だけ返す"""
        result = []
        for r in rows:
            res_val = (r.get("結果") or r.get("対戦結果") or "").strip().upper()
            pt_val  = (r.get("獲得Pt") or "").strip()
            if res_val in ("WIN", "LOSE") or (pt_val and pt_val.isdigit()):
                result.append(r)
        return result

    def _is_win(self, r: dict) -> bool:
        res = (r.get("結果") or r.get("対戦結果") or "").strip().upper()
        pt  = r.get("獲得Pt", "")
        return res == "WIN" or (pt.isdigit() and int(pt) > 50)

    def _format_single_season(self, season: str, date: str = "", recent_count: int = 5) -> str:
        rows   = self._match_histories.get(season, [])
        valid  = self._valid_matches(rows)
        if not valid:
            return f"※ シーズン {season} にはまだ記録された対戦がありません。"

        # 日付フィルタ処理
        target_matches = valid
        date_title = ""
        if date:
            q_date = date.strip().lower()
            if q_date in ("today", "今日", "本日"):
                # 最新の対戦日を採用（通常は今日の日付）
                latest_date = valid[-1].get("日付", "")
                target_matches = [r for r in valid if r.get("日付", "") == latest_date]
                date_title = f"（日付: {latest_date} / 本日分）"
            else:
                # 指定文字列に部分一致
                matched = [r for r in valid if q_date in r.get("日付", "").lower()]
                if matched:
                    target_matches = matched
                    date_title = f"（日付: {date}）"
                else:
                    # 見つからない場合は直近5件
                    target_matches = valid[-recent_count:]
                    date_title = f"（※日付 '{date}' の一致なし ➔ 直近データ）"

        total    = len(target_matches)
        wins     = sum(1 for r in target_matches if self._is_win(r))
        losses   = total - wins
        win_rate = wins / total * 100 if total > 0 else 0
        pts      = [int(r["獲得Pt"]) for r in target_matches if r.get("獲得Pt", "").isdigit()]
        avg_pt   = sum(pts) / len(pts) if pts else 0
        total_pt = sum(pts)

        # ステージ別スコアの集計（平均自スコア、平均敵スコア）
        def _get_scores(key: str) -> list[int]:
            res = []
            for r in target_matches:
                v = re.sub(r"\D", "", str(r.get(key, "")))
                if v.isdigit():
                    res.append(int(v))
            return res

        s1_my = _get_scores("自S1")
        s1_en = _get_scores("敵S1")
        s2_my = _get_scores("自S2")
        s2_en = _get_scores("敵S2")
        s3_my = _get_scores("自S3")
        s3_en = _get_scores("敵S3")

        avg_s1_my = sum(s1_my) / len(s1_my) if s1_my else 0
        avg_s1_en = sum(s1_en) / len(s1_en) if s1_en else 0
        avg_s2_my = sum(s2_my) / len(s2_my) if s2_my else 0
        avg_s2_en = sum(s2_en) / len(s2_en) if s2_en else 0
        avg_s3_my = sum(s3_my) / len(s3_my) if s3_my else 0
        avg_s3_en = sum(s3_en) / len(s3_en) if s3_en else 0

        title_prefix = f"【コンテスト シーズン {season} 対戦成績{date_title}】"
        lines = [
            title_prefix,
            f"- 対戦数: **{total} 戦** ｜ 勝敗: **{wins} 勝 {losses} 敗**（勝率: **{win_rate:.1f}%**）",
            f"- 獲得Pt合計: **{total_pt:,} Pt**（平均: **{avg_pt:.1f} Pt/戦**）",
            f"\n📊 **【各ステージの平均スコア】**",
            f"• **ステージ1**: 自平均 `{avg_s1_my:,.0f}` vs 敵平均 `{avg_s1_en:,.0f}`",
            f"• **ステージ2**: 自平均 `{avg_s2_my:,.0f}` vs 敵平均 `{avg_s2_en:,.0f}`",
            f"• **ステージ3**: 自平均 `{avg_s3_my:,.0f}` vs 敵平均 `{avg_s3_en:,.0f}`",
            f"\n■ 各対戦の詳細（全 {total} 戦）:",
        ]

        for r in target_matches:
            r_date  = r.get("日付", "")
            res_str = "🏆 WIN" if self._is_win(r) else "❌ LOSE"
            pt      = r.get("獲得Pt", "-")
            opp     = r.get("相手名") or r.get("対戦相手") or "-"
            s1  = f"自 `{r.get('自S1','-')}` vs 敵 `{r.get('敵S1','-')}`"
            s2  = f"自 `{r.get('自S2','-')}` vs 敵 `{r.get('敵S2','-')}`"
            s3  = f"自 `{r.get('自S3','-')}` vs 敵 `{r.get('敵S3','-')}`"
            lines.append(
                f"- **{r_date}** | {res_str} | +{pt}Pt | 相手: `{opp}`\n"
                f"  └ S1: {s1} ｜ S2: {s2} ｜ S3: {s3}"
            )

        if not date:
            lines.append(f"\n※ シーズン全体の総対戦数: {len(valid)} 戦（通算勝率: {sum(1 for r in valid if self._is_win(r))/len(valid)*100:.1f}%）")

        return "\n".join(lines)

    def _format_multi_season(self, seasons: list[str]) -> str:
        lines = ["【コンテスト 各シーズン別 対戦成績まとめ】\n"]
        total_all, wins_all, pt_all = 0, 0, 0

        for s in seasons:
            valid = self._valid_matches(self._match_histories.get(s, []))
            if not valid:
                continue
            total    = len(valid)
            wins     = sum(1 for r in valid if self._is_win(r))
            win_rate = wins / total * 100 if total > 0 else 0
            pts      = [int(r["獲得Pt"]) for r in valid if r.get("獲得Pt", "").isdigit()]
            total_pt = sum(pts)
            avg_pt   = total_pt / len(pts) if pts else 0

            total_all += total
            wins_all  += wins
            pt_all    += total_pt

            lines.append(
                f"◆ **シーズン {s}**: {total}戦 {wins}勝 {total-wins}敗 "
                f"（勝率: {win_rate:.1f}%） / 獲得Pt: {total_pt:,}（平均: {avg_pt:.1f}）"
            )

            lines.append(
                f"\n📊 **通算（シーズン {seasons[0]} 〜 {seasons[-1]}）**\n"
                f"- {total_all}戦 {wins_all}勝 {total_all-wins_all}敗（通算勝率: **{overall_rate:.1f}%**）\n"
                f"- 獲得Pt総計: **{pt_all:,} Pt**"
            )
        return "\n".join(lines)

    # ── ツール: get_support_card_details ─────────────────────────────────────

    def get_support_card_details(self, card_name: str = "", **kwargs: Any) -> str:
        if not self._support_cards_master:
            return "※ サポートカード詳細マスタデータが見つかりませんでした。"

        q_raw = card_name.strip()
        # 記号除去用正規化関数
        def _clean_s(s: str) -> str:
            return re.sub(r"[！？\?!\s♪〜～\.\…「」『』【】]", "", s.lower())

        q_clean = _clean_s(q_raw)
        matched: list[dict[str, Any]] = []

        # 1. 完全一致 ➔ 2. 記号正規化一致 ➔ 3. 部分一致
        for card in self._support_cards_master:
            c_name = card.get("name", "")
            c_clean = _clean_s(c_name)
            if q_raw == c_name:
                matched = [card]
                break
            elif q_clean and q_clean == c_clean:
                matched = [card]
                break
            elif q_clean and (q_clean in c_clean or c_clean in q_clean):
                matched.append(card)

        if not matched:
            return f"※ '{card_name}' に一致するサポートカードは見つかりませんでした。"

        lines = []
        for card in matched[:3]:  # 最大3件表示
            c_name = card.get("name", "")
            rarity = card.get("rarity", "")
            c_type = card.get("type", "")

            lines.append(f"【サポートカード詳細: **{c_name}** `[{rarity} / {c_type}]`】")

            # 獲得 Pアイテム情報（p_items.csv との照合）
            obtained_pitems = []
            for p in self._p_items:
                p_src = p.get("source", "")
                p_desc = p.get("desc", "")
                p_name = p.get("name", "")
                if c_name in p_src or c_name in p_desc:
                    p_eff = self._dsl.translate(p.get("effects", ""))
                    obtained_pitems.append(f"- 🏆 獲得Pアイテム: **『{p_name}』**\n  効果: {p_eff}")
            if obtained_pitems:
                lines.extend(obtained_pitems)

            # 解放アビリティ・効果
            effects = card.get("unlocked_effects", [])
            if effects:
                lines.append("\n■ サポートアビリティ（解放効果）:")
                for eff in effects:
                    lv = eff.get("level", 0)
                    dsl_raw = eff.get("dsl", "")
                    values = eff.get("values", [])
                    jp_dsl = self._dsl.translate(dsl_raw)

                    # values がある場合、各凸段階（無凸〜完凸）の数値を整形
                    if values and isinstance(values, list):
                        val_str = " / ".join([f"★{i}:{v}" for i, v in enumerate(values)])
                        lines.append(f"- Lv.{lv}〜: {jp_dsl}\n  └ 各凸段階の効果値: `{val_str}`")
                    else:
                        lines.append(f"- Lv.{lv}〜: {jp_dsl}")

            # サポートイベント
            events = card.get("support_events", [])
            if events:
                lines.append("\n■ サポートイベント効果:")
                for ev in events:
                    lv = ev.get("level", 0)
                    dsl_raw = ev.get("dsl", "")
                    jp_dsl = self._dsl.translate(dsl_raw)
                    lines.append(f"- Lv.{lv}〜: {jp_dsl}")

            # 獲得Pアイテム
            item = card.get("acquired_p_item", {})
            if item and isinstance(item, dict) and item.get("name"):
                item_name = item.get("name", "")
                item_eff = self._dsl.translate(item.get("effect", ""))
                lines.append(f"\n■ 獲得Pアイテム: **{item_name}**\n  効果: {item_eff}")

            lines.append("")

        if len(matched) > 3:
            lines.append(f"※他 {len(matched) - 3} 件の一致するサポカがあります。正確なカード名で絞り込んでください。")

        return "\n".join(lines).strip()

    # ── ツール: get_p_idol_details ───────────────────────────────────────────

    def get_p_idol_details(
        self,
        idol_name: str = "",
        title: str = "",
        **kwargs: Any,
    ) -> str:
        from master_data import GakumasMaster, RECOMMENDED_EFFECT_MAP
        master = GakumasMaster()

        target_idol = master.resolve_idol_name(idol_name) if idol_name else ""

        # タイトルの正規化（鉤括弧、ぇ/え、句読点、空白等の除去）
        def normalize_str(s: str) -> str:
            return re.sub(r"[「」『』【】\s、。,\.]", "", s).replace("ぇ", "え").replace("っ", "")

        q_title = normalize_str(title) if title else ""

        matched_pidols = []
        for p in master.p_idols:
            iid = int(p.get("idolId", 0))
            p_iname = master.idols.get(iid, "")
            p_title = p.get("title", "")

            if target_idol and target_idol != p_iname:
                continue

            if q_title:
                norm_p_title = normalize_str(p_title)
                if q_title in norm_p_title or norm_p_title in q_title:
                    matched_pidols.append((p, p_iname))
            elif target_idol:
                matched_pidols.append((p, p_iname))

        if not matched_pidols:
            return f"※ 条件に一致するPアイドルは見つかりませんでした（アイドル: '{idol_name}', タイトル: '{title}'）。"

        lines = []
        for p, iname in matched_pidols[:3]:
            pid = str(p.get("id"))
            t = p.get("title")
            rarity = p.get("rarity")
            plan = p.get("plan", "").upper()
            rec_eff = p.get("recommendedEffect", "")
            rec_eff_jp = RECOMMENDED_EFFECT_MAP.get(rec_eff, {}).get("jp", rec_eff)

            # 固有スキルカードの探索
            unique_skills = []
            for sc in self._skill_cards:
                if str(sc.get("pIdolId", "")).strip() == pid:
                    s_name = sc.get("name", "")
                    s_type = sc.get("type", "")
                    s_cost = sc.get("cost", "")
                    s_act = sc.get("actions", "")
                    s_eff = sc.get("effects", "")
                    dsl_full = "; ".join([x for x in [s_act, s_eff] if x])
                    s_eff_jp = self._dsl.translate(dsl_full) if dsl_full else "（効果記載なし）"
                    unique_skills.append(f"- 『{s_name}』 `[{s_type} / コスト: {s_cost}]`: {s_eff_jp}")

            # MongoDB から所持状況を取得
            owned_status = "未所持"
            if self._db is not None:
                doc = self._db["owned_p_idols"].find_one({"idol_name": iname, "title": t})
                if doc:
                    talent = doc.get("talent_level", 0)
                    awaken = doc.get("awaken_level", 0)
                    owned_status = f"所持中（才能開花: ★{talent} ｜ 特訓: Lv.{awaken}）"

            skills_text = "\n".join(unique_skills) if unique_skills else "  - （固有スキルデータなし）"
            lines.append(
                f"【Pアイドル詳細: **{iname}** 【{t}】 `[{rarity} / {plan} / {rec_eff_jp}]`】\n"
                f"- 所持・育成状況: **{owned_status}**\n"
                f"- 固有スキルカード:\n{skills_text}"
            )

        return "\n\n".join(lines).strip()

    # ── ツール: get_optimized_deck ───────────────────────────────────────────

    def get_optimized_deck(
        self,
        stage: int | None = None,
        idol_name: str = "",
        **kwargs: Any,
    ) -> str:
        """
        最新のコンテスト最適化デッキ Markdown レポートから指定ステージ（または全ステージ）の
        3名編成、メイン/サブメモリー構成、期待中央値スコアを取得する。
        idol_name が指定された場合は、該当アイドルのメイン・サブメモリーの全スキルカード12枚・Pアイテム・ステータスを詳細展開する。
        """
        search_dirs = [
            WORKSPACE_DIR / "shared" / "documents",
            WORKSPACE_DIR / "documents",
            Path("/root/gakumas-workspace/shared/documents"),
        ]

        found_files = []
        for d in search_dirs:
            if d.exists():
                for p in d.glob("*_optimized.md"):
                    found_files.append(p)

        if not found_files:
            return "※ 最適化デッキレポート（*_optimized.md）が見つかりませんでした。"

        # ファイル名で降順ソート（最新の日付・シーズンのものを取得）
        found_files.sort(key=lambda p: p.name, reverse=True)
        latest_file = found_files[0]

        try:
            content = latest_file.read_text(encoding="utf-8")
        except Exception as e:
            return f"※ 最適化レポートの読み込みに失敗しました: {e}"

        # 総合期待中央値の抽出
        overall_score = ""
        m_overall = re.search(r"総合期待中央値：約\s*([\d,]+)\s*Pt", content)
        if m_overall:
            overall_score = m_overall.group(1)

        # アイドル名解決用
        from master_data import GakumasMaster
        master = GakumasMaster()
        target_idol = master.resolve_idol_name(idol_name) if idol_name else ""

        # マッピング辞書の作成
        cards_map = {int(sc["id"]): sc["name"] for sc in self._skill_cards if sc.get("id", "").isdigit()}
        items_map = {int(pi["id"]): pi["name"] for pi in self._p_items if pi.get("id", "").isdigit()}

        # 各ステージのパース
        stages_data = {}
        for s_num in [1, 2, 3]:
            stage_pattern = re.compile(
                rf"###\s+■\s+ステージ{s_num}([\s\S]*?)(?=###\s+■\s+ステージ|$)",
                re.IGNORECASE
            )
            m_stage = stage_pattern.search(content)
            if not m_stage:
                continue

            stage_text = m_stage.group(1)
            stage_total = ""
            m_total = re.search(r"合計期待中央値：約\s*([\d,]+)\s*Pt", stage_text)
            if m_total:
                stage_total = m_total.group(1)

            idols_list = []
            for line in stage_text.split("\n"):
                line = line.strip()
                if line.startswith("|") and not ("アイドル" in line or ":---" in line):
                    cols = [c.strip() for c in line.split("|") if c.strip()]
                    # | アイドル | 順位 | メインメモリー | サブメモリー | 中央値 |
                    if len(cols) >= 5:
                        idols_list.append({
                            "idol": cols[0],
                            "main_mem": cols[2],
                            "sub_mem": cols[3],
                            "median": cols[4],
                        })
            stages_data[s_num] = {
                "total": stage_total,
                "idols": idols_list,
            }

        # ── 特定アイドルの詳細デッキ構成（スキルカード12枚展開）────────────────
        if target_idol or idol_name:
            def norm_n(s: str) -> str:
                return s.replace(" ", "").replace("　", "").strip()

            target_norm = norm_n(target_idol or idol_name)
            matched_entries = []
            for s_num, s_info in stages_data.items():
                if stage is not None and stage != s_num:
                    continue
                for idx, item in enumerate(s_info["idols"]):
                    iname = item["idol"]
                    i_norm = norm_n(iname)
                    if target_norm and (target_norm in i_norm or i_norm in target_norm):
                        matched_entries.append((s_num, idx + 1, item))

            if not matched_entries:
                return f"※ 最適化レポート `{latest_file.name}` 内に、指定されたアイドル '{idol_name}'（ステージ: {stage or '全ステージ'}）の配置が見つかりませんでした。"

            detail_lines = [
                f"【🛡️ コンテスト最適化デッキ詳細: **{target_idol or idol_name}**（参照: `{latest_file.name}`）】",
            ]

            def unpack_memory_details(mem_str: str, label: str) -> list[str]:
                res = [f"■ **{label}**: `{mem_str}`"]
                # メモリーID（5桁前後の数字）を抽出
                m_id = re.search(r"(\d{4,6})", mem_str)
                if not m_id or self._db is None:
                    res.append("  - （メモリー詳細データ取得不可）")
                    return res

                mem_num = m_id.group(1)
                doc = self._db["memories"].find_one({"name": {"$regex": mem_num}})
                if not doc:
                    res.append(f"  - （MongoDB内に ID `{mem_num}` のメモリーが見つかりませんでした）")
                    return res

                params = doc.get("params", [])
                if params and len(params) >= 4:
                    res.append(f"  - ステータス: Vo `{params[0]}` ｜ Da `{params[1]}` ｜ Vi `{params[2]}` ｜ HP `{params[3]}`")

                c_ids = doc.get("skillCardIds", [])
                custs = doc.get("customizations", [])
                res.append("  - 習得スキルカード（6枚）:")
                for i, cid in enumerate(c_ids):
                    cname = cards_map.get(cid, f"ID:{cid}")
                    cust = custs[i] if i < len(custs) else {}
                    cust_names = []
                    if cust and isinstance(cust, dict):
                        for k in cust.keys():
                            c_info = self._customizations.get(str(k), {})
                            cust_names.append(c_info.get("name", str(k)))
                    cust_desc = f" *(カスタム: {', '.join(cust_names)})*" if cust_names else ""
                    res.append(f"    {i+1}. 『{cname}』{cust_desc}")

                i_ids = [iid for iid in doc.get("pItemIds", []) if iid != 0]
                if i_ids:
                    inames = [items_map.get(iid, f"ID:{iid}") for iid in i_ids]
                    res.append(f"  - 獲得Pアイテム: {', '.join(inames)}")

                return res

            for s_num, slot, item in matched_entries:
                detail_lines.append(f"\n### ◆ ステージ {s_num} （枠 {slot} / 期待中央値: `{item['median']} Pt`）")
                detail_lines.extend(unpack_memory_details(item["main_mem"], "メインメモリー"))
                detail_lines.append("")
                detail_lines.extend(unpack_memory_details(item["sub_mem"], "サブメモリー"))

            return "\n".join(detail_lines).strip()

        # ── 全ステージ（または指定ステージ）のサマリー一覧 ────────────────────
        stages_to_show = [stage] if stage in (1, 2, 3) else [1, 2, 3]
        output_lines = [
            f"【🛡️ 現在のコンテスト最適化編成（参照: `{latest_file.name}`）】",
        ]
        if overall_score and stage is None:
            output_lines.append(f"- **3ステージ総合期待中央値**: **約 {overall_score} Pt**\n")

        for s_num in stages_to_show:
            s_data = stages_data.get(s_num)
            if not s_data:
                continue
            output_lines.append(f"### ■ ステージ {s_num} （合計期待中央値: **約 {s_data['total']} Pt**）")
            for idx, idol_item in enumerate(s_data["idols"]):
                output_lines.append(
                    f"- **枠{idx+1}: {idol_item['idol']}** ｜ 期待中央値: `{idol_item['median']} Pt`\n"
                    f"  └ メイン: `{idol_item['main_mem']}`\n"
                    f"  └ サブ: `{idol_item['sub_mem']}`"
                )
            output_lines.append("")

        return "\n".join(output_lines).strip()




