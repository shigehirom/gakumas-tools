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

# ── アイドル特性（Vo/Da/Vi 得意傾向）と審査基準判定 ─────────────────────────

DEFAULT_IDOL_CHARACTERISTICS: dict[str, str] = {
    "花海咲季": "Vi>Da>Vo",
    "月村手毬": "Vo>Da>Vi",
    "藤田ことね": "Da>Vi>Vo",
    "有村麻央": "Vo>Vi>Da",
    "葛城リーリヤ": "Vi>Da>Vo",
    "倉本千奈": "Da>Vi>Vo",
    "紫雲清夏": "Da>Vi>Vo",
    "篠澤広": "Vo>Da>Vi",
    "姫崎莉波": "Vi>Da>Vo",
    "花海佑芽": "Da>Vo>Vi",
    "十王星南": "Vi>Vo>Da",
    "秦谷美鈴": "Vo>Vi>Da",
    "雨夜燕": "Da>Vo>Vi",
    "根緒亜紗里": "",
}


def parse_criteria(criteria_str: str) -> tuple[int, int, int, str]:
    """
    審査基準文字列から (vo, da, vi, trend_str) を抽出する。
    例: '(Vo, Da, Vi) = (45, 35, 20)' -> (45, 35, 20, 'Vo>Da>Vi')
        '0.45,0.2,0.35' -> (45, 20, 35, 'Vo>Vi>Da')
    """
    if not criteria_str:
        return 0, 0, 0, ""

    m = re.search(r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)", criteria_str)
    if not m:
        m_vo = re.search(r"Vo\D*(\d+)", criteria_str, re.IGNORECASE)
        m_da = re.search(r"Da\D*(\d+)", criteria_str, re.IGNORECASE)
        m_vi = re.search(r"Vi\D*(\d+)", criteria_str, re.IGNORECASE)
        if m_vo and m_da and m_vi:
            vo = float(m_vo.group(1))
            da = float(m_da.group(1))
            vi = float(m_vi.group(1))
        else:
            return 0, 0, 0, ""
    else:
        vo = float(m.group(1))
        da = float(m.group(2))
        vi = float(m.group(3))
        if vo <= 1.0 and da <= 1.0 and vi <= 1.0:
            vo, da, vi = round(vo * 100), round(da * 100), round(vi * 100)
        else:
            vo, da, vi = round(vo), round(da), round(vi)

    scores = [("Vo", vo), ("Da", da), ("Vi", vi)]
    scores.sort(key=lambda x: x[1], reverse=True)
    trend = f"{scores[0][0]}>{scores[1][0]}>{scores[2][0]}"
    return int(vo), int(da), int(vi), trend


