import { Stages, PIdols, SkillCards } from "gakumas-data";
import { MongoClient } from "mongodb";
import { Worker } from 'worker_threads';
import crypto from "crypto";
import os from 'os';
import path from "path";
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const IDOL_NAME_TO_ID = {
    "saki": 1, "temari": 2, "kotone": 3, "mao": 4, "lilja": 5, "china": 6,
    "sumika": 7, "hiro": 8, "rina": 9, "rinami": 9, "ume": 10, "sena": 11, "misuzu": 12, "tsubame": 13
};

function calculateMemoryHash(memoryData) {
    const parts = [
        memoryData.pIdolId,
        JSON.stringify(memoryData.params),
        JSON.stringify(memoryData.pItemIds),
        JSON.stringify(memoryData.skillCardIds),
        JSON.stringify(memoryData.customizations || [{}, {}, {}, {}, {}, {}])
    ];
    return crypto.createHash('sha256').update(parts.join('|')).digest('hex');
}

// Hierarchy Definition
// 1 = SSR+, 2 = SSR, 3 = SR+, 4 = SR, 5 = R+, 6 = R, 7 = N+, 8 = N, 9 = Trouble/Other
function getCardHierarchy(card) {
    if (card.sourceType === 'pIdol') return -1; // 固有カードは交換不可
    let rank = 9;
    if (card.rarity === 'SSR') rank = card.upgraded ? 1 : 2;
    else if (card.rarity === 'SR') rank = card.upgraded ? 3 : 4;
    else if (card.rarity === 'R') rank = card.upgraded ? 5 : 6;
    else if (card.rarity === 'N') rank = card.upgraded ? 7 : 8;
    return rank;
}

const HIERARCHY_NAMES = {
    1: "SSR+", 2: "SSR", 3: "SR+", 4: "SR", 5: "R+", 6: "R", 7: "N+", 8: "N"
};

async function loadMemoriesFromDB(uri, options) {
    const client = new MongoClient(uri);
    try {
        await client.connect();
        const db = client.db(process.env.MONGODB_DB || "gakumas-tools");
        const collection = db.collection("memories");

        let query = {};
        const { idolName, plan } = options;

        if (idolName) {
            const idolId = IDOL_NAME_TO_ID[idolName.toLowerCase()];
            if (idolId) {
                const targetPIdols = PIdols.getAll().filter(p => p.idolId === idolId);
                const pIdolIds = targetPIdols.map(p => p.id);
                query.pIdolId = { $in: pIdolIds };
            }
        }

        if (plan) {
            const targetPIdols = PIdols.getAll().filter(p => p.plan === plan);
            const planPIdolIds = targetPIdols.map(p => p.id);

            if (query.pIdolId && query.pIdolId.$in) {
                const existing = query.pIdolId.$in;
                const intersection = existing.filter(id => planPIdolIds.includes(id));
                query.pIdolId = { $in: intersection };
            } else {
                query.pIdolId = { $in: planPIdolIds };
            }
        }

        const memories = await collection.find(query).toArray();
        return memories.map(m => ({
            filename: m.name || m._id.toString(),
            data: m
        }));

    } catch (e) {
        console.error("MongoDB Error in loadMemories:", e);
        return [];
    } finally {
        await client.close();
    }
}

async function sendDiscordWebhook(content) {
    const webhookUrl = process.env.DISCORD_WEBHOOK_URL;
    if (!webhookUrl) {
        console.error("[Advisor] DISCORD_WEBHOOK_URL is not set.");
        return;
    }
    try {
        const response = await fetch(webhookUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content })
        });
        if (!response.ok) {
            console.error(`[Advisor] Failed to send Discord message: ${response.statusText}`);
        } else {
            console.error("[Advisor] Discord notification sent successfully.");
        }
    } catch (error) {
        console.error("[Advisor] Error sending Discord notification:", error);
    }
}

