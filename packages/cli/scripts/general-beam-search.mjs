/**
 * general-beam-search.mjs
 * 
 * 自律型推奨デッキ導出 (Auto-Advisory) 汎用ビームサーチ検証
 * 1. ケース1: シーズン51 ステージ1 (センス) - 藤田ことね 【自己肯定感爆上げ↑↑しゅきしゅきソング】(ID: 106)
 * 2. ケース2: シーズン51 ステージ2 (ロジック) - 月村手毬 【ガラクタロード】(ID: 138)
 */

import { MongoClient } from "mongodb";
import { Stages, PIdols, SkillCards, PItems } from "gakumas-data";
import { IdolConfig, StageConfig, IdolStageConfig, StageEngine, StagePlayer, STRATEGIES } from "gakumas-engine";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const MONGO_URI = process.env.MONGODB_URI || "mongodb://192.168.100.4:27017";
const BEAM_WIDTH = 3;
const STEP_RUNS = 25;
const FINAL_RUNS = 1000;

/**
 * MongoDBから平均パラメータを取得
 */
async function getBaselineParams(pIdolId, fallbackParams) {
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
            return [
                base[0] + Math.floor(base[0] * 0.2),
                base[1] + Math.floor(base[1] * 0.2),
                base[2] + Math.floor(base[2] * 0.2),
                base[3]
            ];
        }
    } catch (e) {
        // フォールバックへ
    } finally {
        if (client) await client.close();
    }

    return [
        fallbackParams[0] + Math.floor(fallbackParams[0] * 0.2),
        fallbackParams[1] + Math.floor(fallbackParams[1] * 0.2),
        fallbackParams[2] + Math.floor(fallbackParams[2] * 0.2),
        fallbackParams[3]
    ];
}

/**
 * シミュレーション実行ヘルパー
 */
