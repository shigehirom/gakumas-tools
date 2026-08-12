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

async function fixPIdolsSheet() {
  const auth = await getAuthClient();
  const sheets = google.sheets({ version: 'v4', auth });
  
  console.log("Fetching P-Idols from Google Sheets...");
  const response = await sheets.spreadsheets.values.get({
    spreadsheetId: SHEET_ID,
    range: SHEET_RANGE,
  });
  
  const rows = response.data.values || [];
  if (rows.length === 0) {
    console.log("No rows found.");
    return;
  }
  
  const headers = rows[0].map(h => h ? h.trim() : "");
  console.log("Headers:", headers);
  
  const idxMap = {};
  headers.forEach((h, i) => {
    if (h) idxMap[h] = i;
  });
  
  const idCol = idxMap['ID'];
  // Look for 楽曲名 or カード名 or タイトル
  let titleCol = idxMap['楽曲名'];
  if (titleCol === undefined) titleCol = idxMap['カード名'];
  if (titleCol === undefined) titleCol = idxMap['タイトル'];
  if (titleCol === undefined) titleCol = idxMap['title'];
  
  let idolCol = idxMap['アイドル名'];
  if (idolCol === undefined) idolCol = idxMap['idol_name'];
  
  let planCol = idxMap['プラン'];
  if (planCol === undefined) planCol = idxMap['plan'];
  
  let rarityCol = idxMap['レアリティ'];
  if (rarityCol === undefined) rarityCol = idxMap['rarity'];
  
  let effectCol = idxMap['得意効果'];
  if (effectCol === undefined) effectCol = idxMap['recommendedEffect'];

  console.log({ idCol, titleCol, idolCol, planCol, rarityCol, effectCol });
  
  const pIdolsData = JSON.parse(fs.readFileSync(PIDOLS_JSON_PATH, 'utf8'));
  const idolsData = JSON.parse(fs.readFileSync(IDOLS_JSON_PATH, 'utf8'));
  const pIdolsMap = {};
  pIdolsData.forEach(p => pIdolsMap[p.id] = p);
  const idolsMap = {};
  idolsData.forEach(i => idolsMap[i.id] = i.name);
  
  let fixedCount = 0;
  const updatedRows = [rows[0]];
  
  for (let i = 1; i < rows.length; i++) {
    const row = [...rows[i]];
    // pad row if needed
    while (row.length < headers.length) row.push('');
    
    const idStr = row[idCol];
    if (idStr) {
      const pId = parseInt(idStr, 10);
      const ref = pIdolsMap[pId];
      if (ref) {
        let rowModified = false;
        
        // Fix title / 楽曲名
        if (titleCol !== undefined) {
          const curTitle = (row[titleCol] || '').trim();
          if (!curTitle && ref.title) {
            console.log(`[Fix Title] Row ${i+1} (ID ${pId}): '' -> '${ref.title}'`);
            row[titleCol] = ref.title;
            rowModified = true;
          }
        }
        
        // Fix idol name
        if (idolCol !== undefined) {
          const curIdol = (row[idolCol] || '').trim();
          const targetIdol = idolsMap[ref.idolId] || '';
          if (!curIdol && targetIdol) {
            console.log(`[Fix Idol] Row ${i+1} (ID ${pId}): '' -> '${targetIdol}'`);
            row[idolCol] = targetIdol;
            rowModified = true;
          }
        }
        
        // Fix plan
        if (planCol !== undefined) {
          const curPlan = (row[planCol] || '').trim();
          if (!curPlan && ref.plan) {
            row[planCol] = ref.plan;
            rowModified = true;
          }
        }
        
        // Fix rarity
        if (rarityCol !== undefined) {
          const curRarity = (row[rarityCol] || '').trim();
          if (!curRarity && ref.rarity) {
            row[rarityCol] = ref.rarity;
            rowModified = true;
          }
        }
        
        // Fix recommendedEffect
        if (effectCol !== undefined) {
          const curEffect = (row[effectCol] || '').trim();
          if (!curEffect && ref.recommendedEffect) {
            row[effectCol] = ref.recommendedEffect;
            rowModified = true;
          }
        }
        
        if (rowModified) fixedCount++;
      }
    }
    updatedRows.push(row);
  }
  
  console.log(`\nFound ${fixedCount} rows to fix.`);
  
  if (process.argv.includes('--execute')) {
    console.log("Updating spreadsheet...");
    await sheets.spreadsheets.values.update({
      spreadsheetId: SHEET_ID,
      range: SHEET_RANGE,
      valueInputOption: 'USER_ENTERED',
      requestBody: {
        values: updatedRows,
      },
    });
    console.log("[+] Successfully updated spreadsheet!");
  } else {
    console.log("[DRY RUN] Run with '--execute' to apply changes to Google Sheets.");
  }
}

fixPIdolsSheet().catch(console.error);
