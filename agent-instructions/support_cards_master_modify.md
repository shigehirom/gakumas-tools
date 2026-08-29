# 依頼：support_cards_master.json のトリガーおよびパッシブ効果の厳格化（リファクタリング）

先に生成した `support_cards_master.json` について、Python側のout-gameシミュレーションロジックと結合するにあたり、トリガーの解釈をより厳密にする必要があります。以下の修正ルールをすべてのカードに一括適用して、JSONデータを再生成してください。

## 1. 修正ルール

1. **初期ステータス加算のみを `@init` とする**
   - プロデュース開始時に、アイドルのステータス（`vo`, `da`, `vi`, `hp_max`, `coin`）に直接数値がプラスされるものだけを `@init` トリガーとして残してください。
   - 例：`"dsl": "@init: vo+65"`、`"dsl": "@init: coin+40"`、`"dsl": "@init: hp_max+9"` 

2. **常時発動・確率アップ・倍率系はすべて `@passive` へ変更**
   - 初期値に直接加算されず、プロデュース中に常時発動するパッシブ効果、確率変動、およびイベント倍率上昇などは、すべてトリガーを `@passive` に変更してください。
   - 例：`@init: vo_bonus+8.5` ➔ `@passive: vo_bonus+8.5`
   - 例：`@init: vo_sp_lesson_rate+21` ➔ `@passive: vo_sp_lesson_rate+21`
   - 例：`@init: self_lesson_support_rate+100` ➔ `@passive: self_lesson_support_rate+100`
   - 例：`@init: self_event_param_bonus+100` ➔ `@passive: self_event_param_bonus+100`
   - 例：`@init: drink_discount` ➔ `@passive: drink_discount`

3. **特別指導のトリガー化**
   - 元テキストで「特別指導開始時」となっている効果（例：『謹厳実直』や『眠れる森の王子様』など）は、`@init` ではなく、新設する `@special_class_start` トリガーを正確に割り当ててください。
   - 例：`@init: da+13(limit=3)` ➔ `@special_class_start: da+13(limit=3)`

4. **サポートイベントのトリガーを `@event` に統一**
   - `support_events` 配下内の効果は、開始時ではなくプロデュース進行中に発生するため、トリガーを `@init` ではなくすべて `@event` に書き換えてください。
   - 例：`"dsl": "@init: vo+20"` ➔ `"dsl": "@event: vo+20"`
   - 例：`"dsl": "@init: pitem_get"` ➔ `"dsl": "@event: pitem_get"`

5. **レッスン終了トリガーの属性（type）付与**
   - 「ボーカルSPレッスン終了時」などの効果は、どのレッスンで発動するかを判別するため、`(type=vocal)` などの属性をトリガー側に付与してください。
   - 例：`@sp_lesson_end: vo+13` ➔ `@sp_lesson_end(type=vocal): vo+13`

## 2. 出力要求
上記の修正ルールを適用し、Pythonの計算エンジンが誤判定を起こさない堅牢なデータ構造になった `support_cards_master.json` の全容を出力してください。
コードを書き換える前に、どのような方針で置換・修正アプローチをとるかを `## 思考プロセス` セクションを設けて日本語でステップバイステップで説明してください。