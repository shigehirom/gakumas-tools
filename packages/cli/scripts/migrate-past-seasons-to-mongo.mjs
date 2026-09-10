#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { MongoClient } from 'mongodb';
import { loadEnvLocal } from './utils/sheetsAuth.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

loadEnvLocal();

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://192.168.100.4:27017';
const MONGODB_DB = process.env.MONGODB_DB || 'gakumas-tools';

function parseNumber(val) {
    if (!val) return 0;
    const clean = String(val).replace(/,/g, '').trim();
    const n = parseInt(clean, 10);
    return isNaN(n) ? 0 : n;
}

async function migrateSeasons() {
    const client = new MongoClient(MONGODB_URI, { serverSelectionTimeoutMS: 5000 });
    await client.connect();
    const db = client.db(MONGODB_DB);
    const col = db.collection('contest_matches');

    const seasons = [47, 48, 49, 50, 51];
    let totalInserted = 0;
    let totalUpdated = 0;

    for (const season of seasons) {
        const candidates = [
            path.resolve(__dirname, '../../../agent-instructions', `match_history_${season}.csv`),
            path.resolve(__dirname, '../../../../shared/agent-instructions', `match_history_${season}.csv`)
        ];
        let csvPath = candidates.find(p => fs.existsSync(p));
        if (!csvPath) {
            console.log(`[Season ${season}] CSV not found, skipping.`);
            continue;
        }

        console.log(`\nProcessing Season ${season} from ${csvPath}...`);
        const content = fs.readFileSync(csvPath, 'utf-8');
        const lines = content.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
        if (lines.length <= 1) continue;

        const headers = lines[0].split(',').map(h => h.trim());
        const colMap = {};
        headers.forEach((h, idx) => {
            if (h === '日付') colMap.date = idx;
            else if (h === '相手名') colMap.opponent = idx;
            else if (h === 'メモ') colMap.grade = idx;
            else if (h === '自S1') colMap.s1_my = idx;
            else if (h === '敵S1') colMap.s1_enemy = idx;
            else if (h === '自S2') colMap.s2_my = idx;
            else if (h === '敵S2') colMap.s2_enemy = idx;
            else if (h === '自S3') colMap.s3_my = idx;
            else if (h === '敵S3') colMap.s3_enemy = idx;
            else if (h === '結果') colMap.result = idx;
            else if (h === '獲得Pt') colMap.earnedPt = idx;
        });

        const dateMatchCounts = {};
        let seasonInserted = 0;
        let seasonUpdated = 0;

        for (let i = 1; i < lines.length; i++) {
            const parts = lines[i].split(',').map(p => p.trim());
            const dateStr = parts[colMap.date] || '';
            if (!dateStr) continue;

            if (!dateMatchCounts[dateStr]) dateMatchCounts[dateStr] = 0;
            dateMatchCounts[dateStr]++;
            const matchIndex = dateMatchCounts[dateStr];

            const opponentName = colMap.opponent !== undefined ? parts[colMap.opponent] : '';
            const s1My = parseNumber(parts[colMap.s1_my]);
            const s1Enemy = parseNumber(parts[colMap.s1_enemy]);
            const s2My = parseNumber(parts[colMap.s2_my]);
            const s2Enemy = parseNumber(parts[colMap.s2_enemy]);
            const s3My = parseNumber(parts[colMap.s3_my]);
            const s3Enemy = parseNumber(parts[colMap.s3_enemy]);
            const result = colMap.result !== undefined ? parts[colMap.result] : '';
            const earnedPt = parseNumber(parts[colMap.earnedPt]);
            const grade = parseNumber(parts[colMap.grade]) || 3;

            // 実データがあるか判定（相手名があるか、スコアがあるか、結果が確定しているか）
            const hasData = opponentName.length > 0 || (s1My > 0 || s1Enemy > 0) || result === 'WIN' || result === 'LOSE';
            if (!hasData) continue;

            const doc = {
                season,
                date: dateStr,
                matchIndex,
                opponent: {
                    name: opponentName,
                    grade
                },
                stages: {
                    stage1: { myScore: s1My, enemyScore: s1Enemy, result: s1My >= s1Enemy ? 'WIN' : 'LOSE' },
                    stage2: { myScore: s2My, enemyScore: s2Enemy, result: s2My >= s2Enemy ? 'WIN' : 'LOSE' },
                    stage3: { myScore: s3My, enemyScore: s3Enemy, result: s3My >= s3Enemy ? 'WIN' : 'LOSE' }
                },
                overallResult: result,
                earnedPt,
                migratedAt: new Date()
            };

            const res = await col.updateOne(
                { season, date: dateStr, matchIndex },
                { $set: doc },
                { upsert: true }
            );

            if (res.upsertedCount > 0) seasonInserted++;
            else if (res.modifiedCount > 0) seasonUpdated++;
        }

        console.log(`[Season ${season}] Inserted: ${seasonInserted}, Updated: ${seasonUpdated}`);
        totalInserted += seasonInserted;
        totalUpdated += seasonUpdated;
    }

    console.log(`\n🎉 All migrations complete! Total inserted: ${totalInserted}, Total updated: ${totalUpdated}`);
    await client.close();
}

migrateSeasons().catch(err => {
    console.error('Migration failed:', err);
    process.exit(1);
});