def evaluate_stage_compatibility(criteria_str: str, char_str: str) -> dict[str, Any]:
    """
    審査基準文字列とアイドルの特性（例: 'Vo>Da>Vi'）を照合し、適合度判定結果を返す。
    """
    _, _, _, crit_trend = parse_criteria(criteria_str)
    if not crit_trend or not char_str:
        return {"level": "unknown", "tag": "", "reason": "判定不可"}

    c_parts = crit_trend.split(">")
    p_parts = char_str.split(">")
    if len(c_parts) != 3 or len(p_parts) != 3:
        return {"level": "unknown", "tag": "", "reason": "判定不可"}

    # 1. 完全合致
    if crit_trend == char_str:
        return {
            "level": "perfect",
            "tag": "🎯完全合致",
            "reason": f"審査基準の優先度（{crit_trend}）と特性が100%一致（最優秀適合）"
        }

    # 2. 準合致 (1位得意が一致)
    if c_parts[0] == p_parts[0]:
        return {
            "level": "semi",
            "tag": f"🥈準合致({c_parts[0]}得意一致)",
            "reason": f"審査最高配分の {c_parts[0]} が最も得意"
        }

    # 3. 準合致 (最低比率のステータスが最低得意)
    if c_parts[2] == p_parts[2]:
        return {
            "level": "semi",
            "tag": f"🥈準合致(低配分{c_parts[2]}抑制・上位集中)",
            "reason": f"審査最低配分の {c_parts[2]} を抑え、高配分2種にステータスが集中"
        }

    # 4. 逆相性（審査1位が最も苦手、または審査3位が最も得意）
    if c_parts[0] == p_parts[2]:
        return {
            "level": "disadvantage",
            "tag": f"⚠️逆相性(最高配分{c_parts[0]}苦手)",
            "reason": f"審査最高配分の {c_parts[0]} が最も苦手なためステータス面で不利"
        }
    if c_parts[2] == p_parts[0]:
        return {
            "level": "disadvantage",
            "tag": f"⚠️逆相性(最低配分{c_parts[2]}特化)",
            "reason": f"審査最低配分の {c_parts[2]} にステータスが偏るため効率低下"
        }

    # 5. 普通
    return {
        "level": "normal",
        "tag": "中立",
        "reason": "突出した得意・苦手相性なし"
    }


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
    {
        "type": "function",
        "function": {
            "name": "get_stage_loadout",
            "description": (
                "MongoDB loadouts コレクションから、指定ステージ・指定アイドルの最新の実走シミュレーション結果"
                "（期待中央値、平均値、Vo/Da/Vi/HP実効パラメータ、スキルカード12枚、獲得Pアイテム、メイン/サブメモリー名）を直接取得する。"
                "「広の最新シミュレーション結果はどう？」「今の実走構成を教えて」「ステージ3の最新ロードアウト」「シミュレーションで出たスコアとカード」などの質問に実行する。"
                "日次最適化レポート（get_optimized_deck）の更新前でも、最新のローカル計算結果を即座に確認できる。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "integer",
                        "description": "対象ステージ番号（1, 2, 3）。必須。",
                    },
                    "idol_name": {
                        "type": "string",
                        "description": "アイドル名またはキー（例: '篠澤広', '広', 'hiro', '手毬', 'temari'）。必須。",
                    },
                },
                "required": ["stage", "idol_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_contest_advisory",
            "description": (
                "あじふらい氏のコンテスト推奨編成・理想デッキアドバイザリデータ（fried_aji3_advisory_XX.md）を取得する。"
                "「あじふらい氏の推奨構成」「おすすめのスキルカード」「理想のPアイテム」「ステージ1の推奨アイドルは誰？」「手持ちメモリーとあじふらい氏の推奨構成の差分」などの質問には必ずこのツールを実行する。"
                "指定ステージの推奨Pアイドル優先度一覧（上位順）、推奨Pアイテム、推奨スキルカード10枚（カスタマイズ指定付き）を返す。"
                "idol_name を指定すると、そのアイドル専用の推奨構成・カード差替をピンポイントで取得できる。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "integer",
                        "description": "対象ステージ番号（1, 2, 3）。必須。",
                    },
                    "idol_name": {
                        "type": "string",
                        "description": "特定のアイドル名（例: '篠澤 広', '広', '星南', '手毬'）。指定するとそのアイドル向けの推奨カードを抽出。省略時はステージの全体推奨およびトップ推奨アイドル",
                    },
                    "season": {
                        "type": "integer",
                        "description": "対象シーズン番号（例: 52）。省略時は最新シーズン",
                    },
                },
                "required": ["stage"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_contest_regulation",
            "description": (
                "コンテストのステージレギュレーション（指定プラン、審査基準Vo/Da/Vi比率、ターン数、Pアイテム、ギミック）を取得し、"
                "各アイドルのパラメータ特性（Vo/Da/Vi得意傾向）と照合した適合度診断（完全合致・準合致・逆相性アイドル）を返す。"
                "「ステージ3の審査基準に合致したアイドルは？」「第52シーズンのルールとおすすめの特性は？」「このステージに向いているアイドルは？」"
                "「なぜ手毬や星南が推奨されるの？」といった質問には必ずこのツールを実行する。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "integer",
                        "description": "ステージ番号（1〜3）。省略時は全ステージの概要を返す",
                    },
                    "season": {
                        "type": "integer",
                        "description": "コンテストシーズン番号（例: 52）。省略時は最新シーズン",
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
        self._init_mongo()
        self._load_csv_data()

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

        self._load_contest_matches()

    def _load_contest_matches(self) -> None:
        """MongoDB contest_matches コレクションから対戦履歴をロードする"""
        if self._db is None:
            return
        try:
            col = self._db["contest_matches"]
            docs = list(col.find({}).sort([("season", 1), ("date", 1), ("matchIndex", 1)]))
            self._match_histories = {}
            for doc in docs:
                s = str(doc.get("season", ""))
                if not s:
                    continue
                if s not in self._match_histories:
                    self._match_histories[s] = []
                self._match_histories[s].append({
                    "日付": doc.get("date", ""),
                    "相手名": doc.get("opponent", {}).get("name", ""),
                    "グレード": str(doc.get("opponent", {}).get("grade", "")),
                    "自S1": str(doc.get("stages", {}).get("stage1", {}).get("myScore", "")),
                    "敵S1": str(doc.get("stages", {}).get("stage1", {}).get("enemyScore", "")),
                    "自S2": str(doc.get("stages", {}).get("stage2", {}).get("myScore", "")),
                    "敵S2": str(doc.get("stages", {}).get("stage2", {}).get("enemyScore", "")),
                    "自S3": str(doc.get("stages", {}).get("stage3", {}).get("myScore", "")),
                    "敵S3": str(doc.get("stages", {}).get("stage3", {}).get("enemyScore", "")),
                    "結果": doc.get("overallResult", ""),
                    "獲得Pt": str(doc.get("earnedPt", "")),
                })
        except Exception as e:
            print(f"[GakumasToolExecutor] Failed to load contest_matches from MongoDB: {e}")

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

    def get_idol_characteristic(self, idol_name: str) -> str:
        """アイドルのパラメータ特性（例: 'Vo>Da>Vi'）を返す。MongoDB から優先取得し、なければ定数にフォールバック"""
        if not idol_name:
            return ""
        norm_name = re.sub(r"\s+", "", idol_name)
        if self._db is not None:
            try:
                doc = self._db["owned_idols"].find_one({
                    "$or": [
                        {"name": norm_name},
                        {"name": " ".join(norm_name)},
                        {"name": {"$regex": re.escape(norm_name)}},
                    ]
                })
                if doc and doc.get("characteristic"):
                    return str(doc["characteristic"]).strip()
            except Exception:
                pass
        for k, v in DEFAULT_IDOL_CHARACTERISTICS.items():
            if k in norm_name or norm_name in k:
                return v
        return ""

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
            "get_stage_loadout":        self.get_stage_loadout,
            "get_support_bonus":        self.get_support_bonus,
            "get_contest_advisory":     self.get_contest_advisory,
            "get_contest_regulation":   self.get_contest_regulation,
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
        # 常に最新の対戦履歴をMongoDBからリロード
        self._load_contest_matches()

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
            char = self.get_idol_characteristic(iname)
            char_line = f"- パラメータ特性: **`{char}`**\n" if char else ""
            lines.append(
                f"【Pアイドル詳細: **{iname}** 【{t}】 `[{rarity} / {plan} / {rec_eff_jp}]`】\n"
                f"{char_line}"
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
        MongoDB loadouts コレクションから各ステージ（または指定ステージ）の最新シミュレーション結果を直接集計し、
        最新の最適化編成（3ステージ上位アイドル、メイン/サブメモリー、期待中央値）を取得する。
        idol_name が指定された場合は、該当アイドルの実効ステータス、全スキルカード12枚（カスタム付き）、Pアイテムを詳細展開する。
        MongoDB 未接続時はフォールバックとして *_optimized.md を参照する。
        """
        if self._db is None:
            return self._get_optimized_deck_from_markdown(stage=stage, idol_name=idol_name, **kwargs)

        try:
            from advisory_parser import IDOL_NAME_TO_KEY, IDOL_KEY_MAP
            from image_resolver import ImageResolver
            resolver = ImageResolver()

            cards_map = {int(sc["id"]): sc["name"] for sc in self._skill_cards if sc.get("id", "").isdigit()}
            items_map = {int(pi["id"]): pi["name"] for pi in self._p_items if pi.get("id", "").isdigit()}

            # ── 1. 特定アイドルの詳細デッキ構成展開 ───────────────────────────
            if idol_name:
                target_key = IDOL_NAME_TO_KEY.get(idol_name, idol_name.lower())
                target_name = IDOL_KEY_MAP.get(target_key, idol_name)
                norm_target = target_name.replace(" ", "").replace("　", "")

                stages_to_search = [stage] if stage in (1, 2, 3) else [3, 2, 1]
                matched_doc = None
                matched_stage = None

                for s_num in stages_to_search:
                    stage_id = 180 + s_num
                    docs = list(self._db["loadouts"].find({"stageId": stage_id}).sort([("createdAt", -1)]))
                    for d in docs:
                        pidol_id = d.get("derived", {}).get("pIdolId")
                        for p in resolver.p_idols:
                            if str(p.get("id")) == str(pidol_id):
                                norm_p = p.get("idol_name", "").replace(" ", "").replace("　", "")
                                if norm_p == norm_target or norm_target in norm_p:
                                    matched_doc = d
                                    matched_stage = s_num
                                    break
                        if matched_doc:
                            break
                    if matched_doc:
                        break

                if not matched_doc:
                    return f"※ MongoDB loadouts 内に、指定されたアイドル '{idol_name}'（ステージ: {stage or '全ステージ'}）の実走データが見つかりませんでした。"

                derived = matched_doc.get("derived", {})
                season = derived.get("season", 52)
                main_pidol_id = derived.get("pIdolId")
                main_pinfo = next((p for p in resolver.p_idols if str(p.get("id")) == str(main_pidol_id)), {})
                display_title = main_pinfo.get("title", "")

                params = matched_doc.get("params", [0, 0, 0, 0])
                stats = matched_doc.get("stats", {})
                med = stats.get("median", 0)
                mean = stats.get("mean", 0)

                groups = matched_doc.get("skillCardIdGroups", [])
                cust_groups = matched_doc.get("customizationGroups", [])

                main_mem_name = ""
                sub_mem_name = ""
                if len(groups) > 0:
                    m_doc = self._db["memories"].find_one({"skillCardIds": groups[0]})
                    if m_doc:
                        main_mem_name = m_doc.get("name", "")
                if len(groups) > 1:
                    s_doc = self._db["memories"].find_one({"skillCardIds": groups[1]})
                    if s_doc:
                        sub_mem_name = s_doc.get("name", "")

                detail_lines = [
                    f"【🛡️ コンテスト最新実走デッキ詳細: **{target_name} 【{display_title}】**】",
                    f"- **配置ステージ**: ステージ {matched_stage} (SEASON {season}) ｜ **ロードアウト名**: `{matched_doc.get('name', 'latest')}`",
                    f"- **期待中央値スコア**: **{int(med):,} Pt** ｜ 平均値: `{int(mean):,} Pt`",
                    f"- **実効ステータス**: Vo `{params[0]}` ｜ Da `{params[1]}` ｜ Vi `{params[2]}` ｜ HP `{params[3]}`",
                ]
                if main_mem_name or sub_mem_name:
                    detail_lines.append(f"- **使用メモリー**: メイン `{main_mem_name or '不明'}` ｜ サブ `{sub_mem_name or '不明'}`")

                pitems = []
                for p_idx, iid in enumerate(matched_doc.get("pItemIds", [])):
                    if iid != 0:
                        iname = items_map.get(iid, f"ID:{iid}")
                        p_desc = f"『{iname}』"
                        if p_idx == 0:
                            p_desc += " *(メイン固有)*"
                        elif p_idx == 1:
                            p_desc += " *(サブ固有)*"
                        elif p_idx >= 2:
                            p_desc += " *(サポカ持ち込み)*"
                        pitems.append(p_desc)
                if pitems:
                    detail_lines.append("- **獲得Pアイテム**:")
                    for idx, pi in enumerate(pitems, 1):
                        detail_lines.append(f"  {idx}. {pi}")

                detail_lines.append("- **採用スキルカード（12枚）**:")
                card_count = 1
                for g_idx, grp in enumerate(groups):
                    grp_label = "メインメモリー由来" if g_idx == 0 else "サブメモリー由来"
                    detail_lines.append(f"  ■ **{grp_label}**:")
                    cg = cust_groups[g_idx] if g_idx < len(cust_groups) else []
                    for c_idx, cid in enumerate(grp):
                        cname = cards_map.get(cid, f"ID:{cid}")
                        cust = cg[c_idx] if c_idx < len(cg) else {}
                        cust_names = []
                        if cust and isinstance(cust, dict):
                            for k in cust.keys():
                                c_info = self._customizations.get(str(k), {})
                                cust_names.append(c_info.get("name", str(k)))
                        cust_desc = f" *(カスタム: {', '.join(cust_names)})*" if cust_names else ""
                        detail_lines.append(f"    {card_count}. 『{cname}』{cust_desc}")
                        card_count += 1

                return "\n".join(detail_lines).strip()

            # ── 2. 全ステージ（または指定ステージ）の最新最適化編成サマリー ──
            stages_to_show = [stage] if stage in (1, 2, 3) else [1, 2, 3]
            stages_data = {}
            overall_median = 0
            all_top_idols = []

            for s_num in [1, 2, 3]:
                stage_id = 180 + s_num
                docs = list(self._db["loadouts"].find({"stageId": stage_id}).sort([("createdAt", -1)]))

                idol_best = {}
                for d in docs:
                    d_name = d.get("name", "")
                    if ".old" in d_name:
                        continue
                    pidol_id = d.get("derived", {}).get("pIdolId")
                    if not pidol_id:
                        continue

                    pinfo = next((p for p in resolver.p_idols if str(p.get("id")) == str(pidol_id)), {})
                    iname = pinfo.get("idol_name", "")
                    title = pinfo.get("title", "")
                    med = d.get("stats", {}).get("median", 0)

                    if iname not in idol_best or med > idol_best[iname]["median"]:
                        groups = d.get("skillCardIdGroups", [])
                        m_name = ""
                        s_name = ""
                        if len(groups) > 0:
                            m_doc = self._db["memories"].find_one({"skillCardIds": groups[0]})
                            if m_doc:
                                m_name = m_doc.get("name", "")
                        if len(groups) > 1:
                            s_doc = self._db["memories"].find_one({"skillCardIds": groups[1]})
                            if s_doc:
                                s_name = s_doc.get("name", "")

                        idol_best[iname] = {
                            "doc": d,
                            "idol_name": iname,
                            "title": title,
                            "median": med,
                            "name": d_name,
                            "main_mem": m_name,
                            "sub_mem": s_name,
                        }

                sorted_idols = sorted(idol_best.values(), key=lambda x: x["median"], reverse=True)
                top3 = sorted_idols[:3]
                stg_sum = sum(x["median"] for x in top3)
                overall_median += stg_sum

                stages_data[s_num] = {
                    "total": stg_sum,
                    "idols": top3,
                }
                for itm in top3:
                    all_top_idols.append((s_num, itm["idol_name"]))

            output_lines = [
                "【🛡️ 現在のコンテスト最新最適化編成（MongoDB `loadouts` 直読）】",
            ]
            if stage is None:
                output_lines.append(f"- **3ステージ総合期待中央値**: **約 {int(overall_median):,} Pt**\n")

            for s_num in stages_to_show:
                s_data = stages_data.get(s_num)
                if not s_data:
                    continue
                output_lines.append(f"### ■ ステージ {s_num} （合計期待中央値: **約 {int(s_data['total']):,} Pt**）")
                for idx, idol_item in enumerate(s_data["idols"], 1):
                    full_id = f"{idol_item['idol_name']}【{idol_item['title']}】" if idol_item['title'] else idol_item['idol_name']
                    output_lines.append(
                        f"- **枠{idx}: {full_id}** ｜ 期待中央値: **{int(idol_item['median']):,} Pt**\n"
                        f"  └ メイン: `{idol_item['main_mem'] or '不明'}`\n"
                        f"  └ サブ: `{idol_item['sub_mem'] or '不明'}`"
                    )
                output_lines.append("")

            # 同一アイドルの重複検出
            seen_idols = {}
            duplicates = []
            for s_num, iname in all_top_idols:
                if iname in seen_idols:
                    duplicates.append((iname, seen_idols[iname], s_num))
                else:
                    seen_idols[iname] = s_num

            if duplicates and stage is None:
                dup_msgs = [f"『{name}』（ステージ{s1} と ステージ{s2}）" for name, s1, s2 in duplicates]
                output_lines.append(
                    f"⚠️ **アイドル重複の注意**: {', '.join(dup_msgs)} が各ステージの単体トップ3で重複しています。"
                    f"実際のコンテスト本番では同一アイドルはいずれか1ステージにのみ配置可能です。"
                )

            return "\n".join(output_lines).strip()

        except Exception as e:
            return f"※ MongoDB loadouts からの最適化編成取得エラー: {e}（フォールバック試行中...）\n" + self._get_optimized_deck_from_markdown(stage=stage, idol_name=idol_name, **kwargs)

    def _get_optimized_deck_from_markdown(
        self,
        stage: int | None = None,
        idol_name: str = "",
        **kwargs: Any,
    ) -> str:
        """Markdown ファイル (*_optimized.md) から過去のレポートを取得するフォールバック"""
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

        found_files.sort(key=lambda p: p.name, reverse=True)
        latest_file = found_files[0]

        try:
            content = latest_file.read_text(encoding="utf-8")
        except Exception as e:
            return f"※ 最適化レポートの読み込みに失敗しました: {e}"

        return f"【🛡️ 過去のコンテスト最適化編成（フォールバック参照: `{latest_file.name}`）】\n" + content[:1500]

    # ── ツール: get_stage_loadout ────────────────────────────────────────────

    def get_stage_loadout(
        self,
        stage: int,
        idol_name: str,
        **kwargs: Any,
    ) -> str:
        """
        MongoDB loadouts コレクションから、指定ステージ・指定アイドルの最新の実走シミュレーション結果
        （期待中央値、平均値、Vo/Da/Vi/HP実効パラメータ、スキルカード12枚、獲得Pアイテム、メイン/サブメモリー名）を直接取得する。
        """
        if self._db is None:
            return "※ MongoDB に接続されていないため、実走ロードアウトを取得できません。"

        try:
            from advisory_parser import IDOL_NAME_TO_KEY, IDOL_KEY_MAP
            from image_resolver import ImageResolver
            resolver = ImageResolver()

            target_key = IDOL_NAME_TO_KEY.get(idol_name, idol_name.lower())
            target_name = IDOL_KEY_MAP.get(target_key, idol_name)

            stage_id = 180 + stage if stage in (1, 2, 3) else stage

            # loadouts を検索 (最新のシミュレーション結果)
            cursor = list(self._db["loadouts"].find({"stageId": stage_id}).sort([("createdAt", -1)]))
            if not cursor:
                cursor = list(self._db["loadouts"].find({"stageId": stage_id}).sort([("stats.median", -1)]))

            matched_doc = None
            norm_target = target_name.replace(" ", "").replace("　", "")
            for d in cursor:
                pidol_id = d.get("derived", {}).get("pIdolId")
                for p in resolver.p_idols:
                    if str(p.get("id")) == str(pidol_id):
                        norm_p_name = p.get("idol_name", "").replace(" ", "").replace("　", "")
                        if norm_p_name == norm_target or norm_target in norm_p_name:
                            matched_doc = d
                            break
                if matched_doc:
                    break

            if not matched_doc:
                return f"※ ステージ {stage} のアイドル '{idol_name}'（{target_name}）の実走ロードアウトが見つかりませんでした。"

            # データ展開
            derived = matched_doc.get("derived", {})
            season = derived.get("season", 52)
            main_pidol_id = derived.get("pIdolId")
            main_pinfo = next((p for p in resolver.p_idols if str(p.get("id")) == str(main_pidol_id)), {})
            display_title = main_pinfo.get("title", "")

            params = matched_doc.get("params", [0, 0, 0, 0])
            stats = matched_doc.get("stats", {})
            med = stats.get("median", 0)
            mean = stats.get("mean", 0)

            # メモリー名照合
            groups = matched_doc.get("skillCardIdGroups", [])
            cust_groups = matched_doc.get("customizationGroups", [])
            main_mem_name = ""
            sub_mem_name = ""
            if len(groups) > 0:
                m_doc = self._db["memories"].find_one({"skillCardIds": groups[0]})
                if m_doc:
                    main_mem_name = m_doc.get("name", "")
            if len(groups) > 1:
                s_doc = self._db["memories"].find_one({"skillCardIds": groups[1]})
                if s_doc:
                    sub_mem_name = s_doc.get("name", "")

            lines = [
                f"【⚔️ ステージ{stage} 実走シミュレーション結果: **{target_name} 【{display_title}】**】",
                f"- **シーズン**: SEASON {season} ｜ **ロードアウト名**: `{matched_doc.get('name', 'latest')}`",
                f"- **期待中央値スコア**: **{int(med):,} Pt** ｜ 平均値: `{int(mean):,} Pt`",
                f"- **実効パラメータ**: Vo `{params[0]}` ｜ Da `{params[1]}` ｜ Vi `{params[2]}` ｜ HP `{params[3]}`",
            ]
            if main_mem_name or sub_mem_name:
                lines.append(f"- **使用メモリー**: メイン `{main_mem_name or '不明'}` ｜ サブ `{sub_mem_name or '不明'}`")

            # Pアイテム
            pitems = []
            for idx, pid in enumerate(matched_doc.get("pItemIds", [])):
                if pid > 0:
                    p_info = resolver.p_items_by_id.get(pid, {"name": f"Item_{pid}"})
                    p_label = resolver.get_p_item_card_label(p_info["name"])
                    grp = "メイン" if idx < 4 else "サブ"
                    pitems.append(f"{p_info['name']} ({grp}: {p_label})")
            if pitems:
                lines.append(f"- **獲得Pアイテム ({len(pitems)}枠)**: " + ", ".join(pitems))

            # スキルカード12枚
            raw_cards = []
            for g_idx, group in enumerate(groups):
                cust_group = cust_groups[g_idx] if g_idx < len(cust_groups) else []
                for c_idx, cid in enumerate(group):
                    if cid <= 0:
                        continue
                    info = resolver.get_card_details(cid)
                    cust_dict = cust_group[c_idx] if c_idx < len(cust_group) else {}
                    cust_names = []
                    for k, v in cust_dict.items():
                        c_name = resolver.customizations.get(int(k), f"カスタム{k}")
                        cust_names.append(f"{c_name} Lv{v}" if v > 1 else c_name)

                    is_unique = (c_idx == 0 and info.get("pIdolId", 0) > 0) or info.get("sourceType") == "pidol"
                    raw_cards.append({
                        "name": info.get("name", f"Card_{cid}"),
                        "rarity": info.get("rarity", "R").upper(),
                        "sourceType": info.get("sourceType", "produce").lower(),
                        "group": "メイン" if g_idx == 0 else "サブ",
                        "is_main_unique": (g_idx == 0 and is_unique),
                        "is_sub_unique": (g_idx == 1 and is_unique),
                        "customizations": cust_names,
                    })

            def _sort_key(c):
                r_order = {"SSR": 0, "SR": 1, "R": 2}.get(c["rarity"], 3)
                is_support = (c["sourceType"] == "support") or bool(resolver.get_skill_card_support_card_name(c["name"]))
                if is_support:
                    s_order = 0
                elif c.get("is_main_unique"):
                    s_order = 1
                elif c.get("is_sub_unique"):
                    s_order = 2
                elif c["sourceType"] == "pidol":
                    s_order = 3
                else:
                    s_order = 4
                return (r_order, s_order, c["name"])

            raw_cards.sort(key=_sort_key)

            lines.append("\n■ **実走スキルカード（12枚構成・レアリティ順）**:")
            for i, c in enumerate(raw_cards):
                badge = "[サポカ]" if (c["sourceType"] == "support" or resolver.get_skill_card_support_card_name(c["name"])) else ("[メイン固有]" if c.get("is_main_unique") else ("[サブ固有]" if c.get("is_sub_unique") else f"[{c['group']}]"))
                cust_desc = f" *(カスタム: {', '.join(c['customizations'])})*" if c["customizations"] else ""
                lines.append(f"  {i+1}. [{c['rarity']}] {badge} 『{c['name']}』{cust_desc}")

            return "\n".join(lines).strip()

        except Exception as e:
            log.error(f"[get_stage_loadout] エラー: {e}", exc_info=True)
            return f"※ 実走ロードアウト取得中にエラーが発生しました: {e}"

    # ── ツール: get_contest_advisory ─────────────────────────────────────────

    def get_contest_advisory(
        self,
        stage: int,
        idol_name: str = "",
        season: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        あじふらい氏推奨構成 Markdown（fried_aji3_advisory_XX.md）から指定ステージ（およびアイドル）の
        推奨Pアイドル優先度順、推奨Pアイテム、推奨スキルカード10枚（カスタマイズ付き）を取得する。
        """
        try:
            from advisory_parser import parse_advisory, get_stage_recommended_pidols, find_latest_season, get_stage_regulation
        except ImportError:
            import sys
            sys.path.insert(0, str(WORKSPACE_DIR / "gakumas-agent-bot"))
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from advisory_parser import parse_advisory, get_stage_recommended_pidols, find_latest_season, get_stage_regulation

        season_info = find_latest_season(season)
        if not season_info:
            return f"※ 第{season if season else ''}シーズンのあじふらい氏推奨アドバイザリ（fried_aji3_advisory_*.md）が見つかりませんでした。"

        cur_season, _ = season_info
        reg_info = get_stage_regulation(cur_season, stage)
        pidols = get_stage_recommended_pidols(stage, cur_season)

        lines = [
            f"【第{cur_season}シーズン ステージ{stage} あじふらい氏推奨アドバイザリ】",
            f"■ 審査基準: {reg_info.get('criteria', '')} ｜ プラン: {reg_info.get('plan_jp', '')} ({reg_info.get('plan', '')}) ｜ ターン数: {reg_info.get('turns', 12)}T"
        ]

        # おすすめPアイドル一覧（上位順）
        if pidols:
            criteria_str = reg_info.get("criteria", "")
            lines.append("\n■ おすすめPアイドル一覧（上から優先度順・特性適合度）:")
            for idx, p in enumerate(pidols, 1):
                p_name = p.get("idol_name", "")
                p_char = self.get_idol_characteristic(p_name)
                p_eval = evaluate_stage_compatibility(criteria_str, p_char)
                compat_str = f" `[{p_char} {p_eval['tag']}]`" if p_char else ""
                sub_str = f" (サブ候補: {', '.join([s['title'] for s in p.get('subs', [])])})" if p.get("subs") else ""
                extra_str = f" {p.get('extra', '')}" if p.get("extra") else ""
                lines.append(f"  {idx}. {p_name}【{p.get('title', '')}】{compat_str}{extra_str}{sub_str}")

        # 特定アイドルまたはトップ推奨アイドルの詳細推奨構成
        data = parse_advisory(stage=stage, idol_query=idol_name if idol_name else None, season=cur_season)
        if data:
            target_p = data.get("p_idol", {})
            target_name = target_p.get("idol_name", "")
            target_title = target_p.get("title", "")
            target_char = self.get_idol_characteristic(target_name)
            char_note = f" (特性: `{target_char}`)" if target_char else ""
            lines.append(f"\n■ 【{target_name}【{target_title}】向けの推奨構成{char_note}】")

            # 推奨Pアイテム
            p_items = data.get("p_items", [])
            if p_items:
                lines.append(f"  - 推奨Pアイテム: {', '.join([f'『{item}』' for item in p_items])}")

            # 推奨スキルカード（最大10枚）
            skill_cards = data.get("skill_cards", [])
            if skill_cards:
                lines.append("  - 推奨スキルカード10枚（カスタマイズ指定）:")
                for c_idx, c in enumerate(skill_cards, 1):
                    cust_str = f" (カスタム: {', '.join(c['customizations'])})" if c.get("customizations") else ""
                    lines.append(f"    {c_idx}. 『{c.get('name', '')}』{cust_str}")

        return "\n".join(lines)

    # ── ツール: get_contest_regulation ───────────────────────────────────────

    def get_contest_regulation(
        self,
        stage: int | None = None,
        season: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        コンテストのステージレギュレーション（プラン、審査基準、ターン数、Pアイテム、バフ）を取得し、
        各アイドルのパラメータ特性（Vo/Da/Vi）との適合度診断を行う。
        """
        try:
            from advisory_parser import find_latest_season, get_stage_regulation, get_stage_recommended_pidols, INSTRUCTIONS_DIRS
        except ImportError:
            import sys
            sys.path.insert(0, str(WORKSPACE_DIR / "gakumas-agent-bot"))
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from advisory_parser import find_latest_season, get_stage_regulation, get_stage_recommended_pidols, INSTRUCTIONS_DIRS


        season_info = find_latest_season(season)
        if not season_info:
            return f"※ 第{season if season else ''}シーズンのレギュレーション情報（regulation_*.md）が見つかりませんでした。"

        cur_season, _ = season_info
        stages_to_process = [stage] if stage in (1, 2, 3) else [1, 2, 3]

        # アイドルごとのプラン所持情報（センス/ロジック/アノマリー）を把握
        from master_data import GakumasMaster
        master = GakumasMaster()
        idol_plans: dict[str, dict[str, list[str]]] = {}
        for p in master.p_idols:
            iid = int(p.get("idolId", 0))
            iname = re.sub(r"\s+", "", master.idols.get(iid, ""))
            pl = p.get("plan", "").lower()
            title = p.get("title", "")
            if iname and pl:
                if iname not in idol_plans:
                    idol_plans[iname] = {}
                if pl not in idol_plans[iname]:
                    idol_plans[iname][pl] = []
                if title and title not in idol_plans[iname][pl]:
                    idol_plans[iname][pl].append(title)

        output_lines = [
            f"【🏆 第{cur_season}コンテストシーズン レギュレーション＆アイドル適合診断】\n"
        ]

        # regulation_{season}.md のテキスト全体を読み込んで詳細ギミックを取得
        reg_text = ""
        for d in INSTRUCTIONS_DIRS:
            rf = d / f"regulation_{cur_season}.md"
            if rf.exists():
                reg_text = rf.read_text(encoding="utf-8")
                break

        for s_num in stages_to_process:
            reg_info = get_stage_regulation(cur_season, s_num)
            plan = reg_info.get("plan", "")
            plan_jp = reg_info.get("plan_jp", "")
            criteria = reg_info.get("criteria", "")
            turns = reg_info.get("turns", 12)
            vo, da, vi, crit_trend = parse_criteria(criteria)

            # 詳細なバフやPアイテム情報を抽出
            buff_info = "なし"
            p_item_info = "なし"
            if reg_text:
                stages_split = re.split(r"(?m)^#\s*Stage:\s*", reg_text)
                for sp in stages_split:
                    lines = sp.strip().splitlines()
                    if lines and lines[0].strip().startswith(str(s_num)):
                        buff_m = re.search(r"buf/debuf:\s*(.*)", sp)
                        if buff_m and buff_m.group(1).strip() and buff_m.group(1).strip() != "none":
                            buff_info = buff_m.group(1).strip()
                        p_item_m = re.search(r"name:\s*(.*)", sp)
                        if p_item_m:
                            p_item_info = p_item_m.group(1).strip()
                        break

            output_lines.append(f"### ■ ステージ {s_num} （{plan_jp} / {turns}ターン）")
            output_lines.append(f"- **審査基準**: `{criteria}` ➔ **傾向: 【{crit_trend}】** (Vo:{vo}% / Da:{da}% / Vi:{vi}%)")
            output_lines.append(f"- **ステージギミック/バフ**: {buff_info}")
            output_lines.append(f"- **ステージPアイテム**: {p_item_info}\n")

            # 適合度分類
            perfect_list = []
            semi_list = []
            disadv_list = []

            for idol_name, default_char in DEFAULT_IDOL_CHARACTERISTICS.items():
                if not idol_name or idol_name == "根緒亜紗里":
                    continue
                char = self.get_idol_characteristic(idol_name) or default_char
                if not char:
                    continue
                eval_res = evaluate_stage_compatibility(criteria, char)
                norm_idol = re.sub(r"\s+", "", idol_name)
                matching_titles = idol_plans.get(norm_idol, {}).get(plan, [])
                if matching_titles:
                    plan_note = f"✅{plan_jp}衣装あり（【{matching_titles[0]}】等）"
                else:
                    plan_note = f"⚠️{plan_jp}衣装なし"

                entry = f"- **{idol_name}** (`{char}` ｜ {plan_note}): {eval_res['reason']}"
                if eval_res["level"] == "perfect":
                    perfect_list.append(entry)
                elif eval_res["level"] == "semi":
                    semi_list.append(entry)
                elif eval_res["level"] == "disadvantage":
                    disadv_list.append(entry)


            output_lines.append("【📊 審査基準 × アイドル特性 適合度診断】")
            if perfect_list:
                output_lines.append("🎯 **完全合致（最優秀適合）**:")
                output_lines.extend(["  " + e for e in perfect_list])
            if semi_list:
                output_lines.append("🥈 **準合致（好相性）**:")
                output_lines.extend(["  " + e for e in semi_list])
            if disadv_list:
                output_lines.append("⚠️ **逆相性・ステータス不利（要サポート補強）**:")
                output_lines.extend(["  " + e for e in disadv_list])

            # あじふらい氏推奨アイドル上位との照合
            pidols = get_stage_recommended_pidols(s_num, cur_season)
            if pidols:
                output_lines.append("\n【💡 あじふらい氏推奨アイドル上位との照合】")
                for idx, p in enumerate(pidols[:5], 1):
                    p_name = p.get("idol_name", "")
                    p_char = self.get_idol_characteristic(p_name)
                    p_eval = evaluate_stage_compatibility(criteria, p_char)
                    output_lines.append(f"  {idx}. {p_name}【{p.get('title', '')}】 `[{p_char} {p_eval['tag']}]`")

            output_lines.append("")

        return "\n".join(output_lines).strip()





