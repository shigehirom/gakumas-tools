Term:
    begin: 2026/08/26
    end: 2026/09/10

# Stage:1
criteria: (Vo, Da, Vi) = (45, 35, 20)
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
criteria: (Vo, Da, Vi) = (20, 35, 45)
plan: logic
turn: 12
buf/debuf: 1ターン目、アイドル固有のスキルカードのコスト値減少-5・体力消費コスト値減少-5
p_item:
    name: 初星ライト（紫）
    effect:
        直接効果でやる気が5回増加時、
        - 元気+2
        - やる気の350%分スコア上昇
        - (試験・ステージ内4回)

# Stage:3
criteria: (Vo, Da, Vi) = (45, 35, 20)
plan: anomaly
turn: 12
buf/debuf: none
p_item:
    name: 初星フラッグ（青）
    effect:
        ターン開始時、強気2段段階の場合、
        - ランダムな山札か捨札の強気効果のスキルカードを手札に移動
        - 強気効果のスキルカードのスコア値上昇+20
        - (試験・ステージ内2回)
