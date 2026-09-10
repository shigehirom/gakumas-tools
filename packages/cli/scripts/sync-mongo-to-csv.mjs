#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const require = createRequire(import.meta.url);

// 手動で .env.local をロード（dotenv パッケージ不要）
const envCandidates = [
    path.resolve(__dirname, '../../../.env.local'),
    path.resolve(__dirname, '../../.env.local'),
    path.resolve(process.cwd(), '.env.local'),
    '/root/gakumas-workspace/gakumas-tools/.env.local',
    '/app/.env.local'
];
for (const ep of envCandidates) {
    if (fs.existsSync(ep)) {
        const content = fs.readFileSync(ep, 'utf8');
        content.split('\n').forEach(line => {
            const match = line.match(/^([^=]+)=(.*)$/);
            if (match) {
                let key = match[1].trim();
                let value = match[2].trim();
                if (value.startsWith('"') && value.endsWith('"')) {
                    value = value.slice(1, -1);
                }
                process.env[key] = value;
            }
        });
        break;
    }
}

// mongodb パッケージを探索してロード
let MongoClient;
const mongoPaths = [
    'mongodb',
    path.resolve(__dirname, '../../discord-bot/node_modules/mongodb'),
    '/root/gakumas-workspace/gakumas-tools/packages/discord-bot/node_modules/mongodb',
    '/app/packages/discord-bot/node_modules/mongodb'
];
for (const mp of mongoPaths) {
    try {
        const mod = require(mp);
        MongoClient = mod.MongoClient;
        if (MongoClient) break;
    } catch {}
}

if (!MongoClient) {
    console.warn('[sync-mongo-to-csv] mongodb module not found, skipping sync.');
    process.exit(0);
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
    console.error('[sync-mongo-to-csv error]', err.message);
});
