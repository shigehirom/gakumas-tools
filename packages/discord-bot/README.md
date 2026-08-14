# 学園アイドルマスター ツール - Discord Bot 連携

Discord のチャット・スラッシュコマンドから直接、学マスツールのコンテストシミュレーションや最適化デッキの確認、登録メモリーの閲覧を実行できる専用 Bot です。

---

## 🚀 提供コマンド

| スラッシュコマンド | 説明 |
|---|---|
| **`/contest stage:[1\|2\|3] idol:[all\|saki...]`** | 現在開催中シーズンの指定ステージに対して、2000 runs・2段階ステップ実行（`--step`）の最適化シミュレーションを実行し、上位編成サマリーと詳細 Markdown レポート（添付ファイル）を返信します。 |
| **`/deck stage:[1\|2\|3]`** | 現在コンテスト用に最適化されている指定ステージの 3 人のアイドル編成（アイドル名、メイン/サブメモリー、期待中央値 Pt）を表示します。 |
| **`/recent-memories [count:1-25]`** | データベースに登録されている最新のメモリー（デフォルト: 最新 10 件）を一覧表示します（`cli list \| sort \| tail -10` 相当）。 |
| **`/import-memory image:[screenshot] [name]`** | メモリーのスクリーンショット画像を添付すると、OCRとONNXモデルで自動解析（ステータス・Pアイテム・スキルカード・Pアイドル・パワー）し、MongoDB に自動保存します。 |

---

## ⚙️ セットアップ手順

### 1. Discord Developer Portal で Bot を作成
1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセスし、「New Application」を作成。
2. **Bot** タブから Bot を作成し、Token（`DISCORD_BOT_TOKEN`）を発行。
3. **General Information** から `APPLICATION ID`（`DISCORD_CLIENT_ID`）をコピー。
4. **OAuth2 > URL Generator** から `bot` および `applications.commands` をチェックし、生成された URL からご自身の Discord サーバーに Bot を招待。

### 2. 環境変数の設定 (`.env.local`)
`.env.local`（プロジェクトルートまたは `gakumas-tools/.env.local`）に以下を追加します：

```env
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CLIENT_ID=your_client_id_here
DISCORD_GUILD_ID=your_discord_server_id_here   # オプショナル（設定するとコマンドが即時反映されます）
```

---

## 🏃 起動方法

### 開発実行
```bash
cd packages/discord-bot
pnpm install
pnpm start
```

### ビルド
```bash
pnpm --filter gakumas-discord-bot build
```

### バックグラウンド常駐起動（PM2 を使用する場合の例）
```bash
pm2 start dist/index.js --name gakumas-bot
```
