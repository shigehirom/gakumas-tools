import { MongoClient } from 'mongodb';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { SkillCards } from 'gakumas-data';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Manual .env loading to avoid dependency issues with PNP/dotenv
function loadEnv(filePath) {
  if (fs.existsSync(filePath)) {
    const envFile = fs.readFileSync(filePath, 'utf-8');
    envFile.split('\n').forEach(line => {
      const parts = line.split('=');
      if (parts.length === 2) {
        process.env[parts[0].trim()] = parts[1].trim();
      }
    });
  }
}

// Target ID mapping for Anomaly plan optimization
const ID_MAPPING = {
  770: 780, // せーのでぱくっ！+ -> 羽ばたけ！+
};

async function run() {
  loadEnv(path.join(__dirname, '../../gakumas-tools/.env.local'));

  if (!process.env.MONGODB_URI) {
    console.error('Error: MONGODB_URI is not set in environment (check gakumas-tools/.env.local)');
    process.exit(1);
  }

  const client = new MongoClient(process.env.MONGODB_URI);
  try {
    await client.connect();
    const db = client.db(process.env.MONGODB_DB || "gakumas-tools");
    const collection = db.collection('memories');

    const oldIds = Object.keys(ID_MAPPING).map(id => parseInt(id, 10));
    
    // Find memories that have any of the old IDs
    const memories = await collection.find({ skillCardIds: { $in: oldIds } }).toArray();

    console.log(`スキャン完了: ${memories.length} 件の対象メモリーが見つかりました。\n`);

    let totalUpdated = 0;
    for (const mem of memories) {
      let modified = false;
      const originalCards = [...mem.skillCardIds];
      const newCards = originalCards.map(id => {
        if (ID_MAPPING[id]) {
          const oldCard = SkillCards.getById(id);
          const newCard = SkillCards.getById(ID_MAPPING[id]);
          
          // Safety: only convert if both are anomaly
          if (oldCard?.plan === 'anomaly' && (newCard?.plan === 'anomaly' || !newCard)) {
              console.log(`置換実行 [${mem.name || mem._id}] :`);
              console.log(`  - 修正前: ${oldCard?.name || 'Unknown'} (ID:${id})`);
              console.log(`  - 修正後: ${newCard?.name || 'Unknown'} (ID:${ID_MAPPING[id]})`);
              modified = true;
              return ID_MAPPING[id];
          }
        }
        return id;
      });

      if (modified) {
        await collection.updateOne(
          { _id: mem._id },
          { $set: { skillCardIds: newCards } }
        );
        totalUpdated++;
      }
    }
    
    console.log(`\n🎉 更新完了: 合計 ${totalUpdated} 件のメモリーを最新のIDに修正しました。`);

  } catch (e) {
    console.error('MongoDB Error:', e);
  } finally {
    await client.close();
  }
}

run();
