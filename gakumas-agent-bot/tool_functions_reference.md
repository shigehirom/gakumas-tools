# 🛠️ gakumas-tools Tool-Use API リファレンス

本ドキュメントでは、ローカル LLM（`llama.cpp` / Qwen 2.5 7B）および Gemini 等の AI エージェントが自律的に呼び出す **Tool-Use（Function Calling）用データアクセス関数群** の仕様をまとめています。

エージェントはユーザーからの自然言語の質問に応じてこれらのツールを自動選択・実行し、学マスのマスタデータ（CSV）やユーザー環境データ（MongoDB / 対戦ログ）を参照して回答します。

---

## 📋 ツール一覧（サマリー）

| ツール名 (`name`) | データソース | 主な用途・対象 |
| :--- | :--- | :--- |
| **`get_optimized_deck`** | MongoDB (`loadouts`) | **【現行3ステージ編成】** 各ステージの最新シミュレーション結果（上位アイドル、12枚デッキ、期待中央値）を直読集計 |
| **`get_stage_loadout`** | MongoDB (`loadouts`) | **【直近実走値直読】** 指定ステージ・指定アイドルの最新シミュレーション結果（中央値・実効ステータス・12枚デッキ・Pアイテム・メモリー） |
| **`get_contest_advisory`** | Markdown (`documents/`) | **【あじふらい氏推奨構成】** トッププレイヤーによるステージ別推奨アイドル優先度、推奨Pアイテム、推奨スキルカード10枚（カスタム付き） |
| **`get_contest_regulation`** | 設定・マスタ | **【ステージ審査基準・相性診断】** ステージ審査比率（Vo/Da/Vi）、ターン数、ルールと各アイドルの得意傾向照合 |
| **`get_contest_stats`** | 対戦ログ (`match-histories`) | コンテスト対戦成績・勝率集計・日別/シーズン別実績 |
| **`search_skill_cards`** | `gakumas-data/csv` | スキルカードの条件検索（プラン、効果種別、繰り返し可否、キーワード。DSL日本語変換付き） |
| **`search_p_items`** | `gakumas-data/csv` | Pアイテムの条件検索（プラン、効果種別、キーワード） |
| **`get_owned_p_idols`** | MongoDB (`p_idols`) | ユーザー所持 P アイドル一覧（才能開花★、特訓段階、型・プラン別） |
| **`get_p_idol_details`** | CSV + MongoDB | 特定 P アイドルの詳細能力・固有スキル・固有Pアイテム・所持状況 |
| **`get_owned_support_cards`** | MongoDB (`support_cards`) | ユーザー所持サポートカード一覧（凸数、習得可能スキルカード別） |
| **`get_support_card_details`** | サポカマスタ / MongoDB | サポートカードのアビリティ詳細、上限解放ボーナス、イベント効果 |
| **`get_owned_memories`** | MongoDB (`memories`) | ユーザー所持メモリー一覧（付与スキル、パラメータ合計） |
| **`get_support_bonus`** | MongoDB (`owned_support_cards`) | 現在の最新サポートボーナス値（%・倍率）、所持枚数・レベル別内訳 |

---

## 🔍 各ツールの詳細仕様

### 1. `search_skill_cards`（スキルカード検索）
学園アイドルマスターの全スキルカード（通常、固有、トラブル、アイテム付与等）をマスタデータから複合条件検索します。
内部で DSL（カード効果コード）を自然な日本語表現へ自動変換して返します。

- **引数パラメータ (`arguments`):**
  - `plan` (`string`): プランフィルタ (`"sense"`, `"logic"`, `"anomaly"`, `"free"`, `"any"`)
  - `card_type` (`string`): カード種類 (`"active"`, `"mental"`, `"trouble"`, `"any"`)
  - `effect_type` (`string`): 主な効果種別 (`"goodConditionTurns"`, `"concentration"`, `"perfectConditionTurns"`, `"goodImpressionTurns"`, `"motivation"`, `"enthusiasm"`, `"fullPower"`, `"strength"`, `"preservation"`, `"genki"`, `"score"`, `"draw"`, `"hold"`, `"any"`)
  - `is_repeatable` (`boolean`): `true` で繰り返し使用可能カードのみ抽出
  - `keyword` (`string`): カード名や効果テキストへの部分一致検索
  - `max_results` (`integer`): 取得上限件数（デフォルト: 20）
- **出力内容:** カード名、レアリティ、コスト、効果内容（日本語）、カスタマイズ枠情報

---

### 2. `search_p_items`（Pアイテム検索）
Pアイテム（通常アイテム、Pアイドル固有アイテム、サポートカード獲得アイテム）を検索します。

- **引数パラメータ (`arguments`):**
  - `plan` (`string`): 対象プラン (`"anomaly"`, `"sense"`, `"logic"`, `"free"`, `"any"`)
  - `effect_type` (`string`): 主な効果種別 (`"fullPower"`, `"genki"`, `"score"`, `"draw"`, `"any"`)
  - `keyword` (`string`): アイテム名・効果文へのキーワード
  - `max_results` (`integer`): 取得上限件数（デフォルト: 15）
- **出力内容:** アイテム名、レアリティ、プラン、効果詳細

---

### 3. `get_owned_p_idols`（所持Pアイドル一覧）
MongoDBに同期されているユーザーの所持Pアイドル一覧を取得します。

- **引数パラメータ (`arguments`):**
  - `plan` (`string`): プラン (`"anomaly"`, `"sense"`, `"logic"`, `"any"`)
  - `idol_name` (`string`): アイドル名（例: `"花海 咲季"`, `"咲季"`, `"星南"` など愛称対応）
  - `effect_type` (`string`): 型フィルタ (`"fullPower"`, `"strength"`, `"goodConditionTurns"`, `"concentration"` 等)
  - `rarity` (`string`): レアリティ (`"SSR"`, `"SR"`, `"R"`, `"any"`)
  - `min_talent` (`integer`): 最低才能開花段階（★0〜4）
