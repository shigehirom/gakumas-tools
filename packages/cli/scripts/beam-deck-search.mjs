/**
 * beam-deck-search.mjs
 * 
 * 自律型推奨デッキ導出 (Auto-Advisory) ビームサーチ最適化エンジン
 * - 目的: スキルカード10枚 (SSR 5枚 + SR 5枚) をシミュレータ主導のビームサーチで自動探索
 * - 対象: シーズン51 ステージ1 (センス), 篠澤広 【ガラクタロード】
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

const BEAM_WIDTH = 3;       // 保持する有望デッキ数
const STEP_RUNS = 25;       // 各ステップでのシミュレーション試行回数
const FINAL_RUNS = 1000;    // 最終検証の試行回数

/**
 * 1. MongoDB から当該Pアイドルの実メモリー平均パラメータを取得
 */
async function getBaselineParams(pIdolId) {
    console.log(`[1/4] MongoDB から PIdolId: ${pIdolId} の平均パラメータを集計中...`);
    const fallbackParams = [2573, 1654, 1306, 37];

    let client = null;
    try {
        client = new MongoClient(MONGO_URI, { serverSelectionTimeoutMS: 2000 });
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
            const combined = [
                base[0] + Math.floor(base[0] * 0.2),
                base[1] + Math.floor(base[1] * 0.2),
                base[2] + Math.floor(base[2] * 0.2),
                base[3]
            ];
            console.log(`  -> 集計成功 (件数: ${r.count}件): 合成実効 = [Vo: ${combined[0]}, Da: ${combined[1]}, Vi: ${combined[2]}, HP: ${combined[3]}]`);
            return combined;
        }
    } catch (e) {
        console.warn(`  -> MongoDB接続失敗。フォールバック値を使用します。`);
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
async function simulateDeck(stage, pIdolId, params, cardIds, runs = 50) {
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
            cardIds.slice(0, 5).map(() => ({})),
            cardIds.slice(5, 10).map(() => ({}))
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
 * 2. あじふらい氏推奨デッキのベンチマーク測定
 */
async function runBenchmark(stage, pIdolId, params, runs = 1000) {
    console.log(`\n[2/4] あじふらい氏推奨デッキのベンチマーク測定 (runs=${runs})...`);

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
 * 3. 候補カードプールの抽出 (プロデュース産 + サポートカード由来)
 */
function getCandidatePool() {
    const allCards = SkillCards.getAll();
    const pool = allCards.filter(c =>
        (c.plan === "sense" || c.plan === "free") &&
        (c.rarity === "SSR" || c.rarity === "SR") &&
        ["produce", "support"].includes(c.sourceType) &&
        c.upgraded
    );

    // 重複する同名カードを整理（IDユニーク）
    const uniquePool = [];
    const seenNames = new Set();
    for (const c of pool) {
        if (!seenNames.has(c.name)) {
            seenNames.add(c.name);
            uniquePool.push(c);
        }
    }

    const ssr = uniquePool.filter(c => c.rarity === "SSR");
    const sr = uniquePool.filter(c => c.rarity === "SR");

    console.log(`\n[3/4] 探索対象カードプールの準備完了: SSR ${ssr.length}枚, SR ${sr.length}枚 (ユニーク計 ${uniquePool.length}枚)`);
    return { ssr, sr, all: uniquePool };
}

/**
 * 4. ビームサーチ（Beam Search）による10枚デッキの逐次構築
 */
async function runBeamSearch(stage, pIdolId, params, pool) {
    console.log(`\n[4/4] ビームサーチ（逐次追加探索）の開始 (ビーム幅 B=${BEAM_WIDTH}, 各ステップ runs=${STEP_RUNS})...`);

    // 初期状態: 空デッキ（スコア0）
    let beam = [
        {
            cards: [],
            ssrCount: 0,
            srCount: 0,
            score: 0
        }
    ];

    const totalSteps = 10;
    const searchStartTime = Date.now();

    for (let step = 1; step <= totalSteps; step++) {
        console.log(`\n--- 【Step ${step} / ${totalSteps}】カード ${step}枚目の選定中 ---`);
        const stepStartTime = Date.now();

        const candidateExpansions = [];

        for (const currentDeck of beam) {
            const currentCardIds = new Set(currentDeck.cards.map(c => c.id));

            // 追加可能なカードをフィルタリング
            const availableCards = pool.all.filter(c => {
                // 重複カード除外
                if (currentCardIds.has(c.id)) return false;
                // SSR枠制限 (最大5枚)
                if (c.rarity === "SSR" && currentDeck.ssrCount >= 5) return false;
                // SR枠制限 (最大5枚)
                if (c.rarity === "SR" && currentDeck.srCount >= 5) return false;
                return true;
            });

            // 各候補カードを追加してシミュレーション評価
            for (const nextCard of availableCards) {
                const newCardList = [...currentDeck.cards, nextCard];
                const cardIds = newCardList.map(c => c.id);

                const res = await simulateDeck(stage, pIdolId, params, cardIds, STEP_RUNS);

                candidateExpansions.push({
                    cards: newCardList,
                    ssrCount: currentDeck.ssrCount + (nextCard.rarity === "SSR" ? 1 : 0),
                    srCount: currentDeck.srCount + (nextCard.rarity === "SR" ? 1 : 0),
                    score: res.med,
                    avg: res.avg
                });
            }
        }

        // スコア（中央値）降順でソートし、上位 B 個を次のステップのビームとする
        candidateExpansions.sort((a, b) => b.score - a.score);

        // 重複する同一構成を除外して上位 B 件を保持
        const nextBeam = [];
        const seenDeckKeys = new Set();
        for (const cand of candidateExpansions) {
            const key = cand.cards.map(c => c.id).sort().join(",");
            if (!seenDeckKeys.has(key)) {
                seenDeckKeys.add(key);
                nextBeam.push(cand);
                if (nextBeam.length >= BEAM_WIDTH) break;
            }
        }

        beam = nextBeam;

        const stepDuration = ((Date.now() - stepStartTime) / 1000).toFixed(1);
        console.log(`  -> Step ${step} 完了 (${stepDuration}s): 保持デッキ Top ${beam.length}`);
        beam.forEach((d, idx) => {
            const cardNames = d.cards.map(c => c.name).join(" + ");
            console.log(`     [#${idx + 1}] スコア(中央値): ${d.score.toLocaleString()} pt (SSR ${d.ssrCount}/SR ${d.srCount}) -> ${cardNames}`);
        });
    }

    const totalSearchTime = ((Date.now() - searchStartTime) / 1000).toFixed(1);
    console.log(`\n===============================================================`);
    console.log(` ビームサーチ完了 (総探索時間: ${totalSearchTime}s)`);
    console.log(`===============================================================`);

    // 最終上位デッキの高精度シミュレーション (runs=1000)
    console.log(`\n最終上位 ${beam.length} デッキを runs=${FINAL_RUNS} で高精度検証中...`);
    const finalResults = [];

    for (let i = 0; i < beam.length; i++) {
        const d = beam[i];
        const cardIds = d.cards.map(c => c.id);
        const cardNames = d.cards.map(c => c.name);
        const res = await simulateDeck(stage, pIdolId, params, cardIds, FINAL_RUNS);
        finalResults.push({ cardIds, cardNames, ...res });
    }

    finalResults.sort((a, b) => b.med - a.med);
    return finalResults[0]; // 最高のデッキ
}

/**
 * 5. 結果レポート
 */
function reportComparison(benchmark, bestDeck) {
    console.log(`\n===============================================================`);
    console.log(` 【最終総合検証レポート】 あじふらい氏推奨 vs ビームサーチ自発導出`);
    console.log(`===============================================================`);

    console.log(`\n【スコア比較】`);
    console.log(` 指標           | あじふらい氏推奨デッキ  | ビームサーチ自発導出   | 差分`);
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
    console.log(`  ■ あじふらい氏推奨構成 (10枚): ${benchmark.cardNames.join(", ")}`);
    console.log(`  ■ ビームサーチ導出構成 (10枚): ${bestDeck.cardNames.join(", ")}`);

    const benchSet = new Set(benchmark.cardNames);
    const bestSet = new Set(bestDeck.cardNames);

    const commonCards = [...benchSet].filter(c => bestSet.has(c));
    const onlyBench = [...benchSet].filter(c => !bestSet.has(c));
    const onlyAI = [...bestSet].filter(c => !bestSet.has(c));

    console.log(`\n  ★ 一致したカード (${commonCards.length} / 10枚, 一致率: ${commonCards.length * 10}%):`);
    commonCards.forEach(c => console.log(`     - [共通] ${c}`));

    console.log(`\n  ▲ あじふらい氏のみ採用 (${onlyBench.length}枚):`);
    onlyBench.forEach(c => console.log(`     - ${c}`));

    console.log(`\n  ▲ ビームサーチ自発導出のみ採用 (${onlyAI.length}枚):`);
    onlyAI.forEach(c => console.log(`     - ${c}`));

    console.log(`\n===============================================================\n`);
}

/**
 * メイン実行
 */
async function main() {
    console.log("===============================================================");
    console.log(` 自律型推奨デッキ導出 (Auto-Advisory) ビームサーチ実行`);
    console.log(` 対象: シーズン${SEASON} ステージ${STAGE_NUM} (センス), 篠澤広 【ガラクタロード】`);
    console.log("===============================================================");

    const stage = Stages.getAll().find(s => s.type === "contest" && s.season === SEASON && s.stage === STAGE_NUM);
    if (!stage) {
        console.error(`Error: シーズン${SEASON} ステージ${STAGE_NUM} が見つかりません。`);
        process.exit(1);
    }

    // 1. パラメータ取得
    const params = await getBaselineParams(P_IDOL_ID);

    // 2. ベンチマーク測定
    const benchmark = await runBenchmark(stage, P_IDOL_ID, params, FINAL_RUNS);

    // 3. カードプール抽出
    const pool = getCandidatePool();

    // 4. ビームサーチ探索
    const bestDeck = await runBeamSearch(stage, P_IDOL_ID, params, pool);

    // 5. 結果レポート出力
    reportComparison(benchmark, bestDeck);
}

main().catch(err => {
    console.error("Fatal error:", err);
    process.exit(1);
});

