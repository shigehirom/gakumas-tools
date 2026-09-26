"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.updateMatchHistoryCsv = void 0;
exports.getLatestSeasonNumber = getLatestSeasonNumber;
exports.formatDateToYYMMDD = formatDateToYYMMDD;
exports.saveContestMatchToMongo = saveContestMatchToMongo;
exports.recordContestMatch = recordContestMatch;
exports.syncContestMatchesToSheets = syncContestMatchesToSheets;
exports.syncContestMatchesBidirectional = syncContestMatchesBidirectional;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const child_process_1 = require("child_process");
const mongodb_1 = require("mongodb");
const config_1 = require("../config");
const master_data_1 = require("./master-data");
/** regulation_*.md を検索するディレクトリ候補 */
const REGULATION_CANDIDATE_DIRS = [
    config_1.config.instructionsDir,
    '/root/gakumas-workspace/shared/agent-instructions',
    '/root/gakumas-workspace/gakumas-tools/agent-instructions',
    '/mnt/NVMe/gakumas-tools/agent-instructions',
    '/app/agent-instructions',
    path.resolve(process.cwd(), 'agent-instructions'),
    path.resolve(process.cwd(), 'shared/agent-instructions'),
    path.resolve(__dirname, '../../agent-instructions'),
    path.resolve(__dirname, '../../../agent-instructions'),
    path.resolve(__dirname, '../../../../agent-instructions'),
];
/**
 * stages.json または regulation_*.md から最新のシーズン番号を自動取得する
 */
function getLatestSeasonNumber() {
    let maxSeason = 50;
    // 1. stages.json からコンテストの最大シーズン番号を取得
    try {
        const stages = master_data_1.MasterData.getStages();
        for (const s of stages) {
            if (s.type === 'contest' && typeof s.season === 'number' && s.season > maxSeason) {
                maxSeason = s.season;
            }
        }
    }
    catch { }
    // 2. regulation_*.md から最大シーズン番号を取得
    for (const dir of REGULATION_CANDIDATE_DIRS) {
        if (dir && fs.existsSync(dir)) {
            try {
                const files = fs.readdirSync(dir);
                for (const f of files) {
                    const match = f.match(/^regulation_(\d+)\.md$/);
                    if (match) {
                        const s = parseInt(match[1], 10);
                        if (s > maxSeason)
                            maxSeason = s;
                    }
                }
            }
            catch { }
        }
    }
    return maxSeason;
}
/**
 * 日付を JST (Asia/Tokyo) 基準の YY/MM/DD 形式に変換する
 */
function formatDateToYYMMDD(date) {
    const formatter = new Intl.DateTimeFormat('ja-JP', {
        timeZone: 'Asia/Tokyo',
        year: '2-digit',
        month: '2-digit',
        day: '2-digit'
    });
    const parts = formatter.formatToParts(date);
    const yy = parts.find(p => p.type === 'year')?.value || '26';
    const mm = parts.find(p => p.type === 'month')?.value || '01';
    const dd = parts.find(p => p.type === 'day')?.value || '01';
    return `${yy}/${mm}/${dd}`;
}
/**
 * 対戦結果を MongoDB の contest_matches コレクションに保存する
 * 同一シーズン・日付・対戦番号の記録は upsert で上書き。
 */
async function saveContestMatchToMongo(analysis, options = {}) {
    const season = options.season ?? getLatestSeasonNumber();
    const targetDate = options.date ?? new Date();
    const dateStr = formatDateToYYMMDD(targetDate);
    const userId = options.userId ?? config_1.config.userId;
    let client = null;
    try {
        client = new mongodb_1.MongoClient(config_1.config.mongoUri, { serverSelectionTimeoutMS: 5000 });
        await client.connect();
        const db = client.db(config_1.config.mongoDb);
        const col = db.collection('contest_matches');
        const doc = {
            season,
            date: dateStr,
            matchIndex: analysis.matchIndex,
            opponent: {
                name: analysis.opponent.name,
                grade: analysis.opponent.grade
            },
            stages: {
                stage1: analysis.stages.stage1,
                stage2: analysis.stages.stage2,
                stage3: analysis.stages.stage3
            },
            overallResult: analysis.overallResult,
            earnedPt: analysis.earnedPt,
            extra: analysis.extra,
            userId,
            recordedAt: new Date()
        };
        // season + date + matchIndex で一意にupsert
        const result = await col.updateOne({ season, date: dateStr, matchIndex: analysis.matchIndex }, { $set: doc }, { upsert: true });
        const insertedId = result.upsertedId?.toString() ?? null;
        console.log(`[MongoDB] contest_matches upserted: season=${season} date=${dateStr} match=${analysis.matchIndex}`);
        return insertedId;
    }
    catch (err) {
        console.error('[MongoDB] Failed to save contest match:', err.message);
        return null;
    }
    finally {
        if (client)
            await client.close();
    }
}
/**
 * 対戦結果を MongoDB に保存し、Google スプレッドシート（Contest タブ）と双方向同期する。
 */
