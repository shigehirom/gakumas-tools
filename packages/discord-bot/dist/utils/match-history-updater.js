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
exports.findMatchHistoryCsv = findMatchHistoryCsv;
exports.getLatestSeasonNumber = getLatestSeasonNumber;
exports.formatDateToYYMMDD = formatDateToYYMMDD;
exports.saveContestMatchToMongo = saveContestMatchToMongo;
exports.updateMatchHistoryCsv = updateMatchHistoryCsv;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const mongodb_1 = require("mongodb");
const config_1 = require("../config");
/** match_history_*.csv を検索するディレクトリ候補（優先順） */
const CSV_CANDIDATE_DIRS = [
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
 * 既存の match_history_XX.csv ファイルパスを探す
 */
function findMatchHistoryCsv(season) {
    const fileName = `match_history_${season}.csv`;
    for (const dir of CSV_CANDIDATE_DIRS) {
        if (dir && fs.existsSync(dir)) {
            const p = path.join(dir, fileName);
            if (fs.existsSync(p)) {
                return p;
            }
        }
    }
    // 既存ファイルがない場合は instructionsDir に配置
    const targetDir = config_1.config.instructionsDir;
    try {
        fs.mkdirSync(targetDir, { recursive: true });
    }
    catch { }
    return path.join(targetDir, fileName);
}
/**
 * 既存の match_history_XX.csv から最新のシーズン番号を自動取得する
 */
function getLatestSeasonNumber() {
    let maxSeason = 50;
    for (const dir of CSV_CANDIDATE_DIRS) {
        if (dir && fs.existsSync(dir)) {
            try {
                const files = fs.readdirSync(dir);
                for (const f of files) {
                    const match = f.match(/^match_history_(\d+)\.csv$/);
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
        // MongoDB 保存失敗はログのみ（CSV保存は続行）
        console.error('[MongoDB] Failed to save contest match:', err.message);
        return null;
    }
    finally {
        if (client)
            await client.close();
    }
}
/**
 * 解析結果を match_history_XX.csv に反映・上書き保存し、MongoDB にも保存する。
 */
async function updateMatchHistoryCsv(analysis, options = {}) {
    const season = options.season ?? getLatestSeasonNumber();
    const targetDate = options.date ?? new Date();
    const dateStr = formatDateToYYMMDD(targetDate);
    const csvPath = options.targetFilePath ?? findMatchHistoryCsv(season);
    if (!fs.existsSync(csvPath)) {
        fs.mkdirSync(path.dirname(csvPath), { recursive: true });
        fs.writeFileSync(csvPath, '日付,相手名,メモ,自S1,敵S1,自S2,敵S2,自S3,敵S3,結果,獲得Pt\n', 'utf-8');
    }
    const fileContent = fs.readFileSync(csvPath, 'utf-8');
    const lines = fileContent.split(/\r?\n/);
    const newRow = [
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
    // 対象日付の行を探して上書き（なければ末尾に追加）
    const matchingIndices = [];
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].startsWith(`${dateStr},`)) {
            matchingIndices.push(i);
        }
    }
    let targetLineIndex = -1;
    if (matchingIndices.length > 0) {
        const offset = Math.max(0, Math.min(matchingIndices.length - 1, analysis.matchIndex - 1));
        targetLineIndex = matchingIndices[offset];
        lines[targetLineIndex] = newRow;
    }
    else {
        lines.push(newRow);
        targetLineIndex = lines.length - 1;
    }
    fs.writeFileSync(csvPath, lines.join('\n'), 'utf-8');
    // MongoDB への保存（失敗してもCSV保存の結果には影響させない）
    const mongoId = await saveContestMatchToMongo(analysis, options);
    return {
        filePath: csvPath,
        updatedLine: newRow,
        lineIndex: targetLineIndex + 1,
        ...(mongoId ? { mongoId } : {})
    };
}
