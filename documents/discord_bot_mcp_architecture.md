# Discord Bot & MCP 分散アーキテクチャ・開発運用ガイド

本書では、学園アイドルマスター（Gakumas）ツールの Discord Bot 近代化プロジェクト（Phase 1〜3）を通じて確立された、**Raspberry Pi 5 ネイティブ常駐型 Thin Client & MCP 連携アーキテクチャ**の詳細、設計思想、および開発・保守運用手順を記録します。今後のエージェントおよび開発者が機能追加・トラブルシューティングを行う際の標準リファレンスとして活用してください。

---

## 1. 全体アーキテクチャ概要

従来の構成では、TrueNAS 上の Docker コンテナ（`Dockerfile.bot`）内でモノレポ全体（シミュレーションエンジン・画像・TypeScript/Python環境）をビルドして Bot を動かしていましたが、リソース消費が大きく（1GB超）、保守性や拡張性に課題がありました。

新アーキテクチャでは、**「軽量 Thin Client + 高速 MCP サーバー + 常駐型 AI エージェント」**の完全分離を行い、Raspberry Pi 5 上へ集約しました。

```
+-----------------------------------------------------------------------------------+
| TrueNAS Scale (192.168.100.4)                                                     |
|                                                                                   |
|  +-----------------------------+       +---------------------------------------+  |
|  | Web UI (gakumas-tools)     |       | MongoDB (Port 27017)                  |  |
|  | Port 30000 (Docker Compose) |       |  - simulation_results                 |  |
|  +-----------------------------+       |  - loadouts, memories, contest_matches|  |
|                                        +---------------------------------------+  |
|  +-----------------------------------------------------------------------------+  |
|  | Incus Sandbox (Ubuntu 24.04 /root/gakumas-workspace)                        |  |
|  |  - 開発・ビルド拠点 (VS Code Remote-SSH)                                     |  |
|  +-----------------------------------------------------------------------------+  |
+------------------------------------------^----------------------------------------+
                                           |
                    MongoDB 接続 / SSH 同期 |
                                           v
+-----------------------------------------------------------------------------------+
| Raspberry Pi 5 (192.168.100.32 / Ubuntu 24.04 LTS aarch64)                        |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | gakumas-mcp.service (Python 3.12 / FastAPI + SSE / Port 30081)               |  |
|  |  - メモリ使用量: ~75 MB                                                      |  |
|  |  - ゲームデータ検索 (Pアイドル、サポカ、スキルカード、Pアイテム、レギュレーション)  |  |
|  |  - シミュレーション & デッキ探索 (ステージ最適化、アドバイザリ算出)           |  |
|  |  - 高解像度画像レンダリング (PIL: カード詳細、ロードアウト、箱ひげ図、アドバイザリ)   |  |
|  +-----------------------^-----------------------------^-----------------------+  |
|                          | HTTP/SSE (127.0.0.1:30081)  |                          |
|                          |                             |                          |
|  +-----------------------+--------+   +----------------+-----------------------+  |
|  | gakumas-discord-bot.service     |   | asari-agent.service                   |  |
|  | (Node.js v22 Thin Client)       |   | (Python 3.12 / Gemini 3.6 Flash)       |  |
|  |  - メモリ使用量: ~49 MB         |   |  - メモリ使用量: ~107 MB              |  |
|  |  - Discord スラッシュコマンド    |   |  - Discord あさり先生 Bot (@メンション)|  |
|  |    (/contest, /advisory, etc.) |   |  - MCP ToolBridge で全ツール自律呼出   |  |
|  +--------------------------------+   +---------------------------------------+  |
|                                                                                   |
|  * 3 サービス合計メモリ使用量: わずか約 231 MB (Pi 5 8GB RAM の 3% 未満)           |
+-----------------------------------------------------------------------------------+
```

---

## 2. 各コンポーネントの責務と詳細

### 2.1 gakumas-mcp-server (`gakumas-mcp.service`)
- **ディレクトリ**: `/home/pi/gakumas-mcp-server`
- **実行環境**: Python 3.12 (`.venv`), `uvicorn`, `fastapi`, `mcp` SDK
- **ポート / トランスポート**: `http://0.0.0.0:30081/sse` (SSE / HTTP)
- **主な提供ツール**:
  1. `get_optimized_deck`: 指定ステージの最適メモリ探索・スコア計算
  2. `get_contest_advisory`: アドバイザリ診断（カード推薦・目標パラメータ算出）
  3. `get_contest_stats`: コンテスト対戦統計およびスコア分布箱ひげ図（Boxplot）Base64 画像生成
  4. `get_loadout_image`: 1列/2列レイアウトの編成詳細 Base64 画像生成
  5. `get_memory_summary`: 所持メモリ一覧（S4+向けパラボ、コンテスト用等）
  6. `get_idol_profile`: アイドルの誕生日、CV、年齢、3サイズ、性格、ふりがな情報
  7. その他マスタデータ検索 (`search_skill_cards`, `search_p_items`, `get_p_idol_details` 等)

