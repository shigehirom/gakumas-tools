import fs from 'fs';
import path from 'path';
import { MongoClient } from 'mongodb';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const MONGODB_URI = process.env.MONGODB_URI;
const MONGODB_DB = process.env.MONGODB_DB || 'gakumas';
const JSON_DIR = path.resolve(process.cwd(), 'gakumas-support_cards/support_cards');

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

const args = process.argv.slice(2);
const force = args.includes('--force');

async function main() {
  let auth;
  try {
    auth = await getAuthClient();
  } catch (err) {
    console.error("Authentication failed.");
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

  if (idxMap['card_name'] === undefined || idxMap['is_owned'] === undefined) {
    console.error('Spreadsheet is missing required columns (card_name, is_owned).');
    process.exit(1);
  }

  const ownedCards = [];

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row || row.length === 0) continue;

    const isOwnedStr = row[idxMap['is_owned']] ? row[idxMap['is_owned']].trim().toLowerCase() : '';
    
    // Check if is_owned is truthy (e.g. TRUE, true, 1, yes, o, ○, etc.)
    if (isOwnedStr && isOwnedStr !== 'false' && isOwnedStr !== '0' && isOwnedStr !== 'no') {
      const cardName = row[idxMap['card_name']];
      const rarity = row[idxMap['rarity']];
      const planRestriction = row[idxMap['plan_restriction']];
      const type = row[idxMap['type']];
      const uncap = parseInt(row[idxMap['uncap']] || '0', 10);
      const lv = parseInt(row[idxMap['lv']] || '1', 10);
      
      let wikiId = row[idxMap['wiki_id']] || cardName;

      // Load additional JSON data
      // For Support Cards, JSON is read from gakumas-support_cards/support_cards
      const jsonPath = path.join('/Users/shigehiro/gakumas-workspace/gakumas-support_cards/support_cards', `${cardName}.json`);
      let obtainedSkillCard = null;
      let obtainedItem = null;
      let imageUrl = null;

      if (fs.existsSync(jsonPath)) {
        try {
          const jsonContent = fs.readFileSync(jsonPath, 'utf8');
          const data = JSON.parse(jsonContent);
          const cardData = Array.isArray(data) ? data[0] : data;
          if (cardData) {
            obtainedSkillCard = cardData.obtained_skill_card || null;
            obtainedItem = cardData.obtained_item || null;
            if (!row[idxMap['wiki_id']] && cardData.wiki_id) wikiId = cardData.wiki_id;
            if (cardData.image_url) imageUrl = cardData.image_url;
          }
        } catch (err) {
          console.error(`Warning: Failed to parse JSON for ${cardName}`);
        }
      } else {
        console.warn(`Warning: JSON file not found for ${cardName}`);
      }

      ownedCards.push({
        _id: wikiId,
        wiki_id: wikiId,
        image_url: imageUrl,
        card_name: cardName,
        rarity,
        plan_restriction: planRestriction,
        type,
        uncap,
        lv,
        obtained_skill_card: obtainedSkillCard,
        obtained_item: obtainedItem,
        updatedAt: new Date()
      });
    }
  }

  console.log(`Found ${ownedCards.length} owned cards to synchronize.`);

  if (ownedCards.length === 0) {
    console.log("No owned cards found. Exiting.");
    process.exit(0);
  }

  let client;
  try {
    client = new MongoClient(MONGODB_URI);
    await client.connect();
    console.log("Connected to MongoDB.");

    const db = client.db(MONGODB_DB);
    const collection = db.collection('owned_support_cards');

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
    for (const card of ownedCards) {
      try {
        await collection.updateOne(
          { _id: card._id },
          { $set: card },
          { upsert: true }
        );
        successCount++;
      } catch (err) {
        console.error(`Failed to upsert card: ${card.card_name}`, err.message);
      }
    }

    console.log(`Successfully synchronized ${successCount}/${ownedCards.length} cards.`);
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
