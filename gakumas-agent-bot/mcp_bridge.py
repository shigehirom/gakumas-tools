"""
mcp_bridge.py — gakumas-mcp-server と あさり先生 Bot (AgentEngine) の連携ブリッジ

FastMCP / MCP Client (SSE) 経由で gakumas-mcp-server から動的にツール一覧を取得し、
LLM（Gemini / llama.cpp）向けの Function Calling スキーマを生成・実行する。
MCP サーバーダウン時はローカルの GakumasToolExecutor に自動フォールバック。
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
from typing import Any

log = logging.getLogger("mcp_bridge")

# フォールバック用ローカルエグゼキュータ
try:
    from gakumas_tools import GakumasToolExecutor, TOOLS_SCHEMA as LOCAL_TOOLS_SCHEMA
except ImportError:
    GakumasToolExecutor = None  # type: ignore
    LOCAL_TOOLS_SCHEMA = []     # type: ignore


class McpToolBridge:
    """
    gakumas-mcp-server と連携するツール実行ブリッジ
    """

    def __init__(
        self,
        mcp_url: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.mcp_url = mcp_url or os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:30081/sse")
        self.timeout = timeout
        self.is_connected = False
        self._local_executor: Any = None
        self._tools_cache: list[Any] = []
        self._openai_schema_cache: list[dict[str, Any]] = []
        self._gemini_schema_cache: list[dict[str, Any]] = []
        self._master_counts: dict[str, int] = {}

    async def initialize(self) -> bool:
        """
        MCP サーバーへ接続してツール一覧を取得し、スキーマキャッシュを構築する。
        失敗した場合はローカルエグゼキュータへフォールバックする。
        """
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            async with asyncio.timeout(self.timeout):
                async with sse_client(self.mcp_url) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        self._tools_cache = tools_result.tools

            self._build_schemas()
            self.is_connected = True
            log.info(f"[McpToolBridge] MCP サーバー接続成功: {len(self._tools_cache)} 件のツールを登録 ({self.mcp_url})")
            return True
        except Exception as e:
            log.warning(f"[McpToolBridge] MCP サーバー接続失敗 ({self.mcp_url}): {e}。ローカルフォールバックを使用します")
            self.is_connected = False
            self._init_local_fallback()
            return False

    def _init_local_fallback(self) -> None:
        """ローカルエグゼキュータを初期化"""
        if self._local_executor is None and GakumasToolExecutor is not None:
            self._local_executor = GakumasToolExecutor()
        self._openai_schema_cache = LOCAL_TOOLS_SCHEMA
        self._gemini_schema_cache = []
        for s in LOCAL_TOOLS_SCHEMA:
            fn = s.get("function", {})
            self._gemini_schema_cache.append({
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters"),
            })

    def _build_schemas(self) -> None:
        """MCP の Tool 定義から OpenAI 互換 / Gemini 互換のスキーマを構築"""
        openai_schemas = []
        gemini_schemas = []

        for t in self._tools_cache:
            name = t.name
            desc = t.description or f"学園アイドルマスター ツール: {name}"
            raw_schema = getattr(t, "input_schema", getattr(t, "inputSchema", None)) or {"type": "object", "properties": {}}

            # OpenAI 互換
            openai_schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": raw_schema,
                },
            })

            # Gemini 互換（非対応フィールドを除去・正規化）
            cleaned_params = self._sanitize_gemini_schema(raw_schema)
            gemini_schemas.append({
                "name": name,
                "description": desc,
                "parameters": cleaned_params,
            })

        self._openai_schema_cache = openai_schemas
        self._gemini_schema_cache = gemini_schemas

    @staticmethod
    def _sanitize_gemini_schema(schema: Any) -> Any:
        """Gemini API の parameters が受け付ける OpenAPI 3.0 サブセットへ正規化"""
        if not isinstance(schema, dict):
            if isinstance(schema, list):
                return [McpToolBridge._sanitize_gemini_schema(x) for x in schema]
            return schema

        cleaned: dict[str, Any] = {}

        # anyOf: [{'type': 'boolean'}, {'type': 'null'}] -> type='boolean', nullable=True
        if "anyOf" in schema and isinstance(schema["anyOf"], list):
            types_list = [x.get("type") for x in schema["anyOf"] if isinstance(x, dict) and "type" in x]
            non_null_types = [t for t in types_list if t != "null"]
            cleaned["type"] = non_null_types[0] if non_null_types else "string"
            if "null" in types_list:
                cleaned["nullable"] = True
        elif "type" in schema:
            cleaned["type"] = schema["type"]

        if "description" in schema and schema["description"]:
            cleaned["description"] = str(schema["description"])

        if "enum" in schema and isinstance(schema["enum"], list):
            cleaned["enum"] = [str(x) for x in schema["enum"]]

        if "properties" in schema and isinstance(schema["properties"], dict):
            cleaned["properties"] = {
                k: McpToolBridge._sanitize_gemini_schema(v)
                for k, v in schema["properties"].items()
            }

        if "required" in schema and isinstance(schema["required"], list):
            cleaned["required"] = [str(x) for x in schema["required"]]

        if "items" in schema:
            cleaned["items"] = McpToolBridge._sanitize_gemini_schema(schema["items"])

        if "nullable" in schema:
            cleaned["nullable"] = bool(schema["nullable"])

        return cleaned

    def get_openai_tools_schema(self) -> list[dict[str, Any]]:
        """llama.cpp / OpenAI 用の tools スキーマを返す"""
        if not self._openai_schema_cache:
            self._init_local_fallback()
        return self._openai_schema_cache

    def get_gemini_tools_schema(self) -> list[dict[str, Any]]:
        """Gemini 用の tools スキーマを返す"""
        if not self._gemini_schema_cache:
            self._init_local_fallback()
        return self._gemini_schema_cache

    def get_tool_names(self) -> list[str]:
        """利用可能なツール名一覧"""
        if self.is_connected and self._tools_cache:
            return [t.name for t in self._tools_cache]
        return [s.get("function", {}).get("name", "") for s in LOCAL_TOOLS_SCHEMA]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        """
        ツールを実行し、結果文字列を返す。
        MCP サーバーへ接続可能な場合は MCP 経由、不可または例外時はローカルフォールバック。
        """
        if self.is_connected:
            try:
                from mcp import ClientSession
                from mcp.client.sse import sse_client

                async with asyncio.timeout(self.timeout):
                    async with sse_client(self.mcp_url) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            res = await session.call_tool(tool_name, arguments=args)

                            # 結果テキストを結合
                            texts = []
                            for c in res.content:
                                text_val = getattr(c, "text", None)
                                if text_val:
                                    texts.append(text_val)
                                elif hasattr(c, "data") and getattr(c, "mimeType", "") == "image/png":
                                    texts.append("【インフォグラフィック画像を生成しました】")

                            result_str = "\n".join(texts).strip()
                            if result_str:
                                return result_str
                            return "（ツールを実行しましたが結果が空でした）"
            except Exception as e:
                log.warning(f"[McpToolBridge] MCP call_tool 失敗 ({tool_name}): {e}。ローカルフォールバックを実行")

        # ローカルフォールバック
        if self._local_executor is None:
            self._init_local_fallback()
        if self._local_executor is not None:
            return await self._local_executor.execute(tool_name, args)

        return f"※ ツール {tool_name} を実行できませんでした (MCP 未接続かつローカルなし)"