- **出力内容:** アイドル名、二つ名、レアリティ、才能開花★、特訓レベル、プラン、型

---

### 4. `get_p_idol_details`（Pアイドル詳細情報）
特定 P アイドルの初期ステータス、成長率、固有スキルカード、固有Pアイテム、型、所持状況を網羅的に返します。

- **引数パラメータ (`arguments`):**
  - `idol_name` (`string`): アイドル名（例: `"十王 星南"`, `"月村 手毬"`）
  - `title` (`string`): Pアイドルのタイトル・二つ名・楽曲名（例: `"ねえ、言っちゃうよ。"`, `"小さな野望"`, `"Star-mine"`）
- **出力内容:** 詳細ステータス、固有スキルカード効果、固有Pアイテム効果、おすすめ型、ユーザー所持状況

---

### 5. `get_owned_support_cards`（所持サポートカード一覧）
ユーザーが所持しているサポートカード一覧および上限解放数（凸数）を取得します。

- **引数パラメータ (`arguments`):**
  - `rarity` (`string`): レアリティ (`"SSR"`, `"SR"`, `"R"`, `"any"`)
  - `min_uncap` (`integer`): 最低上限解放数（`4` で完凸のみ抽出）
  - `target_skill` (`string`): イベント等で習得できるスキルカード名でのフィルタ
  - `keyword` (`string`): サポートカード名キーワード
  - `max_results` (`integer`): 取得上限件数
- **出力内容:** カード名、レアリティ、上限解放数（凸数）、レベル、獲得可能スキル

---

### 6. `get_support_card_details`（サポートカード詳細）
サポートカードのアビリティ詳細（各上限解放ごとのボーナス値、サポート効果、イベント効果）を取得します。

- **引数パラメータ (`arguments`):**
  - `card_name` (`string`, 必須): サポートカード名（完全一致または部分一致、例: `"ほら、一緒に持と？"`）
- **出力内容:** サポートアビリティ（レッスンボーナス等）、イベント発生時効果・習得スキル

---

### 7. `get_owned_memories`（所持メモリー一覧）
所持している育成完了メモリーの一覧を検索します。

- **引数パラメータ (`arguments`):**
  - `keyword` (`string`): メモリー名への部分一致（日付プレフィックス等）
  - `card_name` (`string`): 付与されているスキルカード名
  - `min_param` (`integer`): パラメータ合計の下限値
  - `max_results` (`integer`): 取得上限件数
- **出力内容:** メモリー名、付与スキルカード一覧、ステータスボーナス

---

### 8. `get_contest_stats`（コンテスト対戦履歴・集計）
記録されたコンテスト対戦CSVから勝敗、勝率、平均スコア、最高スコアを集計します。

- **引数パラメータ (`arguments`):**
  - `season` (`integer`): シーズン番号（省略時は最新シーズン）
  - `date` (`string`): 特定日フィルタ（`"today"`, `"今日"`, `"26/08/21"` 等）
  - `season_start` / `season_end` (`integer`): 複数シーズンにまたがる推移比較用
  - `recent_count` (`integer`): 詳細表示する直近対戦数（デフォルト: 5）
- **出力内容:** 勝敗数・勝率、各ステージ平均/最高スコア、直近対戦一覧

---

### 9. `get_optimized_deck`（最適化デッキ・現在編成）
MongoDB (`loadouts`) コレクションから各ステージ（または指定ステージ）の最新シミュレーション結果を直接集計し、
現在開催中コンテストの最新最適化編成を取得します（静的 Markdown レポートへの依存を排除）。

- **引数パラメータ (`arguments`):**
  - `stage` (`integer`): ステージ番号 (`1`, `2`, `3`。省略時は全3ステージ9名および総合期待中央値)
  - `idol_name` (`string`): 特定アイドルを指定した場合、そのアイドルの実効ステータス（Vo/Da/Vi/HP）、全採用スキルカード12枚（メイン/サブメモリー由来・カスタム付き）、獲得Pアイテム詳細を取得
- **出力内容:** ステージごとの配置アイドル、メイン/サブメモリー名、期待中央値スコア、重複警告（全ステージ表示時）

---

### 10. `get_support_bonus`（サポートボーナス確認・診断）
ユーザーが所持する全サポートカードのレベルから算出される最新の総合サポートボーナス値を取得します。

- **引数パラメータ (`arguments`):** なし
- **出力内容:** 総合サポートボーナス（%およびスコア乗算倍率）、所持枚数（SSR/SR/R）、レベル帯別内訳（Lv.60完凸達成枚数等）、コンテストへの影響と育成アドバイス

---

## 🧩 補助モジュール群

- **`DslTranslator` (`dsl_translator.py`):**
  - カード効果の生 DSL（例: `goodConditionTurns:3`, `addScore:0.7*concentration`）を、人間にもLLMにも読みやすい自然な日本語（例:「好調3ターン付与」「集中×0.7のスコア獲得」）に自動翻訳します。
- **`ImageResolver` (`image_resolver.py`):**
  - LLMが回答内で言及したPアイドル（`アイドル名【二つ名】`）、スキルカード（`『カード名』`）、サポートカードの画像パスをワークスペース（`gk-img` / `packages/gakumas-images`）から自動解決し、Discord上に添付画像として送信します。
- **`GakumasSyncService` (`sync_service.py`):**
  - Web UI / MongoDB 側のデータ更新や対戦履歴 CSV を定期同期・キャッシュ更新します。
