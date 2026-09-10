import fs from 'fs';
import path from 'path';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const SHEET_ID = process.env.SYNC_SHEET_ID;
const SHEET_RANGE = 'P-Idols!A:Z';

const JSON_DIR = path.resolve(process.cwd(), 'packages/gakumas-data/json');
const PIDOLS_JSON_PATH = path.join(JSON_DIR, 'p_idols.json');
const IDOLS_JSON_PATH = path.join(JSON_DIR, 'idols.json');

async function checkPIdols() {
  const auth = await getAuthClient();
  const sheets = google.sheets({ version: 'v4', auth });
  
  const response = await sheets.spreadsheets.values.get({
    spreadsheetId: SHEET_ID,
    range: SHEET_RANGE,
  });
  
  const rows = response.data.values || [];
  if (rows.length === 0) {
    console.log("No rows found.");
    return;
  }
  
  const headers = rows[0];
  console.log("Headers:", headers);
  
  const existingIds = new Set();
  const planCounts = {};
  const effectCounts = {};
  let ownedCount = 0;

  const idxMap = {};
  headers.forEach((h, i) => idxMap[h] = i);

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    const id = row[idxMap['ID']];
    if (id) existingIds.add(parseInt(id, 10));

    const plan = row[idxMap['plan']] || '(empty)';
    planCounts[plan] = (planCounts[plan] || 0) + 1;

    const effect = row[idxMap['recommended_effect']] || '(empty)';
    effectCounts[effect] = (effectCounts[effect] || 0) + 1;

    if (row[idxMap['is_owned']] === 'TRUE' || row[idxMap['is_owned']] === 'true') {
      ownedCount++;
    }
  }
  
  console.log(`\nFound ${existingIds.size} existing P-Idols in spreadsheet (${ownedCount} owned).`);
  console.log("Plan distribution:", planCounts);
  console.log("Recommended effect distribution:", effectCounts);

  console.log("\nSample row 1:", rows[1]);
  console.log("Sample row 154 (last):", rows[rows.length - 1]);

  const pIdolsData = JSON.parse(fs.readFileSync(PIDOLS_JSON_PATH, 'utf8'));
  const idolsData = JSON.parse(fs.readFileSync(IDOLS_JSON_PATH, 'utf8'));
  const idolsMap = {};
  idolsData.forEach(item => idolsMap[item.id] = item.name);
  
  const missing = [];
  for (const p of pIdolsData) {
    if (!existingIds.has(p.id)) {
      missing.push({
        id: p.id,
        idol_name: idolsMap[p.idolId] || "",
        title: p.title,
        rarity: p.rarity,
        plan: p.plan
      });
    }
  }
  
  console.log(`\nMissing P-Idols in spreadsheet (${missing.length}):`);
  missing.forEach(m => {
    console.log(`  ID: ${m.id} | [${m.rarity}] ${m.idol_name} 【${m.title}】 (${m.plan})`);
  });
}

checkPIdols().catch(console.error);
