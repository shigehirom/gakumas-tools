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

const EFFECT_TO_JA = {
  goodConditionTurns: '好調',
  concentration: '集中',
  goodImpressionTurns: '好印象',
  motivation: 'やる気',
  strength: '強気',
  fullPower: '全力',
  preservation: '温存'
};

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

  const idIdx = idxMap['ID'];
  const nameIdx = idxMap['アイドル名'] ?? idxMap['idol_name'];
  const titleIdx = idxMap['楽曲名'] ?? idxMap['カード名'] ?? idxMap['曲名'] ?? idxMap['衣装名'] ?? idxMap['title'];
  const rarityIdx = idxMap['レアリティ'] ?? idxMap['rarity'];
  const planIdx = idxMap['plan'] ?? idxMap['プラン'];
  const effectIdx = idxMap['recommended_effect'] ?? idxMap['得意効果'] ?? idxMap['recommendedEffect'] ?? idxMap['タイプ'];
  const ownedIdx = idxMap['is_owned'];
  const awakenIdx = idxMap['awaken_level'];
  const talentIdx = idxMap['talent_level'];
  const primaStellaIdx = Object.keys(idxMap).find(k => k.trim().startsWith('prima_stella')) !== undefined 
    ? idxMap[Object.keys(idxMap).find(k => k.trim().startsWith('prima_stella'))] 
    : undefined;

  // Check for missing P-idols from master
  const existingIds = new Set();
  const emptyTitleRows = [];

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (row && row[idIdx]) {
      const pid = parseInt(row[idIdx], 10);
      existingIds.add(pid);
      if (titleIdx !== undefined && (!row[titleIdx] || row[titleIdx].trim() === '')) {
        const p = pIdolsDict[pid.toString()];
        if (p && p.title) {
          const colLetter = String.fromCharCode(65 + titleIdx);
          emptyTitleRows.push({
            range: `P-Idols!${colLetter}${i + 1}`,
            values: [[p.title]],
            id: pid,
            title: p.title
          });
        }
      }
    }
  }

  // Auto-repair missing titles if any
  if (emptyTitleRows.length > 0) {
    console.log(`Found ${emptyTitleRows.length} P-Idols with missing titles. Repairing in Google Sheets...`);
    for (const item of emptyTitleRows) {
      console.log(`  + ID ${item.id}: Setting title -> 【${item.title}】 at ${item.range}`);
    }
    await sheets.spreadsheets.values.batchUpdate({
      spreadsheetId: SHEET_ID,
      requestBody: {
        valueInputOption: 'USER_ENTERED',
        data: emptyTitleRows.map(r => ({ range: r.range, values: r.values }))
      }
    });
    console.log(`[+] Successfully repaired ${emptyTitleRows.length} titles in Google Sheets!\n`);
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
      if (idIdx !== undefined) newRow[idIdx] = String(p.id);
      if (nameIdx !== undefined) newRow[nameIdx] = idol_name;
      if (titleIdx !== undefined) newRow[titleIdx] = p.title;
      if (rarityIdx !== undefined) newRow[rarityIdx] = p.rarity;
      if (planIdx !== undefined) newRow[planIdx] = p.plan;
      if (effectIdx !== undefined) newRow[effectIdx] = EFFECT_TO_JA[p.recommendedEffect] || p.recommendedEffect || '';
      if (ownedIdx !== undefined) newRow[ownedIdx] = 'FALSE';
      if (awakenIdx !== undefined) newRow[awakenIdx] = '0';
      if (talentIdx !== undefined) newRow[talentIdx] = '1';

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

  let client;
  try {
    client = new MongoClient(MONGODB_URI);
    await client.connect();
    console.log("Connected to MongoDB.");

    const db = client.db(MONGODB_DB);
    const collection = db.collection('owned_p_idols');
    const ownedIdolsCol = db.collection('owned_idols');

    // Fetch current idol status (STEP, produce_rank, ichibanboshi)
    const ownedIdolsList = await ownedIdolsCol.find({}).toArray();
    const idolStatusMap = new Map();
    ownedIdolsList.forEach(item => {
      idolStatusMap.set(item.id, {
        step: item.step,
        produce_rank: item.produce_rank,
        ichibanboshi: item.ichibanboshi
      });
    });

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
        const idolStatus = idolStatusMap.get(pIdolRef.idolId) || {};

        const isPrimaStella = primaStellaIdx !== undefined && row[primaStellaIdx] 
          ? (row[primaStellaIdx].trim().toLowerCase() === 'true' || row[primaStellaIdx].trim() === '1')
          : false;

        ownedPIdols.push({
          _id: idStr,
          id: parseInt(idStr, 10),
          idolId: pIdolRef.idolId,
          idol_name,
          title: pIdolRef.title,
          plan: pIdolRef.plan,
          recommendedEffect: pIdolRef.recommendedEffect,
          recommended_effect: EFFECT_TO_JA[pIdolRef.recommendedEffect] || pIdolRef.recommendedEffect || '',
          rarity,
          awaken_level,
          talent_level,
          prima_stella: isPrimaStella,
          step: idolStatus.step,
          produce_rank: idolStatus.produce_rank,
          ichibanboshi: idolStatus.ichibanboshi,
          skill_cards: associatedCards,
          updatedAt: new Date()
        });
      }
    }

    console.log(`Found ${ownedPIdols.length} owned P-Idols to synchronize.`);

    if (ownedPIdols.length === 0) {
      console.log("No owned P-Idols found. Exiting.");
      return;
    }

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
