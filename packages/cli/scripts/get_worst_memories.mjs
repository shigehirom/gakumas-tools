import { MongoClient } from 'mongodb';

const uri = "mongodb://192.168.100.4:27017";
const client = new MongoClient(uri);

async function run() {
  try {
    await client.connect();
    const db = client.db("gakumas-tools");
    const coll = db.collection("memories");
    
    // 全メモリーを取得 (名前に 🔑 が含まれる「ロック済み」メモリーを除外)
    const memories = await coll.find({ name: { $not: /🔑/ } }).toArray();

    const scoredMemories = memories.map(m => {
        let score = 9999999;
        if (m.name) {
            // 末尾の連続する数字をスコアとして抽出
            const match = m.name.match(/(\d+)$/);
            if (match) {
                score = parseInt(match[1], 10);
            }
        }
        return { ...m, _parsedScore: score };
    });

    // スコアの昇順（低い順）でソート
    scoredMemories.sort((a, b) => a._parsedScore - b._parsedScore);

    console.log(`\n=== メモリー スコア ワースト10 (全 ${scoredMemories.length} 件中) ===\n`);
    console.log("順位 | スコア | メモリー名 | DB ID");
    console.log("-".repeat(60));
    
    for (let i = 0; i < 10 && i < scoredMemories.length; i++) {
        const mem = scoredMemories[i];
        console.log(`${String(i + 1).padStart(2, ' ')}位 | ${String(mem._parsedScore).padStart(5, ' ')} | ${mem.name} | ${mem._id}`);
    }
    console.log("\n");
  } finally {
    await client.close();
  }
}
run().catch(console.dir);
