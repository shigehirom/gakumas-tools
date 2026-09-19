import { MongoClient } from "mongodb";
import { Stages, PIdols, SkillCards, Idols, PItems, Customizations } from "gakumas-data";
import { Worker } from "worker_threads";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const MONGODB_URI = "mongodb://192.168.100.4:27017";
const client = new MongoClient(MONGODB_URI);

async function run() {
    await client.connect();
    const db = client.db("gakumas-tools");

    const mainDoc = await db.collection("memories").findOne({ name: "26/09/14＿19008" });
    const subDoc = await db.collection("memories").findOne({ name: "26/07/09＿19638" });

    const stages = Stages.getAll();
    const contestStage = stages.find(s => s.season === 52 && s.stage === 2);

    // デッキA: オリジナル (届いて！+ [153] 含む)
    const deckA = {
        id: "DeckA_with_Todokite",
        params: mainDoc.params,
        pItemIds: [...(mainDoc.pItemIds || []), ...(subDoc.pItemIds || [])],
        skillCardIdGroups: [
            mainDoc.skillCardIds, // [810, 824, 127, 153, 306, 521]
            subDoc.skillCardIds   // [808, 586, 129, 138, 297, 772]
        ],
        customizationGroups: [
            mainDoc.customizations || [],
            subDoc.customizations || []
        ]
    };

    // デッキB: 届いて！+ (153) を「気まぐれハート+」 (139) に変更 (元気消費なし)
    const kimagureId = 139; // 気まぐれハート+
    const deckB_cards = [...mainDoc.skillCardIds];
    const idx153 = deckB_cards.indexOf(153);
    if (idx153 !== -1) deckB_cards[idx153] = kimagureId;

    const deckB = {
        id: "DeckB_with_KimagureHeart",
        params: mainDoc.params,
        pItemIds: deckA.pItemIds,
        skillCardIdGroups: [
            deckB_cards,
            subDoc.skillCardIds
        ],
        customizationGroups: deckA.customizationGroups
    };

    // デッキC: 届いて！+ (153) を「成長痛+」 (714) に変更
    const seichotsuId = 714; // 成長痛+
    const deckC_cards = [...mainDoc.skillCardIds];
    if (idx153 !== -1) deckC_cards[idx153] = seichotsuId;

    const deckC = {
        id: "DeckC_with_Seichoutsu",
        params: mainDoc.params,
        pItemIds: deckA.pItemIds,
        skillCardIdGroups: [
            deckC_cards,
            subDoc.skillCardIds
        ],
        customizationGroups: deckA.customizationGroups
    };

    // デッキD: 届いて！+ (153) を「本番前夜+」 (131) に変更
    const zenyaId = 131; // 本番前夜+
    const deckD_cards = [...mainDoc.skillCardIds];
    if (idx153 !== -1) deckD_cards[idx153] = zenyaId;

    const deckD = {
        id: "DeckD_with_Zenya",
        params: mainDoc.params,
        pItemIds: deckA.pItemIds,
        skillCardIdGroups: [
            deckD_cards,
            subDoc.skillCardIds
        ],
        customizationGroups: deckA.customizationGroups
    };

    const targetDecks = [deckA, deckB, deckC, deckD];

    const workerPath = path.join(__dirname, "rehearsal-worker-boot.mjs");
    const numRuns = 500;

    console.log(`Simulating ${targetDecks.length} decks with ${numRuns} runs each...`);

    const worker = new Worker(workerPath, {
        workerData: {
            contestStage,
            numRuns
        }
    });

    worker.on("message", (msg) => {
        if (msg.type === "progress") {
            process.stderr.write(`\rProgress: ${msg.loadoutId} - ${msg.currentRun}/${msg.totalRuns}`);
        } else if (msg.type === "done") {
            console.log("\n--- Simulation Results ---");
            const res = msg.results.filter(r => r.id !== "TOTAL_SCORE");
            console.table(res.map(r => ({
                Deck: r.id,
                Min: r.min,
                Q1: r.q1,
                Median: r.median,
                Q3: r.q3,
                Max: r.max,
                Avg: Math.round(r.score)
            })));
            process.exit(0);
        }
    });

    worker.postMessage({
        type: "start",
        loadouts: targetDecks
    });
}

run().catch(console.error);

