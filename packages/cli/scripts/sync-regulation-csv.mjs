#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '../../..');

const candidateDirs = [
    process.env.CLI_INSTRUCTIONS_DIR,
    path.resolve(projectRoot, '../shared/agent-instructions'),
    path.resolve(projectRoot, 'agent-instructions'),
    '/root/gakumas-workspace/shared/agent-instructions',
    '/root/gakumas-workspace/gakumas-tools/agent-instructions',
    '/mnt/NVMe/gakumas-tools/agent-instructions',
    '/app/agent-instructions'
].filter(Boolean);

// 重複を除去
const targetDirs = Array.from(new Set(candidateDirs)).filter(d => fs.existsSync(d));

/**
 * regulation_XX.md から Term (begin, end) を抽出
 */
export function parseRegulationTerm(content) {
    const beginMatch = content.match(/begin:\s*([0-9]{4}[/-][0-9]{1,2}[/-][0-9]{1,2})/);
    const endMatch = content.match(/end:\s*([0-9]{4}[/-][0-9]{1,2}[/-][0-9]{1,2})/);
    if (!beginMatch || !endMatch) return null;

    const beginParts = beginMatch[1].replace(/\//g, '-').split('-').map(Number);
    const endParts = endMatch[1].replace(/\//g, '-').split('-').map(Number);

    const begin = new Date(beginParts[0], beginParts[1] - 1, beginParts[2]);
    const end = new Date(endParts[0], endParts[1] - 1, endParts[2]);

    if (isNaN(begin.getTime()) || isNaN(end.getTime())) return null;
    return { begin, end };
}

/**
 * 開始日〜終了日（inclusive）の match_history テンプレート行を生成
 */
export function generateCsvTemplate(startDate, endDate) {
    const lines = ['日付,相手名,メモ,自S1,敵S1,自S2,敵S2,自S3,敵S3,結果,獲得Pt'];
    const current = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
    const end = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());

    while (current <= end) {
        const yy = String(current.getFullYear()).slice(-2);
        const mm = String(current.getMonth() + 1).padStart(2, '0');
        const dd = String(current.getDate()).padStart(2, '0');
        const formattedDate = `${yy}/${mm}/${dd}`;

        for (let i = 0; i < 5; i++) {
            lines.push(`${formattedDate},,3,,,,,,,WIN LOSE,`);
        }
        current.setDate(current.getDate() + 1);
    }
    return lines.join('\n') + '\n';
}

/**
 * 全ディレクトリの regulation_*.md をスキャンし、対応する CSV が無ければ生成する
 */
export function syncRegulationsToCsv() {
    let generatedCount = 0;

    // 全ディレクトリ内の regulation_*.md を収集
    const regulationMap = new Map(); // season -> { filePath, term }

    for (const dir of targetDirs) {
        const files = fs.readdirSync(dir);
        for (const f of files) {
            const match = f.match(/^regulation_(\d+)\.md$/);
            if (match) {
                const season = parseInt(match[1], 10);
                if (!regulationMap.has(season)) {
                    const filePath = path.join(dir, f);
                    try {
                        const content = fs.readFileSync(filePath, 'utf-8');
                        const term = parseRegulationTerm(content);
                        if (term) {
                            regulationMap.set(season, { filePath, term });
                        }
                    } catch (e) {
                        console.error(`[sync-regulation-csv] Error reading ${filePath}:`, e.message);
                    }
                }
            }
        }
    }

    for (const [season, { filePath, term }] of regulationMap.entries()) {
        const csvFileName = `match_history_${season}.csv`;

        // 既存の CSV が存在するか全候補ディレクトリでチェック
        let csvExists = false;
        for (const dir of targetDirs) {
            if (fs.existsSync(path.join(dir, csvFileName))) {
                csvExists = true;
                break;
            }
        }

        if (!csvExists) {
            console.log(`[sync-regulation-csv] Found regulation_${season}.md without ${csvFileName}. Generating template...`);
            const csvContent = generateCsvTemplate(term.begin, term.end);

            for (const dir of targetDirs) {
                const targetPath = path.join(dir, csvFileName);
                try {
                    fs.writeFileSync(targetPath, csvContent, 'utf-8');
                    console.log(`[sync-regulation-csv] Created: ${targetPath}`);
                } catch (e) {
                    console.error(`[sync-regulation-csv] Failed to write to ${targetPath}:`, e.message);
                }
            }
            generatedCount++;
        }
    }

    if (generatedCount === 0) {
        console.log('[sync-regulation-csv] All regulations have matching match_history CSV files.');
    } else {
        console.log(`[sync-regulation-csv] Generated templates for ${generatedCount} season(s).`);
    }

    return generatedCount;
}

// 直接実行された場合
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(__filename)) {
    syncRegulationsToCsv();
}