async function executeSimulation(stage, runs, bonus, loadouts, workers) {
    const results = [];
    const promises = [];
    const activeWorkers = [];
    const totalCount = loadouts.length;
    const chunkSize = Math.ceil(totalCount / workers);

    let completed = 0;

    for (let i = 0; i < totalCount; i += chunkSize) {
        const chunk = loadouts.slice(i, i + chunkSize);
        promises.push(new Promise((resolve, reject) => {
            const worker = new Worker(path.join(__dirname, 'advisor-worker.mjs'), {
                workerData: {
                    contestStage: stage,
                    numRuns: runs,
                    supportBonus: bonus,
                    loadouts: chunk
                }
            });

            worker.on('message', (msg) => {
                if (msg.type === 'progress') {
                    completed += msg.count;
                    process.stderr.write(`\r- 進捗: ${completed}/${totalCount} (${Math.round(completed / totalCount * 100)}%)`);
                } else if (msg.type === 'done') {
                    results.push(...msg.results);
                    resolve();
                }
            });

            worker.on('error', reject);
            worker.on('exit', (code) => {
                if (code !== 0) reject(new Error(`Worker stopped with exit code ${code}`));
            });

            activeWorkers.push(worker);
        }));
    }

    try {
        if (totalCount > 0) await Promise.all(promises);
        if (totalCount > 0) process.stderr.write('\n');
    } finally {
        for (const w of activeWorkers) w.terminate();
    }
    return results;
}