async function recordContestMatch(analysis, options = {}) {
    const targetDate = options.date ?? new Date();
    const dateStr = formatDateToYYMMDD(targetDate);
    // 1. MongoDB への保存
    const mongoId = await saveContestMatchToMongo(analysis, options);
    // 2. Google スプレッドシート（Contest タブ）との双方向同期
    const sheetsResult = await syncContestMatchesBidirectional();
    const formattedRow = [
        dateStr,
        analysis.opponent.name,
        analysis.opponent.grade,
        analysis.stages.stage1.myScore,
        analysis.stages.stage1.enemyScore,
        analysis.stages.stage2.myScore,
        analysis.stages.stage2.enemyScore,
        analysis.stages.stage3.myScore,
        analysis.stages.stage3.enemyScore,
        analysis.overallResult,
        analysis.earnedPt
    ].join(',');
    return {
        filePath: 'MongoDB: contest_matches',
        updatedLine: formattedRow,
        lineIndex: analysis.matchIndex,
        ...(mongoId ? { mongoId } : {}),
        sheetsSuccess: sheetsResult.success,
        ...(sheetsResult.error ? { sheetsError: sheetsResult.error } : {})
    };
}
// 呼び出し元の後方互換性エイリアス
exports.updateMatchHistoryCsv = recordContestMatch;
/**
 * MongoDB の最新対戦記録を Google スプレッドシート（Contest シート）へ同期する
 */
async function syncContestMatchesToSheets() {
    return runSyncScript(['--execute']);
}
/**
 * Google スプレッドシートと MongoDB の対戦記録を双方向同期する
 * (スプレッドシートの手入力データを MongoDB に取り込み ➔ MongoDB の最新確定データをスプレッドシートに書き出し)
 */
async function syncContestMatchesBidirectional() {
    return runSyncScript(['--mode', 'bidirectional', '--execute']);
}
function runSyncScript(args) {
    return new Promise((resolve) => {
        const candidates = [
            path.resolve(process.cwd(), 'scripts/sync-contest-matches.mjs'),
            path.resolve(__dirname, '../scripts/sync-contest-matches.mjs'),
            path.resolve(__dirname, '../../scripts/sync-contest-matches.mjs'),
            path.resolve(__dirname, '../../../../packages/cli/scripts/sync-contest-matches.mjs'),
            path.resolve(__dirname, '../../../cli/scripts/sync-contest-matches.mjs'),
            '/app/packages/cli/scripts/sync-contest-matches.mjs',
            '/root/gakumas-workspace/gakumas-tools/packages/cli/scripts/sync-contest-matches.mjs',
        ];
        const scriptPath = candidates.find(p => fs.existsSync(p));
        if (!scriptPath) {
            console.warn('[SheetsSync] sync-contest-matches.mjs not found in candidates:', candidates);
            return resolve({ success: false, error: 'sync-contest-matches.mjs not found' });
        }
        console.log(`[SheetsSync] Running: node ${scriptPath} ${args.join(' ')}`);
        const child = (0, child_process_1.spawn)('node', [scriptPath, ...args], {
            env: { ...process.env },
            timeout: 30000,
        });
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', d => { stdout += d.toString(); });
        child.stderr.on('data', d => { stderr += d.toString(); });
        child.on('close', (code) => {
            if (code === 0) {
                console.log(`[SheetsSync] Sync success: ${stdout.trim().split('\n').pop()}`);
                resolve({ success: true, output: stdout });
            }
            else {
                const errMsg = stderr.trim() || stdout.trim() || `Exit code ${code}`;
                console.error(`[SheetsSync] Sync failed (code ${code}):`, errMsg);
                resolve({ success: false, error: errMsg });
            }
        });
        child.on('error', (err) => {
            console.error('[SheetsSync] Process error:', err);
            resolve({ success: false, error: err.message });
        });
    });
}
