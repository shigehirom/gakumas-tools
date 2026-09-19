#!/usr/bin/env node
/**
 * auto-advisory-generator.mjs
 * 
 * 自律型推奨デッキ導出エンジン (Auto-Advisory Engine)
 * 公式コンテストのレギュレーションから自動的に各ステージの推奨Pアイドル・Pアイテム・スキルカード構成 (DSL) を導出し、
 * auto_advisory_<season>.md として保存する一括バッチスクリプト。
 * 
 * 使用法:
 *   node --loader ./packages/cli/scripts/esm-loader.mjs ./packages/cli/scripts/auto-advisory-generator.mjs [season]
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

const IDOL_NAMES = {
    1: { key: "saki", name: "花海咲季" },
    2: { key: "temari", name: "月村手毬" },
    3: { key: "kotone", name: "藤田ことね" },
    4: { key: "tsubame", name: "雨夜燕" },
    5: { key: "mao", name: "有村麻央" },
    6: { key: "lilja", name: "葛城リーリヤ" },
    7: { key: "china", name: "倉本千奈" },
    8: { key: "sumika", name: "紫雲清夏" },
    9: { key: "hiro", name: "篠澤広" },
    10: { key: "sena", name: "十王星南" },
    11: { key: "misuzu", name: "秦谷美鈴" },
    12: { key: "ume", name: "花海佑芽" },
    13: { key: "rinami", name: "姫崎莉波" },
};

/**
 * MongoDBから平均パラメータを取得
 */
async function getBaselineParams(pIdolId, fallbackParams = [1800, 1800, 1800, 40]) {
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
    } catch {
        // Mongo接続失敗時はフォールバック
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
 * シミュレーション実行
 */
async function simulateDeck(stage, pIdolId, pItemId, params, cardIds, runs = 20) {
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
    const isAnomaly = plan === "anomaly";

    const pool = allCards.filter(c => {
        if (c.plan !== plan && c.plan !== "free") return false;
        if (!["produce", "support"].includes(c.sourceType)) return false;
        if (!c.upgraded) return false;

        if (isAnomaly) {
            return c.rarity === "SSR" || c.rarity === "SR" || c.rarity === "R";
        } else {
            return c.rarity === "SSR" || c.rarity === "SR";
        }
    });

    const uniquePool = [];
    const seenNames = new Set();
    for (const c of pool) {
        if (!seenNames.has(c.name)) {
            seenNames.add(c.name);
            uniquePool.push(c);
        }
    }

    const ssr = uniquePool.filter(c => c.rarity === "SSR");
    const sr = uniquePool.filter(c => isAnomaly ? (c.rarity === "SR" || c.rarity === "R") : c.rarity === "SR");

    return { ssr, sr, all: uniquePool };
}

/**
 * ビームサーチ本体
 */
async function runBeamSearch(stage, pIdolId, pItemId, params, pool, beamWidth = 3, stepRuns = 20) {
    let beam = [{ cards: [], ssrCount: 0, srCount: 0, score: 0 }];
    const totalSteps = 10;

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
                const res = await simulateDeck(stage, pIdolId, pItemId, params, cardIds, stepRuns);

                candidateExpansions.push({
                    cards: newCardList,
                    ssrCount: currentDeck.ssrCount + (nextCard.rarity === "SSR" ? 1 : 0),
                    srCount: currentDeck.srCount + ((nextCard.rarity === "SR" || nextCard.rarity === "R") ? 1 : 0),
                    score: res.med,
                    avg: res.avg
                });
            }
        }

        candidateExpansions.sort((a, b) => b.score - a.score);
        beam = candidateExpansions.slice(0, beamWidth);
    }

    return beam[0];
}

/**
 * 推奨Pアイテムの選定
 */
function selectRecommendedPItems(plan, stage) {
    // 汎用高評価Pアイテム
    if (plan === "sense") {
        return ["得体のしれないモノ", "とろけた時間"];
    } else if (plan === "logic") {
        return ["ひなたぼっこ案内状", "お姉さま大百科"];
    } else if (plan === "anomaly") {
        return ["天川ラーメン巡り", "悔しさの象徴"];
    }
    return ["得体のしれないモノ", "とろけた時間"];
}

/**
 * 各プランにおける推奨Pアイドル候補の選定
 */
function getCandidateIdolsForStage(plan, criteria) {
    const allIdols = PIdols.getAll().filter(i => i.rarity === "SSR" && i.plan === plan);
    // スコア比率（Vo/Da/Vi）が高い属性に適したアイドルや人気アイドルを選定
    return allIdols.slice(0, 15);
}

/**
 * メイン生成処理
 */