async function simulateDeck(stage, pIdolId, pItemId, params, cardIds, runs = 50) {
    const loadout = {
        stageId: stage.id,
        supportBonus: 0.04,
        params,
        pItemIds: [pItemId, 0, 0, 0],
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
 * 対象プランに応じた候補カードプールの抽出
 */
function getCandidatePool(plan) {
    const allCards = SkillCards.getAll();
    const pool = allCards.filter(c =>
        (c.plan === plan || c.plan === "free") &&
        (c.rarity === "SSR" || c.rarity === "SR") &&
        ["produce", "support"].includes(c.sourceType) &&
        c.upgraded
    );

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
    return { ssr, sr, all: uniquePool };
}

/**
 * ビームサーチ本体
 */
async function runBeamSearch(stage, pIdolId, pItemId, params, pool) {
    let beam = [{ cards: [], ssrCount: 0, srCount: 0, score: 0 }];
    const totalSteps = 10;
    const searchStartTime = Date.now();

    for (let step = 1; step <= totalSteps; step++) {
        const candidateExpansions = [];

        for (const currentDeck of beam) {
            const currentCardIds = new Set(currentDeck.cards.map(c => c.id));
            const availableCards = pool.all.filter(c => {
                if (currentCardIds.has(c.id)) return false;
                if (c.rarity === "SSR" && currentDeck.ssrCount >= 5) return false;
                if (c.rarity === "SR" && currentDeck.srCount >= 5) return false;
                return true;
            });

            for (const nextCard of availableCards) {
                const newCardList = [...currentDeck.cards, nextCard];
                const cardIds = newCardList.map(c => c.id);
                const res = await simulateDeck(stage, pIdolId, pItemId, params, cardIds, STEP_RUNS);

                candidateExpansions.push({
                    cards: newCardList,
                    ssrCount: currentDeck.ssrCount + (nextCard.rarity === "SSR" ? 1 : 0),
                    srCount: currentDeck.srCount + (nextCard.rarity === "SR" ? 1 : 0),
                    score: res.med,
                    avg: res.avg
                });
            }
        }

        candidateExpansions.sort((a, b) => b.score - a.score);

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
        process.stdout.write(`     Step ${step}/10: Top中央値 = ${beam[0].score.toLocaleString()} pt (${beam[0].cards.map(c => c.name).slice(-1)[0]})\n`);
    }

    const totalSearchTime = ((Date.now() - searchStartTime) / 1000).toFixed(1);
    console.log(`     -> ビーム探索完了 (${totalSearchTime}s)`);

    // 最終上位デッキの高精度シミュレーション (runs=1000)
    const finalResults = [];
    for (let i = 0; i < beam.length; i++) {
        const d = beam[i];
        const cardIds = d.cards.map(c => c.id);
        const cardNames = d.cards.map(c => c.name);
        const res = await simulateDeck(stage, pIdolId, pItemId, params, cardIds, FINAL_RUNS);
        finalResults.push({ cardIds, cardNames, ...res });
    }
    finalResults.sort((a, b) => b.med - a.med);
    return finalResults[0];
}

/**
 * レポート出力ヘルパー
 */
function reportResult(title, benchmark, bestDeck) {
    console.log(`\n===============================================================`);
    console.log(` 【検証結果レポート】 ${title}`);
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

    console.log(`===============================================================\n`);
}

/**
 * メイン実行
 */
async function main() {
    console.log("###############################################################");
    console.log(" 自律型推奨デッキ導出 (Auto-Advisory) 汎用ビームサーチ検証開始");
    console.log("###############################################################");

    // ==========================================================
    // ケース 1: シーズン51 ステージ1 (センス) - 藤田ことね 【しゅきしゅきソング】
    // ==========================================================
    console.log("\n>>> [ケース 1] シーズン51 ステージ1 (センス) - 藤田ことね 【自己肯定感爆上げ↑↑しゅきしゅきソング】(ID: 106)");
    const stage1 = Stages.getAll().find(s => s.season === 51 && s.stage === 1);
    const pIdolId1 = 106;
    const pItemId1 = 320; // ことね【しゅきしゅきソング】固有Pアイテム+
    const params1 = await getBaselineParams(pIdolId1, [2600, 1700, 1400, 35]);

    // あじふらい氏 Stage 1 構成
    const bench1Names = [
        "シュプレヒコール+", "一発勝負+", "大胆不敵+", "精神統一+", "静かな意志+",
        "国民的アイドル+", "ほぐれるひととき+", "脚光+", "天賦の才+", "魅惑のパフォーマンス+"
    ];
    const bench1Ids = bench1Names.map(n => SkillCards.getAll().find(c => c.name === n)?.id).filter(Boolean);

    console.log("  -> あじふらい氏ベンチマーク測定中 (runs=1000)...");
    const bench1Result = await simulateDeck(stage1, pIdolId1, pItemId1, params1, bench1Ids, FINAL_RUNS);
    const benchmark1 = { cardIds: bench1Ids, cardNames: bench1Names, ...bench1Result };
    console.log(`     ベンチマーク中央値: ${benchmark1.med.toLocaleString()} pt`);

    console.log("  -> ビームサーチ自動探索中...");
    const pool1 = getCandidatePool("sense");
    const best1 = await runBeamSearch(stage1, pIdolId1, pItemId1, params1, pool1);
    reportResult("ケース 1: シーズン51-1 藤田ことね 【しゅきしゅきソング】", benchmark1, best1);

    // ==========================================================
    // ケース 2: シーズン51 ステージ2 (ロジック) - 月村手毬 【ガラクタロード】
    // ==========================================================
    console.log("\n>>> [ケース 2] シーズン51 ステージ2 (ロジック) - 月村手毬 【ガラクタロード】(ID: 138)");
    const stage2 = Stages.getAll().find(s => s.season === 51 && s.stage === 2);
    const pIdolId2 = 138;
    const pItemId2 = 423; // 手毬【ガラクタロード】固有Pアイテム+
    const params2 = await getBaselineParams(pIdolId2, [1500, 1900, 2700, 36]);

    // あじふらい氏 Stage 2 構成
    // ワクワクが止まらない+(129), 止められない想い+(607), 成長痛+(735), 気まぐれハート+(756), 私がスター+(157),
    // お手並み拝見+(613), デイドリーミング+(623), せのびの魔法+(719), 夢色リップ+(760), 届いて！+(723)
    const bench2Names = [
        "ワクワクが止まらない+", "止められない想い+", "成長痛+", "気まぐれハート+", "私がスター+",
        "お手並み拝見+", "デイドリーミング+", "せのびの魔法+", "夢色リップ+", "届いて！+"
    ];
    const bench2Ids = bench2Names.map(n => SkillCards.getAll().find(c => c.name === n)?.id).filter(Boolean);

    console.log("  -> あじふらい氏ベンチマーク測定中 (runs=1000)...");
    const bench2Result = await simulateDeck(stage2, pIdolId2, pItemId2, params2, bench2Ids, FINAL_RUNS);
    const benchmark2 = { cardIds: bench2Ids, cardNames: bench2Names, ...bench2Result };
    console.log(`     ベンチマーク中央値: ${benchmark2.med.toLocaleString()} pt`);

    console.log("  -> ビームサーチ自動探索中...");
    const pool2 = getCandidatePool("logic");
    const best2 = await runBeamSearch(stage2, pIdolId2, pItemId2, params2, pool2);
    reportResult("ケース 2: シーズン51-2 月村手毬 【ガラクタロード】(ロジック)", benchmark2, best2);

    console.log("###############################################################");
    console.log(" 全検証完了");
    console.log("###############################################################");
}

main().catch(err => {
    console.error("Fatal error:", err);
    process.exit(1);
});
