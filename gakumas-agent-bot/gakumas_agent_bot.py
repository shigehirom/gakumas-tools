"""
gakumas_agent_bot.py — 学園アイドルマスター 特化型 Discord 相談 Bot (スマート自動判別 & ハイブリッド版)

主な機能:
  - 質問内容に応じて最適なモデルを自動選択（Auto Mode / デフォルト）:
    * データ検索・カード効果 ──► Qwen 3.5 9B (最速・高精度)
    * 戦術・考察・シナジー ──► DeepSeek-R1 8B (思考推論)
    * 一般解説・ガイド ────► Gemma 2 9B (丁寧な解説)
    * 画像・高度なシミュレーション ──► Gemini 3.6 Flash (Antigravity SDK)
  - /model コマンドで [auto | qwen | gemma | deepseek | gemini] を手動固定も可能
  - 完全ローカル・API消費ゼロの高速対話
  - コードブロック保護ストリーミング分割送信 (SmartMessageBuffer)
"""

import asyncio
import io
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import aiohttp
import discord
from google.antigravity import (
    Agent,
    CapabilitiesConfig,
    LocalAgentConfig,
)
from google.antigravity.hooks import policy
from google.antigravity.types import ChatResponse, SessionContinuationMode

from agent_engine import AgentEngine
from quota_tracker import quota_tracker
from contest_parser import parse_contest_images
from dsl_translator import DslTranslator
from gakumas_data_searcher import GakumasDataSearcher
from gakumas_tools import GakumasToolExecutor
from image_resolver import ImageResolver
from match_history_updater import update_match_history_csv, get_latest_season_number
from sync_service import GakumasSyncService

# ────────────────────────────── .env 読み込み ────────────────────────────────

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
                    # インラインコメントを除去
                    if "#" in line:
                        line = line.split("#", 1)[0].strip()
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v

_load_env()

# ────────────────────────────── 設定 ────────────────────────────────────────

DISCORD_TOKEN      = os.environ.get("DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_TOKEN", "")
ALLOWED_CHANNEL_ID = int(os.environ.get("ALLOWED_CHANNEL_ID", "0"))
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
LLM_BASE_URL       = os.environ.get("LLM_BASE_URL", os.environ.get("OLLAMA_HOST", "http://192.168.100.4:30080/v1"))
LLM_MODEL          = os.environ.get("LLM_MODEL", "/models/qwen2.5-7b.gguf")
LLM_API_KEY        = os.environ.get("LLM_API_KEY", "dummy")
OLLAMA_HOST        = LLM_BASE_URL

AVAILABLE_MODELS = {
    "gemini": "Gemini 3.7 Flash (あさり先生 高度推論・Function Calling・デフォルト)",
    "qwen": "Qwen 2.5 7B (llama.cpp Vulkan / ローカル高速フォールバック)"
}

DISCORD_MAX_LEN   = 1800
FLUSH_TIMEOUT_SEC = 0.8

# ──────────────────────────── ログ設定 ──────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("gakumas_bot")
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.client").setLevel(logging.WARNING)

# ───────────────────────── ヘルプテキスト ───────────────────────────────────

HELP_TEXT = """**🎓 初星学園プロデューサー科 相談室（あさり先生）**

チャットで自由に質問するだけで、担任の**根緒 亜紗里（あさり先生 / Gemini 3.7 Flash）**が学マスのマスタデータや所持データ（MongoDB）を自律検索しながら高精度にアドバイス・解説します。

**【主な相談内容】**
- 🔍 **カード・アイテム・サポカ検索**: スキルカード効果、獲得Pアイテム、サポートアビリティを即座に特定
- 🏆 **所持・戦績診断**: 所持アイドル、所持メモリー、コンテスト対戦成績（シーズン勝率）を総合診断
- 🛡️ **コンテスト編成指導**: ステージごとの最適編成やキーカード、改善点のアドバイス
- 🖼️ **カード画像自動解決**: 言及されたPアイドル、スキルカード、サポートカードの画像を自動添付
- 📊 **クォータ追跡**: 回答フッターおよび `/quota` で本日のAPI利用状況を確認可能

**【相談室コマンド一覧】**
`/advisory [1-3] [アイドル名]` : あじふらい氏推奨のPアイテム・スキルカード構成画像（Pixel 10 Pro Fold 最適化）を即座に出力
`/help` : このヘルプを表示
`/quota` : 本日の Gemini API 利用状況・クォータ残量グラフを表示
`/status` : 本日のシステム稼働状態とモデル情報を表示
`/model [gemini|qwen]` : メイン推論エンジンを切り替え
`/clear [件数]` : チャンネル内の過去メッセージを一括削除（デフォルト50件）
`/new` : 会話セッションをリセット
`/cancel` : 処理中の回答を中断

※コンテスト記録（`/record-contest`）やシミュレーション（`/contest`）等のツール機能は **My Gakumas Tools** をご利用ください。
"""

_KNOWN_COMMANDS = frozenset(["/help", "/quota", "/status", "/cancel", "/retry", "/continue", "/new", "/model", "/clear", "/sync", "/advisory"])
# ────────────────────── スマート自動ルーター ────────────────────────────────