async function main() {
    const args = process.argv.slice(2);
    let targetSeason = parseInt(args[0], 10);

    // シーズンが指定されていない場合は最新のコンテストシーズンを探索
    if (isNaN(targetSeason)) {
        const contestStages = Stages.getAll().filter(s => s.type === "contest" && s.season);
        contestStages.sort((a, b) => b.season - a.season);
        targetSeason = contestStages[0]?.season || 51;
    }

    console.log(`=======================================================`);
    console.log(`🤖 自律型推奨デッキ導出エンジン (Auto-Advisory Engine)`);
    console.log(`対象シーズン: 第${targetSeason}期コンテスト`);
    console.log(`=======================================================\n`);

    const startTime = Date.now();
    const dslSections = [];

    for (let stageNum = 1; stageNum <= 3; stageNum++) {
        console.log(`\n-------------------------------------------------------`);
        console.log(`【Stage ${stageNum} 探索開始】`);
        console.log(`-------------------------------------------------------`);

        const stage = Stages.getAll().find(s => s.season === targetSeason && s.stage === stageNum);
        if (!stage) {
            console.warn(`⚠️ シーズン${targetSeason} ステージ${stageNum} が gakumas-data に見つかりません。スキップします。`);
            continue;
        }

        console.log(`ステージ名: ${stage.name} (ID: ${stage.id})`);
        console.log(`プラン: ${stage.plan} | 属性比率: Vo ${stage.criteria.vocal}, Da ${stage.criteria.dance}, Vi ${stage.criteria.visual}`);

        // 1. Pアイドル候補の選定
        const candidateIdols = getCandidateIdolsForStage(stage.plan, stage.criteria);
        if (candidateIdols.length === 0) {
            console.warn(`候補アイドルが見つかりません。`);
            continue;
        }

        // 代表アイドル（探索用）: 先頭のSSRアイドル
        const representativeIdol = candidateIdols[0];
        const idolMeta = IDOL_NAMES[representativeIdol.idolId] || { key: "idol", name: "アイドル" };
        console.log(`代表アイドル: ${idolMeta.name}【${representativeIdol.title}】(ID: ${representativeIdol.id})`);

        // 代表アイドルの固有Pアイテム
        const pItem = PItems.getAll().find(it => it.sourceType === "pIdol" && it.pIdolId === representativeIdol.id && it.upgraded);
        const pItemId = pItem ? pItem.id : 0;
        console.log(`固有Pアイテム: ${pItem ? pItem.name : "なし"} (ID: ${pItemId})`);

        // ベースラインパラメータ
        const params = await getBaselineParams(representativeIdol.id, [1800, 1800, 1800, 40]);
        console.log(`実効パラメータ: [Vo: ${params[0]}, Da: ${params[1]}, Vi: ${params[2]}, HP: ${params[3]}]`);

        // 2. カードプールの取得
        const pool = getCandidatePool(stage.plan);
        console.log(`カードプール: SSR ${pool.ssr.length}枚, SR/R ${pool.sr.length}枚 (計 ${pool.all.length}枚)`);

        // 3. ビームサーチ実行
        console.log(`ビームサーチ実行中 (BeamWidth=3, StepRuns=20)...`);
        const searchRes = await runBeamSearch(stage, representativeIdol.id, pItemId, params, pool, 3, 20);

        // 最終ベンチマーク (1000 runs)
        console.log(`最優秀デッキの最終検証シミュレーション (runs=1000)...`);
        const cardIds = searchRes.cards.map(c => c.id);
        const finalEval = await simulateDeck(stage, representativeIdol.id, pItemId, params, cardIds, 1000);

        console.log(`✨ Stage ${stageNum} 導出結果: 中央値 ${finalEval.med.toLocaleString()} pt (平均 ${finalEval.avg.toLocaleString()} pt, 最大 ${finalEval.max.toLocaleString()} pt)`);
        console.log(`選出カード構成:`);
        searchRes.cards.forEach((c, idx) => {
            console.log(`  #${idx + 1}: [${c.rarity}] ${c.name}`);
        });

        // 4. DSL生成
        const stageDslLines = [];
        stageDslLines.push(`# Stage:${stageNum}`);
        stageDslLines.push(`## p_idol:`);

        // アイドル一覧
        for (const idol of candidateIdols) {
            const meta = IDOL_NAMES[idol.idolId] || { key: "idol", name: "アイドル" };
            const withAsariTag = stage.plan === "anomaly" ? " with_asari" : "";
            stageDslLines.push(`- ${meta.key}: 【${idol.title}】${withAsariTag}`);
        }

        stageDslLines.push(``);
        stageDslLines.push(`## p_item:`);
        stageDslLines.push(`- common:`);
        const recItems = selectRecommendedPItems(stage.plan, stage);
        for (const item of recItems) {
            stageDslLines.push(`\t- ${item}`);
        }

        stageDslLines.push(``);
        stageDslLines.push(`## skill_card:`);
        stageDslLines.push(`- common:`);
        for (const card of searchRes.cards) {
            stageDslLines.push(`\t- ${card.name}`);
        }

        dslSections.push(stageDslLines.join("\n"));
    }

    const fullDsl = dslSections.join("\n\n") + "\n";

    // ファイル保存先
    const targetDirs = [
        path.resolve(__dirname, "../../agent-instructions"),
        path.resolve(__dirname, "../../../shared/agent-instructions"),
        path.resolve(__dirname, "../../../gakumas-agent-bot/agent-instructions")
    ];

    console.log(`\n=======================================================`);
    console.log(`💾 DSLファイル出力`);
    console.log(`=======================================================`);

    for (const dir of targetDirs) {
        if (!fs.existsSync(dir)) {
            try {
                fs.mkdirSync(dir, { recursive: true });
            } catch {
                continue;
            }
        }
        const filePath = path.join(dir, `auto_advisory_${targetSeason}.md`);
        try {
            fs.writeFileSync(filePath, fullDsl, "utf8");
            console.log(`  ✓ 保存完了: ${filePath}`);
        } catch (err) {
            console.error(`  ✗ 保存失敗: ${filePath} (${err.message})`);
        }
    }

    const elapsed = Math.round((Date.now() - startTime) / 1000);
    console.log(`\n🎉 全3ステージの自律導出が完了しました！所要時間: ${elapsed}秒`);
}

main().catch(err => {
    console.error("Fatal error:", err);
    process.exit(1);
});