### 2.2 gakumas-discord-bot (`gakumas-discord-bot.service`)
- **ディレクトリ**: `/home/pi/gakumas-discord-bot`
- **実行環境**: Node.js `v22.23.3` (LTS ARM64 standalone)
- **設計原則（Thin Client）**:
  - Python やローカルでのシミュレーション・画像レンダリング（PIL）を**一切行わない**。
  - すべて MCP クライアント (`@modelcontextprotocol/sdk`) を介して `http://127.0.0.1:30081/sse` のツールを呼び出し、返却された Base64 画像（`data:image/png;base64,...`）をバッファ化して Discord の `AttachmentBuilder` で送信する。
  - レガシー・不要コマンド（`/calc`, `/deck`, `/compare-memory`, `/sync-contest` 等）を廃止し、以下の 5 コマンドに厳選：
    - `/contest`: ステージ指定で最適デッキ・スコアを算出（Base64 画像添付）
    - `/advisory`: メモリ調教・目標設定アドバイザー（Base64 アドバイザリ画像添付）
    - `/memory`: 所持メモリの概要・パラボ確認（ステージ用 / HIF プロデュース用）
    - `/record-contest`: スクリーショット 3 枚から Gemini 3 で結果を自動解析し、MongoDB と Google スプレッドシートに二重記録
    - `/sync`: MongoDB ⇔ Google スプレッドシートの双方向同期

### 2.3 asari-agent (`asari-agent.service`)
- **ディレクトリ**: `/home/pi/gakumas-agent-bot`
- **実行環境**: Python 3.12 (`.venv`), `discord.py`, `google-genai` (Gemini 3.6 Flash)
- **役割**:
  - Discord 上でメンション（`@あさり先生`）された際、MCP ToolBridge を通じて `gakumas-mcp-server` のツールを自律的に使いこなし、自然な会話形式で助言を行う。
  - 生徒プロファイル（誕生日、読み仮名など）も MCP 経由で取得して回答可能。

---

## 3. ディレクトリ構成と同期の絶対ルール (Gotchas)

### 3.1 多重配置ディレクトリの同一性維持
本ワークスペースでは、Sandbox 内および Pi 5 間で以下のディレクトリが同期関係にあります。片側のみを変更することは**厳禁**です。

1. **`gakumas-mcp-server`**:
   - `/root/gakumas-workspace/gakumas-mcp-server`
   - `/root/gakumas-workspace/gakumas-tools/gakumas-mcp-server`
   - Pi 5: `/home/pi/gakumas-mcp-server`
2. **`gakumas-agent-bot`**:
   - `/root/gakumas-workspace/gakumas-agent-bot`
   - `/root/gakumas-workspace/gakumas-tools/gakumas-agent-bot`
   - Pi 5: `/home/pi/gakumas-agent-bot`
3. **`gakumas-discord-bot`**:
   - ソースコード: `/root/gakumas-workspace/gakumas-tools/packages/discord-bot`
   - Pi 5 配置先: `/home/pi/gakumas-discord-bot`

### 3.2 パス解決のマルチレイヤー・フォールバック
スタンドアロン環境（Pi 5）、Sandbox 開発環境、TrueNAS Docker（Web UI）のいずれでも正しく動作するよう、コード内のパス解決は必ず以下の優先順位で安全にフォールバックさせてください：
```typescript
// 例: master-data.ts / config.ts
const candidatePaths = [
    path.resolve(process.cwd(), 'data/json', filename),          // Pi 5 standalone
    path.resolve(process.cwd(), 'json', filename),
    path.resolve(process.cwd(), 'packages/gakumas-data/json', filename), // Sandbox
    path.resolve(__dirname, '../../../gakumas-data/json', filename),
    path.resolve('/app/packages/gakumas-data/json', filename),    // Docker
    path.resolve('/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/json', filename)
];
```

---

## 4. Raspberry Pi 5 へのデプロイ・反映手順

Sandbox 内でコードを編集した後、Pi 5 へ反映する手順は以下の通りです。

