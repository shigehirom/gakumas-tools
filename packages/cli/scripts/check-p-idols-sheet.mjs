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
  for (let i = 1; i < rows.length; i++) {
    const id = rows[i][0];
    if (id) existingIds.add(parseInt(id, 10));
  }
  
  console.log(`Found ${existingIds.size} existing P-Idols in spreadsheet.`);
  
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
