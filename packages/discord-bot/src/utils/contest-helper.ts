import * as fs from 'fs';
import * as path from 'path';
import { config } from '../config';
import { MasterData } from './master-data';

/**
 * 現在開催中の最新コンテストシーズンを取得します
 */
export function getCurrentSeason(): number {
    const allStages = MasterData.getStages();
    const contestStages = allStages.filter((s: any) => s.type === 'contest');
    if (contestStages.length === 0) return 50;

    // 最大のシーズン番号を返す
    const seasons = contestStages.map((s: any) => s.season).filter((n: any) => typeof n === 'number');
    return Math.max(...seasons);
}

export interface DeckIdolInfo {
    idol: string;
    rank: string;
    mainMem: string;
    subMem: string;
    medianScore: number;
}

export interface StageDeckResult {
    stageNum: number;
    totalExpectedScore: number;
    idols: DeckIdolInfo[];
    overallScore?: number;
    sourceFile?: string;
}

/**
 * 最新の最適化デッキ Markdown ファイルを探索して指定ステージの編成を抽出
 */
export function getOptimizedDeckFromFiles(stageNum: number): StageDeckResult | null {
    const searchDirs = [
        process.env.CLI_DOCS_DIR,
        '/root/gakumas-workspace/shared/documents',
        '/shared/documents',
        '/app/documents',
        '/app/shared/documents',
        path.resolve(process.cwd(), '../../shared/documents'),
        path.resolve(process.cwd(), '../shared/documents'),
        path.resolve(process.cwd(), 'shared/documents'),
        path.resolve(process.cwd(), 'documents'),
        path.resolve(process.cwd(), 'packages/cli'),
        path.resolve(__dirname, '../../../../shared/documents'),
        path.resolve(__dirname, '../../../cli'),
        config.docsDir
    ].filter(Boolean) as string[];

    let allFiles: { fullPath: string; filename: string }[] = [];
    for (const dir of searchDirs) {
        if (fs.existsSync(dir)) {
            try {
                const found = fs.readdirSync(dir)
                    .filter(f => f.endsWith('_optimized.md'))
                    .map(f => ({ fullPath: path.join(dir, f), filename: f }));
                allFiles.push(...found);
            } catch {}
        }
    }

    if (allFiles.length === 0) return null;

    // ファイル名で降順ソート (最新の日付・シーズンのものを取得)
    allFiles.sort((a, b) => b.filename.localeCompare(a.filename));
    const latestFile = allFiles[0].fullPath;
    const content = fs.readFileSync(latestFile, 'utf-8');

    // 総合期待中央値を抽出
    let overallScore: number | undefined;
    const overallMatch = content.match(/総合期待中央値：約\s*([\d,]+)\s*Pt/);
    if (overallMatch) {
        overallScore = parseInt(overallMatch[1].replace(/,/g, ''), 10);
    }

    // 指定ステージのセクションを抽出
    // ### ■ ステージ1
    const stagePattern = new RegExp(`###\\s+■\\s+ステージ${stageNum}([\\s\\S]*?)(?=###\\s+■\\s+ステージ|$)`, 'i');
    const stageMatch = content.match(stagePattern);
    if (!stageMatch) return null;

    const stageSection = stageMatch[1];
    let totalScore = 0;
    const totalMatch = stageSection.match(/合計期待中央値：約\s*([\d,]+)\s*Pt/);
    if (totalMatch) {
        totalScore = parseInt(totalMatch[1].replace(/,/g, ''), 10);
    }

    const idols: DeckIdolInfo[] = [];
    const lines = stageSection.split('\n');
    for (const line of lines) {
        // | アイドル | #1 | メイン | サブ | 54000 |
        if (line.startsWith('|') && !line.includes('アイドル') && !line.includes(':---')) {
            const cols = line.split('|').map(c => c.trim()).filter(c => c.length > 0);
            if (cols.length >= 5) {
                const idol = cols[0];
                const rank = cols[1];
                const mainMem = cols[2];
                const subMem = cols[3];
                const medianScore = parseInt(cols[4].replace(/,/g, ''), 10) || 0;
                idols.push({ idol, rank, mainMem, subMem, medianScore });
            }
        }
    }

    return {
        stageNum,
        totalExpectedScore: totalScore,
        idols,
        overallScore,
        sourceFile: path.basename(latestFile)
    };
}
