# 🎓 学園アイドルマスター 総合ナレッジベース (gakumas-dev Knowledge Hub)

本ディレクトリ（`shared/gakumas-dev/knowledge/`）は、初星学園プロデューサー科担任講師「あさり先生」（AI エージェント）およびプロデューサー（人間）が共有する、体系化されたプロデュース・シミュレーション・攻略ナレッジのハブです。

---

## 🌟 ナレッジベースの設計方針

1. **確定ローカル資産（Local Truth）に基づく高精度な基礎**:
   - シミュレーションエンジン（`gakumas-tools`）や評価値計算ロジック（`utils/hif.js`）、公式マスタデータ（`packages/gakumas-data`）、所持資産（MongoDB）と 100% 整合した正確な数値をベースとします。
2. **Web サーベイ（Gemini Grounding）との融合**:
   - Web 上の最新攻略トレンドや編成論を動的に取り込みつつ、本ナレッジの計算モデル・診断フレームワークを通じて「プロデューサー個人の所持資産に最適なアドバイス」へと昇華させます。
3. **Obsidian 保管庫（`shared/gakumas-dev`）完全連動**:
   - 人間側からも Obsidian 上でノートとして閲覧・加筆・リンク探索が可能です。

---

## 📚 ディレクトリ構成 & 目次

### 🏆 1. H.I.F. (Hatsuboshi Idol Festival) シナリオ攻略
大型育成シナリオ「H.I.F.」における **S4+（評価値 30,000pt）および S5（35,000pt）達成** のための完全ガイド・診断知識群です。

| ドキュメント | 概要 | 主な内容 |
| :--- | :--- | :--- |
| [00_hif_overview.md](file:///root/gakumas-workspace/shared/gakumas-dev/knowledge/hif/00_hif_overview.md) | **シナリオ概要 & 評価値計算式** | シナリオ構造、評価値（Produce Rating）の完全換算テーブル（`utils/hif.js` 準拠）、ランク基準 |
| [01_s4_plus_target_models.md](file:///root/gakumas-workspace/shared/gakumas-dev/knowledge/hif/01_s4_plus_target_models.md) | **S4+ 目標配分モデル & 逆算表** | 4大達成モデル（王道・高ステ・スコア・スター）、Round 2 必要スコア逆算表、段階別チェックポイント |
| [02_produce_abilities_and_memories.md](file:///root/gakumas-workspace/shared/gakumas-dev/knowledge/hif/02_produce_abilities_and_memories.md) | **アビリティ & メモリー選定** | out-game DSL Ver 1.2 仕様、除外（`card_exclude`）・追加行動（`extra_card_play`）、持ち込み戦略 |
| [03_plan_strategies.md](file:///root/gakumas-workspace/shared/gakumas-dev/knowledge/hif/03_plan_strategies.md) | **プラン別攻略・デッキ戦術** | センス（好調/集中）、ロジック（好印象/やる気）、アノマリー（強気/温存/全力）の立ち回り・キーカード |
| [04_schedule_and_resource_management.md](file:///root/gakumas-workspace/shared/gakumas-dev/knowledge/hif/04_schedule_and_resource_management.md) | **スケジュール & リソース管理** | SPレッスン・授業・相談の優先度、Pドリンク温存、Pポイント（コイン）運用、体力管理 |
| [05_asari_advice_framework.md](file:///root/gakumas-workspace/shared/gakumas-dev/knowledge/hif/05_asari_advice_framework.md) | **あさり先生 診断フレームワーク** | プロデューサーからの相談に対する逆算アルゴリズム、不足値の特定、あさり先生口調での回答テンプレート |

---

### 🎪 2. コンテスト改善 & メモリー育成ガイド
コンテスト（シーズン51等）におけるスコア最大化と、**「手持ちメモリー交換（アクション1）」＆「Webサーベイを活用した新規メモリー育成目標（アクション2）」** の完全ガイドです。

| ファイル | 概要・役割 | 主要トピック |
| :--- | :--- | :--- |
| [00_contest_mechanics_and_criteria.md](file:///root/gakumas-workspace/shared/gakumas-dev/knowledge/contest/00_contest_mechanics_and_criteria.md) | **審査基準 & Pアイドル適性分析** | ステージ審査基準（Vo/Da/Vi比率）、ステージ効果（DSL）、専用Pアイテムシナジー、適性判定理論、S51全3ステージ分析 |
| [01_action1_local_replacement_guide.md](file:///root/gakumas-workspace/shared/gakumas-dev/knowledge/contest/01_action1_local_replacement_guide.md) | **アクション1: 手持ちメモリー交換** | `advisor` シミュレーション差分スコア活用法、MongoDB所持メモリーからの差替候補特定、サブ20%実効パラメータ計算 |
| [02_action2_web_survey_and_breeding_guide.md](file:///root/gakumas-workspace/shared/gakumas-dev/knowledge/contest/02_action2_web_survey_and_breeding_guide.md) | **アクション2: Webサーベイ ✕ H.I.F. プロデュース** | 第三者分析・環境トップ編成の逆算、未所持の理想メモリー仕様特定、H.I.F. 育成レシピ化 |

---

## 🔄 連携と今後のロードマップ
- **フェーズ 1 (完了)**: `knowledge/hif/` への基礎・実践ナレッジの完全整備。
- **フェーズ 2 (完了)**: `knowledge/contest/` へのコンテスト改善ナレッジ整備 ＆ `gakumas-agent-bot` への Web サーベイ機能統合。
- **フェーズ 3**: MongoDB 所持メモリー・Pアイドルと連携した「完全自動プロデュースシミュレーション & 個別最適アドバイス」。
