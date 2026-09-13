import * as fs from 'fs';
import * as path from 'path';
import { spawn } from 'child_process';
import { MongoClient } from 'mongodb';
import { config } from '../config';
import { ContestAnalysisResult } from './contest-parser';
import { MasterData } from './master-data';

export interface UpdateOptions {
    season?: number; // default: auto-detected from CSV files or master data
    date?: Date;     // default: today (JST)
    targetFilePath?: string;
    userId?: string; // Discord UserID of the recording user
}

export interface UpdateResult {
    filePath: string;
    updatedLine: string;
    lineIndex: number;
    mongoId?: string; // MongoDB ObjectId string if saved to DB
    sheetsSuccess?: boolean;
    sheetsError?: string;
}

/** match_history_*.csv を検索するディレクトリ候補（優先順） */
const CSV_CANDIDATE_DIRS: string[] = [
    config.instructionsDir,
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
export function findMatchHistoryCsv(season: number): string {
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
    const targetDir = config.instructionsDir;
    try { fs.mkdirSync(targetDir, { recursive: true }); } catch {}
    return path.join(targetDir, fileName);
}

/**
 * 新シーズン用の match_history_XX.csv テンプレートを自動生成する
 */
export function createMatchHistoryTemplate(season: number, startDate?: Date, days: number = 16): string {
    let start = startDate;
    if (!start) {
        // 前シーズンの最終日の翌日を開始日候補として探索
        const prevCsvPath = findMatchHistoryCsv(season - 1);
        if (fs.existsSync(prevCsvPath)) {
            try {
                const content = fs.readFileSync(prevCsvPath, 'utf-8');
                const lines = content.split(/\r?\n/).filter(l => l.trim().length > 0);
                for (let i = lines.length - 1; i >= 1; i--) {
                    const match = lines[i].split(',')[0]?.trim().match(/^(\d{2})\/(\d{2})\/(\d{2})$/);
                    if (match) {
                        const year = 2000 + parseInt(match[1], 10);
                        const month = parseInt(match[2], 10) - 1;
                        const day = parseInt(match[3], 10);
                        const prevEnd = new Date(year, month, day);
                        prevEnd.setDate(prevEnd.getDate() + 1);
                        start = prevEnd;
                        break;
                    }
                }
            } catch {}
        }
    }
    if (!start) {
        start = new Date();
    }

    const lines: string[] = ['日付,相手名,メモ,自S1,敵S1,自S2,敵S2,自S3,敵S3,結果,獲得Pt'];
    const current = new Date(start.getFullYear(), start.getMonth(), start.getDate());
    for (let d = 0; d < days; d++) {
        const yy = String(current.getFullYear()).slice(-2);
        const mm = String(current.getMonth() + 1).padStart(2, '0');
        const dd = String(current.getDate()).padStart(2, '0');
        const formattedDate = `${yy}/${mm}/${dd}`;
        for (let i = 0; i < 5; i++) {
            lines.push(`${formattedDate},,3,,,,,,,WIN LOSE,`);
        }
        current.setDate(current.getDate() + 1);
    }
    const csvContent = lines.join('\n') + '\n';

    const targetPath = findMatchHistoryCsv(season);
    try {
        fs.mkdirSync(path.dirname(targetPath), { recursive: true });
        fs.writeFileSync(targetPath, csvContent, 'utf-8');
        console.log(`[match-history-updater] Created new template: ${targetPath}`);

        // shared/agent-instructions または gakumas-tools/agent-instructions 等の主要候補にも複製
        const candidateDirsToSync = [
            '/root/gakumas-workspace/shared/agent-instructions',
            '/root/gakumas-workspace/gakumas-tools/agent-instructions'
        ];
        for (const dir of candidateDirsToSync) {
            if (fs.existsSync(dir)) {
                const mirrorPath = path.join(dir, `match_history_${season}.csv`);
                if (mirrorPath !== targetPath) {
                    fs.writeFileSync(mirrorPath, csvContent, 'utf-8');
                }
            }
        }
    } catch (e) {
        console.error(`[match-history-updater] Failed to create template:`, e);
    }
    return targetPath;
}

/**
 * 既存の match_history_XX.csv または stages.json から最新のシーズン番号を自動取得する
 */
export function getLatestSeasonNumber(): number {
    let maxSeason = 50;

    // 1. stages.json からコンテストの最大シーズン番号を取得
    try {
        const stages = MasterData.getStages();
        for (const s of stages) {
            if (s.type === 'contest' && typeof s.season === 'number' && s.season > maxSeason) {
                maxSeason = s.season;
            }
        }
    } catch {}

    // 2. CSV ディレクトリから最大シーズン番号を取得
    for (const dir of CSV_CANDIDATE_DIRS) {
        if (dir && fs.existsSync(dir)) {
            try {
                const files = fs.readdirSync(dir);
                for (const f of files) {
                    const match = f.match(/^match_history_(\d+)\.csv$/);
                    if (match) {
                        const s = parseInt(match[1], 10);
                        if (s > maxSeason) maxSeason = s;
                    }
                }
            } catch {}
        }
    }
    return maxSeason;
}

/**
 * 日付を JST (Asia/Tokyo) 基準の YY/MM/DD 形式に変換する
 */
export function formatDateToYYMMDD(date: Date): string {
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
export async function saveContestMatchToMongo(
    analysis: ContestAnalysisResult,
    options: UpdateOptions = {}
): Promise<string | null> {
    const season = options.season ?? getLatestSeasonNumber();
    const targetDate = options.date ?? new Date();
    const dateStr = formatDateToYYMMDD(targetDate);
    const userId = options.userId ?? config.userId;

    let client: MongoClient | null = null;
    try {
        client = new MongoClient(config.mongoUri, { serverSelectionTimeoutMS: 5000 });
        await client.connect();
        const db = client.db(config.mongoDb);
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
        const result = await col.updateOne(
            { season, date: dateStr, matchIndex: analysis.matchIndex },
            { $set: doc },
            { upsert: true }
        );

        const insertedId = result.upsertedId?.toString() ?? null;
        console.log(`[MongoDB] contest_matches upserted: season=${season} date=${dateStr} match=${analysis.matchIndex}`);
        return insertedId;
    } catch (err: any) {
        // MongoDB 保存失敗はログのみ（CSV保存は続行）
        console.error('[MongoDB] Failed to save contest match:', err.message);
        return null;
    } finally {
        if (client) await client.close();
    }
}

/**
 * 解析結果を match_history_XX.csv に反映・上書き保存し、MongoDB にも保存する。
 */
export async function updateMatchHistoryCsv(
    analysis: ContestAnalysisResult,
    options: UpdateOptions = {}
): Promise<UpdateResult> {
    const season = options.season ?? getLatestSeasonNumber();
    const targetDate = options.date ?? new Date();
    const dateStr = formatDateToYYMMDD(targetDate);

    let csvPath = options.targetFilePath ?? findMatchHistoryCsv(season);

    if (!fs.existsSync(csvPath)) {
        csvPath = createMatchHistoryTemplate(season);
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
    const matchingIndices: number[] = [];
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
    } else {
        lines.push(newRow);
        targetLineIndex = lines.length - 1;
    }

    const updatedContent = lines.join('\n');
    fs.writeFileSync(csvPath, updatedContent, 'utf-8');

    // shared/agent-instructions または gakumas-tools/agent-instructions 等の主要候補にも同期
    const candidateDirsToSync = [
        '/root/gakumas-workspace/shared/agent-instructions',
        '/root/gakumas-workspace/gakumas-tools/agent-instructions'
    ];
    for (const dir of candidateDirsToSync) {
        if (fs.existsSync(dir)) {
            const mirrorPath = path.join(dir, `match_history_${season}.csv`);
            if (mirrorPath !== csvPath) {
                try { fs.writeFileSync(mirrorPath, updatedContent, 'utf-8'); } catch {}
            }
        }
    }

    // MongoDB への保存（失敗してもCSV保存の結果には影響させない）
    const mongoId = await saveContestMatchToMongo(analysis, options);

    // Google スプレッドシート（Contest タブ）への即時同期
    const sheetsResult = await syncContestMatchesToSheets();

    return {
        filePath: csvPath,
        updatedLine: newRow,
        lineIndex: targetLineIndex + 1,
        ...(mongoId ? { mongoId } : {}),
        sheetsSuccess: sheetsResult.success,
        ...(sheetsResult.error ? { sheetsError: sheetsResult.error } : {})
    };
}

/**
 * MongoDB の最新対戦記録を Google スプレッドシート（Contest シート）へ同期する
 */
export async function syncContestMatchesToSheets(): Promise<{ success: boolean; error?: string; output?: string }> {
    return runSyncScript(['--execute']);
}

/**
 * Google スプレッドシートと MongoDB の対戦記録を双方向同期する
 * (スプレッドシートの手入力データを MongoDB に取り込み ➔ MongoDB の最新確定データをスプレッドシートに書き出し)
 */
export async function syncContestMatchesBidirectional(): Promise<{ success: boolean; error?: string; output?: string }> {
    return runSyncScript(['--mode', 'bidirectional', '--execute']);
}

function runSyncScript(args: string[]): Promise<{ success: boolean; error?: string; output?: string }> {
    return new Promise((resolve) => {
        const candidates = [
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
        const child = spawn('node', [scriptPath, ...args], {
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
            } else {
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