### 4.1 Discord Bot (Thin Client) の反映
1. **Sandbox 側でビルド**:
   ```bash
   cd /root/gakumas-workspace/gakumas-tools
   pnpm --filter gakumas-discord-bot build
   ```
2. **Pi 5 への rsync 転送**:
   ```bash
   rsync -avz packages/discord-bot/dist/ pi@192.168.100.32:/home/pi/gakumas-discord-bot/dist/
   rsync -avz packages/gakumas-data/json/ pi@192.168.100.32:/home/pi/gakumas-discord-bot/data/json/
   rsync -avz packages/cli/scripts/sync-*.mjs pi@192.168.100.32:/home/pi/gakumas-discord-bot/scripts/
   rsync -avz packages/cli/scripts/utils/ pi@192.168.100.32:/home/pi/gakumas-discord-bot/scripts/utils/
   rsync -avz agent-instructions/ pi@192.168.100.32:/home/pi/gakumas-discord-bot/agent-instructions/
   ```
3. **Pi 5 サービス再起動**:
   ```bash
   ssh pi@192.168.100.32 "sudo systemctl restart gakumas-discord-bot"
   ```

### 4.2 MCP Server の反映
1. **Sandbox 間の同期**:
   ```bash
   rsync -av /root/gakumas-workspace/gakumas-mcp-server/ /root/gakumas-workspace/gakumas-tools/gakumas-mcp-server/
   ```
2. **Pi 5 への転送とサービス再起動**:
   ```bash
   rsync -avz --exclude='.venv' --exclude='__pycache__' /root/gakumas-workspace/gakumas-mcp-server/ pi@192.168.100.32:/home/pi/gakumas-mcp-server/
   ssh pi@192.168.100.32 "sudo systemctl restart gakumas-mcp"
   ```

### 4.3 asari-agent の反映
1. **Sandbox 間の同期**:
   ```bash
   rsync -av /root/gakumas-workspace/gakumas-agent-bot/ /root/gakumas-workspace/gakumas-tools/gakumas-agent-bot/
   ```
2. **Pi 5 への転送とサービス再起動**:
   ```bash
   rsync -avz --exclude='.venv' --exclude='__pycache__' /root/gakumas-workspace/gakumas-agent-bot/ pi@192.168.100.32:/home/pi/gakumas-agent-bot/
   ssh pi@192.168.100.32 "sudo systemctl restart asari-agent"
   ```

---

## 5. systemd サービス管理コマンド集

SSH 経由で Pi 5 の稼働状況を一括監視・操作できます。

```bash
# 全 3 サービスの稼働状況を一括確認
ssh pi@192.168.100.32 "systemctl status gakumas-mcp.service asari-agent.service gakumas-discord-bot.service --no-pager"

# 各サービスのログ確認 (直近 50 行)
ssh pi@192.168.100.32 "journalctl -u gakumas-discord-bot -n 50 --no-pager"
ssh pi@192.168.100.32 "journalctl -u gakumas-mcp -n 50 --no-pager"
ssh pi@192.168.100.32 "journalctl -u asari-agent -n 50 --no-pager"

# 一括再起動 (MCP ➔ Agent / Bot の順)
ssh pi@192.168.100.32 "sudo systemctl restart gakumas-mcp && sudo systemctl restart asari-agent gakumas-discord-bot"
```

---

## 6. トラブルシューティング

| 症状 | 原因 | 対処法 |
| :--- | :--- | :--- |
| Discord でコマンド実行時「アプリケーションが応答しませんでした」 | Bot または MCP サーバーが停止している、あるいはタイムアウト | `systemctl status gakumas-discord-bot` と `gakumas-mcp` を確認。`journalctl` でエラー詳細を特定 |
| Google Sheets 同期に失敗する | OAuth トークンの失効または未配置 | Pi 5 の `/home/pi/.config/gakumas-tools/sheets_tokens.json` の存在を確認。必要に応じて Sandbox で `node packages/cli/scripts/reauth-sheets.mjs` を対話実行し、Pi 5 へ再転送 |
| Discord Bot が二重返答する | TrueNAS Docker 側の旧コンテナが停止していない | TrueNAS 上で `docker ps \| grep gakumas-bot` を確認し、残存コンテナを停止・削除する |
| 新規追加したアイドルやサポカが Bot に認識されない | マスタデータ JSON が Pi 5 側に未同期 | `pnpm --filter gakumas-data generate` 後、`packages/gakumas-data/json/` を Pi 5 の `data/json/` へ rsync して Bot を再起動 |

