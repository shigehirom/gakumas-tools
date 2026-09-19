import { MongoClient } from "mongodb";
import readline from "readline";

function parseArgs(args) {
    const options = {
        seasonBefore: null,
        beforeDate: null,
        dryRun: false,
        force: false,
    };

    for (let i = 0; i < args.length; i++) {
        const arg = args[i];
        if (arg === '--season-before' && i + 1 < args.length) {
            options.seasonBefore = parseInt(args[++i], 10);
        } else if (arg === '--before' && i + 1 < args.length) {
            options.beforeDate = args[++i];
        } else if (arg === '--dry-run') {
            options.dryRun = true;
        } else if (arg === '--force' || arg === '-f') {
            options.force = true;
        }
    }
    return options;
}

async function askQuestion(query) {
    if (!process.stdin.isTTY) {
        throw new Error("非対話環境では --force オプションを指定してください。");
    }
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    return new Promise((resolve) => rl.question(query, (ans) => {
        rl.close();
        resolve(ans);
    }));
}

async function main() {
    const args = process.argv.slice(2);
    const options = parseArgs(args);

    if (options.seasonBefore === null && !options.beforeDate) {
        console.error("使用方法: node loadout-prune.mjs [--season-before <season>] [--before <YY-MM-DD>] [--dry-run] [--force]");
        process.exit(1);
    }

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
        const collection = db.collection("loadouts");

        const conditions = [];

        if (options.seasonBefore !== null) {
            conditions.push({ "derived.season": { $lt: options.seasonBefore } });
        }

        if (options.beforeDate) {
            // YY-MM-DD をパース
            let targetDate;
            const parts = options.beforeDate.split(/[-/]/);
            if (parts.length === 3) {
                let y = parseInt(parts[0], 10);
                if (y < 100) y += 2000;
                const m = parseInt(parts[1], 10) - 1;
                const d = parseInt(parts[2], 10);
                targetDate = new Date(Date.UTC(y, m, d, 0, 0, 0));
            } else {
                targetDate = new Date(options.beforeDate);
            }

            if (isNaN(targetDate.getTime())) {
                console.error(`エラー: 無効な日付形式です: ${options.beforeDate}`);
                process.exit(1);
            }

            conditions.push({
                $or: [
                    { createdAt: { $lt: targetDate } },
                    { name: { $lt: options.beforeDate } }
                ]
            });
        }

        const query = conditions.length === 1 ? conditions[0] : { $and: conditions };

        const count = await collection.countDocuments(query);
        console.log(`\n[Loadout Prune] 検索条件: ${JSON.stringify(query)}`);
        console.log(`対象件数: ${count} 件`);

        if (count === 0) {
            console.log("削除対象のロードアウトは見つかりませんでした。");
            return;
        }

        // サンプル表示
        const samples = await collection.find(query).limit(5).toArray();
        console.log("\n削除対象サンプル (最大5件):");
        for (const s of samples) {
            console.log(`- ID: ${s._id} | Name: ${s.name} | Season: ${s.derived?.season ?? '不明'} | Stage: ${s.derived?.stageName ?? s.stageId} | Date: ${s.createdAt ? s.createdAt.toISOString() : '不明'}`);
        }

        if (options.dryRun) {
            console.log("\n[Dry Run] 削除は実行されませんでした。(--dry-run が指定されています)");
            return;
        }

        if (!options.force) {
            const answer = await askQuestion(`\nこれらの ${count} 件のロードアウトを本当に削除しますか？ [y/N]: `);
            if (answer.toLowerCase() !== 'y') {
                console.log("削除をキャンセルしました。");
                return;
            }
        }

        console.log("削除を実行中...");
        const result = await collection.deleteMany(query);
        console.log(`✅ 正常に ${result.deletedCount} 件のロードアウトを削除しました。\n`);

    } catch (e) {
        console.error("エラーが発生しました:", e);
        process.exit(1);
    } finally {
        await client.close();
    }
}

main();

