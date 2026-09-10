import fs from 'fs';
import path from 'path';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const SHEET_ID = process.env.SYNC_SHEET_ID;
const SHEET_RANGE = 'P-Idols!A:Z';

const JSON_DIR = path.resolve(process.cwd(), 'packages/gakumas-data/json');
const PIDOLS_JSON_PATH = path.join(JSON_DIR, 'p_idols.json');

const EFFECT_TO_JA = {
  goodConditionTurns: '好調',
  concentration: '集中',
  goodImpressionTurns: '好印象',
  motivation: 'やる気',
  strength: '強気',
  fullPower: '全力',
  preservation: '温存'
};

async function main() {
  if (!SHEET_ID) {
    console.error("Error: SYNC_SHEET_ID is not set.");
    process.exit(1);
  }

  if (!fs.existsSync(PIDOLS_JSON_PATH)) {
    console.error(`Error: p_idols.json not found at ${PIDOLS_JSON_PATH}`);
    process.exit(1);
  }

  const pIdolsData = JSON.parse(fs.readFileSync(PIDOLS_JSON_PATH, 'utf8'));
  const pIdolsMap = new Map();
  pIdolsData.forEach(p => pIdolsMap.set(String(p.id), p));

  const auth = await getAuthClient();
  const sheets = google.sheets({ version: 'v4', auth });

  console.log(`Fetching existing P-Idols sheet data (Sheet ID: ${SHEET_ID})...`);
  const response = await sheets.spreadsheets.values.get({
    spreadsheetId: SHEET_ID,
    range: SHEET_RANGE,
  });

  const rows = response.data.values || [];
  if (rows.length === 0) {
    console.error("No data found in P-Idols sheet.");
    process.exit(1);
  }

  // Backup existing data locally
  const backupPath = path.resolve(process.cwd(), 'scratch/p_idols_sheet_backup.json');
  fs.mkdirSync(path.dirname(backupPath), { recursive: true });
  fs.writeFileSync(backupPath, JSON.stringify(rows, null, 2), 'utf8');
  console.log(`[Backup] Saved existing sheet data to: ${backupPath}`);

  const originalHeaders = rows[0].map(h => h.trim());
  console.log("Original Headers:", originalHeaders);

  const idxMap = {};
  originalHeaders.forEach((h, i) => idxMap[h] = i);

  const idIdx = idxMap['ID'];
  const nameIdx = idxMap['アイドル名'] ?? idxMap['idol_name'];
  const titleIdx = idxMap['楽曲名'] ?? idxMap['カード名'] ?? idxMap['曲名'] ?? idxMap['衣装名'] ?? idxMap['title'];
  const rarityIdx = idxMap['レアリティ'] ?? idxMap['rarity'];
  const ownedIdx = idxMap['is_owned'];
  const awakenIdx = idxMap['awaken_level'];
  const talentIdx = idxMap['talent_level'];

  if (idIdx === undefined || ownedIdx === undefined) {
    console.error("Missing critical columns in sheet (ID, is_owned).");
    process.exit(1);
  }

  const newHeaders = [
    'ID',
    'アイドル名',
    '楽曲名',
    'レアリティ',
    'plan',
    'recommended_effect',
    'is_owned',
    'awaken_level',
    'talent_level'
  ];

  const newRows = [newHeaders];

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row || row.length === 0) continue;

    const idStr = row[idIdx]?.trim();
    if (!idStr) continue;

    const p = pIdolsMap.get(idStr);
    const planVal = p ? p.plan : '';
    const effectRaw = p ? p.recommendedEffect : '';
    const effectJa = EFFECT_TO_JA[effectRaw] || effectRaw || '';

    const newRow = [
      idStr,
      (nameIdx !== undefined ? row[nameIdx] : '') || '',
      (titleIdx !== undefined ? row[titleIdx] : '') || '',
      (rarityIdx !== undefined ? row[rarityIdx] : (p?.rarity || '')) || '',
      planVal,
      effectJa,
      (ownedIdx !== undefined ? row[ownedIdx] : 'FALSE') || 'FALSE',
      (awakenIdx !== undefined ? row[awakenIdx] : '1') || '1',
      (talentIdx !== undefined ? row[talentIdx] : '1') || '1'
    ];

    newRows.push(newRow);
  }

  console.log(`Prepared ${newRows.length - 1} rows with new columns (plan, recommended_effect).`);
  console.log("Sample new row 1:", newRows[1]);
  console.log("Sample new row 2:", newRows[2]);

  // Update Google Sheets P-Idols sheet
  console.log(`Writing updated data to P-Idols!A1:I${newRows.length}...`);
  await sheets.spreadsheets.values.update({
    spreadsheetId: SHEET_ID,
    range: `P-Idols!A1:I${newRows.length}`,
    valueInputOption: 'USER_ENTERED',
    requestBody: {
      values: newRows
    }
  });

  console.log(`[+] Successfully updated P-Idols sheet with ${newRows.length} rows (including header)!`);
}

main().catch(err => {
  console.error("Migration failed:", err);
  process.exit(1);
});

