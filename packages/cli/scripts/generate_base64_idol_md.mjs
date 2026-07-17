import { MongoClient } from 'mongodb';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';
import os from 'os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '../../..');

const uri = "mongodb://192.168.100.4:27017";
const client = new MongoClient(uri);

const imageSrcDir = path.join(projectRoot, "packages/gakumas-images/images/pIdols");
const outputMdPath = path.join(projectRoot, "owned_p_idols_obsidian.md");

async function run() {
  try {
    await client.connect();
    const db = client.db("gakumas-tools");
    const coll = db.collection("owned_p_idols");
    const idols = await coll.find({ rarity: "SSR" }).toArray();

    const plans = { "sense": {}, "logic": {}, "anomaly": {} };
    const planNames = { "sense": "Sense (センス)", "logic": "Logic (ロジック)", "anomaly": "Anomaly (アノマリー)" };
    const rarityOrder = { "SSR": 1, "SR": 2, "R": 3 };
    const idolOrder = {
      "花海 咲季": 1,
      "月村 手毬": 2,
      "藤田 ことね": 3,
      "雨夜 燕": 4,
      "有村 麻央": 5,
      "葛城 リーリヤ": 6,
      "倉本 千奈": 7,
      "紫雲 清夏": 8,
      "篠澤 広": 9,
      "十王 星南": 10,
      "秦谷 美鈴": 11,
      "花海 佑芽": 12,
      "姫崎 莉波": 13
    };
    
    for (const idol of idols) {
      const plan = idol.plan || "unknown";
      if (!plans[plan]) plans[plan] = {};
      
      const idolId = idol.idolId || 999;
      if (!plans[plan][idolId]) plans[plan][idolId] = { idol_name: idol.idol_name, cards: [] };
      
      plans[plan][idolId].cards.push(idol);
    }
    
    let md = "# 所有Pアイドル一覧（プラン・アイドル別）\n\n";
    md += "このマークダウンは、所有しているPアイドルをプランごと、アイドル順に整理し、アイコン画像をBase64形式で埋め込んだものです。\n\n";
    
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
          let imgCol = `No Image`;
          if (fs.existsSync(srcImage)) {
             const tmpImg = path.join(os.tmpdir(), `resized_${id}.png`);
             // Resize using macOS built-in sips command (height width)
             execSync(`sips -z 128 96 "${srcImage}" --out "${tmpImg}"`, { stdio: 'ignore' });
             const base64Data = fs.readFileSync(tmpImg, { encoding: 'base64' });
             fs.unlinkSync(tmpImg); // Clean up temp file
             
             // Use HTML img tag for resizing in Obsidian
             imgCol = `<img src="data:image/png;base64,${base64Data}" width="96" height="128" alt="${card.title}">`;
          }
          md += `| ${imgCol} | **${card.title}** | ${card.rarity} |\n`;
        }
        md += "\n";
      }
    }
    
    fs.writeFileSync(outputMdPath, md);
    console.log("Markdown created at " + outputMdPath);
  } finally {
    await client.close();
  }
}
run().catch(console.dir);
