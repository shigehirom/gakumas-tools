# Gakumas Tools CLI Utility

`gakumas-tools` のシミュレーションエンジンおよびデータ管理機能をより使いやすく、拡張可能にするための統合 TypeScript CLI ユーティリティです。
Handlebars テンプレートエンジンによる構造化 Markdown 出力、Google Drive / ローカルファイル自動保存、Discord Webhook 連携、および高度な編成最適化・調教アドバイザー機能をサポートしています。

---

## 📦 インストール & 準備

プロジェクトルート（`gakumas-tools`）から `pnpm cli` で実行可能です。個別にビルドする場合は `packages/cli` ディレクトリで以下のコマンドを実行します。

```bash
cd packages/cli
pnpm install
pnpm build
```

### 便利なエイリアス設定
ターミナルやシェル設定（`~/.bashrc` や `~/.zshrc`）にエイリアスを設定しておくと、任意の場所から `gakumas` コマンドで呼び出せます。

```bash
alias gakumas='pnpm --dir /root/gakumas-workspace/gakumas-tools cli'
```

---

## 🌐 グローバルオプション

すべてのコマンド共通で使用できるオプションです。

| オプション | 説明 |
|---|---|
| `--gdrive [filename]` | 出力レポートを Google Drive へ自動アップロードします。ファイル名を省略した場合はコマンド引数と日付から自動命名されます。アップロード成功時に Markdown 先頭へ YAML フロントマター（`reference_url`）が付与され、URL は `.gdriveurl` にも保存されます。 |
| `--local [filename]` | 出力レポートをローカルファイル（Markdown）として保存します。保存先ディレクトリは環境変数 `CLI_DOCS_DIR`（未指定時はカレントディレクトリ）に従います。 |

---

## 🛠️ コマンドリファレンス

### 1. コンテスト最適化 (`contest`)
MongoDB 上のメモリデータを使用し、指定ステージにおける最適なメモリ組み合わせ（メイン＋サブ2枚）を高速に探索・シミュレーションします。

```bash
gakumas contest <stage> [runs] [idolName] [plan] [options]
```

* **引数**:
  * `stage`: ステージ番号 (例: `46-1`, `37-3`)
  * `runs`: 1組み合わせあたりの試行回数 (デフォルト: `1000`)。省略してアイドル名を指定することも可能 (例: `gakumas contest 46-1 hiro`)。
  * `idolName`: 特定のアイドルのみ計算する場合。カンマ区切りで複数指定可能 (`saki,temari`)。`all` を指定すると全アイドルを順次計算します。
  * `plan`: プラン絞り込み (`sense`, `logic`, `anomaly`)。省略時はステージ情報から自動決定。
* **主なオプション**:
  * `--save [count]`: スコア上位 N 件の組み合わせを Loadout（編成）として DB に保存 (デフォルト: 1, 最大: 5)。
  * `--name <name>`: 保存する Loadout の名前プレフィックスを指定。
  * `--userId <id>`: 特定のユーザー ID に紐づけて保存。
  * `--supportBonus <value>`: サポートボーナス値を指定 (例: `0.12` または `12.00`。デフォルト: `.env.local` の設定値または `0.04`)。
  * `--step`: 2段階シミュレーション（スクリーニング → 上位候補のみ本シミュレーション）を実行。
  * `--force`: キャッシュを無視して強制的に再計算し、DB キャッシュを更新。
  * `--synth`: スキルカード合成シミュレーションと合成提案を実行。
  * `--compare <pattern>`: 指定パターン（ワイルドカード `*` 可）に一致するメモリとの組み合わせのみを対象にして比較。
  * `--showWorst`: 平均スコアの低いワースト組み合わせも表示。
  * `--allResults`: 全ての組み合わせシミュレーション結果を出力。
  * `--filterHashes <hashes>`: 指定ハッシュリスト（JSON 配列文字列）に絞り込んで計算。
  * `--json`: 結果を JSON 形式で出力。

---

### 2. メモリ調教・目標設定アドバイザー (`advisor`)
最適化された編成や特定のメモリ構成に対して、ステータス向上（パラメータ）やスキルカードの入れ替えによるスコア影響を詳細に診断・アドバイスします。

```bash
gakumas advisor <stage> [runs] [idolName] [plan] --mode <params|cards> [options]
```

* **必須オプション**:
  * `--mode <mode>`: アドバイザーの診断モード（`params`: ステータス配分診断 / `cards`: スキルカード選択診断）。
* **オプション**:
  * `--main <name>`: 診断対象とするメインメモリの名前を指定。
  * `--sub <name>`: 診断対象とするサブメモリの名前を指定。
  * `--optimized [file]`: 参照するデッキ最適化 Markdown ファイルのパス (省略時は最新ファイルを自動検出)。
  * `--supportBonus <value>`: サポートボーナスの値を指定。
  * `--discord`: 診断サマリーを Discord Webhook (`DISCORD_WEBHOOK_URL`) へ送信。
  * `--sort <order>`: レポートの並び順 (`normal` または `reverse`)。

---

