import fs from 'fs';
import path from 'path';
import { MongoClient } from 'mongodb';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const MONGODB_URI = process.env.MONGODB_URI;
const MONGODB_DB = process.env.MONGODB_DB || 'gakumas';
const SHEET_ID = process.env.SYNC_SHEET_ID;
const SHEET_RANGE = 'P-Idols!A:Z';

const JSON_DIR = path.resolve(process.cwd(), 'packages/gakumas-data/json');
const PIDOLS_JSON_PATH = path.join(JSON_DIR, 'p_idols.json');
const SKILLCARDS_JSON_PATH = path.join(JSON_DIR, 'skill_cards.json');
const IDOLS_JSON_PATH = path.join(JSON_DIR, 'idols.json');

if (!MONGODB_URI) {
  console.error("Error: MONGODB_URI is not set in .env.local");
  process.exit(1);
}

if (!SHEET_ID) {
  console.error("Error: SYNC_SHEET_ID is not set in .env.local");
  process.exit(1);
}

const args = process.argv.slice(2);
const force = args.includes('--force');
const exportMode = args.includes('--export');

async function main() {
  let auth;
  try {
    auth = await getAuthClient();
  } catch (err) {
    console.error("Authentication failed.");
    process.exit(1);
  }

  // Load JSON reference data
  let pIdolsDict = {};
  if (fs.existsSync(PIDOLS_JSON_PATH)) {
    const data = JSON.parse(fs.readFileSync(PIDOLS_JSON_PATH, 'utf8'));
    data.forEach(item => {
      // Use string keys to ensure matches
      pIdolsDict[item.id.toString()] = item;
    });
  } else {
    console.error(`Error: Reference JSON not found at ${PIDOLS_JSON_PATH}`);
    process.exit(1);
  }

  let skillCardsData = [];
  if (fs.existsSync(SKILLCARDS_JSON_PATH)) {
    skillCardsData = JSON.parse(fs.readFileSync(SKILLCARDS_JSON_PATH, 'utf8'));
  } else {
    console.error(`Error: Reference JSON not found at ${SKILLCARDS_JSON_PATH}`);
    process.exit(1);
  }

  let idolsDict = {};
  if (fs.existsSync(IDOLS_JSON_PATH)) {
    const data = JSON.parse(fs.readFileSync(IDOLS_JSON_PATH, 'utf8'));
    data.forEach(item => {
      idolsDict[item.id.toString()] = item;
    });
  } else {
    console.error(`Error: Reference JSON not found at ${IDOLS_JSON_PATH}`);
    process.exit(1);
  }

  const sheets = google.sheets({ version: 'v4', auth });
  
  console.log(`Fetching data from Google Sheets (ID: ${SHEET_ID}, Range: ${SHEET_RANGE})...`);
  let response;
  try {
    response = await sheets.spreadsheets.values.get({
      spreadsheetId: SHEET_ID,
      range: SHEET_RANGE,
    });
  } catch (err) {
    console.error('The API returned an error:', err.message);
    process.exit(1);
  }

  const rows = response.data.values;
  if (!rows || rows.length === 0) {
    console.log('No data found in the spreadsheet.');
    process.exit(1);
  }

  const headers = rows[0].map(h => h.trim());
  const idxMap = {};
  headers.forEach((h, i) => idxMap[h] = i);

  if (idxMap['ID'] === undefined || idxMap['is_owned'] === undefined) {
    console.error('Spreadsheet is missing required columns (ID, is_owned).');
    process.exit(1);
  }

  // Check for missing P-idols from master
  const existingIds = new Set();
  for (let i = 1; i < rows.length; i++) {
    if (rows[i] && rows[i][idxMap['ID']]) {
      existingIds.add(parseInt(rows[i][idxMap['ID']], 10));
    }
  }

  const allPIdolList = Object.values(pIdolsDict);
  const missingPIdols = allPIdolList.filter(p => !existingIds.has(p.id));

  if (exportMode) {
    if (missingPIdols.length === 0) {
      console.log("All P-Idols from gakumas-tools master are already present in Google Sheets!");
      process.exit(0);
    }

    console.log(`\nFound ${missingPIdols.length} new P-Idols to add to Google Sheets:`);
    const newRows = [];
    for (const p of missingPIdols) {
      const baseIdol = idolsDict[p.idolId.toString()];
      const idol_name = baseIdol ? baseIdol.name : "";
      console.log(`  + ID: ${p.id} | [${p.rarity}] ${idol_name} 【${p.title}】 (${p.plan})`);

      const newRow = new Array(headers.length).fill('');
      if (idxMap['ID'] !== undefined) newRow[idxMap['ID']] = String(p.id);
      if (idxMap['アイドル名'] !== undefined) newRow[idxMap['アイドル名']] = idol_name;
      else if (idxMap['idol_name'] !== undefined) newRow[idxMap['idol_name']] = idol_name;
      if (idxMap['カード名'] !== undefined) newRow[idxMap['カード名']] = p.title;
      else if (idxMap['title'] !== undefined) newRow[idxMap['title']] = p.title;
      if (idxMap['レアリティ'] !== undefined) newRow[idxMap['レアリティ']] = p.rarity;
      else if (idxMap['rarity'] !== undefined) newRow[idxMap['rarity']] = p.rarity;
      if (idxMap['プラン'] !== undefined) newRow[idxMap['プラン']] = p.plan;
      else if (idxMap['plan'] !== undefined) newRow[idxMap['plan']] = p.plan;
      if (idxMap['得意効果'] !== undefined) newRow[idxMap['得意効果']] = p.recommendedEffect || '';
      else if (idxMap['recommendedEffect'] !== undefined) newRow[idxMap['recommendedEffect']] = p.recommendedEffect || '';
      if (idxMap['is_owned'] !== undefined) newRow[idxMap['is_owned']] = 'FALSE';
      if (idxMap['awaken_level'] !== undefined) newRow[idxMap['awaken_level']] = '0';
      if (idxMap['talent_level'] !== undefined) newRow[idxMap['talent_level']] = '1';

      newRows.push(newRow);
    }

    console.log(`\nAppending ${newRows.length} rows to Google Sheets 'P-Idols' tab...`);
    await sheets.spreadsheets.values.append({
      spreadsheetId: SHEET_ID,
      range: 'P-Idols!A:Z',
      valueInputOption: 'USER_ENTERED',
      requestBody: {
        values: newRows,
      },
    });

    console.log(`[+] Successfully added ${newRows.length} P-Idols to Google Sheets!`);
    process.exit(0);
  }

  if (missingPIdols.length > 0) {
    console.log(`[Info] There are ${missingPIdols.length} new P-Idols available in gakumas-tools. Run with '--export' to append them to Google Sheets.`);
  }

  const ownedPIdols = [];

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row || row.length === 0) continue;

    const isOwnedStr = row[idxMap['is_owned']] ? row[idxMap['is_owned']].trim().toLowerCase() : '';
    
    // Check if is_owned is truthy (e.g. TRUE, true, 1, yes, o, ○, etc.)
    if (isOwnedStr && isOwnedStr !== 'false' && isOwnedStr !== '0' && isOwnedStr !== 'no') {
      const idStr = row[idxMap['ID']];
      if (!idStr) continue;

      const pIdolRef = pIdolsDict[idStr];
      if (!pIdolRef) {
        console.warn(`Warning: P-Idol with ID ${idStr} not found in p_idols.json`);
        continue;
      }

      const rarity = row[idxMap['レアリティ']] || pIdolRef.rarity;
      const awaken_level = parseInt(row[idxMap['awaken_level']] || '0', 10);
      const talent_level = parseInt(row[idxMap['talent_level']] || '1', 10);

      // Find associated skill cards
      // sourceType == 'pIdol' and pIdolId == id
      const associatedCards = skillCardsData.filter(card => 
        card.sourceType === 'pIdol' && String(card.pIdolId) === idStr
      );

      const baseIdol = idolsDict[pIdolRef.idolId.toString()];
      const idol_name = baseIdol ? baseIdol.name : "";

      ownedPIdols.push({
        _id: idStr,
        id: parseInt(idStr, 10),
        idolId: pIdolRef.idolId,
        idol_name,
        title: pIdolRef.title,
        plan: pIdolRef.plan,
        recommendedEffect: pIdolRef.recommendedEffect,
        rarity,
        awaken_level,
        talent_level,
        skill_cards: associatedCards,
        updatedAt: new Date()
      });
    }
  }

  console.log(`Found ${ownedPIdols.length} owned P-Idols to synchronize.`);

  if (ownedPIdols.length === 0) {
    console.log("No owned P-Idols found. Exiting.");
    process.exit(0);
  }

  let client;
  try {
    client = new MongoClient(MONGODB_URI);
    await client.connect();
    console.log("Connected to MongoDB.");

    const db = client.db(MONGODB_DB);
    const collection = db.collection('owned_p_idols');

    if (force) {
      console.log("--force flag provided. Dropping existing collection...");
      try {
        await collection.drop();
        console.log("Collection dropped.");
      } catch (err) {
        if (err.codeName !== 'NamespaceNotFound') {
          throw err;
        }
      }
    }

    let successCount = 0;
    for (const idol of ownedPIdols) {
      try {
        await collection.updateOne(
          { _id: idol._id },
          { $set: idol },
          { upsert: true }
        );
        successCount++;
      } catch (err) {
        console.error(`Failed to upsert P-Idol ID: ${idol._id}`, err.message);
      }
    }

    console.log(`Successfully synchronized ${successCount}/${ownedPIdols.length} P-Idols.`);
  } catch (err) {
    console.error("Database connection or operation failed:", err);
  } finally {
    if (client) {
      await client.close();
      console.log("MongoDB connection closed.");
    }
  }
}

main();
