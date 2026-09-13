"""
agent_engine.py — 学園アイドルマスター AI エージェント ReAct ループ

Gemini 3.6 Flash をメイン頭脳とし、必要に応じてローカル llama.cpp (Qwen 2.5 7B) への
自動フォールバックを備えたハイブリッド自律型エージェント。
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Callable, Awaitable

from openai import AsyncOpenAI
from google import genai
from google.genai import types

from gakumas_tools import GakumasToolExecutor, TOOLS_SCHEMA
from master_data import GakumasMaster, generate_system_prompt
from quota_tracker import quota_tracker

log = logging.getLogger("agent_engine")

def get_system_prompt() -> str:
    try:
        return generate_system_prompt()
    except Exception as e:
        log.warning(f"[AgentEngine] generate_system_prompt 失敗、フォールバック: {e}")
        return "あなたは学園アイドルマスターの講師「あさり先生」です。プロデューサーくんの質問に優しく正確に回答してください。"


class AgentEngine:
    """
    あさり先生 AI エージェント（Gemini 3.6 Flash メイン ＆ llama.cpp フォールバック）
    """

    MAX_ITER = 4
    MAX_HISTORY = 20

    def __init__(
        self,
        executor: GakumasToolExecutor,
        base_url: str = "http://192.168.100.4:30080/v1",
        api_key: str = "dummy",
        gemini_api_key: str = "",
    ) -> None:
        self.executor = executor
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "")

        self.history: list[dict[str, Any]] = []
        self.last_tool_call_count = 0
        self.last_tokens = 0
        self.last_duration = 0.0
        self.last_model_used = "Gemini 3.6 Flash"

        # ローカル OpenAI / llama.cpp クライアント
        self._local_client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=60.0,
        )

        # Gemini クライアント初期化
        self._gemini_client: genai.Client | None = None
        if self.gemini_api_key:
            try:
                self._gemini_client = genai.Client(api_key=self.gemini_api_key)
            except Exception as e:
                log.warning(f"[AgentEngine] Gemini Client 初期化失敗: {e}")

    def reset(self) -> None:
        """会話履歴をリセット"""
        self.history.clear()
        self.last_tool_call_count = 0
        self.last_tokens = 0
        self.last_duration = 0.0

    def _trim(self) -> None:
        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.MAX_HISTORY:]

    # ── メイン実行（Gemini 3.6 Flash メイン ＆ フォールバック）─────────────────

    async def run(
        self,
        user_message: str,
        model: str = "gemini-3.6-flash",
        on_status: Callable[[str], Awaitable[None]] | None = None,
        on_token: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """
        エージェントを実行し、あさり先生の最終回答を返す。
        """
        t_start = time.perf_counter()
        self.history.append({"role": "user", "content": user_message})
        self._trim()
        self.last_tool_call_count = 0
        self.last_tokens = 0

        # 1. google-genai SDK 経由で Gemini 実行（3.6-flash -> 3.5-flash -> flash-latest -> 3.7-flash 自動フォールバック）
        if self._gemini_client and ("gemini" in model.lower() or model == "auto"):
            gemini_models = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.7-flash", "gemini-3.1-flash-lite"]

            for g_model in gemini_models:
                try:
                    ans = await self._run_gemini(user_message, model=g_model, on_status=on_status)
                    if ans and ans.strip():
                        self.last_duration = time.perf_counter() - t_start
                        self.last_model_used = f"Gemini ({g_model})"
                        if on_token:
                            await on_token(ans)
                        return ans
                except Exception as e:
                    err_str = str(e)
                    log.warning(f"[AgentEngine] Gemini モデル {g_model} 実行失敗: {err_str[:120]}")
                    continue

            log.error("[AgentEngine] 全 Gemini モデル失敗、ローカル llama.cpp へフォールバックします")
            if on_status:
                await on_status("🔄 ローカルエンジンへ切り替えて回答を生成中...")

        # 2. ローカル llama.cpp (Qwen 2.5 7B) 実行（フォールバック）
        try:
            ans = await self._run_local(user_message, model="/models/qwen2.5-7b.gguf", on_status=on_status)
            self.last_duration = time.perf_counter() - t_start
            self.last_model_used = "Qwen 2.5 7B (Local)"
            if on_token and ans:
                await on_token(ans)
            return ans
        except Exception as e:
            log.error(f"[AgentEngine] ローカル推論エラー: {e}", exc_info=True)
            self.last_duration = time.perf_counter() - t_start
            return f"ふふっ、少し通信が不安定だったみたいね。もう一度聞いてもらえるかしら？ (エラー: {str(e)[:80]})"

    # ── google-genai SDK Gemini 実行ループ ───────────────────────────────────

    async def _run_gemini(
        self,
        user_message: str,
        model: str = "gemini-3.6-flash",
        on_status: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        if not self._gemini_client:
            raise RuntimeError("Gemini Client is not initialized")

        tool_call_count = 0
        prompt_tokens_total = 0
        candidate_tokens_total = 0

        # TOOLS_SCHEMA を Gemini の関数宣言形式へ変換（enum等の型バリデーションを正規化）
        def _clean_schema(schema: Any) -> Any:
            if isinstance(schema, dict):
                cleaned = {}
                for k, v in schema.items():
                    if k == "enum" and isinstance(v, list):
                        cleaned[k] = [str(x) for x in v]
                    else:
                        cleaned[k] = _clean_schema(v)
                return cleaned
            elif isinstance(schema, list):
                return [_clean_schema(x) for x in schema]
            return schema

        gemini_tools = []
        for s in TOOLS_SCHEMA:
            fn = s.get("function", {})
            params = fn.get("parameters")
            gemini_tools.append({
                "name": fn.get("name"),
                "description": fn.get("description"),
                "parameters": _clean_schema(params) if params else None,
            })

        # Gemini Chat セッションのメッセージ構築
        chat_contents = []
        for h in self.history[:-1]:
            role = "user" if h.get("role") == "user" else "model"
            content = h.get("content")
            if content and isinstance(content, str):
                chat_contents.append(types.Content(role=role, parts=[types.Part.from_text(text=content)]))

        # 現在のユーザーメッセージ
        chat_contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

        system_prompt = get_system_prompt()
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            tools=[{"function_declarations": gemini_tools}],
        )

        def _extract_response_text(resp: Any) -> str:
            if not resp or not resp.candidates:
                return ""
            parts = resp.candidates[0].content.parts if resp.candidates[0].content else []
            texts = [p.text for p in parts if getattr(p, "text", None)]
            return "\n".join(texts).strip() if texts else (resp.text or "")

        for iteration in range(self.MAX_ITER):
            log.info(f"[AgentEngine-Gemini] 反復 {iteration + 1}/{self.MAX_ITER}")

            # 最終反復のみツール呼び出しを禁止してテキスト生成を強制
            is_last_iter = (iteration == self.MAX_ITER - 1)
            if is_last_iter:
                current_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                    tools=[{"function_declarations": gemini_tools}],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(mode="NONE")
                    ),
                )
            else:
                current_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                    tools=[{"function_declarations": gemini_tools}],
                )

            response = await asyncio.to_thread(
                self._gemini_client.models.generate_content,
                model=model,
                contents=chat_contents,
                config=current_config,
            )

            # トークン数の集計
            if response.usage_metadata:
                prompt_tokens_total += (response.usage_metadata.prompt_token_count or 0)
                candidate_tokens_total += (response.usage_metadata.candidates_token_count or 0)

            # 関数呼び出し（Function Calls）のチェック
            function_calls = []
            if response.function_calls:
                function_calls = response.function_calls

            if not function_calls or is_last_iter:
                final_text = _extract_response_text(response)
                if not final_text and is_last_iter:
                    # 最終反復でテキストが空の場合は明示的プロンプトを付与して再試行
                    summary_prompt = "これまでのツール検索結果を踏まえて、プロデューサーくんへの親切で具体的なアドバイスとして最終回答をまとめてください。"
                    force_contents = chat_contents + [types.Content(role="user", parts=[types.Part.from_text(text=summary_prompt)])]
                    force_resp = await asyncio.to_thread(
                        self._gemini_client.models.generate_content,
                        model=model,
                        contents=force_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=0.7,
                            tools=[{"function_declarations": gemini_tools}],
                            tool_config=types.ToolConfig(
                                function_calling_config=types.FunctionCallingConfig(mode="NONE")
                            ),
                        ),
                    )
                    final_text = _extract_response_text(force_resp)

                if not final_text and not is_last_iter:
                    # テキストがなくfunction_callsもない場合は再試行
                    pass
                else:
                    self.history.append({"role": "assistant", "content": final_text})
                    self.last_tool_call_count = tool_call_count
                    self.last_tokens = prompt_tokens_total + candidate_tokens_total

                    quota_tracker.record_usage(
                        prompt_tokens=prompt_tokens_total,
                        candidate_tokens=candidate_tokens_total,
                    )
                    return final_text

            # ツール呼び出しがある場合: モデル応答をそのまま履歴に追加（thought_signatureを完全保持）
            if response.candidates and response.candidates[0].content:
                chat_contents.append(response.candidates[0].content)
            else:
                model_parts = []
                if response.text:
                    model_parts.append(types.Part.from_text(text=response.text))
                for fc in function_calls:
                    model_parts.append(types.Part.from_function_call(name=fc.name, args=dict(fc.args)))
                chat_contents.append(types.Content(role="model", parts=model_parts))

            # 各ツールを実行して結果を返す
            function_response_parts = []
            for fc in function_calls:
                tool_call_count += 1
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}

                log.info(f"[AgentEngine-Gemini] ツール実行: {fn_name}({fn_args})")
                if on_status:
                    await on_status(f"🔍 `{fn_name}` を実行中...")

                tool_result = await self.executor.execute(fn_name, fn_args)
                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fn_name,
                        response={"result": tool_result}
                    )
                )

            chat_contents.append(types.Content(role="user", parts=function_response_parts))

        # 最大反復到達時
        fallback_contents = chat_contents + [types.Content(role="user", parts=[types.Part.from_text(text="これまでのツール検索結果を踏まえて、プロデューサーくんへの親切で具体的なアドバイスとして最終回答をまとめてください。")])]
        fallback_resp = await asyncio.to_thread(
            self._gemini_client.models.generate_content,
            model=model,
            contents=fallback_contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                tools=[{"function_declarations": gemini_tools}],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="NONE")
                ),
            ),
        )
        final_text = _extract_response_text(fallback_resp) or "（アドバイスをまとめきれませんでした。もう一度具体的に教えてもらえるかしら？）"
        self.history.append({"role": "assistant", "content": final_text})
        self.last_tool_call_count = tool_call_count
        self.last_tokens = prompt_tokens_total + candidate_tokens_total
        quota_tracker.record_usage(prompt_tokens=prompt_tokens_total, candidate_tokens=candidate_tokens_total)
        return final_text

    # ── ローカル llama.cpp 実行ループ ────────────────────────────────────────

    async def _run_local(
        self,
        user_message: str,
        model: str = "/models/qwen2.5-7b.gguf",
        on_status: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        tool_call_count = 0
        # ローカル推論 (llama.cpp 16k context) の溢れ防止のため、履歴を直近6件に制限
        recent_history = self.history[-6:] if len(self.history) > 6 else self.history
        messages = [{"role": "system", "content": get_system_prompt()}] + recent_history


        for iteration in range(self.MAX_ITER):
            has_recent_tool = bool(messages and messages[-1].get("role") == "tool")
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": 0.5,
            }
            if not has_recent_tool:
                kwargs["tools"] = TOOLS_SCHEMA
                kwargs["tool_choice"] = "auto"

            response = await self._local_client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg = choice.message
            content = msg.content or ""
            tool_calls = msg.tool_calls or []

            if not tool_calls and content:
                self.history.append({"role": "assistant", "content": content})
                self.last_tool_call_count = tool_call_count
                return content

            if tool_calls:
                raw_tcs = []
                for tc in tool_calls:
                    raw_tcs.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    })
                messages.append({"role": "assistant", "content": content or None, "tool_calls": raw_tcs})

                for call in tool_calls:
                    tool_call_count += 1
                    fn_name = call.function.name
                    try:
                        fn_args = json.loads(call.function.arguments) if isinstance(call.function.arguments, str) else call.function.arguments
                    except Exception:
                        fn_args = {}

                    if on_status:
                        await on_status(f"🔍 `{fn_name}` を実行中...")

                    res = await self.executor.execute(fn_name, fn_args)
                    formatted_tool_res = (
                        f"{res}\n\n"
                        f"【指示】上記の検索結果データに基づいて正確に回答してください。"
                        f"検索結果に件数が記載されている場合はその件数を明確に伝え、絶対に『見つからない』『所持していない』と嘘をつかないでください。"
                    )
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": formatted_tool_res})
                continue

            break

        self.last_tool_call_count = tool_call_count
        return "ふふっ、少し考えがまとまらなかったみたい。もう一度質問してくれると嬉しいな、プロデューサーくん！"
