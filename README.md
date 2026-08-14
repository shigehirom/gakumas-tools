# 学園アイドルマスター ツール (gakumas-tools)

本リポジトリは、[surisuririsu/gakumas-tools](https://github.com/surisuririsu/gakumas-tools) をベースに、TrueNAS Incus Sandbox 環境での高速計算、TypeScript 統合 CLI、MongoDB による計算結果キャッシュ、Google Drive / ローカル連携、および自動デプロイ機能を追加・拡張したフォーク環境です。

---

## 🌟 主な機能と特徴

1. **高速シミュレーションエンジン (`packages/gakumas-engine`)**:
   - 最新のブロック構文 DSL（`{ }`）に対応した AST パーサーと JIT 最適化エンジン。
   - コンテスト（メイン＋サブ2枚構成）およびリハーサルのスコア計算・期待値算出。
2. **統合 TypeScript CLI (`packages/cli`)**:
   - `contest`, `rehearsal`, `advisor`, `optimize-deck`, `recommend`, `match-history` 等の多彩なコマンド群。
   - Markdown レポートの自動生成、Google Drive アップロード、Discord Webhook 連携。
3. **共有 MongoDB キャッシュ連携**:
   - シミュレーション結果を自動キャッシュし、同一条件下での再計算を瞬時に完了。
   - 所持メモリー、保存編成（Loadout）の永続化。
4. **Web UI とローカル静的アセット配信**:
   - Next.js 製の直感的な Web UI。
   - カスタム P アイドル画像のローカル静的配信と unoptimized 最適化による軽量運用。
5. **TrueNAS デプロイ & RAG 知識ベース生成**:
   - `./deploy.sh` による TrueNAS Web UI コンテナへのワンクリック反映。
   - `generate_rag_docs.py` による NotebookLM / Gemini 用 Markdown ドキュメント自動生成。

---

## 📦 パッケージ構成

```
gakumas-tools/
├── gakumas-tools/          # Next.js Web アプリケーション本体
├── packages/
│   ├── cli/                # 統合 TypeScript CLI ツール
│   ├── gakumas-engine/     # シミュレーションコアエンジン
│   ├── gakumas-data/       # カード・Pアイテム・ステージのマスタデータと DSL 定義
│   └── gakumas-images/     # 画像アセット管理・ローカルマッピング
├── scripts/                # 内部ワーカー・補助スクリプト群
├── deploy.sh               # TrueNAS Web UI コンテナへのデプロイスクリプト
└── generate_rag_docs.py    # RAG用ナレッジベース生成スクリプト
```

---

## 🚀 クイックスタート

### 1. 依存関係のインストールとビルド
```bash
# ルートでインストール
pnpm install

# マスタデータの生成と全パッケージのビルド
pnpm --filter gakumas-data generate
pnpm build
```

### 2. 環境設定 (`.env.local`)
`.env.example` を参考に `.env.local` を作成・設定します。

```env
MONGODB_URI=mongodb://192.168.100.4:27017
MONGODB_DB=gakumas-tools
SUPPORT_BONUS=12.00
```

### 3. CLI の実行
```bash
# コンテスト最適化 (例: ステージ 46-1)
pnpm cli contest 46-1 1000 all --save --local

# リハーサル合計スコア予測
pnpm cli rehearsal 200 deck_1 deck_2 deck_3 --local
```

詳細な CLI コマンド仕様は [packages/cli/README.md](./packages/cli/README.md) を参照してください。

---

## 🔄 アップストリーム同期ルール

公式リポジトリの更新を取り込む際は、以下の手順を実施してください。

```bash
# 1. 変更をコミットしてワークツリーをクリーンにする
git add -A && git commit -m "Save working changes before upstream merge"

# 2. アップストリームを取得してマージ
git fetch upstream && git merge upstream/master

# 3. 競合時は公式CSV/アセットを優先
git checkout upstream/master -- packages/gakumas-data/csv/
git checkout upstream/master -- gk-img
git commit -m "Merge upstream/master and resolve conflicts"

# 4. データ再生成とビルド
pnpm --filter gakumas-data generate && pnpm build
```

---

## 🚢 Web UI デプロイ (TrueNAS)

CLI やデータの更新を TrueNAS 上の Web UI コンテナへ反映させる場合は、ターミナルで `./deploy.sh` を手動実行します。

```bash
./deploy.sh
```

---

## 📖 関連ドキュメント
- [エージェント開発ガイド (AGENTS.md)](./AGENTS.md)
- [CLI リファレンス (packages/cli/README.md)](./packages/cli/README.md)
- [データ DSL 仕様書 (packages/gakumas-data/README.md)](./packages/gakumas-data/README.md)
