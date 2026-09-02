#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { MongoClient } from 'mongodb';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const envPaths = [
    path.resolve(__dirname, '../../../.env.local'),
    path.resolve(__dirname, '../../.env.local'),
    path.resolve(process.cwd(), '.env.local')
];
for (const ep of envPaths) {
    if (fs.existsSync(ep)) {
        dotenv.config({ path: ep });
        break;
    }
}

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://192.168.100.4:27017';
const MONGODB_DB = process.env.MONGODB_DB || 'gakumas-tools';

async function syncMongoToCsv() {
    const client = new MongoClient(MONGODB_URI, { serverSelectionTimeoutMS: 5000 });
    try {
        await client.connect();
        const db = client.db(MONGODB_DB);
        
        const seasons = await db.collection('contest_matches').distinct('season');
        const seasonList = seasons.length > 0 ? seasons : [51];

        for (const season of seasonList) {
            const matches = await db.collection('contest_matches')
                .find({ season })
                .sort({ date: 1, matchIndex: 1 })
                .toArray();

            if (matches.length === 0) continue;

            const targetPaths = [
                path.resolve(__dirname, '../../../agent-instructions', `match_history_${season}.csv`),
                path.resolve(__dirname, '../../../../shared/agent-instructions', `match_history_${season}.csv`)
            ];

            for (const csvPath of targetPaths) {
                if (!fs.existsSync(csvPath)) continue;

                const content = fs.readFileSync(csvPath, 'utf-8');
                const lines = content.split(/\r?\n/);
                
                const dateIndices = {};
                for (let i = 1; i < lines.length; i++) {
                    const line = lines[i].trim();
                    if (!line) continue;
                    const parts = line.split(',');
                    const d = parts[0];
                    if (!dateIndices[d]) dateIndices[d] = [];
                    dateIndices[d].push(i);
                }

                let updated = 0;
                for (const m of matches) {
                    const row = [
                        m.date,
                        m.opponent?.name || '',
                        m.opponent?.grade || 3,
                        m.stages?.stage1?.myScore ?? '',
                        m.stages?.stage1?.enemyScore ?? '',
                        m.stages?.stage2?.myScore ?? '',
                        m.stages?.stage2?.enemyScore ?? '',
                        m.stages?.stage3?.myScore ?? '',
                        m.stages?.stage3?.enemyScore ?? '',
                        m.overallResult || '',
                        m.earnedPt ?? ''
                    ].join(',');

                    const idxList = dateIndices[m.date];
                    if (idxList) {
                        const targetIdx = idxList[m.matchIndex - 1];
                        if (targetIdx !== undefined) {
                            lines[targetIdx] = row;
                            updated++;
                        }
                    }
                }

                fs.writeFileSync(csvPath, lines.join('\n'), 'utf-8');
                console.log(`[sync-mongo-to-csv] Synced ${updated} matches to ${csvPath}`);
            }
        }
    } finally {
        await client.close();
    }
}

syncMongoToCsv().catch(err => {
    console.error('[sync-mongo-to-csv error]', err);
});
