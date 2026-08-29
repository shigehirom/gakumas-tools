# 🎓 学園アイドルマスター Discord 相談 Bot (ローカルLLM & Gemini ハイブリッド)

TrueNAS 上のローカル LLM（Ollama）と Google Antigravity SDK（Gemini）を統合した学園アイドルマスター専用の相談 Bot です。

マスタデータ（スキルカード、Pアイテム、ステージ情報、DSL仕様）を自動検索・コンテキスト注入するため、**Gemini API の消費ゼロ（完全ローカル）で高速・高精度な回答**が得られます。

---

## 🚀 起動方法

```bash
cd /root/gakumas-workspace/gakumas-agent-bot

# 1. 仮想環境をアクティベートして起動
source .venv/bin/activate
python3 gakumas_agent_bot.py
```

※バックグラウンドで永続起動する場合:
```bash
nohup /root/gakumas-workspace/gakumas-agent-bot/.venv/bin/python3 /root/gakumas-workspace/gakumas-agent-bot/gakumas_agent_bot.py > /root/gakumas-workspace/gakumas-agent-bot/bot.log 2>&1 &
```

---

## 🤖 利用可能な AI モデル一覧 (`/model` で切替可能)

| モデル名 | コマンド | 特徴・向いている用途 | API消費 |
| :--- | :--- | :--- | :--- |
| **Qwen 2.5 7B** (初期設定) | `/model qwen` | **最推奨・表検索特化**<br>・スキルカードやアイテムの条件検索に最も高精度 | **無料 (0)** |
| **Gemma 2 9B** | `/model gemma` | **自然言語対話・解説特化**<br>・ゲーム仕様やキャラクター育成の丁寧な解説 | **無料 (0)** |
| **DeepSeek-R1 8B** | `/model deepseek` | **思考・推論特化 (`thinking`)**<br>・戦術やシナジー考察、デッキ構成の深い分析 | **無料 (0)** |
| **Gemini 3.6 Flash** | `/model gemini` | **Google Cloud SDK**<br>・Antigravity SDK の自律エージェントモード | API利用 |

---

## 💬 コマンド一覧

- `/help` : コマンド一覧と使い方ヘルプを表示
- `/model <name>` : 使用する AI モデルを切り替え (`qwen` / `gemma` / `deepseek` / `gemini`)
- `/status` : 現在のモデル設定とマスタデータ読込状況を表示
- `/new` : 会話セッションをリセット
- `/cancel` : 処理中の回答を中断
- `/retry` : 直前の質問を再試行

---

## 💡 質問の例

- 「アノマリーのスキルカードで、繰り返して使える、全力値を増加する効果のあるものを教えて」
- 「好印象プランでオススメのPアイテムとシナジーのあるカードは？」
- 「コンテストシーズン50のステージ1の仕様と推奨編成の考え方を教えて」
