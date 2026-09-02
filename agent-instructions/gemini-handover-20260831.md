# Gemini への引継書
**作成日時**: 2026-08-31 21:28 JST  
**前担当**: Claude Sonnet 4.6 (Thinking)  
**対象ワークスペース**: `/root/gakumas-workspace`

---

## 1. プロジェクト全体概要

「学園アイドルマスター（Gakumas）」のシミュレーション・対戦管理ツール群のモノレポ。
TrueNAS 上の Incus Sandbox (Ubuntu 24.04 / NVMe) で開発・実行。

### 主要ディレクトリ
| ディレクトリ | 用途 |
|---|---|
| `gakumas-tools/` | シミュレーションエンジン・CLI・Discord Bot（Next.js + TypeScript） |
| `gakumas-agent-bot/` | あさり先生 Discord Bot（Python / Gemini API + llama.cpp） |
| `gakumas-og-tools/` | Google Sheets 連携・スクレイピングスクリプト（Python） |
| `gakumas-support_cards/` | サポートカード DSL 変換・マスタ生成 |
| `shared/` | agent-instructions, match_history CSV, documents |

### インフラ
- **MongoDB**: `192.168.100.4`（`loadouts`, `simulation_results`, `memories`, `contest_matches`, `owned_support_cards`, `owned_p_idols` コレクション）
- **ローカルLLM**: `http://192.168.100.4:30080/v1`（llama.cpp Vulkan / `qwen2.5-7b.gguf`、コンテキスト16384）
- **Web UI**: TrueNAS コンテナ port 30000 / デプロイは `./deploy.sh` を手動実行
- **Google Sheets スプレッドシート ID**: `1MPHcaLbZcTNxjFFaSKBmKWkRqRqOn-YDVrdInPLDcOQ`（`SYNC_SHEET_ID` 環境変数）

---

## 2. 今セッション（8/26〜8/31）で完了した主要作業

### 2-1. コンテスト対戦記録の Google Sheets & MongoDB 統合移行（完了済み）

**背景**: 従来 `match_history_NN.csv` というローカルファイル管理だったコンテスト対戦記録を、MongoDB + Google Sheets の双方向管理に移行した。

