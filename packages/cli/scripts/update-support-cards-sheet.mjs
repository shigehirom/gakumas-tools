import fs from 'fs';
import path from 'path';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const SHEET_ID = process.env.SYNC_SHEET_ID;
const SHEET_RANGE = 'Support-Cards!A:Z';
const CSV_PATH = '/Users/shigehiro/gakumas-workspace/gakumas-support_cards/support_cards.csv';
const JSON_DIR = '/Users/shigehiro/gakumas-workspace/gakumas-support_cards/support_cards';

if (!SHEET_ID) {
  console.error("Error: SYNC_SHEET_ID is not set in .env.local");
  process.exit(1);
}

// 簡単なCSVパーサー (カンマ区切り)
function parseCSV(content) {
  const lines = content.trim().split('\n');
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map(h => h.trim());
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(',').map(v => v.trim());
    const row = {};
    headers.forEach((h, idx) => {
      row[h] = values[idx] || '';
    });
    rows.push(row);
  }
  return rows;
}

async function main() {
  console.log("Reading CSV...");
  let csvContent = "";
  try {
    csvContent = fs.readFileSync(CSV_PATH, 'utf8');
  } catch (err) {
    console.error("Failed to read CSV:", err.message);
    process.exit(1);
  }
  
  const csvCards = parseCSV(csvContent);
  console.log(`Found ${csvCards.length} cards in CSV.`);

  let auth;
  try {
    auth = await getAuthClient();
  } catch (err) {
    console.error("Authentication failed.", err);
    process.exit(1);
  }

  const sheets = google.sheets({ version: 'v4', auth });
  
  console.log(`Fetching existing data from Google Sheets...`);
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

  const rows = response.data.values || [];
  if (rows.length === 0) {
    console.error('No data found in the spreadsheet. Expected headers.');
    process.exit(1);
  }

  const headers = rows[0].map(h => h.trim());
  const idxMap = {};
  headers.forEach((h, i) => idxMap[h] = i);

  if (idxMap['card_name'] === undefined) {
    console.error('Spreadsheet is missing required column: card_name');
    process.exit(1);
  }

  // 既存のカード名をセットに格納 (表記揺れ対策として、♡の変換なども考慮可能だが一旦そのまま比較)
  const existingCardNames = new Set();
  const updatesToPerform = [];
  const colLetter = (colName) => String.fromCharCode(65 + (idxMap[colName] || 0));

  for (let i = 1; i < rows.length; i++) {
    if (rows[i] && rows[i][idxMap['card_name']]) {
      const cName = rows[i][idxMap['card_name']];
      existingCardNames.add(cName);
      const rowNumber = i + 1;
      
      // First, ensure we have the wiki_id for this card
      let currentWikiId = '';
      if (idxMap['wiki_id'] !== undefined) {
        const wId = rows[i][idxMap['wiki_id']];
        if (!wId || wId.trim() === '') {
          const csvCard = csvCards.find(c => c.name === cName || c.name.replace(/♡/g, '&#9825;') === cName || c.name.replace(/&#9825;/g, '♡') === cName);
          if (csvCard && csvCard.wiki_id) {
            currentWikiId = csvCard.wiki_id;
            updatesToPerform.push({
              range: `Support-Cards!${colLetter('wiki_id')}${rowNumber}`,
              values: [[currentWikiId]]
            });
          }
        } else {
          currentWikiId = wId;
        }
      }

      // JSONを読み込んで plan_restriction, type などの情報を取得しておく
      let planRestriction = '';
      let type = '';
      
      if (currentWikiId) {
        const jsonPath = path.join(JSON_DIR, `${currentWikiId}.json`);
        if (fs.existsSync(jsonPath)) {
          try {
            const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
            const cardData = Array.isArray(data) ? data[0] : data;
            if (cardData) {
              planRestriction = cardData.plan_restriction || '';
              type = cardData.type || '';
            }
          } catch(e) {}
        }
      }
      
      // Check plan_restriction
      if (idxMap['plan_restriction'] !== undefined) {
        const pRest = rows[i][idxMap['plan_restriction']];
        if ((!pRest || pRest.trim() === '') && planRestriction) {
          updatesToPerform.push({
            range: `Support-Cards!${colLetter('plan_restriction')}${rowNumber}`,
            values: [[planRestriction]]
          });
        }
      }

      // Check type
      if (idxMap['type'] !== undefined) {
        const tVal = rows[i][idxMap['type']];
        if ((!tVal || tVal.trim() === '') && type) {
          updatesToPerform.push({
            range: `Support-Cards!${colLetter('type')}${rowNumber}`,
            values: [[type]]
          });
        }
      }
    }
  }

  console.log(`Found ${existingCardNames.size} existing cards in the sheet.`);

  const newRowsToAppend = [];
  
  // CSVのカードをループし、シートにないものを抽出
  for (const card of csvCards) {
    let cardName = card.name;
    
    // 表記揺れの対応 ("♡" と "&#9825;")
    // シート側がどちらで登録されているか分からないため、両方チェックする
    const altName = cardName.replace(/♡/g, '&#9825;');
    const altName2 = cardName.replace(/&#9825;/g, '♡');
    
    if (!existingCardNames.has(cardName) && !existingCardNames.has(altName) && !existingCardNames.has(altName2)) {
      // JSONを読み込んで plan_restriction, type などの補足情報を取得
      let planRestriction = '';
      let type = '';
      let wikiId = card.wiki_id || cardName; // CSVから直接取得
      
      const jsonPath = path.join(JSON_DIR, `${cardName}.json`);
      if (fs.existsSync(jsonPath)) {
        try {
          const jsonContent = fs.readFileSync(jsonPath, 'utf8');
          const data = JSON.parse(jsonContent);
          const cardData = Array.isArray(data) ? data[0] : data;
          if (cardData) {
            planRestriction = cardData.plan_restriction || '';
            type = cardData.type || '';
            // if (cardData.wiki_id) wikiId = cardData.wiki_id; // CSVの方が確実
          }
        } catch(e) {}
      } else {
        // 代替ファイル名
        const altPath = path.join(JSON_DIR, `${altName}.json`);
        if (fs.existsSync(altPath)) {
          try {
            const jsonContent = fs.readFileSync(altPath, 'utf8');
            const data = JSON.parse(jsonContent);
            const cardData = Array.isArray(data) ? data[0] : data;
            if (cardData) {
              planRestriction = cardData.plan_restriction || '';
              type = cardData.type || '';
              if (cardData.wiki_id) wikiId = cardData.wiki_id;
            }
          } catch(e) {}
        }
      }
      
      // シートのヘッダー順に合わせて配列を作成
      // ヘッダーにない列は空にする
      const newRow = new Array(headers.length).fill('');
      
      if (idxMap['wiki_id'] !== undefined) newRow[idxMap['wiki_id']] = wikiId;
      if (idxMap['card_name'] !== undefined) newRow[idxMap['card_name']] = cardName;
      if (idxMap['rarity'] !== undefined) newRow[idxMap['rarity']] = card.rarity;
      if (idxMap['plan_restriction'] !== undefined) newRow[idxMap['plan_restriction']] = planRestriction;
      if (idxMap['type'] !== undefined) newRow[idxMap['type']] = type;
      if (idxMap['is_owned'] !== undefined) newRow[idxMap['is_owned']] = 'FALSE'; // デフォルトは未所持
      if (idxMap['uncap'] !== undefined) newRow[idxMap['uncap']] = '0';
      if (idxMap['lv'] !== undefined) newRow[idxMap['lv']] = '1';
      
      newRowsToAppend.push(newRow);
      console.log(`Adding new card: ${cardName}`);
    }
  }

  if (newRowsToAppend.length === 0) {
    console.log("No new cards to append.");
  } else {
    console.log(`Appending ${newRowsToAppend.length} new cards to the spreadsheet...`);
    try {
      await sheets.spreadsheets.values.append({
        spreadsheetId: SHEET_ID,
        range: SHEET_RANGE,
        valueInputOption: 'USER_ENTERED',
        requestBody: {
          values: newRowsToAppend,
        },
      });
      console.log("Successfully appended new cards.");
    } catch (err) {
      console.error("Failed to append to spreadsheet:", err.message);
    }
  }

  if (updatesToPerform.length > 0) {
    console.log(`Patching ${updatesToPerform.length} missing fields...`);
    try {
      await sheets.spreadsheets.values.batchUpdate({
        spreadsheetId: SHEET_ID,
        requestBody: {
          valueInputOption: 'USER_ENTERED',
          data: updatesToPerform
        }
      });
      console.log("Successfully patched missing fields.");
    } catch (err) {
      console.error("Failed to patch fields:", err.message);
    }
  }
  
  if (newRowsToAppend.length === 0 && updatesToPerform.length === 0) {
    console.log("The spreadsheet is fully up-to-date.");
  }
}

main();
