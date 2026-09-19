/**
 * prototype-deck-search.mjs
 * 
 * 自律型推奨デッキ導出 (Auto-Advisory) Phase 1 プロトタイプ
 * - Phase 1-1: あじふらい氏推奨デッキのベンチマーク測定
 * - Phase 1-2 & 1-3: ゼロベース仮想メモリー探索 (2段階スクリーニング)
 */

import { MongoClient } from "mongodb";
import { Stages, PIdols, SkillCards, PItems } from "gakumas-data";
import { IdolConfig, StageConfig, IdolStageConfig, StageEngine, StagePlayer, STRATEGIES } from "gakumas-engine";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 設定
const SEASON = 51;
const STAGE_NUM = 1;
const P_IDOL_ID = 140; // 篠澤広 【ガラクタロード】(sense)
const MONGO_URI = process.env.MONGODB_URI || "mongodb://192.168.100.4:27017";

/**
 * 1. MongoDB から当該Pアイドルの実メモリー平均パラメータを取得
 */
async function getBaselineParams(pIdolId) {
    console.log(`[1/5] MongoDB から PIdolId: ${pIdolId} の平均パラメータを集計中...`);
    const fallbackParams = [2573, 1654, 1306, 37]; // フォールバック値

    let client = null;
    try {
        client = new MongoClient(MONGO_URI, { serverSelectionTimeoutMS: 3000 });
        await client.connect();
        const db = client.db("gakumas-tools");
        const memories = db.collection("memories");

        const result = await memories.aggregate([
            { $match: { pIdolId } },
            {
                $group: {
                    _id: "$pIdolId",
                    avgVo: { $avg: { $arrayElemAt: ["$params", 0] } },
                    avgDa: { $avg: { $arrayElemAt: ["$params", 1] } },
                    avgVi: { $avg: { $arrayElemAt: ["$params", 2] } },
                    avgHp: { $avg: { $arrayElemAt: ["$params", 3] } },
                    count: { $sum: 1 }
                }
            }
        ]).toArray();

        if (result && result.length > 0 && result[0].count > 0) {
            const r = result[0];
            const base = [
                Math.round(r.avgVo),
                Math.round(r.avgDa),
                Math.round(r.avgVi),
                Math.round(r.avgHp)
            ];
            console.log(`  -> 集計成功 (件数: ${r.count}件): Base = [Vo: ${base[0]}, Da: ${base[1]}, Vi: ${base[2]}, HP: ${base[3]}]`);
            // メイン100% ＋ サブ20%
            const combined = [
                base[0] + Math.floor(base[0] * 0.2),
                base[1] + Math.floor(base[1] * 0.2),
                base[2] + Math.floor(base[2] * 0.2),
                base[3]
            ];
            console.log(`  -> 合成実効ステータス (Main + Sub 20%): [Vo: ${combined[0]}, Da: ${combined[1]}, Vi: ${combined[2]}, HP: ${combined[3]}]`);
            return combined;
        }
    } catch (e) {
        console.warn(`  -> MongoDB接続/集計失敗 (${e.message})。フォールバック値を使用します。`);
    } finally {
        if (client) await client.close();
    }

    const combined = [
        fallbackParams[0] + Math.floor(fallbackParams[0] * 0.2),
        fallbackParams[1] + Math.floor(fallbackParams[1] * 0.2),
        fallbackParams[2] + Math.floor(fallbackParams[2] * 0.2),
        fallbackParams[3]
    ];
    console.log(`  -> フォールバック実効ステータス: [Vo: ${combined[0]}, Da: ${combined[1]}, Vi: ${combined[2]}, HP: ${combined[3]}]`);
    return combined;
}

/**
 * シミュレーション実行ヘルパー
 */
async function simulateDeck(stage, pIdolId, params, cardIds, runs = 100) {
    const loadout = {
        stageId: stage.id,
        supportBonus: 0.04,
        params,
        pItemIds: [443, 0, 0, 0], // 篠澤広固有アイテムのみ（追加Pアイテムなし）
        skillCardIdGroups: [
            cardIds.slice(0, 5),
            cardIds.slice(5, 10)
        ],
        customizationGroups: [
            [{}, {}, {}, {}, {}],
            [{}, {}, {}, {}, {}]
        ]
    };

    const idolConfig = new IdolConfig(loadout);
    const stageConfig = new StageConfig(stage);
    const config = new IdolStageConfig(idolConfig, stageConfig);

    let scores = [];
    for (let i = 0; i < runs; i++) {
        const engine = new StageEngine(config);
        const strategy = new STRATEGIES.HeuristicStrategy(engine);
        engine.strategy = strategy;
        const player = new StagePlayer(engine, strategy);
        const res = await player.play();
        scores.push(res.score);
    }

    scores.sort((a, b) => a - b);
    const avg = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
    const med = scores[Math.floor(scores.length / 2)];
    const min = scores[0];
    const max = scores[scores.length - 1];

    return { avg, med, min, max, scores };
}

