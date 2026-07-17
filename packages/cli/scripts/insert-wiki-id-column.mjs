import fs from 'fs';
import path from 'path';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const SHEET_ID = process.env.SYNC_SHEET_ID;
const SHEET_NAME = 'Support-Cards';
const SHEET_RANGE = `${SHEET_NAME}!A:Z`;
const JSON_DIR = '/Users/shigehiro/gakumas-workspace/gakumas-support_cards/support_cards';

if (!SHEET_ID) {
  console.error("Error: SYNC_SHEET_ID is not set in .env.local");
  process.exit(1);
}

async function main() {
  let auth;
  try {
    auth = await getAuthClient();
  } catch (err) {
    console.error("Authentication failed.", err);
    process.exit(1);
  }

  const sheets = google.sheets({ version: 'v4', auth });
  
  // 1. Get sheetId
  console.log(`Fetching spreadsheet metadata to find sheetId for '${SHEET_NAME}'...`);
  const metaResponse = await sheets.spreadsheets.get({
    spreadsheetId: SHEET_ID,
  });
  
  const sheet = metaResponse.data.sheets.find(s => s.properties.title === SHEET_NAME);
  if (!sheet) {
    console.error(`Sheet '${SHEET_NAME}' not found.`);
    process.exit(1);
  }
  const sheetId = sheet.properties.sheetId;
  console.log(`Found sheetId: ${sheetId}`);

  // 2. Fetch existing data to prepare wiki_id values
  console.log(`Fetching current data from ${SHEET_RANGE}...`);
  const response = await sheets.spreadsheets.values.get({
    spreadsheetId: SHEET_ID,
    range: SHEET_RANGE,
  });

  const rows = response.data.values || [];
  if (rows.length === 0) {
    console.error('No data found in the spreadsheet.');
    process.exit(1);
  }

  const headers = rows[0].map(h => h.trim());
  const cardNameIdx = headers.indexOf('card_name');
  if (cardNameIdx === -1) {
    console.error('Could not find card_name column.');
    process.exit(1);
  }
  
  // Read CSV for wiki_id mapping
  console.log("Reading CSV mapping...");
  const csvPath = '/Users/shigehiro/gakumas-workspace/gakumas-support_cards/support_cards.csv';
  const csvContent = fs.readFileSync(csvPath, 'utf8');
  const csvLines = csvContent.trim().split('\n');
  const csvMap = {};
  if (csvLines.length > 1) {
    const csvHeaders = csvLines[0].split(',').map(h => h.trim());
    const nameIdx = csvHeaders.indexOf('name');
    const wikiIdIdx = csvHeaders.indexOf('wiki_id');
    for (let i = 1; i < csvLines.length; i++) {
      const vals = csvLines[i].split(',').map(v => v.trim());
      if (nameIdx !== -1 && wikiIdIdx !== -1) {
        csvMap[vals[nameIdx]] = vals[wikiIdIdx];
      }
    }
  }
  
  // 既に wiki_id があるか確認 (A列が wiki_id であること前提)
  if (headers[0] !== 'wiki_id') {
    console.log("First column is not wiki_id. Aborting to prevent overwriting wrong column.");
    process.exit(1);
  }

  const newColumnValues = [['wiki_id']];
  
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row || row.length === 0) {
      newColumnValues.push(['']);
      continue;
    }
    
    // card_name のインデックスから取得
    const cardName = row[cardNameIdx];
    if (!cardName) {
      newColumnValues.push(['']);
      continue;
    }

    let wikiId = csvMap[cardName];
    if (!wikiId) {
      const altName = cardName.replace(/♡/g, '&#9825;');
      const altName2 = cardName.replace(/&#9825;/g, '♡');
      if (csvMap[altName]) wikiId = csvMap[altName];
      else if (csvMap[altName2]) wikiId = csvMap[altName2];
    }
    
    // フォールバック
    if (!wikiId) {
      wikiId = cardName;
    }
    
    newColumnValues.push([wikiId]);
  }

  // 4. Update the existing Column A with wiki_id values
  console.log("Populating Column A with correct wiki_id values from CSV...");
  try {
    await sheets.spreadsheets.values.update({
      spreadsheetId: SHEET_ID,
      range: `${SHEET_NAME}!A1:A${newColumnValues.length}`,
      valueInputOption: 'USER_ENTERED',
      requestBody: {
        values: newColumnValues
      }
    });
    console.log("Successfully populated wiki_id column.");
  } catch (err) {
    console.error("Failed to update wiki_id values:", err.message);
  }
}

main();
