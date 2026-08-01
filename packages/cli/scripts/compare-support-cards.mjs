import fs from 'fs';
import path from 'path';
import { MongoClient } from 'mongodb';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const MONGODB_URI = process.env.MONGODB_URI;
const MONGODB_DB = process.env.MONGODB_DB || 'gakumas';
const SHEET_ID = process.env.SYNC_SHEET_ID;
const SHEET_RANGE = 'Support-Cards!A:Z';

if (!MONGODB_URI) {
  console.error("Error: MONGODB_URI is not set in .env.local");
  process.exit(1);
}

if (!SHEET_ID) {
  console.error("Error: SYNC_SHEET_ID is not set in .env.local");
  process.exit(1);
}

async function main() {
  let auth;
  try {
    auth = await getAuthClient();
  } catch (err) {
    console.error("Google Sheets authentication failed.");
    process.exit(1);
  }

  const sheets = google.sheets({ version: 'v4', auth });
  
  console.log("Fetching from Google Sheets...");
  let response;
  try {
    response = await sheets.spreadsheets.values.get({
      spreadsheetId: SHEET_ID,
      range: SHEET_RANGE,
    });
  } catch (err) {
    console.error('Sheets API Error:', err.message);
    process.exit(1);
  }

  const rows = response.data.values;
  if (!rows || rows.length === 0) {
    console.error('No sheet data found.');
    process.exit(1);
  }

  const headers = rows[0].map(h => h.trim());
  const idxMap = {};
  headers.forEach((h, i) => idxMap[h] = i);

  if (idxMap['card_name'] === undefined || idxMap['is_owned'] === undefined) {
    console.error('Spreadsheet is missing required columns (card_name, is_owned).');
    process.exit(1);
  }

  // Sheets owned cards map
  const sheetOwned = new Map();
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row || row.length === 0) continue;
    const cardName = row[idxMap['card_name']];
    if (!cardName) continue;

    const isOwnedStr = row[idxMap['is_owned']] ? row[idxMap['is_owned']].trim().toLowerCase() : '';
    const isOwned = isOwnedStr && isOwnedStr !== 'false' && isOwnedStr !== '0' && isOwnedStr !== 'no';
    
    if (isOwned) {
      const lv = parseInt(row[idxMap['lv']] || '1', 10);
      const uncap = parseInt(row[idxMap['uncap']] || '0', 10);
      sheetOwned.set(cardName, { lv, uncap });
    }
  }

  // MongoDB owned cards map
  console.log("Connecting to MongoDB and loading data...");
  const client = new MongoClient(MONGODB_URI);
  await client.connect();
  const db = client.db(MONGODB_DB);
  const collection = db.collection('owned_support_cards');
  const dbCards = await collection.find({}).toArray();
  await client.close();

  const dbOwned = new Map();
  dbCards.forEach(c => {
    dbOwned.set(c.card_name, { lv: c.lv, uncap: c.uncap, id: c._id });
  });

  // Comparisons
  const onlyInSheet = [];
  const onlyInDb = [];
  const mismatches = [];

  for (const [cardName, sheetData] of sheetOwned.entries()) {
    if (!dbOwned.has(cardName)) {
      onlyInSheet.push({ name: cardName, ...sheetData });
    } else {
      const dbData = dbOwned.get(cardName);
      if (sheetData.lv !== dbData.lv || sheetData.uncap !== dbData.uncap) {
        mismatches.push({
          name: cardName,
          sheet: sheetData,
          db: dbData
        });
      }
    }
  }

  for (const [cardName, dbData] of dbOwned.entries()) {
    if (!sheetOwned.has(cardName)) {
      onlyInDb.push({ name: cardName, ...dbData });
    }
  }

  // Output markdown report
  console.log("\n## ■ スプレッドシート vs MongoDB 所持サポートカード比較レポート\n");
  console.log(`- **スプレッドシート上の所持カード数**: ${sheetOwned.size} 件`);
  console.log(`- **MongoDB上の所持カード数**: ${dbOwned.size} 件\n`);

  if (onlyInSheet.length === 0 && onlyInDb.length === 0 && mismatches.length === 0) {
    console.log("✨ **完全に一致しています！** スプレッドシートと MongoDB のデータは同期されています。");
    return;
  }

  if (onlyInSheet.length > 0) {
    console.log("### ⚠️ スプレッドシートのみに存在する（MongoDBに未同期の）カード");
    console.log("| カード名 | Lv | 特訓 (uncap) |");
    console.log("| :--- | :---: | :---: |");
    onlyInSheet.forEach(c => {
      console.log(`| ${c.name} | ${c.lv} | ${c.uncap} |`);
    });
    console.log();
  }

  if (onlyInDb.length > 0) {
    console.log("### ⚠️ MongoDBのみに存在する（スプレッドシートで所持から外れた？）カード");
    console.log("| カード名 | ID | Lv | 特訓 (uncap) |");
    console.log("| :--- | :--- | :---: | :---: |");
    onlyInDb.forEach(c => {
      console.log(`| ${c.name} | ${c.id} | ${c.lv} | ${c.uncap} |`);
    });
    console.log();
  }

  if (mismatches.length > 0) {
    console.log("### ⚠️ パラメータ（Lv / 特訓数）が一致しないカード");
    console.log("| カード名 | スプレッドシート (Lv / 特訓) | MongoDB (Lv / 特訓) |");
    console.log("| :--- | :---: | :---: |");
    mismatches.forEach(c => {
      console.log(`| ${c.name} | ${c.sheet.lv} / ${c.sheet.uncap} | ${c.db.lv} / ${c.db.uncap} |`);
    });
    console.log();
  }

  console.log("\n**※同期するには以下を実行してください:**");
  console.log("```bash\nnode packages/cli/scripts/compare-support-cards.mjs --force\n```");
  console.log("※ または `node packages/cli/scripts/sync-support-cards.mjs --force` を実行して同期を上書きします。");
}

main().catch(console.error);
