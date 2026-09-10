import { MongoClient } from "mongodb";
import readline from "readline";
import { getLatestSupportBonus } from "./utils/supportBonus.mjs";

async function askQuestion(query) {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    return new Promise((resolve) => rl.question(query, (ans) => {
        rl.close();
        resolve(ans);
    }));
}

async function run() {
    const mongodbUri = process.env.MONGODB_URI;
    const dbName = process.env.MONGODB_DB || "gakumas-tools";

    if (!mongodbUri) {
        console.error("エラー: MONGODB_URI が環境変数に設定されていません。");
        process.exit(1);
    }

    const client = new MongoClient(mongodbUri);
    try {
        await client.connect();
        const db = client.db(dbName);
        
        const normalizedTarget = await getLatestSupportBonus(db);
        console.error(`基準サポートボーナス: ${(normalizedTarget * 100).toFixed(2)}% (MongoDBから動的取得)`);

        const collection = db.collection("loadouts");

        // Find documents with supportBonus < normalizedTarget
        const query = { supportBonus: { $lt: normalizedTarget, $ne: 0 } };
        
        // Count first
        const count = await collection.countDocuments(query);
        if (count === 0) {
            console.log(`サポートボーナスが ${normalizedTarget} 未満のロードアウトは見つかりませんでした。`);
            return;
        }

        console.error(`サポートボーナスが ${normalizedTarget} 未満のロードアウトが ${count} 件見つかりました。`);
        
        const answer = await askQuestion(`これらの ${count} 件のデータを削除しますか？ [y/N]: `);
        if (answer.toLowerCase() !== 'y') {
            console.log("削除をキャンセルしました。");
            return;
        }

        console.error("削除を実行中...");
        const result = await collection.deleteMany(query);
        console.log(`正常に ${result.deletedCount} 件のロードアウトを削除しました。`);

    } catch (e) {
        console.error("MongoDB エラー:", e);
        process.exit(1);
    } finally {
        await client.close();
    }
}

run();
