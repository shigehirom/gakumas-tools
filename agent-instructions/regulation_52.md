Term:
    begin: 2026/09/12
    end: 2026/09/27

# Stage:1
criteria: (Vo, Da, Vi) = (45, 20, 35)
plan: sense
turn: 12
buf/debuf: none
p_item:
    name: 初星オブジェ（銀）
    effect:
        スキルカードコストで強化状態を消費したとき、
        - ランダムな山札か捨札のアクティブスキルカードを手札に移動
        - スキルカード使用数追加+1
        - （試験・ステージ内5回）

# Stage:2
criteria: (Vo, Da, Vi) = (35, 20, 45)
plan: logic
turn: 12
buf/debuf: 6ターン目、好印象1.5倍
p_item:
    name: 初星ライト（オレンジ）
    effect:
        残り3ターン以内のターン終了時、
        - 好印象の100%分スコア上昇

# Stage:3
criteria: (Vo, Da, Vi) = (45, 35, 20)
plan: anomaly
turn: 12
buf/debuf: none
p_item:
    name: 初星フラッグ（紫）
    effect:
        アイドル固有スキルカード使用時、全力の場合、
        - 全力値+9
        - アクティブスキルカードのスコア値増加+25
        - (試験・ステージ内1回)
