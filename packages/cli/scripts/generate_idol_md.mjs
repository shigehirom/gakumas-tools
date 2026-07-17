import { MongoClient } from 'mongodb';
import fs from 'fs';
import path from 'path';

const uri = "mongodb://192.168.100.4:27017";
const client = new MongoClient(uri);

const artifactDir = "/Users/shigehiro/.gemini/antigravity-ide/brain/8e6226cc-aaf5-46c0-bc36-cbd94a692f7f/artifacts";
const imageDestDir = path.join(artifactDir, "pIdols");
const imageSrcDir = "/Users/shigehiro/gakumas-workspace/gakumas-tools/packages/gakumas-images/images/pIdols";

if (!fs.existsSync(imageDestDir)) {
  fs.mkdirSync(imageDestDir, { recursive: true });
}

async function run() {
  try {
    await client.connect();
    const db = client.db("gakumas-tools");
    const coll = db.collection("owned_p_idols");
    const idols = await coll.find({}).toArray();

    const plans = { "sense": {}, "logic": {}, "anomaly": {} };
    const planNames = { "sense": "Sense (センス)", "logic": "Logic (ロジック)", "anomaly": "Anomaly (アノマリー)" };
    const rarityOrder = { "SSR": 1, "SR": 2, "R": 3 };
    const idolOrder = {
      "花海 咲季": 1,
      "月村 手毬": 2,
      "藤田 ことね": 3,
      "有村 麻央": 4,
      "葛城 リーリヤ": 5,
      "倉本 千奈": 6,
      "紫雲 清夏": 7,
      "篠澤 広": 8,
      "姫崎 莉波": 9,
      "花海 佑芽": 10,
      "十王 星南": 11,
      "秦谷 美鈴": 12,
      "雨夜 燕": 13
    };
    
    for (const idol of idols) {
      const plan = idol.plan || "unknown";
      if (!plans[plan]) plans[plan] = {};
      
      const idolId = idol.idolId || 999;
      if (!plans[plan][idolId]) plans[plan][idolId] = { idol_name: idol.idol_name, cards: [] };
      
      plans[plan][idolId].cards.push(idol);
    }
    
    let md = "# 所有Pアイドル一覧（プラン・アイドル別）\n\n";
    md += "このアーティファクトは、所有しているPアイドルをプランごと、アイドル順に整理し、アイコン画像を含めた表形式で表示しています。\n\n";
    
    for (const planKey of ["sense", "logic", "anomaly"]) {
      if (!plans[planKey] || Object.keys(plans[planKey]).length === 0) continue;
      md += `# ${planNames[planKey]}\n\n`;
      
      const idolIds = Object.keys(plans[planKey]).map(Number).sort((a,b) => {
         const nameA = plans[planKey][a].idol_name;
         const nameB = plans[planKey][b].idol_name;
         const orderA = idolOrder[nameA] || 999;
         const orderB = idolOrder[nameB] || 999;
         return orderA - orderB || a - b;
      });
      
      for (const idolId of idolIds) {
        const group = plans[planKey][idolId];
        md += `## ${group.idol_name}\n\n`;
        md += `| 画像 | Pアイドル (楽曲名) | レアリティ |\n`;
        md += `| :---: | :--- | :---: |\n`;
        
        group.cards.sort((a, b) => {
          const rA = rarityOrder[a.rarity] || 9;
          const rB = rarityOrder[b.rarity] || 9;
          if (rA !== rB) return rA - rB;
          return a.id - b.id;
        });
        
        for (const card of group.cards) {
          const id = card.id;
          const srcImage = path.join(imageSrcDir, `${id}.png`);
          const destImage = path.join(imageDestDir, `${id}.png`);
          let hasImage = false;
          if (fs.existsSync(srcImage)) {
             fs.copyFileSync(srcImage, destImage);
             hasImage = true;
          }
          const imgCol = hasImage ? `![${card.title}](/Users/shigehiro/.gemini/antigravity-ide/brain/8e6226cc-aaf5-46c0-bc36-cbd94a692f7f/artifacts/pIdols/${id}.png)` : `No Image`;
          md += `| ${imgCol} | **${card.title}** | ${card.rarity} |\n`;
        }
        md += "\n";
      }
    }
    
    fs.writeFileSync(path.join(artifactDir, "owned_p_idols_by_plan.md"), md);
    console.log("Markdown created at " + path.join(artifactDir, "owned_p_idols_by_plan.md"));
  } finally {
    await client.close();
  }
}
run().catch(console.dir);
