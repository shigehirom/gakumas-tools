/**
 * import-contest-csv.mjs
 * 既存の match_history_NN.csv を MongoDB contest_matches コレクションへ一括インポートする
 *
 * 使用法:
 *   node import-contest-csv.mjs [--csv /path/to/match_history_51.csv] [--season 51] [--execute]
 *
 * CSV フォーマット（ヘッダー行）:
 *   日付,相手名,メモ,自S1,敵S1,自S2,敵S2,自S3,敵S3,結果,獲得Pt
 */

import fs from 'fs';
import path from 'path';
import { MongoClient } from 'mongodb';
import { loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const MONGODB_URI = process.env.MONGODB_URI;
const MONGODB_DB  = process.env.MONGODB_DB || 'gakumas-tools';

if (!MONGODB_URI) {
    console.error('Error: MONGODB_URI is not set.');
    process.exit(1);
}

const args = process.argv.slice(2);
const execute  = args.includes('--execute');
const csvIdx   = args.indexOf('--csv');
const seasIdx  = args.indexOf('--season');
const userId   = args.includes('--user-id') ? args[args.indexOf('--user-id') + 1] : '755794545861591082';

// CSV パスの候補
const csvCandidates = [
    csvIdx !== -1 ? args[csvIdx + 1] : null,
    '/root/gakumas-workspace/shared/agent-instructions/match_history_51.csv',
    '/root/gakumas-workspace/gakumas-tools/agent-instructions/match_history_51.csv',
    '/app/agent-instructions/match_history_51.csv',
].filter(Boolean);

const csvPath = csvCandidates.find(p => fs.existsSync(p));
if (!csvPath) {
    console.error('Error: Could not find match_history CSV file. Specify with --csv <path>');
    process.exit(1);
}

// シーズン番号は --season 引数 or ファイル名から自動取得
let season = seasIdx !== -1 ? parseInt(args[seasIdx + 1], 10) : null;
if (!season) {
    const m = path.basename(csvPath).match(/match_history_(\d+)\.csv/);
    season = m ? parseInt(m[1], 10) : 51;
}

console.log(`CSV: ${csvPath}`);
console.log(`Season: ${season}`);
console.log(`Mode: ${execute ? 'EXECUTE' : 'DRY RUN (--execute to apply)'}`);

// CSV 解析
const content = fs.readFileSync(csvPath, 'utf-8');
const lines = content.split(/\r?\n/).filter(l => l.trim());
// ヘッダー行を除く
const dataLines = lines.slice(1);

const docs = [];
let skipped = 0;

dataLines.forEach((line, idx) => {
    const cols = line.split(',');
    const date        = (cols[0] ?? '').trim();
    const opponent    = (cols[1] ?? '').trim();
    const grade       = parseInt((cols[2] ?? '3').trim(), 10) || 3;
    const s1my        = parseInt(cols[3], 10) || 0;
    const s1enemy     = parseInt(cols[4], 10) || 0;
    const s2my        = parseInt(cols[5], 10) || 0;
    const s2enemy     = parseInt(cols[6], 10) || 0;
    const s3my        = parseInt(cols[7], 10) || 0;
    const s3enemy     = parseInt(cols[8], 10) || 0;
    const result      = (cols[9] ?? '').trim().toUpperCase();
    const earnedPt    = parseInt(cols[10], 10) || 0;

    // 未入力行（結果が WIN/LOSE でない）はスキップ
    if (result !== 'WIN' && result !== 'LOSE') {
        skipped++;
        return;
    }

    // 同日中の matchIndex を算出（同じ日付で何番目か、1始まり）
    const sameDayCount = docs.filter(d => d.date === date).length;
    const matchIndex = sameDayCount + 1;

    docs.push({
        season,
        date,
        matchIndex,
        opponent: { name: opponent, grade },
        stages: {
            stage1: { myScore: s1my, enemyScore: s1enemy, result: s1my >= s1enemy ? 'WIN' : 'LOSE' },
            stage2: { myScore: s2my, enemyScore: s2enemy, result: s2my >= s2enemy ? 'WIN' : 'LOSE' },
            stage3: { myScore: s3my, enemyScore: s3enemy, result: s3my >= s3enemy ? 'WIN' : 'LOSE' },
        },
        overallResult: result,
        earnedPt,
        extra: { fans: 0, coins: 0, currentPt: 0, currentRank: 0 },
        userId,
        recordedAt: new Date(),
        importedFromCsv: true,
    });
});

console.log(`Parsed: ${docs.length} valid records, ${skipped} skipped (empty rows).`);

if (!execute) {
    console.log('\n--- Preview (first 5) ---');
    docs.slice(0, 5).forEach(d => {
        console.log(`  Season${d.season} ${d.date} #${d.matchIndex} vs ${d.opponent.name} → ${d.overallResult} (+${d.earnedPt}Pt)`);
    });
    console.log('\n[DRY RUN] No changes made. Run with --execute to import.');
    process.exit(0);
}

// MongoDB への書き込み
const client = new MongoClient(MONGODB_URI);
try {
    await client.connect();
    console.log('Connected to MongoDB.');
    const col = client.db(MONGODB_DB).collection('contest_matches');

    let upserted = 0;
    for (const doc of docs) {
        await col.updateOne(
            { season: doc.season, date: doc.date, matchIndex: doc.matchIndex },
            { $set: doc },
            { upsert: true }
        );
        upserted++;
    }

    console.log(`[+] Upserted ${upserted} documents into contest_matches.`);

    // インデックス作成（初回のみ有効）
    await col.createIndex({ season: 1, date: 1, matchIndex: 1 }, { unique: true });
    await col.createIndex({ season: 1, userId: 1 });
    console.log('[+] Indexes ensured.');
} finally {
    await client.close();
    console.log('MongoDB connection closed.');
}
