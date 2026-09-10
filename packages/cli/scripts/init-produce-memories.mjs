import fs from 'fs';
import path from 'path';
import { MongoClient, ObjectId } from 'mongodb';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://192.168.100.4:27017';
const MONGODB_DB = process.env.MONGODB_DB || 'gakumas-tools';
const SHEET_ID = process.env.SYNC_SHEET_ID;
const TAB_NAME = 'Produce-Memories';

const WORKSPACE_ROOT = path.resolve(process.cwd(), '../..');
const JSON_DIR = path.resolve(WORKSPACE_ROOT, 'packages/gakumas-data/json');
const PIDOLS_JSON_PATH = path.join(JSON_DIR, 'p_idols.json');
const SKILLCARDS_JSON_PATH = path.join(JSON_DIR, 'skill_cards.json');
const IDOLS_JSON_PATH = path.join(JSON_DIR, 'idols.json');
const CUSTOMIZATIONS_PATH = path.join(JSON_DIR, 'customizations.json');

function loadJson(filePath) {
  if (!fs.existsSync(filePath)) {
    console.warn(`File not found: ${filePath}`);
    return [];
  }
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function parseNumber(val) {
  if (val === undefined || val === null || val === '') return 0;
  const num = parseFloat(String(val).replace(/[^0-9.-]/g, ''));
  return isNaN(num) ? 0 : num;
}

async function main() {
  const args = process.argv.slice(2);
  const dryRun = !args.includes('--execute');
  const writeBackOids = args.includes('--write-back-oids');

  console.log(`=== Produce Memories Init & Migration ===`);
  console.log(`Mode: ${dryRun ? 'DRY-RUN (Use --execute to apply changes)' : 'EXECUTE (Writing to DB)'}`);
  if (writeBackOids) {
    console.log(`Write-back OIDs to Google Sheets: ENABLED`);
  }

  // 1. Load Reference JSON Data
  const skillCards = loadJson(SKILLCARDS_JSON_PATH);
  const customizations = loadJson(CUSTOMIZATIONS_PATH);
  const pIdols = loadJson(PIDOLS_JSON_PATH);
  const idols = loadJson(IDOLS_JSON_PATH);

  const cardByName = new Map();
  for (const card of skillCards) {
    cardByName.set(card.name, card);
  }

  const idolByName = new Map();
  for (const idol of idols) {
    // idol name match (e.g. '花海咲季' or '花海 咲季')
    idolByName.set(idol.name.replace(/\s+/g, ''), idol);
  }

  const pIdolById = new Map();
  for (const pi of pIdols) {
    pIdolById.set(pi.id, pi);
  }

  // 2. Connect to MongoDB
  const client = new MongoClient(MONGODB_URI);
  await client.connect();
  const db = client.db(MONGODB_DB);
  const memoriesCol = db.collection('memories');
  const produceMemCol = db.collection('produce_memories');

  console.log('Connected to MongoDB.');

  // Fetch all existing stage memories
  const stageMemories = await memoriesCol.find({}).toArray();
  console.log(`Loaded ${stageMemories.length} stage memories from MongoDB.`);

  const stageMemById = new Map();
  const stageMemByName = new Map();
  for (const sm of stageMemories) {
    stageMemById.set(sm._id.toString(), sm);
    if (sm.name) {
      // Normalize name e.g. "26/09/06＿20439"
      stageMemByName.set(sm.name.trim(), sm);
    }
  }

  // 3. Fetch rows from Google Sheets
  const auth = await getAuthClient();
  const sheets = google.sheets({ version: 'v4', auth });
  console.log(`Fetching rows from Google Sheets (${TAB_NAME})...`);
  const sheetRes = await sheets.spreadsheets.values.get({
    spreadsheetId: SHEET_ID,
    range: `${TAB_NAME}!A1:V`
  });

  const rows = sheetRes.data.values || [];
  if (rows.length === 0) {
    console.error('No rows found in sheet.');
    await client.close();
    return;
  }

  const headers = rows[0];
  console.log(`Found ${rows.length - 1} data rows with headers:`, headers.join(', '));

  const colIdx = {};
  headers.forEach((h, i) => {
    colIdx[h.trim()] = i;
  });

  const getCol = (row, colName) => {
    const idx = colIdx[colName];
    return idx !== undefined && idx < row.length ? String(row[idx]).trim() : '';
  };

  let stageLinkedCount = 0;
  let produceOnlyCount = 0;
  const docsToUpsert = [];
  const oidsToWriteBack = []; // { rowNumber: number, oid: string }

  const defaultUserId = process.env.CLI_USER_ID || (stageMemories[0]?.userId || 'default_user');

  for (let r = 1; r < rows.length; r++) {
    const row = rows[r];
    const dateStr = getCol(row, '日付');
    const scoreStr = getCol(row, 'ステージ総合力');
    const idolStr = getCol(row, 'アイドル');
    const songStr = getCol(row, '楽曲名');
    let oidStr = getCol(row, 'OID');
    const eventStr = getCol(row, 'イベント');
    const scenarioRaw = getCol(row, 'シナリオ').toLowerCase();
    const difficultyRaw = getCol(row, '難易度');

    // Skip empty rows
    if (!dateStr && !scoreStr && !idolStr && !oidStr) continue;

    // Check if stage memory exists
    let matchedStageMem = null;
    if (oidStr && oidStr.length === 24) {
      matchedStageMem = stageMemById.get(oidStr);
    }

    if (!matchedStageMem && dateStr && scoreStr) {
      // Try match by name "YY/MM/DD＿SCORE"
      const nameKey = `${dateStr}＿${scoreStr}`;
      matchedStageMem = stageMemByName.get(nameKey);
    }

    let memoryId;
    let hasStageMemory = false;
    let name = '';
    let pIdolId = 0;
    let userId = defaultUserId;
    let sourceType = 'regular';

    if (matchedStageMem) {
      hasStageMemory = true;
      memoryId = matchedStageMem._id;
      name = matchedStageMem.name || `${dateStr}＿${scoreStr}`;
      pIdolId = matchedStageMem.pIdolId || 0;
      userId = matchedStageMem.userId || defaultUserId;
      sourceType = 'regular';
      stageLinkedCount++;

      // If sheet was missing OID, record for writeback
      if (!oidStr || oidStr !== memoryId.toString()) {
        oidsToWriteBack.push({
          rowNumber: r + 1,
          oid: memoryId.toString()
        });
      }
    } else {
      hasStageMemory = false;
      sourceType = eventStr.includes('ゼミ') ? 'event_seminar' : 'event_produce_only';
      if (oidStr && oidStr.length === 24) {
        memoryId = new ObjectId(oidStr);
      } else {
        memoryId = new ObjectId();
        oidsToWriteBack.push({
          rowNumber: r + 1,
          oid: memoryId.toString()
        });
      }
      name = dateStr ? `${dateStr}＿プロデュース専用` : 'プロデュース専用';
      produceOnlyCount++;
    }

    // Idol info resolution
    const cleanIdolName = idolStr.replace(/\s+/g, '');
    const matchedIdol = idolByName.get(cleanIdolName);
    const idolId = matchedIdol ? matchedIdol.id : (matchedStageMem ? pIdolById.get(pIdolId)?.idolId : undefined);

    // Scenario & Difficulty
    let scenario = 'hif';
    if (scenarioRaw.includes('初') || scenarioRaw.includes('hajime')) scenario = 'hajime';
    else if (scenarioRaw.includes('nia')) scenario = 'nia';

    let difficulty = 'main';
    if (difficultyRaw.includes('本戦') || difficultyRaw.includes('main')) difficulty = 'main';

    // Skill card resolution
    const acquiredCardName = getCol(row, '獲得可能スキルカード');
    let skillCard = undefined;
    if (acquiredCardName) {
      const cardObj = cardByName.get(acquiredCardName);
      const cardId = cardObj ? cardObj.id : 0;
      const timingRaw = getCol(row, '獲得タイミング');
      const timing = timingRaw.includes('中間') ? 'middle' : 'start';

      const custRaw = getCol(row, 'カスタマイズ');
      const customizationDict = {};
      if (custRaw && cardObj) {
        const availList = String(cardObj.availableCustomizations || '')
          .split(',')
          .map(s => s.trim())
          .filter(Boolean);
        const allowedCusts = customizations.filter(c => availList.includes(String(c.id)));

        for (const token of custRaw.split(',').map(s => s.trim()).filter(Boolean)) {
          let matchedCust = allowedCusts.find(c => {
            const cleanCName = c.name.replace(/[+-]/g, '');
            return token.includes(cleanCName) || (c.alias && token.includes(c.alias));
          });
          if (!matchedCust) {
            if (token.includes('使用数') || token.includes('制限')) {
              matchedCust = allowedCusts.find(c => c.name.includes('使用数') || c.name.includes('制限'));
            } else if (token.includes('元気')) {
              matchedCust = allowedCusts.find(c => c.name.includes('元気'));
            } else if (token.includes('持続') || token.includes('継続')) {
              matchedCust = allowedCusts.find(c => c.name.includes('持続'));
            } else if (token.includes('消費') || token.includes('コスト')) {
              matchedCust = allowedCusts.find(c => c.name.includes('コスト') || c.name.includes('消費'));
            } else {
              const keywords = ['好調', '絶好調', '集中', 'やる気', '元気', 'パラメータ', '好印象', '条件変更'];
              for (const kw of keywords) {
                if (token.includes(kw)) {
                  matchedCust = allowedCusts.find(c => c.name.includes(kw));
                  if (matchedCust) break;
                }
              }
            }
          }
          if (matchedCust) {
            customizationDict[String(matchedCust.id)] = 1;
          }
        }
      }

      skillCard = {
        id: cardId,
        name: acquiredCardName,
        timing,
        customization: customizationDict
      };
    }

    // Parse abilities & bonuses
    const abilities = [];
    let slotIndex = 0;
    const addAbility = (rawText, dsl) => {
      abilities.push({ slotIndex: slotIndex++, rawText, dsl });
    };

    const initCoin = parseNumber(getCol(row, '初期P'));
    if (initCoin > 0) addAbility(`初期Pポイント+${initCoin}`, `@init: coin+${initCoin}`);

    const initVo = parseNumber(getCol(row, '初期Vo'));
    if (initVo > 0) addAbility(`初期ボーカル上昇+${initVo}`, `@init: vo+${initVo}`);

    const initDa = parseNumber(getCol(row, '初期Da'));
    if (initDa > 0) addAbility(`初期ダンス上昇+${initDa}`, `@init: da+${initDa}`);

    const initVi = parseNumber(getCol(row, '初期Vi'));
    if (initVi > 0) addAbility(`初期ビジュアル上昇+${initVi}`, `@init: vi+${initVi}`);

    const voBonus = parseNumber(getCol(row, 'Voパラボ'));
    if (voBonus > 0) addAbility(`ボーカルレッスンボーナス+${voBonus}%`, `@passive: vo_lesson_bonus+${voBonus}`);

    const daBonus = parseNumber(getCol(row, 'Daパラボ'));
    if (daBonus > 0) addAbility(`ダンスレッスンボーナス+${daBonus}%`, `@passive: da_lesson_bonus+${daBonus}`);

    const viBonus = parseNumber(getCol(row, 'Viパラボ'));
    if (viBonus > 0) addAbility(`ビジュアルレッスンボーナス+${viBonus}%`, `@passive: vi_lesson_bonus+${viBonus}`);

    const hifCardName = getCol(row, 'HIF専用スキルカード');
    const hifEffect = getCol(row, '効果');
    let hifCardId = undefined;
    if (hifCardName) {
      const baseCard = cardByName.get(hifCardName);
      const plusCard = cardByName.get(`${hifCardName}+`);
      if (baseCard) {
        hifCardId = baseCard.id;
        const idList = [String(baseCard.id)];
        if (plusCard) idList.push(String(plusCard.id));
        const idsStr = idList.join(',');

        let cardLimit = 2;
        if (String(baseCard.limit) === '1' || (plusCard && String(plusCard.limit) === '1')) {
          cardLimit = 1;
        }

        if (hifEffect.includes('使用数')) {
          addAbility(
            `試験ごとに、以降 ${cardLimit} 回まで、${hifCardName}（ID: ${idsStr}）使用後、スキルカード使用数追加+1`,
            `@card_play(id=(${idsStr})): extra_card_play+1(limit=${cardLimit})`
          );
        } else if (hifEffect.includes('眠気')) {
          addAbility(
            `試験ごとに、以降 1 回まで、${hifCardName}（ID: ${idsStr}）使用後、ランダムな山札か捨札の 眠気（ID: 23）を除外に移動`,
            `@card_play(id=(${idsStr})): card_exclude(id=23)(limit=1)`
          );
        }
      }
    }

    const lessonAfter = getCol(row, 'レッスン後');
    const healProb = parseNumber(getCol(row, '体力回復確率'));
    let healType = undefined;
    if (healProb > 0) {
      if (lessonAfter === 'ボーカル') {
        healType = 'vocal';
        addAbility(`ボーカルレッスン終了後、${healProb}%の確率で体力回復4`, `@lesson_end(type=vocal): hp+4(prob=${healProb})`);
      } else if (lessonAfter === 'ダンス') {
        healType = 'dance';
        addAbility(`ダンスレッスン終了後、${healProb}%の確率で体力回復4`, `@lesson_end(type=dance): hp+4(prob=${healProb})`);
      } else if (lessonAfter === 'ビジュアル') {
        healType = 'visual';
        addAbility(`ビジュアルレッスン終了後、${healProb}%の確率で体力回復4`, `@lesson_end(type=visual): hp+4(prob=${healProb})`);
      } else if (lessonAfter === 'お休み') {
        healType = 'rest';
        addAbility(`お休み選択時、${healProb}%の確率で体力回復4`, `@rest_select: hp+4(prob=${healProb})`);
      } else {
        healType = lessonAfter || 'generic';
        addAbility(`${lessonAfter}後、${healProb}%の確率で体力回復4`, `@event: hp+4(prob=${healProb})`);
      }
    }

    const bonuses = {
      voBonus,
      daBonus,
      viBonus,
      initVo,
      initDa,
      initVi,
      initCoin,
      hifCardName: hifCardName || undefined,
      hifCardId,
      hifEffect: hifEffect || undefined,
      healType,
      healProb: healProb > 0 ? healProb : undefined,
      healAmount: healProb > 0 ? 4 : undefined
    };

    const doc = {
      _id: memoryId,
      userId,
      name,
      idolId,
      idolName: cleanIdolName || (matchedStageMem ? matchedStageMem.name : ''),
      song: songStr || '',
      hasStageMemory,
      sourceType,
      scenario,
      difficulty,
      event: eventStr || undefined,
      skillCard,
      abilities,
      bonuses,
      updatedAt: new Date()
    };

    docsToUpsert.push(doc);
  }

  console.log(`\n=== Parsed Summary ===`);
  console.log(`Total valid produce memories: ${docsToUpsert.length}`);
  console.log(`- Linked to stage memory (_id matched): ${stageLinkedCount}`);
  console.log(`- Produce-only (seminar / event): ${produceOnlyCount}`);
  console.log(`- OIDs to write back to Sheet: ${oidsToWriteBack.length}`);

  const sampleWithBonus = docsToUpsert.find(d => d.bonuses.voBonus > 0 || d.bonuses.daBonus > 0 || d.bonuses.viBonus > 0) || docsToUpsert[0];
  if (sampleWithBonus) {
    console.log(`\nSample produce memory doc (with lesson bonus):`);
    console.log(JSON.stringify(sampleWithBonus, null, 2));
  }

  if (!dryRun) {
    console.log(`\nWriting ${docsToUpsert.length} documents to 'produce_memories' collection...`);
    const operations = docsToUpsert.map(doc => ({
      updateOne: {
        filter: { _id: doc._id },
        update: {
          $set: doc,
          $setOnInsert: { createdAt: new Date() }
        },
        upsert: true
      }
    }));

    const bulkRes = await produceMemCol.bulkWrite(operations);
    console.log(`Bulk write completed: matched=${bulkRes.matchedCount}, modified=${bulkRes.modifiedCount}, upserted=${bulkRes.upsertedCount}`);

    // Create indexes for optimal querying
    console.log('Creating indexes on produce_memories...');
    await produceMemCol.createIndex({ userId: 1, idolName: 1 });
    await produceMemCol.createIndex({ hasStageMemory: 1 });
    await produceMemCol.createIndex({ 'bonuses.voBonus': -1 });
    await produceMemCol.createIndex({ 'bonuses.daBonus': -1 });
    await produceMemCol.createIndex({ 'bonuses.viBonus': -1 });
    await produceMemCol.createIndex({ 'skillCard.name': 1 });
    console.log('Indexes created successfully.');

    // Write back OIDs to Sheet if requested
    if (writeBackOids && oidsToWriteBack.length > 0) {
      console.log(`Writing back ${oidsToWriteBack.length} OIDs to Google Sheets...`);
      const data = oidsToWriteBack.map(item => ({
        range: `${TAB_NAME}!A${item.rowNumber}`,
        values: [[item.oid]]
      }));

      await sheets.spreadsheets.values.batchUpdate({
        spreadsheetId: SHEET_ID,
        requestBody: {
          valueInputOption: 'USER_ENTERED',
          data
        }
      });
      console.log('OIDs successfully written back to Google Sheets.');
    }
  }

  await client.close();
  console.log('\nFinished successfully.');
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
