/**
 * anomaly-beam-search.mjs
 * 
 * 自律型推奨デッキ導出 (Auto-Advisory) アノマリー編ビームサーチ検証
 * - ステージ: シーズン51 ステージ3 (アノマリー / 初星フラッグ（青）)
 * - 対象Pアイドル: 月村手毬 【一体いつから】(ID: 123)
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
const SEASON = 51;
const STAGE_NUM = 3;
const P_IDOL_ID = 123; // 月村手毬 【一体いつから】 (anomaly)
const P_ITEM_ID = 382; // 憧れのはじまり+

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
            console.log(`  -> MongoDB集計成功 (件数: ${r.count}件): Base = [Vo: ${base[0]}, Da: ${base[1]}, Vi: ${base[2]}, HP: ${base[3]}]`);
            return [
                base[0] + Math.floor(base[0] * 0.2),
                base[1] + Math.floor(base[1] * 0.2),
                base[2] + Math.floor(base[2] * 0.2),
                base[3]
            ];
        }
    } catch (e) {
        console.warn(`  -> MongoDB接続失敗。フォールバック値を使用します。`);
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
 * アノマリーカードプールの抽出
 */
function getAnomalyCandidatePool() {
    const allCards = SkillCards.getAll();
    const pool = allCards.filter(c =>
        (c.plan === "anomaly" || c.plan === "free") &&
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
    // SRおよびRを低レア枠（キャパシティ枠）として扱う
    const sr = uniquePool.filter(c => c.rarity === "SR" || c.rarity === "R");

    console.log(`\n[3/4] アノマリーカードプール準備完了: SSR ${ssr.length}枚, SR/R ${sr.length}枚 (ユニーク計 ${uniquePool.length}枚)`);
    return { ssr, sr, all: uniquePool };
}

/**
 * ビームサーチ本体
 */
async function runBeamSearch(stage, pIdolId, pItemId, params, pool) {
    console.log(`\n[4/4] アノマリービームサーチ探索の開始 (ビーム幅 B=${BEAM_WIDTH}, 各ステップ runs=${STEP_RUNS})...`);
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
                if ((c.rarity === "SR" || c.rarity === "R") && currentDeck.srCount >= 5) return false;
                return true;
            });

            for (const nextCard of availableCards) {
                const newCardList = [...currentDeck.cards, nextCard];
                const cardIds = newCardList.map(c => c.id);
                const res = await simulateDeck(stage, pIdolId, pItemId, params, cardIds, STEP_RUNS);

                const isSSR = nextCard.rarity === "SSR";
                candidateExpansions.push({
                    cards: newCardList,
                    ssrCount: currentDeck.ssrCount + (isSSR ? 1 : 0),
                    srCount: currentDeck.srCount + (!isSSR ? 1 : 0),
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
        const lastCard = beam[0].cards.slice(-1)[0];
        console.log(`     Step ${step}/10完了: Top中央値 = ${beam[0].score.toLocaleString()} pt (追加: [${lastCard.rarity}] ${lastCard.name})`);
    }

    const totalSearchTime = ((Date.now() - searchStartTime) / 1000).toFixed(1);
    console.log(`     -> ビーム探索完了 (${totalSearchTime}s)`);

    // 最終上位デッキの高精度シミュレーション (runs=1000)
    console.log(`\n上位 ${beam.length} デッキを runs=${FINAL_RUNS} で高精度検証中...`);
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
 * レポート出力
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
    console.log(" 自律型推奨デッキ導出 (Auto-Advisory) アノマリー編ビームサーチ検証");
    console.log(` 対象: シーズン${SEASON} ステージ${STAGE_NUM} (アノマリー), 月村手毬 【一体いつから】`);
    console.log("###############################################################");

    const stage = Stages.getAll().find(s => s.season === SEASON && s.stage === STAGE_NUM);
    if (!stage) {
        console.error("Error: ステージが見つかりません。");
        process.exit(1);
    }

    // 1. パラメータ取得
    const params = await getBaselineParams(P_IDOL_ID, [2700, 2000, 1500, 36]);
    console.log(`  -> 実効ステータス: [Vo: ${params[0]}, Da: ${params[1]}, Vi: ${params[2]}, HP: ${params[3]}]`);

    // 2. あじふらい氏推奨ベンチマーク測定
    const benchNames = [
        "本領発揮+", "対戦お願いします！+", "全身全霊+", "羽ばたけ！+", "頂点へ+",
        "モチベ+", "アッチェレランド+", "リスキーチャンス+", "プライド+", "セッティング+"
    ];
    const benchIds = benchNames.map(n => SkillCards.getAll().find(c => c.name === n)?.id).filter(Boolean);

    console.log("\n[2/4] あじふらい氏推奨ベンチマーク測定中 (runs=1000)...");
    const benchResult = await simulateDeck(stage, P_IDOL_ID, P_ITEM_ID, params, benchIds, FINAL_RUNS);
    const benchmark = { cardIds: benchIds, cardNames: benchNames, ...benchResult };
    console.log(`     ベンチマーク中央値: ${benchmark.med.toLocaleString()} pt`);

    // 3. アノマリーカードプール抽出
    const pool = getAnomalyCandidatePool();

    // 4. ビームサーチ実行
    const bestDeck = await runBeamSearch(stage, P_IDOL_ID, P_ITEM_ID, params, pool);

    // 5. レポート出力
    reportResult("シーズン51-3 (アノマリー) 月村手毬 【一体いつから】", benchmark, bestDeck);
}

main().catch(err => {
    console.error("Fatal error:", err);
    process.exit(1);
});

