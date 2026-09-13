"""
cli_chat_test.py — あさり先生 CLI 対話テストスクリプト

Discord を起動せずに、ターミナル上で直接あさり先生（AgentEngine）と対話し、
ツール実行ログと回答クオリティを検証するためのテスター。

使用法:
  python3 cli_chat_test.py "質問内容"
  または引数なしで対話モード起動:
  python3 cli_chat_test.py
"""

import asyncio
import os
import sys
from pathlib import Path

# パス設定 & .env 読み込み
WORKSPACE_DIR = Path("/root/gakumas-workspace")
BOT_DIR = WORKSPACE_DIR / "gakumas-agent-bot"
sys.path.insert(0, str(BOT_DIR))

env_paths = [
    BOT_DIR / ".env",
    WORKSPACE_DIR / "gakumas-tools" / ".env.local",
    WORKSPACE_DIR / ".env",
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

from agent_engine import AgentEngine
from gakumas_tools import GakumasToolExecutor



async def status_callback(msg: str) -> None:
    print(f"  [Thinking / Tool] {msg}", flush=True)


async def ask_asari(engine: AgentEngine, question: str, model: str = "gemini-3.6-flash") -> str:
    print(f"\n================================================================================", flush=True)
    print(f"👤 プロデューサーくん: {question}", flush=True)
    print(f"================================================================================", flush=True)
    
    response = await engine.run(
        user_message=question,
        model=model,
        on_status=status_callback,
    )
    
    print(f"\n👩‍🏫 あさり先生 ({engine.last_model_used} / ツール実行: {engine.last_tool_call_count}回 / 処理時間: {engine.last_duration:.2f}秒):", flush=True)
    print(f"--------------------------------------------------------------------------------", flush=True)
    print(response, flush=True)
    print(f"================================================================================\n", flush=True)
    return response


async def main():
    executor = GakumasToolExecutor()
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    
    engine = AgentEngine(
        executor=executor,
        gemini_api_key=gemini_key,
    )
    
    if len(sys.argv) > 1:
        # 引数で直接質問が渡された場合
        question = " ".join(sys.argv[1:])
        await ask_asari(engine, question)
    else:
        # 対話モード
        print("🎓 【あさり先生 CLI 対話テスター起動】 (終了するには 'exit' または 'quit' を入力)")
        print("--------------------------------------------------------------------------------")
        while True:
            try:
                user_input = input("\n👤 質問を入力してください > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    print("対話を終了します。お疲れ様でした！")
                    break
                if user_input.lower() == "reset":
                    engine.reset()
                    print("🔄 会話セッションをリセットしました。")
                    continue
                
                await ask_asari(engine, user_input)
            except (KeyboardInterrupt, EOFError):
                print("\n対話を終了します。")
                break


if __name__ == "__main__":
    asyncio.run(main())