**実装ファイル（新規・変更）**:
- [`packages/discord-bot/src/utils/match-history-updater.ts`](file:///root/gakumas-workspace/gakumas-tools/packages/discord-bot/src/utils/match-history-updater.ts): `saveContestMatchToMongo()` 追加、`updateMatchHistoryCsv()` を async 化
- [`packages/discord-bot/src/commands/record-contest.ts`](file:///root/gakumas-workspace/gakumas-tools/packages/discord-bot/src/commands/record-contest.ts): `await` 化、`userId` 追加、JST 年取得修正
- [`packages/discord-bot/src/commands/sync.ts`](file:///root/gakumas-workspace/gakumas-tools/packages/discord-bot/src/commands/sync.ts): `🏆 コンテスト対戦記録 (Contest)` ターゲット追加
- [`packages/discord-bot/src/config.ts`](file:///root/gakumas-workspace/gakumas-tools/packages/discord-bot/src/config.ts): `syncSheetId` 追加
- [`packages/cli/scripts/sync-contest-matches.mjs`](file:///root/gakumas-workspace/gakumas-tools/packages/cli/scripts/sync-contest-matches.mjs): MongoDB ↔ Sheets 双方向同期スクリプト（`Contest` シートを自動作成する機能含む）
- [`packages/cli/scripts/import-contest-csv.mjs`](file:///root/gakumas-workspace/gakumas-tools/packages/cli/scripts/import-contest-csv.mjs): 既存 CSV の MongoDB 一括インポートスクリプト

**データ移行状況**: `match_history_51.csv`（8/26〜8/28, 14試合）→ MongoDB `contest_matches` インポート済み、Google Sheets `Contest` タブにも同期済み。

**運用フロー（確立済み）**:
1. `/record-contest`（Discord My Gakumas Tools Bot）でスクショ登録 → CSV + MongoDB に自動保存
2. Discord `/sync contest` で MongoDB → Google Sheets `Contest` タブ反映
3. Google Sheets での手動修正を MongoDB に戻す場合: `node sync-contest-matches.mjs --mode sheet-to-mongo --execute`

**MongoDB スキーマ（`contest_matches`）**:
```json
{
  "season": 51, "date": "26/08/26", "matchIndex": 1,
  "opponent": { "name": "ふぁゆ", "grade": 1 },
  "stages": {
    "stage1": { "myScore": 495762, "enemyScore": 140179, "result": "WIN" },
    "stage2": { "myScore": 321376, "enemyScore": 100374, "result": "WIN" },
    "stage3": { "myScore": 613583, "enemyScore": 80752, "result": "WIN" }
  },
  "overallResult": "WIN", "earnedPt": 110,
  "extra": { "fans": null, "coins": null, "currentPt": null, "currentRank": null },
  "userId": "...", "recordedAt": "..."
}
```

---

### 2-2. /advisory 画像出力の改修（完了済み）

**変更内容**:
- Pアイドルセクション: メインアイドルアイコン + サブアイドルアイコンを右下25%シフトで小さく重ねる（サブアイコンは1/4サイズ）
- スキルカード・Pアイテムが2カラムから1カラム（デフォルト）に変更可能。`/advisory` 起動時のオプションで切替。デフォルト1カラム（幅も現在の半分）
- **変更ファイル**: [`gakumas-agent-bot/advisory_image_builder.py`](file:///root/gakumas-workspace/gakumas-agent-bot/advisory_image_builder.py)

---

### 2-3. アップストリーム同期（2026-08-29, 完了済み）

**取り込んだコミット**: `40c3c68f..abc19a10`（`surisuririsu/gakumas-tools`）

**主要内容**:
- 新Pアイドル: 秦谷美鈴【「ねえ、言っちゃうよ。」】（Sense / Concentration, ID: 151）
- 専用Pアイテム: 夏の足音 / 夏の足音+（ID: 475, 476）、サポートPアイテム: 真夏に咲く太陽（ID: 477）
- 専用スキルカード: 波間に揺れる光 / 波間に揺れる光+（ID: 861, 862）、のんびりすやすや / のんびりすやすや+（ID: 863, 864）
- `buffCostConsumed` トリガータイミングの修正
- スタミナ計算機 UI & Data Model の追加
- RAG ドキュメント再生成済み（151 P-Idols / 864 Skill Cards / 477 P-Items）
- 全テスト合格: `pnpm test:stamina` 7/7, `pnpm test:regression` 524/524

---

### 2-4. あさり先生 Bot の修正（2026-08-30, 完了済み）

**ファイル**: [`gakumas-agent-bot/gakumas_agent_bot.py`](file:///root/gakumas-workspace/gakumas-agent-bot/gakumas_agent_bot.py)

**変更内容（未コミット）**:
1. **Bot間誤応答の修正**: 他の Bot（Captain Hook / My Gakumas Tools）の発言に反応しなくなった（L910〜914: `_execute_bot_commentary` 呼び出し → 即 `return` に変更）
2. **「あさり先生」呼びかけでの自動セッションリセット**: メッセージが「あさり先生」「アサリ先生」「asari」で始まる場合、会話履歴を自動リセットして呼びかけ以降を新しい質問として処理
3. **`/cancel` スラッシュコマンドのバグ修正**: 存在しない `bot.ollama_service.cancel()` を呼んでいた → 削除して `bot._is_busy = False` に修正
4. **テキストコマンドとして `/new`・`/cancel` を追加**: スラッシュコマンドなしでも動作するように

---

## 3. 未コミット変更（要対応）

```bash
cd /root/gakumas-workspace/gakumas-tools
git status -s
```

| ファイル | 内容 | 対応 |
|---|---|---|
| `gakumas-agent-bot/gakumas_agent_bot.py` | あさり先生 Bot の修正（8/30） | **要コミット** |
| `agent-instructions/match_history_51.csv` | 最新の対戦記録（継続更新中） | 都度コミット |
| `gakumas-agent-bot/data/quota_usage.json` | Gemini API クォータ自動更新 | 無視可 |
| `.config/gakumas-tools/sheets_tokens.json` | OAuth トークン自動更新 | 無視可 |

**次セッション開始時に実行すべきコマンド**:
```bash
cd /root/gakumas-workspace/gakumas-tools
git add gakumas-agent-bot/gakumas_agent_bot.py
git commit -m "Fix あさり先生 bot: ignore other bots, add session reset on name trigger, fix /cancel"
```

---

## 4. 現在の Bot 構成（チャンネル: #gakumas-tools通知）

| Bot名 | 種別 | 役割 |
|---|---|---|
| **shigehiro** | 人間ユーザー | オーナー |
| **あさり先生** | 双方向対話型 Bot | Python (Antigravity SDK + llama.cpp)、自由な質問に回答 |
| **My Gakumas Tools** | スラッシュコマンド専用 Bot | TypeScript、`/contest` `/record-contest` `/sync` `/advisory` 等 |
| **Captain Hook** | Cron 片方向 Bot | 日次のデッキ推奨・アップストリーム更新情報配信 |

---

## 5. 次のセッションでの推奨アクション

### 優先度 高
1. 未コミットの `gakumas_agent_bot.py` の変更をコミット（上記 Step 参照）
2. `./deploy.sh` を実行して TrueNAS コンテナへ反映（ユーザーが手動で実行）

### 優先度 中
3. Seesaa Wiki サポートカード定期差分チェック（次シーズン対応カード追加に備えて）
4. コンテストシーズン51終了後: 次シーズン（52）用 `import-contest-csv.mjs` の実行準備
5. `route_query_to_model()` 関数（L145〜172）がデッドコード化しているため削除を検討

### 優先度 低
6. アップストリーム（`surisuririsu/gakumas-tools`）の次回更新チェック
7. `gakumas_agent_bot.py` のファイル冒頭 docstring を現実の実装に合わせて更新

---

## 6. 重要な注意事項（AGENTS.md より）

- **デプロイは手動**: `./deploy.sh` はエージェントが自動実行せず、ユーザー（shigehiro）に手動実行を促すこと
- **両 agent-bot ディレクトリの同期義務**: `gakumas-agent-bot/` の Python ファイルを変更した場合は必ず `cp` で `gakumas-tools/gakumas-agent-bot/` にも同期
- **キャッシュ回避**: シミュレーション検証時は `runs` 数を変えて新規計算を確認
- **Python 仮想環境**: `gakumas-og-tools` 系スクリプトは `gakumas-og-tools/.venv/bin/python3` を使用
- **モデル指定**: コード内で Gemini モデルを指定する場合は必ず現行の `gemini-3.6-flash` を使用（deprecated モデルは使用禁止）
- **Google Sheets 認証**: `packages/cli/scripts/utils/sheetsAuth.mjs` の `getAuthClient()` を使用。トークンは `~/.config/gakumas-tools/sheets_tokens.json`
- **アップストリーム同期の標準手順**: `AGENTS.md` 記載の4ステップ（クリーン化→フェッチ＆マージ→コンフリクト解消→データ再生成＆ビルド）を厳守

---

## 7. 主要な環境変数（`.env.local`）

```env
DISCORD_BOT_TOKEN=（あさり先生 Bot のトークン）
DISCORD_TOKEN=（My Gakumas Tools Bot のトークン）
ALLOWED_CHANNEL_ID=（#gakumas-tools通知 チャンネルID）
MONGODB_URI=mongodb://192.168.100.4:27017
MONGODB_DB=gakumas
SYNC_SHEET_ID=1MPHcaLbZcTNxjFFaSKBmKWkRqRqOn-YDVrdInPLDcOQ
LLM_BASE_URL=http://192.168.100.4:30080/v1
LLM_MODEL=/models/qwen2.5-7b.gguf
GEMINI_API_KEY=（Gemini API キー）
```
