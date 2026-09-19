/**
 * sync-idols.mjs
 * Google スプレッドシートの `Idols` シートからアイドルメタデータ（特性、カラー等）を取得し、
 * MongoDB の `owned_idols` コレクションに同期・更新するスクリプト
 */

import { MongoClient } from 'mongodb';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const MONGODB_URI = process.env.MONGODB_URI;
const MONGODB_DB = process.env.MONGODB_DB || 'gakumas-tools';
const SHEET_ID = process.env.SYNC_SHEET_ID;

if (!MONGODB_URI || !SHEET_ID) {
    console.error('Error: MONGODB_URI and SYNC_SHEET_ID must be set in .env.local');
    process.exit(1);
}

const args = process.argv.slice(2);
const execute = args.includes('--execute');

async function syncIdols() {
    console.log(`[sync-idols] Connecting to Google Sheets (${SHEET_ID})...`);
    const auth = await getAuthClient();
    const sheets = google.sheets({ version: 'v4', auth });

    const res = await sheets.spreadsheets.values.get({
        spreadsheetId: SHEET_ID,
        range: 'Idols!A1:Z50',
    });

    const rows = res.data.values || [];
    if (rows.length < 2) {
        console.log('[sync-idols] No idol records found in Idols sheet.');
        return;
    }

    const header = rows[0];
    const idIdx = header.findIndex(h => h.includes('ID'));
    const nameIdx = header.findIndex(h => h.includes('アイドル名') || h.includes('名前'));
    const trustIdx = header.findIndex(h => h.includes('親愛度'));
    const colorNameIdx = header.findIndex(h => h.includes('色名') || h.includes('カラー'));
    const rgbIdx = header.findIndex(h => h.includes('RGB') || h.includes('HEX'));
    const charIdx = header.findIndex(h => h.includes('特性'));
    const cvIdx = header.findIndex(h => h.includes('CV'));
    const classIdx = header.findIndex(h => h.includes('学年・クラス') || h.includes('クラス'));
    const ageIdx = header.findIndex(h => h.includes('年齢'));
    const bdayIdx = header.findIndex(h => h.includes('誕生日'));
    const bloodIdx = header.findIndex(h => h.includes('血液型'));
    const heightIdx = header.findIndex(h => h.includes('身長'));
    const weightIdx = header.findIndex(h => h.includes('体重'));
    const bustIdx = header.findIndex(h => h.includes('バスト'));
    const waistIdx = header.findIndex(h => h.includes('ウエスト'));
    const hipIdx = header.findIndex(h => h.includes('ヒップ'));
    const handIdx = header.findIndex(h => h.includes('利き手'));
    const hometownIdx = header.findIndex(h => h.includes('出身地'));
    const residenceIdx = header.findIndex(h => h.includes('居住地'));
    const enrollmentIdx = header.findIndex(h => h.includes('入学'));
    const hobbyIdx = header.findIndex(h => h.includes('趣味'));
    const skillIdx = header.findIndex(h => h.includes('特技'));

    console.log('[sync-idols] Column indices:', { idIdx, nameIdx, trustIdx, colorNameIdx, rgbIdx, charIdx, cvIdx, bdayIdx, hobbyIdx });

    const client = new MongoClient(MONGODB_URI);
    try {
        await client.connect();
        const db = client.db(MONGODB_DB);
        const col = db.collection('owned_idols');

        let updatedCount = 0;
        console.log(`\n--- Idols Sync Preview (${execute ? 'EXECUTE' : 'DRY RUN'}) ---`);

        for (let i = 1; i < rows.length; i++) {
            const row = rows[i];
            if (!row[idIdx] || !row[nameIdx]) continue;

            const id = parseInt(row[idIdx], 10);
            const name = row[nameIdx].trim();
            const trustLevel = trustIdx !== -1 && row[trustIdx] ? parseInt(row[trustIdx], 10) : undefined;
            const colorName = colorNameIdx !== -1 ? (row[colorNameIdx] || '').trim() : '';
            const colorRgb = rgbIdx !== -1 ? (row[rgbIdx] || '').trim() : '';
            const characteristic = charIdx !== -1 ? (row[charIdx] || '').trim() : '';

            const updateData = {
                id,
                name,
                updatedAt: new Date(),
            };
            if (trustLevel !== undefined && !isNaN(trustLevel)) {
                updateData.trust_level = trustLevel;
            }
            if (colorName) updateData.color_name = colorName;
            if (colorRgb) updateData.color_rgb = colorRgb;
            if (characteristic) updateData.characteristic = characteristic;

            // Profile info
            const profile = {};
            if (cvIdx !== -1 && row[cvIdx]) profile.cv = row[cvIdx].trim();
            if (classIdx !== -1 && row[classIdx]) profile.class = row[classIdx].trim();
            if (ageIdx !== -1 && row[ageIdx] && !isNaN(parseInt(row[ageIdx], 10))) profile.age = parseInt(row[ageIdx], 10);
            if (bdayIdx !== -1 && row[bdayIdx]) profile.birthday = row[bdayIdx].trim();
            if (bloodIdx !== -1 && row[bloodIdx]) profile.blood_type = row[bloodIdx].trim();
            if (heightIdx !== -1 && row[heightIdx] && !isNaN(parseInt(row[heightIdx], 10))) profile.height = parseInt(row[heightIdx], 10);
            if (weightIdx !== -1 && row[weightIdx] && !isNaN(parseInt(row[weightIdx], 10))) profile.weight = parseInt(row[weightIdx], 10);
            if (bustIdx !== -1 && row[bustIdx] && !isNaN(parseInt(row[bustIdx], 10))) profile.bust = parseInt(row[bustIdx], 10);
            if (waistIdx !== -1 && row[waistIdx] && !isNaN(parseInt(row[waistIdx], 10))) profile.waist = parseInt(row[waistIdx], 10);
            if (hipIdx !== -1 && row[hipIdx] && !isNaN(parseInt(row[hipIdx], 10))) profile.hip = parseInt(row[hipIdx], 10);
            if (handIdx !== -1 && row[handIdx]) profile.dominant_hand = row[handIdx].trim();
            if (hometownIdx !== -1 && row[hometownIdx]) profile.hometown = row[hometownIdx].trim();
            if (residenceIdx !== -1 && row[residenceIdx]) profile.residence = row[residenceIdx].trim();
            if (enrollmentIdx !== -1 && row[enrollmentIdx]) profile.enrollment = row[enrollmentIdx].trim();
            if (hobbyIdx !== -1 && row[hobbyIdx]) profile.hobby = row[hobbyIdx].trim();
            if (skillIdx !== -1 && row[skillIdx]) profile.skill = row[skillIdx].trim();

            if (Object.keys(profile).length > 0) {
                updateData.profile = profile;
            }

            console.log(`[${id}] ${name}: 特性=${characteristic || '(なし)'}, 親愛度=${trustLevel ?? '-'}, 色=${colorName}`);

            if (execute) {
                await col.updateOne(
                    { id },
                    { $set: updateData },
                    { upsert: true }
                );
                updatedCount++;
            }
        }

        if (execute) {
            console.log(`\n[+] Successfully synced ${updatedCount} idols into MongoDB 'owned_idols'.`);
        } else {
            console.log('\n[Dry Run] Specify --execute to save changes to MongoDB.');
        }
    } finally {
        await client.close();
    }
}

syncIdols().catch(err => {
    console.error('[sync-idols error]:', err.message);
    process.exit(1);
});
