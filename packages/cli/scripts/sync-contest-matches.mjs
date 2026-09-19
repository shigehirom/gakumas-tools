/**
 * sync-contest-matches.mjs
 * MongoDB `contest_matches` コレクション ⇔ Googleスプレッドシート `Contest` シート 同期スクリプト
 *
 * 動作:
 *   --mode mongo-to-sheet (デフォルト): MongoDB → スプレッドシートに反映
 *   --mode sheet-to-mongo: スプレッドシートの手動修正を MongoDB に反映
 *   --execute: 実際に書き込む（省略時はドライラン）
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { MongoClient } from 'mongodb';
import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

loadEnvLocal();

const MONGODB_URI = process.env.MONGODB_URI;
const MONGODB_DB = process.env.MONGODB_DB || 'gakumas-tools';
const SHEET_ID = process.env.SYNC_SHEET_ID;
const SHEET_NAME = 'Contest';
// シートの列: season, date, match_index, opponent, grade, s1_my, s1_enemy, s2_my, s2_enemy, s3_my, s3_enemy, result, earned_pt
const SHEET_HEADERS = [
    'season', 'date', 'match_index', 'opponent', 'grade',
    's1_my', 's1_enemy', 's2_my', 's2_enemy', 's3_my', 's3_enemy',
    'result', 'earned_pt'
];
const SHEET_RANGE = `${SHEET_NAME}!A:M`;

if (!MONGODB_URI) {
    console.error('Error: MONGODB_URI is not set.');
    process.exit(1);
}
if (!SHEET_ID) {
    console.error('Error: SYNC_SHEET_ID is not set in .env.local');
    process.exit(1);
}

const args = process.argv.slice(2);
const execute = args.includes('--execute');
const mode = args.includes('--mode') ? args[args.indexOf('--mode') + 1] : 'mongo-to-sheet';

// ───────────────────────────────────────────────────────────────
// ドキュメント → シート行への変換
// ───────────────────────────────────────────────────────────────
function docToRow(doc) {
    return [
        String(doc.season ?? ''),
        doc.date ?? '',
        String(doc.matchIndex ?? ''),
        doc.opponent?.name ?? '',
        String(doc.opponent?.grade ?? ''),
        String(doc.stages?.stage1?.myScore ?? ''),
        String(doc.stages?.stage1?.enemyScore ?? ''),
        String(doc.stages?.stage2?.myScore ?? ''),
        String(doc.stages?.stage2?.enemyScore ?? ''),
        String(doc.stages?.stage3?.myScore ?? ''),
        String(doc.stages?.stage3?.enemyScore ?? ''),
        doc.overallResult ?? '',
        String(doc.earnedPt ?? ''),
    ];
}

// ───────────────────────────────────────────────────────────────
// シート行 → MongoDB ドキュメントへの変換（sheet-to-mongo 用）
// ───────────────────────────────────────────────────────────────
function rowToDoc(row, headers) {
    const get = (key) => (row[headers.indexOf(key)] ?? '').trim();
    const num = (key) => parseInt(get(key), 10) || 0;
    return {
        season: num('season'),
        date: get('date'),
        matchIndex: num('match_index'),
        opponent: { name: get('opponent'), grade: num('grade') },
        stages: {
            stage1: { myScore: num('s1_my'), enemyScore: num('s1_enemy') },
            stage2: { myScore: num('s2_my'), enemyScore: num('s2_enemy') },
            stage3: { myScore: num('s3_my'), enemyScore: num('s3_enemy') },
        },
        overallResult: get('result'),
        earnedPt: num('earned_pt'),
    };
}

// ───────────────────────────────────────────────────────────────
// MongoDB → スプレッドシート
// ───────────────────────────────────────────────────────────────
async function ensureSheetExists(sheets) {
    const meta = await sheets.spreadsheets.get({ spreadsheetId: SHEET_ID });
    const existing = (meta.data.sheets ?? []).map(s => s.properties?.title ?? '');
    if (existing.includes(SHEET_NAME)) return;

    console.log(`Creating '${SHEET_NAME}' sheet tab...`);
    await sheets.spreadsheets.batchUpdate({
        spreadsheetId: SHEET_ID,
        requestBody: {
            requests: [{
                addSheet: {
                    properties: { title: SHEET_NAME }
                }
            }]
        }
    });
    console.log(`[+] '${SHEET_NAME}' sheet created.`);
}

async function mongoToSheet(sheets, client) {
    const db = client.db(MONGODB_DB);
    const col = db.collection('contest_matches');
    const docs = await col.find({}).sort({ season: 1, date: 1, matchIndex: 1 }).toArray();
    console.log(`Found ${docs.length} documents in contest_matches.`);

    // ドキュメントをマップ化: key = `${season}_${date}_${matchIndex}`
    const docsMap = new Map();
    const seasonsInDb = new Set();
    const datesBySeason = new Map();

    for (const doc of docs) {
        const s = doc.season ?? 51;
        const d = doc.date ?? '';
        const m = doc.matchIndex ?? 1;
        seasonsInDb.add(s);
        if (!datesBySeason.has(s)) datesBySeason.set(s, new Set());
        if (d) datesBySeason.get(s).add(d);
        docsMap.set(`${s}_${d}_${m}`, doc);
    }

    // 各シーズンについて、regulation_XX.md が存在する場合はその全日程を採用、無ければ DB の日付一覧を採用
    const rows = [];
    const seasonList = Array.from(seasonsInDb).sort((a, b) => a - b);
    if (seasonList.length === 0) seasonList.push(51);

    function getDatesFromRegulation(season) {
        const candidateDirs = [
            path.resolve(__dirname, '../../../agent-instructions'),
            path.resolve(__dirname, '../../../../shared/agent-instructions'),
            '/root/gakumas-workspace/shared/agent-instructions',
            '/root/gakumas-workspace/gakumas-tools/agent-instructions',
            '/mnt/NVMe/gakumas-tools/agent-instructions',
            '/app/agent-instructions'
        ];
        for (const dir of candidateDirs) {
            const p = path.join(dir, `regulation_${season}.md`);
            if (fs.existsSync(p)) {
                try {
                    const content = fs.readFileSync(p, 'utf-8');
                    const beginMatch = content.match(/begin:\s*([0-9]{4}[/-][0-9]{1,2}[/-][0-9]{1,2})/);
                    const endMatch = content.match(/end:\s*([0-9]{4}[/-][0-9]{1,2}[/-][0-9]{1,2})/);
                    if (beginMatch && endMatch) {
                        const bp = beginMatch[1].replace(/\//g, '-').split('-').map(Number);
                        const ep = endMatch[1].replace(/\//g, '-').split('-').map(Number);
                        const cur = new Date(bp[0], bp[1] - 1, bp[2]);
                        const end = new Date(ep[0], ep[1] - 1, ep[2]);
                        const dates = [];
                        while (cur <= end) {
                            const yy = String(cur.getFullYear()).slice(-2);
                            const mm = String(cur.getMonth() + 1).padStart(2, '0');
                            const dd = String(cur.getDate()).padStart(2, '0');
                            dates.push(`${yy}/${mm}/${dd}`);
                            cur.setDate(cur.getDate() + 1);
                        }
                        if (dates.length > 0) return dates;
                    }
                } catch {}
            }
        }
        return [];
    }

    for (const season of seasonList) {
        let orderedDates = getDatesFromRegulation(season);

        // regulation が無ければ DB の日付一覧を採用
        if (orderedDates.length === 0) {
            const dbDates = Array.from(datesBySeason.get(season) || []).sort();
            orderedDates = dbDates;
        }

        // 各日付について、必ず match_index 1〜5 の 5 行を生成
        for (const date of orderedDates) {
            for (let matchIndex = 1; matchIndex <= 5; matchIndex++) {
                const docKey = `${season}_${date}_${matchIndex}`;
                if (docsMap.has(docKey)) {
                    rows.push(docToRow(docsMap.get(docKey)));
                } else {
                    // データ未登録または登録漏れのプレースホルダー行
                    rows.push([
                        String(season),
                        date,
                        String(matchIndex),
                        '', '', '', '', '', '', '', '', '', ''
                    ]);
                }
            }
        }
    }

    const values = [SHEET_HEADERS, ...rows];
    console.log(`Total rows to write: ${values.length - 1} (+ header) across ${rows.length / 5} dates.`);
    if (!execute) {
        console.log('[DRY RUN] No changes written. Pass --execute to apply.');
        return;
    }

    // シートが存在しない場合は自動作成
    await ensureSheetExists(sheets);

    // シートをクリアして全行書き込み
    await sheets.spreadsheets.values.clear({ spreadsheetId: SHEET_ID, range: SHEET_RANGE });
    await sheets.spreadsheets.values.update({
        spreadsheetId: SHEET_ID,
        range: `${SHEET_NAME}!A1`,
        valueInputOption: 'USER_ENTERED',
        requestBody: { values },
    });
    console.log(`[+] Contest sheet updated: ${rows.length} rows written.`);
}

// ───────────────────────────────────────────────────────────────
// スプレッドシート → MongoDB
// ───────────────────────────────────────────────────────────────
async function sheetToMongo(sheets, client) {
    const res = await sheets.spreadsheets.values.get({ spreadsheetId: SHEET_ID, range: SHEET_RANGE });
    const rows = res.data.values ?? [];
    if (rows.length === 0) {
        console.log('No data in Contest sheet.');
        return;
    }

    const headers = rows[0].map(h => h.trim());
    const dataRows = rows.slice(1).filter(r => r && r.some(v => v));
    console.log(`Found ${dataRows.length} data rows in Contest sheet.`);

    if (!execute) {
        console.log('[DRY RUN] No changes written. Pass --execute to apply.');
        return;
    }

    const db = client.db(MONGODB_DB);
    const col = db.collection('contest_matches');
    let upserted = 0;

    for (const row of dataRows) {
        const doc = rowToDoc(row, headers);
        if (!doc.season || !doc.date || !doc.matchIndex) continue;

        // プレースホルダー（空行）は MongoDB を上書きしないようスキップ
        const hasData = doc.opponent?.name ||
            (doc.stages?.stage1?.myScore ?? 0) > 0 ||
            (doc.stages?.stage2?.myScore ?? 0) > 0 ||
            (doc.stages?.stage3?.myScore ?? 0) > 0 ||
            doc.overallResult;

        if (!hasData) continue;

        await col.updateOne(
            { season: doc.season, date: doc.date, matchIndex: doc.matchIndex },
            { $set: { ...doc, updatedAt: new Date() } },
            { upsert: true }
        );
        upserted++;
    }

    console.log(`[+] Upserted ${upserted} documents into contest_matches.`);
}

// ───────────────────────────────────────────────────────────────
// メイン
// ───────────────────────────────────────────────────────────────
async function main() {
    let auth;
    try {
        auth = await getAuthClient();
    } catch (err) {
        console.error('Authentication failed:', err.message);
        process.exit(1);
    }

    const sheets = google.sheets({ version: 'v4', auth });

    const client = new MongoClient(MONGODB_URI);
    try {
        await client.connect();
        console.log('Connected to MongoDB.');

        if (mode === 'sheet-to-mongo') {
            console.log(`Mode: sheet-to-mongo (${execute ? 'EXECUTE' : 'DRY RUN'})`);
            await sheetToMongo(sheets, client);
        } else if (mode === 'bidirectional') {
            console.log(`Mode: bidirectional (${execute ? 'EXECUTE' : 'DRY RUN'})`);
            console.log('--- Step 1: Syncing Sheet -> MongoDB (Importing manual edits) ---');
            await sheetToMongo(sheets, client);
            console.log('--- Step 2: Syncing MongoDB -> Sheet (Writing complete formatted records) ---');
            await mongoToSheet(sheets, client);
        } else {
            console.log(`Mode: mongo-to-sheet (${execute ? 'EXECUTE' : 'DRY RUN'})`);
            await mongoToSheet(sheets, client);
        }
    } finally {
        await client.close();
        console.log('MongoDB connection closed.');
    }
}

main().catch(err => {
    if (err?.message?.includes('invalid_grant') || err?.response?.data?.error === 'invalid_grant') {
        console.error('Fatal error: Google OAuth token expired or revoked (invalid_grant). Please re-authenticate by running "node packages/cli/scripts/reauth-sheets.mjs <code_or_interactive>".');
    } else {
        console.error('Fatal error:', err.message || err);
    }
    process.exit(1);
});