def route_query_to_model(query: str) -> tuple[str, str, str]:
    """
    質問テキストを分析し、最適な (mode, model_name, label) を返す
    Returns: (mode: "ollama"|"gemini", model_name: str, label: str)
    """
    q = query.lower()

    # 0. 対戦成績・勝率・所持データ(MongoDB)・マスタデータ・数値集計系 ➔ Qwen 2.5 (高速・超安定)
    data_keywords = [
        "対戦成績", "戦績", "勝率", "対戦結果", "コンテスト結果", "マッチ履歴", "何勝", "各シーズン", "シーズンごとの",
        "所持", "持っている", "才能開花", "特訓レベル", "完凸", "凸数", "上限解放", "カード", "アイテム", "一覧", "効果", "コスト"
    ]
    if any(k in q for k in data_keywords):
        return ("ollama", "qwen2.5:7b", "Qwen 2.5 7B (マスタ・所持データ検索)")


    # 1. 思考・戦術・理由・考察系 ➔ DeepSeek-R1
    deepseek_keywords = ["なぜ", "どう立ち回る", "戦略", "理由", "考察", "比較", "どっち", "強い理由", "シナジー", "立ち回り", "勝つには", "評価"]
    if any(k in q for k in deepseek_keywords):
        return ("ollama", "deepseek-r1:8b", "DeepSeek-R1 8B (思考・戦術考察)")

    # 2. 一般解説・初心者ガイド・概要系 ➔ Gemma 2
    gemma_keywords = ["初心者", "解説して", "教えて", "概要", "流れ", "とは", "ストーリー", "特徴", "違い"]
    if any(k in q for k in gemma_keywords):
        return ("ollama", "gemma2:9b", "Gemma 2 9B (自然言語解説)")

    # 3. デフォルト ➔ Qwen 2.5
    return ("ollama", "qwen2.5:7b", "Qwen 2.5 7B (標準モデル)")


# ────────────────────── SmartMessageBuffer ─────────────────────────────────

class SmartMessageBuffer:
    def __init__(self, max_len: int = DISCORD_MAX_LEN):
        self.max_len = max_len
        self._buf: list[str] = []
        self._in_code_block: bool = False
        self._code_lang: str = ""

    def add_token(self, token: str) -> None:
        self._buf.append(token)
        if "```" in token:
            lines = "".join(self._buf).splitlines()
            in_code = False
            lang = ""
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("```"):
                    if not in_code:
                        in_code = True
                        lang = stripped[3:].strip()
                    else:
                        in_code = False
                        lang = ""
            self._in_code_block = in_code
            self._code_lang = lang

    def has_content(self) -> bool:
        return bool(self._buf)

    def total_length(self) -> int:
        return sum(len(s) for s in self._buf)

    def flush(self, force: bool = False) -> list[str]:
        if not self._buf:
            return []

        full_text = "".join(self._buf)
        if not force and self._in_code_block and len(full_text) < self.max_len:
            return []

        chunks: list[str] = []
        lines = full_text.splitlines(keepends=True)
        current_chunk: list[str] = []
        current_len = 0
        in_code = False
        current_lang = ""

        for line in lines:
            line_len = len(line)
            stripped = line.strip()

            if stripped.startswith("```"):
                if not in_code:
                    in_code = True
                    current_lang = stripped[3:].strip()
                else:
                    in_code = False
                    current_lang = ""

            if current_len + line_len > self.max_len and current_chunk:
                if in_code:
                    current_chunk.append("```\n")
                    chunks.append("".join(current_chunk))
                    current_chunk = [f"```{current_lang}\n", line]
                    current_len = len(current_chunk[0]) + line_len
                else:
                    chunks.append("".join(current_chunk))
                    current_chunk = [line]
                    current_len = line_len
            else:
                current_chunk.append(line)
                current_len += line_len

        if current_chunk:
            chunks.append("".join(current_chunk))

        self._buf.clear()
        self._in_code_block = in_code
        self._code_lang = current_lang
        return [c for c in chunks if c.strip()]

# ──────────────────── Ollama Service (ローカルLLM) ──────────────────────────

SYSTEM_PROMPT_TEMPLATE = """
あなたは「学園アイドルマスター（学マス）」の厳格かつ高精度なデータ分析アドバイザーです。
提供された公式マスタデータや所持データ（Pアイドル、サポカ、スキルカード、対戦成績）を正確に読み取り、**必ず自然な日本語で**回答してください。

【学マスの絶対厳守ルール】
1. **データの一致と項目捏造の厳禁**:
   - 提供されたデータに記載されている正式名称（アイドル名、二つ名、カード名、数値）を**1文字も変えずにそのまま**出力してください。
   - **データに含まれていない項目（例えばPアイドルのデータに対する「コスト」「効果」など）を勝手に創作・追加することは絶対に禁止です。**

2. **公式用語の厳守**:
   - アノマリープランのスタンス公式名称は **【強気】【温存】【全力】** のみです（「慎重」などの非公式用語は使用禁止）。
   - 他プラン（センス・好印象・やる気）の用語を絶対に混ぜないでください。

3. **DSLコードの排除**:
   - `if:`, `isPreservation`, `{}` などの生DSLコードをそのまま出力せず、提供された自然な日本語効果テキストを用いてください。

4. **回答レイアウト（Discord 最適化フォーマット）**:
   ※Markdown の表（テーブル `|---|`）は使わず、提供されたデータの項目に合わせて出力してください：

   ■ **所持 P アイドルの場合**:
   ◆ 🟣 **【二つ名】アイドル名** `[レアリティ / プラン]`
   ・才能開花: **★X** ｜ 特訓レベル: **Lv.X**

   ■ **所持サポートカードの場合**:
   ◆ **カード名** `[レアリティ / タイプ]`
   ・上限解放: **X 凸** ｜ レベル: **Lv.X** ｜ 習得スキル: 『スキル名』

   ■ **スキルカードの場合**:
   ◆ **カード名** `[レアリティ / タイプ / 使用制限]`
   ・コスト: 体力消費 X ｜ 効果: 効果内容

   ■ **対戦成績・勝率の場合**:
   提供された集計レポート（勝敗、勝率、平均Pt、対戦履歴）をそのまま綺麗に出力してください。
"""