async function run() {
    const rawArgs = process.argv.slice(2);
    const args = [];
    const options = {};
    for (let i = 0; i < rawArgs.length; i++) {
        if (rawArgs[i].startsWith("--")) {
            const key = rawArgs[i].substring(2);
            const value = rawArgs[i + 1] && !rawArgs[i + 1].startsWith("--") ? rawArgs[i + 1] : true;
            options[key] = value;
            if (value !== true) i++;
        } else {
            args.push(rawArgs[i]);
        }
    }

    if (args.length < 3) {
        console.error("Usage: node advisor-process.mjs <mongodb_uri> <season-stage> <runs> [options]");
        process.exit(1);
    }

    const uri = args[0];
    const [seasonStr, stageStr] = args[1].split("-");
    const season = parseInt(seasonStr, 10);
    const stageNumber = parseInt(stageStr, 10);
    const numRuns = parseInt(args[2], 10);

    const stages = Stages.getAll();
    const contestStage = stages.find(s => s.type === "contest" && s.season === season && s.stage === stageNumber);

    if (!contestStage) {
        console.error(`Stage not found: Season ${season} Stage ${stageNumber}`);
        process.exit(1);
    }

    // Auto-detect plan from stage definition if not provided
    if (!options.plan && contestStage.plan && contestStage.plan !== 'free') {
        options.plan = contestStage.plan;
    }

    const supportBonusRaw = parseFloat(options.supportBonus || process.env.SUPPORT_BONUS || "0.04");
    const supportBonus = supportBonusRaw >= 1.0 ? supportBonusRaw / 100 : supportBonusRaw;

    console.error(`[Advisor] Loading memories for idol: ${options.idolName || 'all'}...`);
    const memories = await loadMemoriesFromDB(uri, options);
    
    if (memories.length === 0) {
        console.error("[Advisor] No memories found matching criteria.");
        process.exit(1);
    }

    memories.forEach(m => {
        m.hash = calculateMemoryHash(m.data);
    });

    const cpuCount = os.cpus().length;
    const workerCount = Math.max(1, cpuCount);

    // -------------------------------------------------------------
    // Phase 0: Find current Best Loadout (Screening 200 runs)
    // -------------------------------------------------------------
    console.error(`[Advisor] Phase 0: Finding current best loadout among ${memories.length} memories (200 runs)...`);
    const initialLoadouts = [];
    for (const main of memories) {
        for (const sub of memories) {
            const loadout = {
                id: `${main.hash}_${sub.hash}`,
                mainFilename: main.filename,
                subFilename: sub.filename,
                params: [...main.data.params],
                pItemIds: [...(main.data.pItemIds || [])].filter(id => id > 0),
                skillCardIdGroups: [main.data.skillCardIds, sub.data.skillCardIds],
                customizationGroups: [
                    main.data.customizations || [{}, {}, {}, {}, {}, {}],
                    sub.data.customizations || [{}, {}, {}, {}, {}, {}]
                ]
            };
            // Apply Sub parameter 20%
            loadout.params = loadout.params.map((p, idx) => p + Math.floor((sub.data.params[idx] || 0) * 0.2));
            initialLoadouts.push(loadout);
        }
    }

    // Try finding cached results in simulation_results to skip screening if possible
    let baseResult = null;
    let mongoClient = null;
    let cachedResults = [];
    try {
        mongoClient = new MongoClient(uri);
        await mongoClient.connect();
        const db = mongoClient.db(process.env.MONGODB_DB || "gakumas-tools");
        const cacheCollection = db.collection("simulation_results");
        
        const hashes = memories.map(m => m.hash);
        const query = {
            stageId: contestStage.id,
            runs: { $gte: 200 },
            season: season,
            mainHash: { $in: hashes },
            subHash: { $in: hashes }
        };
        cachedResults = await cacheCollection.find(query).toArray();
    } catch (e) {
        console.error("[Advisor] Cache DB Lookup failed, will run screening:", e);
    } finally {
        if (mongoClient) await mongoClient.close();
    }

    let screeningResults = [];
    if (cachedResults.length > 0) {
        console.error(`[Advisor] Loaded ${cachedResults.length} results from cache.`);
        screeningResults = cachedResults.map(r => ({
            id: `${r.mainHash}_${r.subHash}`,
            score: r.score,
            median: r.median,
            max: r.max,
            min: r.min,
            stats: r.stats
        }));
    } else {
        console.error(`[Advisor] Simulating ${initialLoadouts.length} loadout combinations...`);
        screeningResults = await executeSimulation(contestStage, 200, supportBonus, initialLoadouts, workerCount);
    }

    if (screeningResults.length === 0) {
        console.error("[Advisor] Screening failed to produce results.");
        process.exit(1);
    }

    // Sort to find best
    screeningResults.sort((a, b) => b.median - a.median);
    const bestPairInfo = screeningResults[0];
    const bestLoadoutRaw = initialLoadouts.find(l => l.id === bestPairInfo.id);

    if (!bestLoadoutRaw) {
        console.error("[Advisor] Error identifying best loadout details.");
        process.exit(1);
    }

    // Get detailed base stats with full runs
    console.error(`[Advisor] Base Loadout Identified: ${bestLoadoutRaw.mainFilename} + ${bestLoadoutRaw.subFilename}`);
    console.error(`[Advisor] Simulating Base Loadout with target runs (${numRuns})...`);
    const baseSimResultArray = await executeSimulation(contestStage, numRuns, supportBonus, [bestLoadoutRaw], 1);
    const baseSimResult = baseSimResultArray[0];

    console.log(`\n# メモリーチューニング診断レポート (${options.mode === 'params' ? 'パラメータ感度分析' : 'スキルカード交換提案'})\n`);
    console.log(`- **対象ステージ**: ${contestStage.name} (シーズン${season} ステージ${stageNumber})`);
    console.log(`- **推奨プラン**: ${options.plan || '未指定'}`);
    console.log(`- **アイドル**: ${options.idolName || '指定なし'}`);
    console.log(`- **サポートボーナス**: ${(supportBonus * 100).toFixed(2)}%`);
    console.log(`- **試行回数**: ${numRuns} 回\n`);
    console.log(`### ■ 診断基準（ベースロードアウト）`);
    console.log(`- **メインメモリ**: \`${bestLoadoutRaw.mainFilename}\``);
    console.log(`- **サブメモリ**: \`${bestLoadoutRaw.subFilename}\``);
    console.log(`- **現在の基準スコア平均値**: **${Math.round(baseSimResult.score).toLocaleString()} Pt**`);
    console.log(`- **現在の基準スコア中央値 ($Q_2$)**: **${Math.round(baseSimResult.median).toLocaleString()} Pt**`);
    console.log(`- **スコア分布**: Min ${Math.round(baseSimResult.min).toLocaleString()} / Max ${Math.round(baseSimResult.max).toLocaleString()} Pt\n`);

    let reportMarkdown = "";

    // -------------------------------------------------------------
    // Mode A: Params Sensitivity Analysis
    // -------------------------------------------------------------
    if (options.mode === 'params') {
        const crit = [contestStage.criteria.vocal, contestStage.criteria.dance, contestStage.criteria.visual]; // [Vo, Da, Vi]
        const indexed = crit.map((val, idx) => ({ val, idx }));
        indexed.sort((a, b) => b.val - a.val); // Sort descending

        const paramNames = ["🔴Vo", "🔵Da", "🟡Vi"];
        const pairs = [
            { plus: indexed[0].idx, minus: indexed[2].idx },
            { plus: indexed[0].idx, minus: indexed[1].idx },
            { plus: indexed[1].idx, minus: indexed[2].idx }
        ];

        const deltas = [50, 100, 150, 200];
        const virtualLoadouts = [];

        for (const pair of pairs) {
            for (const delta of deltas) {
                const newParams = [...bestLoadoutRaw.params];
                newParams[pair.plus] += delta;
                newParams[pair.minus] = Math.max(0, newParams[pair.minus] - delta);

                virtualLoadouts.push({
                    id: `${paramNames[pair.plus]}+${delta}_${paramNames[pair.minus]}-${delta}`,
                    mainFilename: bestLoadoutRaw.mainFilename,
                    subFilename: bestLoadoutRaw.subFilename,
                    params: newParams,
                    pItemIds: bestLoadoutRaw.pItemIds,
                    skillCardIdGroups: bestLoadoutRaw.skillCardIdGroups,
                    customizationGroups: bestLoadoutRaw.customizationGroups,
                    meta: {
                        description: `${paramNames[pair.plus]} +${delta} / ${paramNames[pair.minus]} -${delta}`,
                        plusName: paramNames[pair.plus],
                        minusName: paramNames[pair.minus],
                        delta
                    }
                });
            }
        }

        console.error(`[Advisor] Simulating ${virtualLoadouts.length} parameter variation patterns...`);
        const simResults = await executeSimulation(contestStage, numRuns, supportBonus, virtualLoadouts, workerCount);

        reportMarkdown += `### ■ パラメータ感度分析結果\n`;
        reportMarkdown += `ステージの有利パラメータ基準: **Vo ${crit[0]} / Da ${crit[1]} / Vi ${crit[2]}** (優先順: ${indexed.map(x => paramNames[x.idx]).join(' > ')})\n\n`;
        reportMarkdown += `| 変更内容 | 平均スコア | スコア中央値 ($Q_2$) | 基準比 (中央値) | 判定 | Min / Max |\n`;
        reportMarkdown += `| :--- | ---: | ---: | ---: | :---: | :--- |\n`;

        simResults.forEach(res => {
            res.diff = res.median - baseSimResult.median;
        });
        const sortOrder = options.sort || 'normal';
        if (sortOrder === 'reverse') {
            simResults.sort((a, b) => a.diff - b.diff);
        } else {
            simResults.sort((a, b) => b.diff - a.diff);
        }

        simResults.forEach(res => {
            const loadout = virtualLoadouts.find(l => l.id === res.id);
            const diff = res.diff;
            const diffPct = (diff / baseSimResult.median * 100).toFixed(2);
            const diffSign = diff >= 0 ? `+${diff.toLocaleString()}` : diff.toLocaleString();
            const diffPctSign = diff >= 0 ? `+${diffPct}` : diffPct;

            let evaluation = "変化なし";
            if (diff >= 3000) evaluation = "✨ 大幅改善";
            else if (diff >= 1000) evaluation = "👍 改善";
            else if (diff <= -3000) evaluation = "❌ 大幅悪化";
            else if (diff <= -1000) evaluation = "⚠️ 悪化";

            reportMarkdown += `| ${loadout.meta.description} | ${Math.round(res.score).toLocaleString()} | ${Math.round(res.median).toLocaleString()} | ${diffSign} Pt (${diffPctSign}%) | ${evaluation} | ${Math.round(res.min).toLocaleString()} / ${Math.round(res.max).toLocaleString()} |\n`;
        });

        console.log(reportMarkdown);

    // -------------------------------------------------------------
    // Mode B: Skill Card Replacement Advisor
    // -------------------------------------------------------------
    } else if (options.mode === 'cards') {
        const planFilter = options.plan || 'free';
        const allCards = SkillCards.getAll();

        const getCardById = (id) => allCards.find(c => c.id === id);

        // Gather all unique skill card IDs present in the user's memories for this idol and plan
        const ownedCardIds = new Set();
        memories.forEach(m => {
            if (m.data && m.data.skillCardIds) {
                m.data.skillCardIds.forEach(id => {
                    if (id > 0) ownedCardIds.add(id);
                });
            }
        });

        // Map main and sub cards
        const mainCards = bestLoadoutRaw.skillCardIdGroups[0].map(id => getCardById(id)).filter(Boolean);
        const subCards = bestLoadoutRaw.skillCardIdGroups[1].map(id => getCardById(id)).filter(Boolean);

        const virtualLoadouts = [];

        // Try replacing main cards (index 0) and sub cards (index 1)
        const groups = [
            { label: "メイン", index: 0, cards: mainCards },
            { label: "サブ", index: 1, cards: subCards }
        ];

        for (const group of groups) {
            for (let cardIdx = 0; cardIdx < group.cards.length; cardIdx++) {
                const originalCard = group.cards[cardIdx];
                if (originalCard.sourceType === 'pIdol') continue; // Skip signature card

                const originalHierarchy = getCardHierarchy(originalCard);

                // Find candidate replacements
                const candidates = allCards.filter(c => {
                    if (c.sourceType === 'pIdol') return false; // Skip unique pIdols
                    if (c.id === originalCard.id) return false; // Skip self
                    
                    // Only allow replacement cards that are already present in the user's memories for this plan/idol
                    if (!ownedCardIds.has(c.id)) return false;

                    // Plan compatibility
                    if (planFilter !== 'free') {
                        if (c.plan !== 'free' && c.plan !== planFilter) return false;
                    }

                    // Hierarchy check: candidate must be equal or lower rank (value >= original)
                    const candidateHierarchy = getCardHierarchy(c);
                    if (candidateHierarchy === -1 || candidateHierarchy < originalHierarchy) return false;

                    // Unique constraint: If candidate is unique, it shouldn't already exist in the loadout
                    if (c.unique) {
                        const alreadyExists = bestLoadoutRaw.skillCardIdGroups.some(grp => grp.includes(c.id));
                        if (alreadyExists) return false;
                    }

                    return true;
                });

                // Generate virtual loadouts for each candidate
                candidates.forEach(cand => {
                    const newIdGroups = [
                        [...bestLoadoutRaw.skillCardIdGroups[0]],
                        [...bestLoadoutRaw.skillCardIdGroups[1]]
                    ];
                    // Replace
                    newIdGroups[group.index][cardIdx] = cand.id;

                    const newCustomizations = [
                        [...bestLoadoutRaw.customizationGroups[0]],
                        [...bestLoadoutRaw.customizationGroups[1]]
                    ];
                    // Reset customization for the replaced card (since we test without customization)
                    newCustomizations[group.index][cardIdx] = {};

                    virtualLoadouts.push({
                        id: `${group.label}_idx${cardIdx}_replace_${originalCard.id}_with_${cand.id}`,
                        mainFilename: bestLoadoutRaw.mainFilename,
                        subFilename: bestLoadoutRaw.subFilename,
                        params: bestLoadoutRaw.params,
                        pItemIds: bestLoadoutRaw.pItemIds,
                        skillCardIdGroups: newIdGroups,
                        customizationGroups: newCustomizations,
                        meta: {
                            groupLabel: group.label,
                            cardIdx,
                            originalCard,
                            replacedWith: cand
                        }
                    });
                });
            }
        }

        console.error(`[Advisor] Simulating ${virtualLoadouts.length} skill card replacement patterns...`);
        const simResults = await executeSimulation(contestStage, numRuns, supportBonus, virtualLoadouts, workerCount);

        // Sort results by score to see best options
        simResults.forEach(res => {
            const loadout = virtualLoadouts.find(l => l.id === res.id);
            res.meta = loadout.meta;
            res.diff = res.median - baseSimResult.median;
        });

        // Filter improvements or near-equivalent changes
        const candidatesToShow = simResults.filter(r => r.diff > -1000);
        const sortOrder = options.sort || 'normal';
        if (sortOrder === 'reverse') {
            candidatesToShow.sort((a, b) => a.diff - b.diff);
        } else {
            candidatesToShow.sort((a, b) => b.diff - a.diff);
        }

        const top5Candidates = candidatesToShow.slice(0, 5);

        reportMarkdown += `### ■ スキルカード交換提案結果 (期待値上位5件)\n\n`;
        if (top5Candidates.length === 0) {
            reportMarkdown += `基準スコアを上回る、または同等の交換候補は見つかりませんでした。\n`;
        } else {
            reportMarkdown += `| 対象カード (位置) | ランク | 交換先カード | ランク | スコア中央値 ($Q_2$) | 基準差 (中央値) | 判定 |\n`;
            reportMarkdown += `| :--- | :---: | :--- | :---: | ---: | ---: | :---: |\n`;

            top5Candidates.forEach(res => {
                const diffPct = (res.diff / baseSimResult.median * 100).toFixed(2);
                const diffSign = res.diff >= 0 ? `+${res.diff.toLocaleString()}` : res.diff.toLocaleString();
                const diffPctSign = res.diff >= 0 ? `+${diffPct}` : diffPct;

                let evalLabel = "同等";
                if (res.diff >= 2000) evalLabel = "✨ 大幅向上";
                else if (res.diff >= 500) evalLabel = "👍 向上";
                else if (res.diff <= -500) evalLabel = "⚠️ 微妙に低下";

                const origRank = HIERARCHY_NAMES[getCardHierarchy(res.meta.originalCard)] || "N";
                const destRank = HIERARCHY_NAMES[getCardHierarchy(res.meta.replacedWith)] || "N";

                reportMarkdown += `| ${res.meta.originalCard.name} (${res.meta.groupLabel}) | ${origRank} | **${res.meta.replacedWith.name}** | ${destRank} | ${Math.round(res.median).toLocaleString()} | ${diffSign} Pt (${diffPctSign}%) | ${evalLabel} |\n`;
            });

            reportMarkdown += `\n### ■ 各候補の交換用手持ちメモリー詳細 (出現確率)\n\n`;
            
            top5Candidates.forEach((res, index) => {
                const candCard = res.meta.replacedWith;
                const origCard = res.meta.originalCard;
                const destRank = getCardHierarchy(candCard);

                // Find user memories containing this candidate card
                const matchingMemories = memories.filter(m => 
                    m.data && m.data.skillCardIds && m.data.skillCardIds.includes(candCard.id)
                );

                reportMarkdown += `${index + 1}. **${origCard.name} (${res.meta.groupLabel})** ➔ **${candCard.name}** (${HIERARCHY_NAMES[destRank] || 'N'})\n`;
                
                if (matchingMemories.length === 0) {
                    reportMarkdown += `   - ⚠️ 対象カードを所持している手持ちメモリーが見つかりませんでした。\n`;
                } else {
                    const memoryReports = [];
                    matchingMemories.forEach(mem => {
                        let countBelowOrEqual = 0;
                        const cardsInMem = mem.data.skillCardIds.map(id => getCardById(id)).filter(Boolean);
                        
                        cardsInMem.forEach(c => {
                            if (c.sourceType === 'pIdol') return; // 固有カードは除外
                            if (c.rarity === 'T') return;         // トラブルカードは除外
                            
                            const cRank = getCardHierarchy(c);
                            if (cRank >= destRank) { // 交換先カードのランク以下
                                countBelowOrEqual++;
                            }
                        });

                        const probabilityPct = countBelowOrEqual > 0 ? (100 / countBelowOrEqual).toFixed(1) : "0.0";
                        memoryReports.push({
                            filename: mem.filename,
                            count: countBelowOrEqual,
                            prob: probabilityPct
                        });
                    });

                    // Sort by probability descending (count ascending)
                    memoryReports.sort((a, b) => a.count - b.count);

                    reportMarkdown += `   - **交換確率（出現確率が高い順）**:\n`;
                    memoryReports.forEach(mr => {
                        reportMarkdown += `     - 📁 \`${mr.filename}\` : 対象以下カード ${mr.count}枚 (確率: **${mr.prob}%**)\n`;
                    });
                }
                reportMarkdown += `\n`;
            });
        }

        console.log(reportMarkdown);
    }

    // -------------------------------------------------------------
    // Discord Webhook Sending
    // -------------------------------------------------------------
    if (options.discord) {
        let discordMsg = `**【学園アイドルマスター ツール】メモリーチューニング診断完了**\n`;
        discordMsg += `**対象ステージ**: ${contestStage.name} (シーズン${season} ステージ${stageNumber})\n`;
        discordMsg += `**アイドル**: ${options.idolName || '指定なし'} (${options.plan || 'プラン自動指定'})\n`;
        discordMsg += `**基準スコア中央値**: ${Math.round(baseSimResult.median).toLocaleString()} Pt\n\n`;

        if (options.mode === 'params') {
            discordMsg += `**パラメータ感度分析ハイライト** (詳細はスプレッドシート/Driveを確認):\n`;
            // Add top 3 variations
            // To do this, sort sensitivity results by diff
            // Quick parsing:
            const lines = reportMarkdown.split("\n").filter(l => l.startsWith("|") && !l.includes("変更内容") && !l.includes(":---"));
            const parsedRows = lines.map(line => {
                const cols = line.split("|").map(x => x.trim());
                const name = cols[1];
                const median = cols[3];
                const diff = cols[4];
                return { name, median, diff };
            });
            parsedRows.sort((a, b) => {
                const valA = parseInt(a.diff.replace(/[^0-9-]/g, ""));
                const valB = parseInt(b.diff.replace(/[^0-9-]/g, ""));
                return valB - valA;
            });
            parsedRows.slice(0, 3).forEach(row => {
                discordMsg += `- ${row.name}: ${row.median} (${row.diff})\n`;
            });
        } else {
            discordMsg += `**カード交換提案ハイライト**:\n`;
            const lines = reportMarkdown.split("\n").filter(l => l.startsWith("|") && !l.includes("対象カード") && !l.includes(":---"));
            const parsedRows = lines.map(line => {
                const cols = line.split("|").map(x => x.trim());
                const from = cols[1];
                const to = cols[3];
                const median = cols[5];
                const diff = cols[6];
                return { from, to, median, diff };
            });
            parsedRows.slice(0, 5).forEach(row => {
                discordMsg += `- ${row.from} ➔ **${row.to}**: ${row.median} (${row.diff})\n`;
            });
            if (parsedRows.length === 0) {
                discordMsg += `有効な交換候補はありませんでした。\n`;
            }
        }

        // Include GDrive Link if generated
        const gdriveUrlFile = path.resolve(process.env.INIT_CWD || process.cwd(), `${options.gdrive || options.local}.gdriveurl`);
        // Since GoogleDriveClient upload runs on process beforeExit hook, the link might not be written yet.
        // We will try to fetch the default filename check
        if (process.env.CLI_DOCS_DIR) {
            // Note: The global capture process.on('beforeExit') runs later.
            // So we write a footnote that the full report is being uploaded to Drive.
            discordMsg += `\n*※詳細レポートはGoogle Driveおよびローカルに自動保存されます。*`;
        }

        await sendDiscordWebhook(discordMsg);
    }
}

run().then(() => {
    process.exit(0);
}).catch(err => {
    console.error(err);
    process.exit(1);
});
