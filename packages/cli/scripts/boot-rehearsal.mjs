import { MongoClient } from "mongodb";
import { Stages, PIdols, SkillCards, Idols, PItems, Customizations } from "gakumas-data";
import { Worker } from "worker_threads";
import path from "path";
import { fileURLToPath } from "url";
import os from "os";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const MONGODB_URI = process.argv[2];
const runsArg = parseInt(process.argv[3], 10) || 100;
const isDebug = process.argv.includes('--debug');
const deckNames = process.argv.slice(4).filter(n => n && !n.startsWith('--'));

if (!MONGODB_URI) {
    console.error("MongoDB URI is missing.");
    process.exit(1);
}

const client = new MongoClient(MONGODB_URI);
let loadouts = [];
let targetStageId = null;

async function run() {
    try {
        await client.connect();
        const db = client.db(process.env.MONGODB_DB || "gakumas-tools");

        for (const name of deckNames) {
            const loadout = await db.collection("loadouts").findOne({ name });
            if (!loadout) {
                console.error(`Deck "${name}" not found.`);
                process.exit(1);
            }

            // Check missing datamined items (PItems and SkillCards) to prompt user to pull latest source
            for (const pItemId of (loadout.pItemIds || [])) {
                if (pItemId > 0 && !PItems.getById(pItemId)) {
                    console.error(`\n[エラー] デッキ「${name}」内に未知のPアイテムID(${pItemId})が含まれています。GitHubの最新データをPull（更新）してください。`);
                    process.exit(1);
                }
            }
            if (loadout.skillCardIdGroups) {
                for (const group of loadout.skillCardIdGroups) {
                    for (const cardId of (group || [])) {
                        if (cardId > 0 && !SkillCards.getById(cardId)) {
                            console.error(`\n[エラー] デッキ「${name}」内に未知のスキルカードID(${cardId})が含まれています。GitHubの最新データをPull（更新）してください。`);
                            process.exit(1);
                        }
                    }
                }
            }

            // Verify Stage Match
            if (loadout.stageId) {
                if (targetStageId === null) {
                    targetStageId = loadout.stageId;
                } else if (targetStageId !== loadout.stageId) {
                    console.error(`\n[エラー] 指定されたデッキ間でステージ(シーズン)情報が一致しませんでした。同一シーズンのデッキ群を指定してください。`);
                    process.exit(1);
                }
            }

            // Resolve Idol Name
            let idolName = "不明";
            if (loadout.skillCardIdGroups) {
                for (const group of loadout.skillCardIdGroups) {
                    if (group && group[0] > 0) {
                        const card = SkillCards.getById(group[0]);
                        if (card && card.pIdolId) {
                            const pIdol = PIdols.getById(card.pIdolId);
                            if (pIdol) {
                                const idol = Idols.getById(pIdol.idolId);
                                if (idol) {
                                    idolName = idol.name;
                                    break;
                                }
                            }
                        }
                    }
                }
            }

            const pItemsList = (loadout.pItemIds || []).filter(id => id > 0).map(id => {
                const item = PItems.getById(id);
                if (!item) return `Unknown(${id})`;
                return `【${item.rarity}】 ${item.name}`;
            });
            const getCardGroup = (index) => {
                const cardIds = loadout.skillCardIdGroups?.[index] || [];
                const custs = loadout.customizationGroups?.[index] || [];

                return cardIds.map((id, i) => ({ id, i })).filter(item => item.id > 0).map((item) => {
                    const id = item.id;
                    const card = SkillCards.getById(id);
                    if (!card) return `Unknown(${id})`;
                    
                    const prefix = `【${card.rarity}】 `;
                    const name = card.name;
                    const customObj = custs?.[item.i];
                    if (customObj && Object.keys(customObj).length > 0) {
                        const customNames = Object.keys(customObj).map(cId => {
                            const custom = Customizations.getById(cId);
                            return custom ? custom.name : `C(${cId})`;
                        }).join(", ");
                        return `${prefix}${name} (${customNames})`;
                    }
                    return `${prefix}${name}`;
                });
            };

            let mainTitle = "Unknown";
            let subTitle = "Unknown";
            if (loadout.skillCardIdGroups) {
                if (loadout.skillCardIdGroups[0]?.[0] > 0) {
                    const card = SkillCards.getById(loadout.skillCardIdGroups[0][0]);
                    if (card && card.pIdolId) {
                        const pIdol = PIdols.getById(card.pIdolId);
                        if (pIdol) mainTitle = pIdol.title;
                    }
                }
                if (loadout.skillCardIdGroups[1]?.[0] > 0) {
                    const card = SkillCards.getById(loadout.skillCardIdGroups[1][0]);
                    if (card && card.pIdolId) {
                        const pIdol = PIdols.getById(card.pIdolId);
                        if (pIdol) subTitle = pIdol.title;
                    }
                }
            }

            loadouts.push({
                ...loadout,
                id: name,
                idolName: idolName,
                deckDetails: {
                    mainTitle,
                    subTitle,
                    params: loadout.params || [0, 0, 0, 0],
                    pItems: pItemsList,
                    memory1: getCardGroup(0),
                    memory2: getCardGroup(1),
                    memory1Name: loadout.memory1Name || "Unknown (Rerunning optimize command will fix this)",
                    memory2Name: loadout.memory2Name || "Unknown (Rerunning optimize command will fix this)",
                }
            });
        }
    } finally {
        await client.close();
    }

    if (loadouts.length === 0) {
        console.error("No valid decks provided.");
        process.exit(1);
    }

    if (targetStageId === null) {
        console.error(`\n[エラー] デッキ内にステージID情報が保存されていませんでした。`);
        process.exit(1);
    }

    const stages = Stages.getAll();
    const contestStage = stages.find((s) => s.id === targetStageId);
    if (!contestStage) {
        console.error(`\n[エラー] ステージID (${targetStageId}) に該当するステージが見つかりません。最新データを更新してください。`);
        process.exit(1);
    }
    const seasonStr = contestStage.season.toString();
    const stageStr = contestStage.stage.toString();

    // Parallel execution setup
    const cpuCount = os.cpus().length;
    const workerCount = Math.max(1, cpuCount);
    const runsPerWorker = Math.floor(runsArg / workerCount);
    const extraRuns = runsArg % workerCount;

    const workerResults = [];
    let completedWorkers = 0;
    let totalCompletedRuns = 0;

    const createWorker = (numRuns, isLast) => {
        return new Promise((resolve, reject) => {
            const worker = new Worker(path.join(__dirname, 'simulate-loadout-worker.mjs'), {
                workerData: {
                    contestStage,
                    numRuns,
                    debug: isDebug
                }
            });

            worker.on('message', (msg) => {
                if (msg.type === 'progress') {
                    totalCompletedRuns += msg.count || 10;
                    if (isLast) {
                        const totalRuns = runsArg * loadouts.length;
                        process.stderr.write(`\r- 予測シミュレーション実行中: ${Math.min(100, Math.round((totalCompletedRuns / totalRuns) * 100))}%    `);
                    }
                } else if (msg.type === 'done') {
                    workerResults.push(msg.results);
                    resolve();
                }
            });

            worker.on('error', reject);
            worker.on('exit', (code) => {
                if (code !== 0) reject(new Error(`Worker stopped with exit code ${code}`));
            });

            worker.postMessage({ id: 'rehearsal', loadouts });
        });
    };

    const workerPromises = [];
    for (let i = 0; i < workerCount; i++) {
        const workerRuns = runsPerWorker + (i === 0 ? extraRuns : 0);
        if (workerRuns > 0) {
            workerPromises.push(createWorker(workerRuns, i === 0));
        }
    }

    try {
        await Promise.all(workerPromises);
        process.stderr.write(`\r- 予測シミュレーション完了!                                  \n`);

        // Aggregate results from all workers
        const aggregatedIdols = loadouts.map((loadout, lIdx) => {
            const loadoutResults = workerResults.map(res => res.find(r => r.id === loadout.id));

            // Combine scores
            let totalAvg = 0;
            let totalWeight = 0;

            loadoutResults.forEach((res, wIdx) => {
                const workerRuns = runsPerWorker + (wIdx === 0 ? extraRuns : 0);
                totalAvg += res.score * workerRuns;
                totalWeight += workerRuns;
            });

            const finalAvg = totalAvg / totalWeight;
            const finalMin = Math.min(...loadoutResults.map(r => r.min));
            const finalMax = Math.max(...loadoutResults.map(r => r.max));

            return {
                id: loadout.id,
                idolName: loadout.idolName || loadout.id,
                min: finalMin,
                score: Math.floor(finalAvg),
                max: finalMax,
                deckDetails: loadout.deckDetails
            };
        });

        // Helper to calculate score with 1.2x bonus for the highest
        const calcTotal = (key) => {
            const sorted = [...aggregatedIdols].sort((a, b) => b[key] - a[key]);
            let total = 0;
            if (sorted.length > 0) {
                total += sorted[0][key] * 1.2;
                for (let i = 1; i < sorted.length; i++) {
                    total += sorted[i][key];
                }
            }
            return Math.floor(total);
        };

        const planMap = { "sense": "センス", "logic": "ロジック", "anomaly": "アノマリー" };
        const planName = planMap[contestStage.plan] || contestStage.plan;

        const finalData = {
            season: seasonStr,
            stage: stageStr,
            plan: planName,
            runs: runsArg,
            idols: aggregatedIdols,
            totalScore: calcTotal('score'),
            totalMin: calcTotal('min'),
            totalMax: calcTotal('max')
        };

        console.log(JSON.stringify(finalData));
        process.exit(0);

    } catch (err) {
        console.error("Simulation failed:", err);
        process.exit(1);
    }
}

run();