class OllamaService:
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host.rstrip("/")
        self.history: list[dict[str, str]] = []
        self._is_busy = False
        self._cancel_flag = False

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    def reset_session(self):
        self.history = []

    def cancel(self):
        self._cancel_flag = True

    async def chat_stream(self, prompt: str, model: str, context_data: str = "") -> AsyncIterator[str]:
        self._is_busy = True
        self._cancel_flag = False

        user_content = prompt
        if context_data:
            user_content = f"{prompt}\n\n{context_data}"

        messages = [{"role": "system", "content": SYSTEM_PROMPT_TEMPLATE}]
        messages.extend(self.history[-6:])
        messages.append({"role": "user", "content": user_content})

        url = f"{self.host}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.3
            }
        }

        full_response = []
        try:
            # ストリーミング通信用タイムアウト（プロンプト評価と生成の待機時間を十分に確保）
            timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:

                async with session.post(url, json=payload) as res:
                    if res.status != 200:
                        err_text = await res.text()
                        yield f"⚠️ **[Ollama エラー ({res.status})]**: {err_text}"
                        return



                    async for line in res.content:
                        if self._cancel_flag:
                            yield "\n🛑 *[応答を中断しました]*"
                            break

                        if line:
                            try:
                                data = json.loads(line.decode("utf-8"))
                                token = data.get("message", {}).get("content", "")
                                if token:
                                    full_response.append(token)
                                    yield token
                            except Exception:
                                pass

            if full_response and not self._cancel_flag:
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": "".join(full_response)})

        except Exception as e:
            log.error("[Ollama] チャット通信例外: %s", e, exc_info=True)
            yield f"⚠️ **[ローカルLLM通信エラー]**: `{e}`"
        finally:
            self._is_busy = False

# ──────────────────── Antigravity SDK Service (Gemini API) ───────────────────

class AntigravitySDKService:
    def __init__(self):
        self._agent: Agent | None = None
        self._current_response: ChatResponse | None = None
        self._is_busy = False

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    async def start(self):
        config = LocalAgentConfig(
            api_key=GEMINI_API_KEY if GEMINI_API_KEY else None,
            app_data_dir=str(Path.home() / ".gemini/antigravity-ide"),
            workspaces=["/root/gakumas-workspace"],
            model="gemini-3.6-flash",
            policies=[policy.allow_all()],
            system_instructions=SYSTEM_PROMPT_TEMPLATE,
            capabilities=CapabilitiesConfig(enable_subagents=True),
        )
        self._agent = Agent(config)
        await self._agent.__aenter__()

    async def chat_stream(self, prompt: str) -> AsyncIterator[str]:
        if not self._agent or not self._agent.is_started:
            await self.start()
        self._is_busy = True
        try:
            response = await self._agent.chat(prompt)
            self._current_response = response
            async for token in response:
                yield token
        except Exception as e:
            yield f"⚠️ **[Gemini SDK エラー]**: `{e}`"
        finally:
            self._current_response = None
            self._is_busy = False

    def cancel(self):
        if self._current_response:
            self._current_response.cancel()

# ────────────────────────── Discord Bot 本体 ─────────────────────────────────

class GakumasAntigravityBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._executor = GakumasToolExecutor()
        self._agent_engine = AgentEngine(
            self._executor,
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            gemini_api_key=GEMINI_API_KEY,
        )
        self.gemini_service = AntigravitySDKService()
        self.sync_service = GakumasSyncService()
        self._image_resolver = ImageResolver()
        self.user_selected_mode = "gemini"  # "gemini" (あさり先生) または "qwen" (ローカル)
        self._is_busy = False
        self._last_user_message = ""
        self._first_ready = True
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self._register_slash_commands()

    async def on_ready(self) -> None:
        if self._first_ready:
            log.info("===================================")
            log.info("[学マス Bot ログイン] %s (モード: %s)", self.user, self.user_selected_mode)
            log.info("===================================")
            self._first_ready = False

            if self.guilds:
                for guild in self.guilds:
                    try:
                        self.tree.copy_global_to(guild=guild)
                        synced = await self.tree.sync(guild=guild)
                        log.info("[スラッシュコマンド] ギルド '%s' に %d コマンドを同期", guild.name, len(synced))
                        # ギルド内のニックネームを「あさり先生」に設定
                        if guild.me:
                            try:
                                await guild.me.edit(nick="あさり先生")
                                log.info("[Botニックネーム] ギルド '%s' でニックネームを 'あさり先生' に設定しました", guild.name)
                            except Exception as ne:
                                log.warning("[Botニックネーム] ニックネーム設定スキップ (%s): %s", guild.name, ne)
                    except discord.HTTPException as e:
                        log.error("[スラッシュコマンド] 同期失敗 (%s): %s", guild.name, e)

            # Bot 本体のユーザー名変更を試行（レート制限に配慮）
            try:
                if self.user and self.user.name != "あさり先生":
                    await self.user.edit(username="あさり先生")
                    log.info("[Botユーザー名] ユーザー名を 'あさり先生' に更新しました")
            except Exception as ue:
                log.debug("[Botユーザー名] ユーザー名変更スキップ: %s", ue)

            if ALLOWED_CHANNEL_ID != 0:
                channel = self.get_channel(ALLOWED_CHANNEL_ID)
                if channel and isinstance(channel, discord.TextChannel):
                    try:
                        await channel.send(
                            f"👩‍🏫 **プロデューサーくん、お疲れ様！初星学園 講師の根緒亜紗里よ。**\n"
                            f"アイドルの育成やスキルカードの編成、コンテストの分析など、気になることがあれば何でも気軽に聞いてちょうだいね！"
                        )
                    except Exception as e:
                        log.error("[Discord] 起動通知失敗: %s", e)

    def _register_slash_commands(self) -> None:
        bot = self

        @self.tree.command(name="help", description="利用可能なコマンド一覧と使い方を表示します")
        async def slash_help(interaction: discord.Interaction) -> None:
            await interaction.response.send_message(HELP_TEXT, ephemeral=True)

        @self.tree.command(name="model", description="対話に使用する AI モデルを切り替えます（デフォルト: Qwen 3.5 9B）")
        @discord.app_commands.describe(name="モデルを選択してください")
        @discord.app_commands.choices(name=[
            discord.app_commands.Choice(name="⚡ Qwen 2.5 7B (ローカル高速・マスタ/所持データ自律検索・推奨)", value="qwen"),
            discord.app_commands.Choice(name="☁️ Gemini 3.6 Flash (クラウド高度推論・マルチモーダル)", value="gemini"),
        ])
        async def slash_model(interaction: discord.Interaction, name: str) -> None:
            bot.user_selected_mode = name
            desc = AVAILABLE_MODELS.get(name, name)
            await interaction.response.send_message(f"✨ **[モデル設定]** **`{desc}`** に設定しました。")

        @self.tree.command(name="quota", description="本日の Gemini 3.6 Flash 利用状況とクォータ残量を表示します")
        async def slash_quota(interaction: discord.Interaction) -> None:
            stats = quota_tracker.get_today_stats()
            reqs = stats["requests"]
            limit = stats["limit"]
            rem = stats["remaining"]
            pct = stats["percent_used"]
            rem_pct = max(0.0, 100.0 - pct)

            # プログレスバーの生成
            total_blocks = 15
            filled_blocks = int((pct / 100.0) * total_blocks)
            bar = "🟩" * filled_blocks + "⬜" * (total_blocks - filled_blocks)

            embed = discord.Embed(
                title="📊 Gemini 3.6 Flash クォータ・利用状況",
                description=f"**初星学園プロデューサー科 相談室（あさり先生）**\n日付: `{stats['date']}`",
                color=0x4285F4,
            )
            embed.add_field(
                name="📈 1日あたりリクエスト数 (RPD)",
                value=f"**`{reqs:,} / {limit:,} 回`**（残り: **`{rem:,} 回`** ｜ **`{rem_pct:.1f}%`**）\n`[{bar}]`",
                inline=False,
            )
            embed.add_field(
                name="🪙 本日消費トークン",
                value=f"・**合計:** `{stats['total_tokens']:,} tokens`\n・**入力 (Prompt):** `{stats['prompt_tokens']:,}`\n・**出力 (Candidate):** `{stats['candidate_tokens']:,}`",
                inline=False,
            )
            embed.add_field(
                name="🛡️ 安全機能（フェイルオーバー）",
                value="クォータ上限到達時や障害時は、自動的にローカルの **`Qwen 2.5 7B (llama.cpp / Vulkan)`** へ切り替わります。",
                inline=False,
            )
            embed.set_footer(text="初星学園 相談室 ｜ Powered by Google Gemini 3.6 Flash & llama.cpp")
            await interaction.response.send_message(embed=embed)

        @self.tree.command(name="status", description="現在のモデル設定とマスタデータ稼働状態を表示します")
        async def slash_status(interaction: discord.Interaction) -> None:
            mode_desc = AVAILABLE_MODELS.get(bot.user_selected_mode, bot.user_selected_mode)
            busy_label = "処理中" if (bot._is_busy or bot.gemini_service.is_busy) else "待機中 (アイドル)"
            sc_count = len(bot._executor._skill_cards)
            pi_count = len(bot._executor._p_items)
            hist_count = len(bot._agent_engine.history)
            await interaction.response.send_message(
                f"**📊 学マス Bot 稼働状態**\n"
                f"- 現在のモード: **{mode_desc}** (エージェント方式)\n"
                f"- 稼働状態: 🟢 {busy_label}\n"
                f"- マスタデータ: スキルカード `{sc_count}` 件 / Pアイテム `{pi_count}` 件\n"
                f"- 会話履歴: `{hist_count}` 件（/new でリセット）"
            )

        @self.tree.command(name="cancel", description="処理中の回答を中断します")
        async def slash_cancel(interaction: discord.Interaction) -> None:
            bot.gemini_service.cancel()
            bot.ollama_service.cancel()
            await interaction.response.send_message("🛑 **[System]** 応答をキャンセルしました。")

        @self.tree.command(name="new", description="新しい会話セッションを開始します（履歴リセット）")
        async def slash_new(interaction: discord.Interaction) -> None:
            bot._agent_engine.reset()
            await interaction.response.send_message("✨ **[System]** 会話セッションをリセットしました。")

        @self.tree.command(name="clear", description="チャンネル内の直近メッセージを一括削除して掃除します")
        @discord.app_commands.describe(amount="削除するメッセージ件数（1〜100件、デフォルト: 50件）")
        async def slash_clear(interaction: discord.Interaction, amount: int = 50) -> None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("⚠️ テキストチャンネルでのみ実行可能です。", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            try:
                deleted = await interaction.channel.purge(limit=min(max(amount, 1), 100))
                await interaction.followup.send(f"🧹 **[掃除完了]** {len(deleted)} 件のメッセージを削除しました。", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("⚠️ **[権限エラー]** Bot に「メッセージの管理」権限が付与されていません。", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"⚠️ **[エラー]**: `{e}`", ephemeral=True)

        @self.tree.command(name="sync", description="スプレッドシートやWikiとのデータ同期を実行します")
        async def slash_sync(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True)
            try:
                res = await bot.sync_service.sync_all()
                await interaction.followup.send(f"✨ **[データ同期完了]**\n{res}", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"⚠️ **[同期エラー]**: `{e}`", ephemeral=True)

        @self.tree.command(name="advisory", description="あじふらい氏推奨のPアイテム・スキルカード構成画像（Pixel 10 Pro Fold最適化）を出力します")
        @discord.app_commands.describe(
            stage="ステージ番号 (1, 2, 3)",
            idol="アイドル名または衣装名 (例: ことね, 広, 千奈, GO MY WAY!! 等)",
            season="シーズン番号 (省略時は最新シーズン)"
        )
        @discord.app_commands.choices(stage=[
            discord.app_commands.Choice(name="Stage 1 (センス / Vo特化等)", value=1),
            discord.app_commands.Choice(name="Stage 2 (ロジック / Vi特化等)", value=2),
            discord.app_commands.Choice(name="Stage 3 (アノマリー / Vo特化等)", value=3),
        ])
        async def slash_advisory(
            interaction: discord.Interaction,
            stage: int,
            idol: str,
            season: int | None = None
        ) -> None:
            await interaction.response.defer()
            try:
                from advisory_parser import parse_advisory
                from advisory_image_builder import AdvisoryImageBuilder

                data = parse_advisory(stage=stage, idol_query=idol, season=season)
                if not data:
                    await interaction.followup.send(
                        f"⚠️ 指定されたステージ（Stage {stage}）またはアイドル（`{idol}`）の推奨構成情報が見つかりませんでした。\n"
                        f"アイドル名（ことね、広、千奈、手毬、美鈴、燕、リーリヤ等）をご確認ください。"
                    )
                    return

                builder = AdvisoryImageBuilder()
                png_bytes = builder.build(data)

                cur_season = data.get("season", 51)
                p_idol = data.get("p_idol", {})
                idol_name = p_idol.get("idol_name", idol)
                title = p_idol.get("title", "")
                extra = p_idol.get("extra", "")
                full_title = f"{idol_name}【{title}】" + (f" ({extra})" if extra else "")

                msg = (
                    f"👩‍🏫 **プロデューサーくん、お疲れ様！**\n"
                    f"シーズン{cur_season} Stage {stage} の **{full_title}** 推奨構成画像（Pアイテム2枠 ＆ スキルカード10枠）を用意したわよ！\n"
                    f"育成やデッキ構築の参考にしてみてね！ふふっ♪"
                )

                filename = f"advisory_s{cur_season}_stage{stage}_{p_idol.get('idol_key', 'idol')}.png"
                file = discord.File(io.BytesIO(png_bytes), filename=filename)
                await interaction.followup.send(content=msg, file=file)

            except Exception as e:
                log.error(f"[slash_advisory] エラー: {e}", exc_info=True)
                await interaction.followup.send(f"⚠️ 画像生成中にエラーが発生しました: `{e}`")

        @slash_advisory.autocomplete("idol")
        async def idol_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> list[discord.app_commands.Choice[str]]:
            all_idols = [
                "ことね (藤田ことね)", "広 (篠澤広)", "千奈 (倉本千奈)",
                "手毬 (月村手毬)", "美鈴 (秦谷美鈴)", "燕 (雨夜燕)",
                "リーリヤ (葛城リーリヤ)", "清夏 (紫雲清夏)", "星南 (十王星南)",
                "咲季 (花海咲季)", "佑芽 (花海佑芽)", "麻央 (有村麻央)", "莉波 (姫崎莉波)"
            ]
            if not current:
                return [discord.app_commands.Choice(name=i, value=i.split()[0]) for i in all_idols[:10]]
            filtered = [i for i in all_idols if current.lower() in i.lower()]
            return [discord.app_commands.Choice(name=i, value=i.split()[0]) for i in filtered[:10]]

    async def _execute_chat(self, channel: discord.TextChannel, prompt: str) -> None:
        model_name = "gemini-3.6-flash" if self.user_selected_mode == "gemini" else LLM_MODEL
        label = "あさり先生 (Gemini 3.6 Flash)" if self.user_selected_mode == "gemini" else "Qwen 2.5 7B (Local)"

        log.info("[質問受信] %s ➔ %s", label, prompt)

        status_msg: discord.Message | None = None
        self._is_busy = True

        async def on_status(text: str) -> None:
            nonlocal status_msg
            try:
                if status_msg is None:
                    status_msg = await channel.send(text)
                else:
                    await status_msg.edit(content=text)
            except Exception:
                pass

        async with channel.typing():
            try:
                full_text = await self._agent_engine.run(
                    user_message=prompt,
                    model=model_name,
                    on_status=on_status,
                )

                # status_msg を削除
                if status_msg:
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                    status_msg = None

                if not full_text.strip():
                    await channel.send("（回答を生成できませんでした）")
                    return

                footer = quota_tracker.format_footer(
                    duration_sec=self._agent_engine.last_duration,
                    tokens=self._agent_engine.last_tokens,
                    tool_count=self._agent_engine.last_tool_call_count,
                    model_label=self._agent_engine.last_model_used,
                )

                # 1800文字制限に配慮して改行単位で分割
                chunks = []
                current_text = full_text.strip()
                while len(current_text) > 1800:
                    split_idx = current_text.rfind("\n", 0, 1800)
                    if split_idx == -1 or split_idx < 900:
                        split_idx = 1800
                    chunks.append(current_text[:split_idx].strip())
                    current_text = current_text[split_idx:].strip()
                if current_text:
                    chunks.append(current_text)

                # 回答テキスト内の言及からローカル画像アセットを解決
                from image_resolver import ImageResolver
                resolver = ImageResolver()
                found_images = resolver.find_images_in_text(full_text, max_images=6)

                # ユーザーが「1つずつ」「個別に」投稿を求めた場合の判定
                wants_individual = any(w in prompt for w in ["1つずつ", "ひとつずつ", "1枚ずつ", "個別", "順番に"])

                if wants_individual and found_images:
                    # ── 個別投稿モード ──
                    # まず本文を送信
                    if chunks:
                        for chunk in chunks:
                            await channel.send(chunk)

                    # 各画像を1枚ずつラベル付きで個別に投稿
                    for idx, (lbl, img_path) in enumerate(found_images, 1):
                        if img_path.exists():
                            safe_name = re.sub(r'[\\/*?:"<>|]', "", f"{idx:02d}_{lbl}.png")
                            file = discord.File(str(img_path), filename=safe_name)
                            await channel.send(f"🖼️ **[{idx}/{len(found_images)}] {lbl}**", file=file)

                    await channel.send(footer.strip())
                else:
                    # ── 通常投稿モード（画像ファイル名と対応キャプションを整備） ──
                    discord_files = []
                    caption_lines = []
                    num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

                    for idx, (lbl, img_path) in enumerate(found_images, 1):
                        if img_path.exists():
                            emoji = num_emojis[idx - 1] if idx <= len(num_emojis) else f"[{idx}]"
                            safe_name = re.sub(r'[\\/*?:"<>|]', "", f"{idx:02d}_{lbl}.png")
                            discord_files.append(discord.File(str(img_path), filename=safe_name))
                            caption_lines.append(f"{emoji} **{lbl}**")

                    img_caption = ""
                    if caption_lines:
                        img_caption = "\n\n🖼️ **【添付画像の対応一覧】**\n" + "\n".join(caption_lines)

                    for i, chunk in enumerate(chunks):
                        if i == len(chunks) - 1:
                            chunk_with_footer = chunk + img_caption + footer
                            # 最後のメッセージに画像ファイルを添付
                            if len(chunk_with_footer) <= 2000:
                                await channel.send(chunk_with_footer, files=discord_files)
                            else:
                                await channel.send(chunk)
                                if img_caption:
                                    await channel.send(img_caption.strip())
                                await channel.send(footer.strip(), files=discord_files)
                        else:
                            await channel.send(chunk)

                log.info("[回答完了] %s ➔ %d 文字（%d メッセージ, %d 画像添付）",
                         label, len(full_text), len(chunks), len(found_images))

            except Exception as e:
                log.error("[Bot] AgentEngine 例外: %s", e, exc_info=True)
                if status_msg:
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                await channel.send(f"⚠️ **[エラー]**: `{e}`")
            finally:
                self._is_busy = False



    async def _execute_bot_commentary(self, message: discord.Message) -> None:
        """
        My Gakumas Tools 等の Bot の発言を検知し、
        出力されたスキルカード、Pアイテム、編成、戦術についてあさり先生が蘊蓄・解説・アドバイスを行う
        """
        raw_text_parts = []
        if message.content:
            raw_text_parts.append(message.content)
        for emb in message.embeds:
            if emb.title:
                raw_text_parts.append(f"【タイトル】{emb.title}")
            if emb.description:
                raw_text_parts.append(emb.description)
            for f in emb.fields:
                raw_text_parts.append(f"{f.name}: {f.value}")

        bot_output_text = "\n".join(raw_text_parts).strip()
        if not bot_output_text or len(bot_output_text) < 10:
            return

        bot_name = message.author.display_name or message.author.name
        log.info("[Bot発言検知・蘊蓄解説開始] %s ➔ %s...", bot_name, bot_output_text[:60])

        commentary_prompt = (
            f"初星学園の分析ツール「{bot_name}」が以下のシミュレーション結果や編成・カードデータを出力しました。\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{bot_output_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"初星学園プロデューサー科担任講師の根緒亜紗里（あさり先生）として、この出力結果を確認し、ここに出てくるスキルカード、Pアイテム、Pアイドル、あるいは戦術・数値について、プロデューサーくんに向けて指導教師・お姉さん目線で役立つ「ワンポイント蘊蓄（うんちく）・解説・アドバイス」を温かく語りかけてください。\n\n"
            f"【解説のポイント】\n"
            f"- 「ふふっ、この編成（結果）ね！」「このカードの組み合わせは面白いわね」のように自然な語りかけから始めてください。\n"
            f"- 出力に含まれる特徴的なスキルカードやPアイテム、Pアイドルに注目し、「実はこの『カード名』は〜〜」「このPアイテムの〜〜効果が〜〜」「〜〜を意識するとさらに伸びるかも！」といったプロデューサー科講師ならではの専門的かつ実践的な蘊蓄・解説をわかりやすく教えてあげてください。\n"
            f"- 一人称は「私」、二人称は「プロデューサーくん」を厳守してください。\n"
            f"- カード名は 『カード名』、アイドル名は アイドル名【二つ名】 の形式で表記してください（画像表示に連動します）。\n"
            f"- 読みやすいマークダウン箇条書きを活用し、自然な日本語で回答してください。"
        )

        self._is_busy = True
        channel = message.channel
        async with channel.typing():
            try:
                full_text = await self._agent_engine.run(
                    user_message=commentary_prompt,
                    model="gemini-3.6-flash",
                )
                if not full_text.strip():
                    return

                # 画像検索
                found_images = self._image_resolver.find_images_in_text(full_text, max_images=6)

                # テキスト分割
                chunks: list[str] = []
                current_text = full_text.strip()
                while len(current_text) > 1800:
                    split_idx = current_text.rfind("\n", 0, 1800)
                    if split_idx == -1 or split_idx < 900:
                        split_idx = 1800
                    chunks.append(current_text[:split_idx].strip())
                    current_text = current_text[split_idx:].strip()
                if current_text:
                    chunks.append(current_text)

                footer = f"\n\n`👩‍🏫 あさり先生のワンポイント解説`"

                discord_files = []
                caption_lines = []
                num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]

                for idx, (lbl, img_path) in enumerate(found_images, 1):
                    if img_path.exists():
                        emoji = num_emojis[idx - 1] if idx <= len(num_emojis) else f"[{idx}]"
                        safe_name = re.sub(r'[\\/*?:"<>|]', "", f"{idx:02d}_{lbl}.png")
                        discord_files.append(discord.File(str(img_path), filename=safe_name))
                        caption_lines.append(f"{emoji} **{lbl}**")

                img_caption = ""
                if caption_lines:
                    img_caption = "\n\n🖼️ **【添付画像の対応一覧】**\n" + "\n".join(caption_lines)

                for i, chunk in enumerate(chunks):
                    if i == 0:
                        if len(chunks) == 1:
                            reply_text = chunk + img_caption + footer
                            if len(reply_text) <= 2000:
                                await message.reply(reply_text, files=discord_files, mention_author=False)
                            else:
                                await message.reply(chunk, mention_author=False)
                                if img_caption:
                                    await channel.send(img_caption.strip())
                                await channel.send(footer.strip(), files=discord_files)
                        else:
                            await message.reply(chunk, mention_author=False)
                    elif i == len(chunks) - 1:
                        chunk_with_footer = chunk + img_caption + footer
                        if len(chunk_with_footer) <= 2000:
                            await channel.send(chunk_with_footer, files=discord_files)
                        else:
                            await channel.send(chunk)
                            if img_caption:
                                await channel.send(img_caption.strip())
                            await channel.send(footer.strip(), files=discord_files)
                    else:
                        await channel.send(chunk)

                log.info("[Bot蘊蓄解説完了] %d 文字（%d 画像添付）", len(full_text), len(found_images))
            except Exception as e:
                log.error("[_execute_bot_commentary] 例外: %s", e, exc_info=True)
            finally:
                self._is_busy = False

    async def on_message(self, message: discord.Message) -> None:
        # 1. 自身の発言は完全に無視
        if message.author == self.user:
            return
        # 2. チャンネル制限
        if ALLOWED_CHANNEL_ID != 0 and message.channel.id != ALLOWED_CHANNEL_ID:
            return

        # 3. 他の Bot（My Gakumas Tools など）の発言を検知して蘊蓄解説
        if message.author.bot:
            if not self._is_busy:
                asyncio.create_task(self._execute_bot_commentary(message))
            return

        content = message.content.strip()

        if content.startswith("/"):
            first_token = content.split()[0].lower()
            if first_token in _KNOWN_COMMANDS:
                if content == "/help":
                    await message.channel.send(HELP_TEXT)
                    return
                if content == "/quota":
                    stats = quota_tracker.get_today_stats()
                    reqs = stats["requests"]
                    limit = stats["limit"]
                    rem = stats["remaining"]
                    pct = stats["percent_used"]
                    rem_pct = max(0.0, 100.0 - pct)
                    total_blocks = 15
                    filled_blocks = int((pct / 100.0) * total_blocks)
                    bar = "🟩" * filled_blocks + "⬜" * (total_blocks - filled_blocks)

                    embed = discord.Embed(
                        title="📊 Gemini 3.6 Flash クォータ・利用状況",
                        description=f"**初星学園プロデューサー科 相談室（あさり先生）**\n日付: `{stats['date']}`",
                        color=0x4285F4,
                    )
                    embed.add_field(
                        name="📈 1日あたりリクエスト数 (RPD)",
                        value=f"**`{reqs:,} / {limit:,} 回`**（残り: **`{rem:,} 回`** ｜ **`{rem_pct:.1f}%`**）\n`[{bar}]`",
                        inline=False,
                    )
                    embed.add_field(
                        name="🪙 本日消費トークン",
                        value=f"・**合計:** `{stats['total_tokens']:,} tokens`\n・**入力 (Prompt):** `{stats['prompt_tokens']:,}`\n・**出力 (Candidate):** `{stats['candidate_tokens']:,}`",
                        inline=False,
                    )
                    embed.add_field(
                        name="🛡️ 安全機能（フェイルオーバー）",
                        value="クォータ上限到達時や障害時は、自動的にローカルの **`Qwen 2.5 7B (llama.cpp / Vulkan)`** へ切り替わります。",
                        inline=False,
                    )
                    embed.set_footer(text="初星学園 相談室 ｜ Powered by Google Gemini 3.6 Flash & llama.cpp")
                    await message.channel.send(embed=embed)
                    return
                if content == "/status":
                    stats = quota_tracker.get_today_stats()
                    mode_desc = AVAILABLE_MODELS.get(self.user_selected_mode, self.user_selected_mode)
                    status_text = (
                        f"📊 **初星学園 相談室ステータス**\n"
                        f"・**メインモデル:** `{mode_desc}`\n"
                        f"・**ローカル推論:** `{LLM_MODEL}` (`{LLM_BASE_URL}`)\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📈 **本日の Gemini 3.6 Flash 利用状況**\n"
                        f"・**リクエスト回数:** `{stats['requests']} / {stats['limit']} 回`（残り: `{stats['remaining']} 回` / `{100.0 - stats['percent_used']:.1f}%`）\n"
                        f"・**本日消費トークン:** `{stats['total_tokens']:,} tokens`（入力: `{stats['prompt_tokens']:,}` / 出力: `{stats['candidate_tokens']:,}`）\n"
                        f"・**フェイルオーバー:** 異常時・上限到達時は自動でローカル llama.cpp へ切替\n"
                    )
                    await message.channel.send(status_text)
                    return
                if content.startswith("/clear"):
                    parts = content.split()
                    amount = 50
                    if len(parts) > 1 and parts[1].isdigit():
                        amount = int(parts[1])
                    try:
                        deleted = await message.channel.purge(limit=min(max(amount, 1), 100))
                        notify = await message.channel.send(f"🧹 **[掃除完了]** {len(deleted)} 件のメッセージを削除しました。")
                        await asyncio.sleep(3)
                        await notify.delete()
                    except discord.Forbidden:
                        await message.channel.send("⚠️ **[権限エラー]** Bot に「メッセージの管理 (Manage Messages)」権限がありません。")
                    return

                if content.startswith("/sync"):
                    try:
                        res = await self.sync_service.sync_all()
                        await message.channel.send(f"✨ **[データ同期完了]**\n{res}")
                    except Exception as e:
                        await message.channel.send(f"⚠️ **[同期エラー]**: `{e}`")
                    return

                if content.startswith("/model"):
                    parts = content.split()
                    if len(parts) > 1 and parts[1].lower() in AVAILABLE_MODELS:
                        m = parts[1].lower()
                        self.user_selected_mode = m
                        await message.channel.send(f"✨ **[モデル設定]** `{AVAILABLE_MODELS[m]}` に変更しました。")
                    else:
                        await message.channel.send(f"利用可能: `qwen`, `gemini` (例: `/model gemini`)")
                    return

                if content.startswith("/advisory"):
                    parts = content.split()
                    if len(parts) < 3:
                        await message.channel.send("💡 使い方: `/advisory <ステージ(1-3)> <アイドル名>` (例: `/advisory 3 ことね`)")
                        return
                    try:
                        stg = int(parts[1])
                    except ValueError:
                        await message.channel.send("⚠️ ステージ番号は 1, 2, 3 のいずれかを指定してください。")
                        return
                    idol_q = parts[2]
                    
                    from advisory_parser import parse_advisory
                    from advisory_image_builder import AdvisoryImageBuilder

                    data = parse_advisory(stage=stg, idol_query=idol_q)
                    if not data:
                        await message.channel.send(f"⚠️ Stage {stg} のアイドル `{idol_q}` の推奨構成が見つかりませんでした。")
                        return

                    builder = AdvisoryImageBuilder()
                    png_bytes = builder.build(data)
                    p_idol = data.get("p_idol", {})
                    full_title = f"{p_idol.get('idol_name', idol_q)}【{p_idol.get('title', '')}】"
                    msg_text = (
                        f"👩‍🏫 **プロデューサーくん、お疲れ様！**\n"
                        f"シーズン{data.get('season', 51)} Stage {stg} の **{full_title}** 推奨構成画像よ！"
                    )
                    file = discord.File(io.BytesIO(png_bytes), filename=f"advisory_s{data.get('season', 51)}_stage{stg}_{p_idol.get('idol_key', 'idol')}.png")
                    await message.channel.send(content=msg_text, file=file)
                    return

        # 通常メッセージ
        if self._is_busy or self.gemini_service.is_busy:
            await message.reply("⏳ 前の回答を処理中です。少々お待ちください。", mention_author=False)
            return

        self._last_user_message = content
        if isinstance(message.channel, discord.TextChannel):
            asyncio.create_task(self._execute_chat(message.channel, content))

# ────────────────────────────── エントリポイント ─────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

client = GakumasAntigravityBot(intents=intents)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        log.error("DISCORD_BOT_TOKEN が設定されていません。.env を確認してください。")
        sys.exit(1)
    client.run(DISCORD_TOKEN, log_handler=None)