/**
 * 2. Phase 1-1: あじふらい氏推奨デッキのベンチマーク測定
 */
async function runBenchmark(stage, pIdolId, params, runs = 1000) {
    console.log(`\n[2/5] Phase 1-1: あじふらい氏推奨デッキのベンチマーク測定 (runs=${runs})...`);

    // あじふらい氏の推奨共通デッキ（強化済み+版）
    // シュプレヒコール+(87), 一発勝負+(705), 大胆不敵+(709), 精神統一+(752), 静かな意志+(111)
    // 国民的アイドル+(163), ほぐれるひととき+(621), 脚光+(762), 天賦の才+(599), 魅惑のパフォーマンス+(147)
    const benchmarkCardIds = [87, 705, 709, 752, 111, 163, 621, 762, 599, 147];
    const benchmarkCardNames = benchmarkCardIds.map(id => SkillCards.getById(id)?.name);

    console.log(`  -> ベンチマーク構成 (10枚): ${benchmarkCardNames.join(", ")}`);
    const start = Date.now();
    const result = await simulateDeck(stage, pIdolId, params, benchmarkCardIds, runs);
    const duration = ((Date.now() - start) / 1000).toFixed(2);

    console.log(`  -> ベンチマーク完了 (${duration}s):`);
    console.log(`     中央値 (Median): ${result.med.toLocaleString()} pt`);
    console.log(`     平均値 (Average): ${result.avg.toLocaleString()} pt`);
    console.log(`     最小値 (Min)   : ${result.min.toLocaleString()} pt`);
    console.log(`     最大値 (Max)   : ${result.max.toLocaleString()} pt`);

    return { cardIds: benchmarkCardIds, cardNames: benchmarkCardNames, ...result };
}

/**
 * 3. Phase 1-2: ギミック連動型カードスクリーニング (Gimmick-Aware Candidate Screening)
 */
async function screenCandidates(stage, pIdolId, params) {
    console.log(`\n[3/5] Phase 1-2 (Step A): ステージギミックの自動解析とカードスクリーニング...`);

    // 1. ステージ効果（ギミック）の解析
    let requiresBuffCost = false;
    if (stage.effects) {
        for (const eff of stage.effects) {
            if (eff.phase === "buffCostConsumed") {
                requiresBuffCost = true;
                console.log(`  ★ ギミック検知: [強化状態コスト消費 (buffCostConsumed)] が要求されています (上限: ${eff.limit || "なし"}回)`);
            }
        }
    }

    const allCards = SkillCards.getAll();
    const rawCardsPath = path.join(__dirname, "lib/gakumas-data/json/skill_cards.json");
    const rawCards = JSON.parse(fs.readFileSync(rawCardsPath, "utf8"));
    const rawMap = new Map(rawCards.map(c => [c.id, c]));

    const ssrPool = allCards.filter(c =>
        (c.plan === "sense" || c.plan === "free") &&
        c.rarity === "SSR" &&
        c.sourceType === "produce" &&
        c.upgraded
    );
    const srPool = allCards.filter(c =>
        (c.plan === "sense" || c.plan === "free") &&
        c.rarity === "SR" &&
        c.sourceType === "produce" &&
        c.upgraded
    );

    console.log(`  -> 対象カードプール: SSR ${ssrPool.length}枚, SR ${srPool.length}枚`);

    // ギミック特性のスコアリング
    function scoreCardForGimmick(card) {
        const raw = rawMap.get(card.id);
        if (!raw) return 0;
        let score = 0;

        // トリガー役: 強化状態消費コスト
        if (requiresBuffCost && raw.cost) {
            if (raw.cost.includes("concentration-=") || raw.cost.includes("goodConditionTurns-=")) {
                score += 100; // ギミック発動カードは最重要！
            }
        }

        // 加速・リソース役: 手数追加 (cardUsesRemaining+=1)
        if (raw.actions && raw.actions.includes("cardUsesRemaining+=1")) {
            score += 60;
        }

        // バフ役: 集中・好調の大幅付与
        if (raw.actions) {
            if (raw.actions.includes("concentration+=") || raw.actions.includes("goodConditionTurns+=")) {
                score += 30;
            }
            if (raw.actions.includes("drawCard")) {
                score += 20;
            }
        }

        return score;
    }

    // SSRのギミック評価
    const scoredSSR = ssrPool.map(c => ({ card: c, gimmickScore: scoreCardForGimmick(c) }));
    scoredSSR.sort((a, b) => b.gimmickScore - a.gimmickScore);

    // SRのギミック評価
    const scoredSR = srPool.map(c => ({ card: c, gimmickScore: scoreCardForGimmick(c) }));
    scoredSR.sort((a, b) => b.gimmickScore - a.gimmickScore);

    // 上位プールをギミック適合度重視で抽出（SSR 7枚、SR 9枚）
    const topSSR = scoredSSR.slice(0, 7).map(s => s.card);
    const topSR = scoredSR.slice(0, 9).map(s => s.card);

    console.log(`  -> ギミック連動で抽出された 有力SSR Top 7:`);
    topSSR.forEach(c => {
        const raw = rawMap.get(c.id);
        console.log(`     - [SSR] ${c.name} (トリガー/加速スコア: ${scoredSSR.find(s => s.card.id === c.id).gimmickScore})`);
    });

    console.log(`  -> ギミック連動で抽出された 有力SR Top 9:`);
    topSR.forEach(c => {
        const raw = rawMap.get(c.id);
        console.log(`     - [SR] ${c.name} (トリガー/加速スコア: ${scoredSR.find(s => s.card.id === c.id).gimmickScore})`);
    });

    return { topSSR, topSR };
}

