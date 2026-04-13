import { Stages, PIdols, Idols } from "gakumas-data";
import { MongoClient } from "mongodb";
import { calculateMemoryHash, calculateSubEffectiveHash } from "./optimize-memories-parallel.mjs";

async function run() {
    const args = process.argv.slice(2);
    if (args.length < 1) {
        console.error("使用法: yarn node packages/cli/scripts/list-uncached.mjs <season-stage> [runs] [supportBonus]");
        process.exit(1);
    }

    const [seasonStr, stageStr] = args[0].split("-");
    const season = parseInt(seasonStr, 10);
    const stageNumber = parseInt(stageStr, 10);
    const numRuns = parseInt(args[1] || "3000", 10);
    const supportBonusRaw = parseFloat(args[2] || process.env.SUPPORT_BONUS || "0.04");
    const supportBonus = supportBonusRaw >= 1.0 ? supportBonusRaw / 100 : supportBonusRaw;

    const contestStage = Stages.getAll().find(s => s.type === "contest" && s.season === season && s.stage === stageNumber);
    if (!contestStage) {
        console.error(`ステージが見つかりません: シーズン${season} ステージ${stageNumber}`);
        process.exit(1);
    }

    const mongoUri = process.env.MONGODB_URI;
    if (!mongoUri) {
        console.error("MONGODB_URI が設定されていません。");
        process.exit(1);
    }

    const client = new MongoClient(mongoUri);
    try {
        await client.connect();
        const db = client.db(process.env.MONGODB_DB || "gakumas-tools");

        // 1. Fetch all memories
        const memories = await db.collection("memories").find({}).toArray();

        // 2. Fetch all simulation results for this stage/config
        const results = await db.collection("simulation_results").find({
            stageId: contestStage.id,
            runs: numRuns,
            supportBonus: supportBonus
        }).project({ mainHash: 1, subHash: 1 }).toArray();

        const usedMainHashes = new Set(results.map(r => r.mainHash));
        const usedSubHashes = new Set(results.map(r => r.subHash));

        const uncachedMemories = [];

        for (const memory of memories) {
            const hash = calculateMemoryHash(memory);
            const subHash = calculateSubEffectiveHash(memory);

            const isMainUsed = usedMainHashes.has(hash);
            const isSubUsed = usedSubHashes.has(subHash);

            if (!isMainUsed && !isSubUsed) {
                uncachedMemories.push(memory);
            }
        }

        if (uncachedMemories.length === 0) {
            console.log("未計算のメモリーは見つかりませんでした。");
            return;
        }

        // 3. Output Table
        console.log(`## 未計算メモリーリスト (${contestStage.name}, Runs: ${numRuns}, Support Bonus: ${(supportBonus * 100).toFixed(2)}%)`);
        console.log("");
        console.log("| プラン | アイドル名 | 楽曲名 | メモリー名 |");
        console.log("| :-- | :-- | :-- | :-- |");

        for (const mem of uncachedMemories) {
            const pIdol = PIdols.getById(mem.pIdolId);
            const idol = pIdol ? Idols.getById(pIdol.idolId) : null;

            const plan = pIdol ? pIdol.plan : "不明";
            const idolName = idol ? idol.name.replace(" ", "") : "不明";
            const title = pIdol ? pIdol.title : "不明";
            const memoryName = mem.name || "名称未設定";

            console.log(`| ${plan} | ${idolName} | ${title} | ${memoryName} |`);
        }

    } catch (e) {
        console.error("エラーが発生しました:", e);
    } finally {
        await client.close();
    }
}

run();