### 3. リハーサル・合計スコア予測 (`rehearsal`)
保存された Loadout（編成）を複数指定し、コンテスト等の実戦を想定したチーム合計スコアを予測シミュレーションします。

```bash
gakumas rehearsal <runs> [...decks] [options]
```

* **引数**:
  * `runs`: 1デッキあたりのシミュレーション試行回数 (例: `200`)
  * `decks`: Loadout として保存されている編成名（通常は3デッキ指定）。
* **出力**: 各アイドルのスコア統計（最小・平均・最大・中央値・標準偏差）とチーム合計スコアの分布レポート。

---

### 4. デッキ編成最適化 (`optimize-deck`)
コンテストの3ステージ間で「同一アイドルかつ同一衣装（Pアイドル）」の重複を回避しつつ、チーム総合の期待中央値が最大となる組み合わせを探索します。

```bash
gakumas optimize-deck <prefix> [options]
```

* **引数**:
  * `prefix`: `contest` コマンド等で出力された3ステージ分の Markdown ファイルのプレフィックス (例: `26-08-14_46`)。
  * ※ `<prefix>-1_all.md`, `<prefix>-2_all.md`, `<prefix>-3_all.md` を読み込んで最適化します。

---

### 5. 理想メモリー推薦出力 (`recommend`)
理想メモリー Markdown ファイルの内容を解析し、推奨されるメモリ構成や目標スコアを出力します。

```bash
gakumas recommend <file> [options]
```

* **引数**:
  * `file`: 理想メモリーが定義された Markdown ファイルのパス。

---

### 6. 対戦履歴 CSV テンプレート生成 (`match-history`)
コンテストの対戦結果を記録するための CSV テンプレートファイルを自動生成します。

```bash
gakumas match-history <season> <startDate> <endDate>
```

* **引数**:
  * `season`: コンテストシーズン番号 (例: `46`)
  * `startDate`: 開始日 (例: `2026-08-15`)
  * `endDate`: 終了日 (例: `2026-08-30`)
* **出力先**: `CLI_INSTRUCTIONS_DIR`（未設定時は `/root/gakumas-workspace/shared/agent-instructions/match_history_<season>.csv`）

---

### 7. メモリー統計 (`stats`)
MongoDB に登録されているメモリーの統計情報を表示します。

```bash
gakumas stats [idol] [options]
```

* **引数**:
  * `idol`: アイドル名（`saki`, `hiro` 等）。
    * 省略時: 全アイドルの所持数サマリーを表示。
    * `all`: 全アイドルの詳細内訳（プラン・楽曲別）を表示。
* **オプション**:
  * `--json`: JSON 形式で出力。

---

### 8. メモリー一覧 (`list`)
登録されているメモリーの名前一覧を表示します。

```bash
gakumas list [idolName]
```

---

### 9. メモリー詳細レポート (`dump`)
メモリーの詳細情報（ステータス、スキルカード、Pアイテム）を Markdown 形式で出力します。

```bash
gakumas dump [idolName] [outputFile]
```

---

### 10. メモリー削除 (`rm`)
不要なメモリーを対話形式で確認しながら一括削除します。

```bash
gakumas rm <pattern>
```

* **引数**:
  * `pattern`: 削除対象のメモリー名パターン（ワイルドカード `*` 使用可）。

---

### 11. 編成一覧 (`loadout`)
DB に保存されている編成（Loadout）の一覧を表示します。

```bash
gakumas loadout [options]
```

* **オプション**:
  * `--verbose`: Pアイテム、スキルカード、カスタマイズを含む詳細な編成情報を Markdown 形式で出力。

---

### 12. 重複メモリー検索 (`duplicates`)
類似・重複している育成メモリを自動検出し、整理を支援します。

```bash
gakumas duplicates [plan] [idol] [threshold]
```

---

## ⚙️ 環境設定 (`.env.local`)

プロジェクトルートの `.env.local` に以下の設定を記述します。

```env
# MongoDB 接続設定
MONGODB_URI=mongodb://192.168.100.4:27017
MONGODB_DB=gakumas-tools

# サポートボーナス設定 (例: 12.00% = 0.12 または 12.00)
SUPPORT_BONUS=12.00

# レポート・指示書 出力先ディレクトリ (オプショナル)
CLI_DOCS_DIR=shared/reports
CLI_INSTRUCTIONS_DIR=shared/agent-instructions

# Google Drive 連携設定 (オプショナル)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_DRIVE_FOLDER_ID=your-gdrive-folder-id

# Discord 通知連携 (オプショナル)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# デフォルト ユーザー ID (オプショナル)
CLI_USER_ID=your-user-id
```

---

## 🧱 内部設計とカスタマイズ

* **テンプレートエンジン**: `src/templates/` 内の Handlebars (`.hbs`) テンプレートにより、Markdown の出力形式を自由にカスタマイズ可能です。詳細は [TEMPLATES.md](./TEMPLATES.md) を参照してください。
* **オーケストレーションアーキテクチャ**: TypeScript CLI がフロントエンド（引数解析、ファイル/Drive出力、フォーマット）を担当し、ヘビーな並列計算処理は `scripts/` 内の Node.js JS ワーカーへ委譲する設計となっています。