/**
 * 組合せ生成ヘルパー (n_C_k)
 */
function combinations(arr, k) {
    if (k === 0) return [[]];
    if (arr.length === 0) return [];
    const head = arr[0];
    const tail = arr.slice(1);
    const withHead = combinations(tail, k - 1).map(c => [head, ...c]);
    const withoutHead = combinations(tail, k);
    return [...withHead, ...withoutHead];
}

/**
 * 4. Phase 1-3: 2段階スクリーニングによる最良デッキ探索
 */
async function runTwoPhaseSearch(stage, pIdolId, params, topSSR, topSR) {
    console.log(`\n[4/5] Phase 1-3: 2段階スクリーニング探索の開始...`);

    // SSR 7枚から5枚を選ぶ (${}_7C_5 = 21)
    const ssrCombos = combinations(topSSR.map(c => c.id), 5);
    // SR 9枚から5枚を選ぶ (${}_9C_5 = 126)
    const srCombos = combinations(topSR.map(c => c.id), 5);

    const allCandidates = [];
    for (const ssr of ssrCombos) {
        for (const sr of srCombos) {
            allCandidates.push([...ssr, ...sr]);
        }
    }

    console.log(`  -> 第1段階 (粗選考): 総候補数 ${allCandidates.length.toLocaleString()} 組を runs=30 でスクリーニング中...`);
    const startPhase1 = Date.now();

    const stage1Results = [];
    let progress = 0;
    for (const cand of allCandidates) {
        progress++;
        if (progress % 500 === 0) {
            process.stdout.write(`\r     進捗: ${progress} / ${allCandidates.length} (${Math.round(progress / allCandidates.length * 100)}%)`);
        }
        const res = await simulateDeck(stage, pIdolId, params, cand, 30);
        stage1Results.push({ cardIds: cand, med: res.med, avg: res.avg });
    }
    console.log(`\r     進捗: ${allCandidates.length} / ${allCandidates.length} (100%) - 完了 (${((Date.now() - startPhase1) / 1000).toFixed(1)}s)`);

    // 上位20組を抽出
    stage1Results.sort((a, b) => b.med - a.med);
    const top20 = stage1Results.slice(0, 20);

    console.log(`\n  -> 第2段階 (本選考): 上位20組を runs=1000 で高精度検証中...`);
    const startPhase2 = Date.now();
    const stage2Results = [];

    for (let i = 0; i < top20.length; i++) {
        const cand = top20[i].cardIds;
        const res = await simulateDeck(stage, pIdolId, params, cand, 1000);
        const cardNames = cand.map(id => SkillCards.getById(id)?.name);
        stage2Results.push({ cardIds: cand, cardNames, ...res });
    }
    console.log(`     高精度検証完了 (${((Date.now() - startPhase2) / 1000).toFixed(1)}s)`);

    stage2Results.sort((a, b) => b.med - a.med);
    return stage2Results[0]; // 最良デッキ
}

