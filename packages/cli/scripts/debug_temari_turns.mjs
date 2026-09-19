import { MongoClient } from "mongodb";
import { Stages, PIdols, SkillCards, Idols, PItems, Customizations } from "gakumas-data";
import path from "path";
import { fileURLToPath } from "url";

// packages/gakumas-engine からシミュレータを直接インポート
import { ContestSimulator } from "../../../gakumas-engine/index.js";

const MONGODB_URI = "mongodb://192.168.100.4:27017";
const client = new MongoClient(MONGODB_URI);

async function run() {
    await client.connect();
    const db = client.db("gakumas-tools");

    const mainDoc = await db.collection("memories").findOne({ name: "26/09/14＿19008" });
    const subDoc = await db.collection("memories").findOne({ name: "26/07/09＿19638" });

    const stages = Stages.getAll();
    const contestStage = stages.find(s => s.season === 52 && s.stage === 2);

    const deckData = {
        params: mainDoc.params,
        pItemIds: [...(mainDoc.pItemIds || []), ...(subDoc.pItemIds || [])],
        skillCardIdGroups: [
            mainDoc.skillCardIds,
            subDoc.skillCardIds
        ],
        customizationGroups: [
            mainDoc.customizations || [],
            subDoc.customizations || []
        ]
    };

    // 10試合シミュレーションして、最終ターンのログを確認
    for (let i = 0; i < 5; i++) {
        const sim = new ContestSimulator({
            stage: contestStage,
            loadout: deckData,
            supportBonus: 0.1462
        });

        const result = sim.simulate();
        console.log(`\n=== Match ${i + 1} (Score: ${result.score}) ===`);
        if (result.logs) {
            // ログがあれば表示
            result.logs.forEach(l => console.log(l));
        } else if (result.history) {
            result.history.forEach(h => console.log(h));
        } else {
            console.log("Result keys:", Object.keys(result));
            console.log("Turns:", result.turns?.length || result.turnCount);
            if (result.turns) {
                result.turns.forEach((t, tidx) => {
                    console.log(`Turn ${tidx + 1}: Used: ${t.cardUsed?.name || t.usedCard}, Genki: ${t.genki}, Motivation: ${t.motivation}, Score: ${t.score}`);
                });
            }
        }
    }
    process.exit(0);
}

run().catch(console.error);