/**
 * 5. 結果レポートとあじふらい氏デッキとの比較
 */
function reportComparison(benchmark, bestDeck) {
    console.log(`\n===============================================================`);
    console.log(` [5/5] Phase 1 総合検証レポート: あじふらい氏推奨 vs AI自発導出`);
    console.log(`===============================================================`);

    console.log(`\n【スコア比較】`);
    console.log(` 指標           | あじふらい氏推奨デッキ  | AI自発導出デッキ       | 差分`);
    console.log(`----------------+-------------------------+------------------------+-----------`);
    
    const diffMed = bestDeck.med - benchmark.med;
    const diffAvg = bestDeck.avg - benchmark.avg;
    const diffMax = bestDeck.max - benchmark.max;
    const diffMin = bestDeck.min - benchmark.min;

    const fmtDiff = (d) => (d >= 0 ? `+${d.toLocaleString()}` : d.toLocaleString());

    console.log(` 中央値 (Median)| ${benchmark.med.toLocaleString().padStart(20)} pt | ${bestDeck.med.toLocaleString().padStart(19)} pt | ${fmtDiff(diffMed)} pt`);
    console.log(` 平均値 (Average)| ${benchmark.avg.toLocaleString().padStart(20)} pt | ${bestDeck.avg.toLocaleString().padStart(19)} pt | ${fmtDiff(diffAvg)} pt`);
    console.log(` 最大値 (Max)   | ${benchmark.max.toLocaleString().padStart(20)} pt | ${bestDeck.max.toLocaleString().padStart(19)} pt | ${fmtDiff(diffMax)} pt`);
    console.log(` 最小値 (Min)   | ${benchmark.min.toLocaleString().padStart(20)} pt | ${bestDeck.min.toLocaleString().padStart(19)} pt | ${fmtDiff(diffMin)} pt`);

    console.log(`\n【採用スキルカードの比較】`);
    const benchSet = new Set(benchmark.cardNames);
    const bestSet = new Set(bestDeck.cardNames);

    const commonCards = [...benchSet].filter(c => bestSet.has(c));
    const onlyBench = [...benchSet].filter(c => !bestSet.has(c));
    const onlyAI = [...bestSet].filter(c => !bestSet.has(c));

    console.log(`  ★ 一致したカード (${commonCards.length} / 10枚, 一致率: ${commonCards.length * 10}%):`);
    commonCards.forEach(c => console.log(`     - [共通] ${c}`));

    console.log(`\n  ▲ あじふらい氏のみ採用 (${onlyBench.length}枚):`);
    onlyBench.forEach(c => console.log(`     - ${c}`));

    console.log(`\n  ▲ AI自発導出のみ採用 (${onlyAI.length}枚):`);
    onlyAI.forEach(c => console.log(`     - ${c}`));

    console.log(`\n===============================================================\n`);
}

/**
 * メイン実行
 */
async function main() {
    console.log("===============================================================");
    console.log(` 自律型推奨デッキ導出 (Auto-Advisory) プロトタイプ実行`);
    console.log(` 対象: シーズン${SEASON} ステージ${STAGE_NUM} (センス), 篠澤広 【ガラクタロード】`);
    console.log("===============================================================");

    // ステージ情報取得
    const stage = Stages.getAll().find(s => s.type === "contest" && s.season === SEASON && s.stage === STAGE_NUM);
    if (!stage) {
        console.error(`Error: シーズン${SEASON} ステージ${STAGE_NUM} が見つかりません。`);
        process.exit(1);
    }

    // 1. パラメータ導出
    const params = await getBaselineParams(P_IDOL_ID);

    // 2. ベンチマーク測定 (Phase 1-1)
    const benchmark = await runBenchmark(stage, P_IDOL_ID, params, 1000);

    // 3. 有力候補スクリーニング (Phase 1-2)
    const { topSSR, topSR } = await screenCandidates(stage, P_IDOL_ID, params);

    // 4. 2段階スクリーニング探索 (Phase 1-3)
    const bestDeck = await runTwoPhaseSearch(stage, P_IDOL_ID, params, topSSR, topSR);

    // 5. レポート出力
    reportComparison(benchmark, bestDeck);
}

main().catch(err => {
    console.error("Fatal error:", err);
    process.exit(1);
});

