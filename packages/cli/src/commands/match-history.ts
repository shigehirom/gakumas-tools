import { CAC } from 'cac';
import * as fs from 'fs';
import * as path from 'path';

export function registerMatchHistoryCommand(cli: CAC) {
    cli.command('match-history [season] [startDate] [endDate]', 'Generate a template CSV file for match history (dates can be auto-loaded from regulation_XX.md)')
        .action(async (seasonStr?: string, startDateStr?: string, endDateStr?: string) => {
            const instructionsDir = process.env.CLI_INSTRUCTIONS_DIR || '/root/gakumas-workspace/shared/agent-instructions';
            const candidateDirs = [
                instructionsDir,
                '/root/gakumas-workspace/shared/agent-instructions',
                '/root/gakumas-workspace/gakumas-tools/agent-instructions',
                path.resolve(process.cwd(), 'agent-instructions'),
                path.resolve(process.cwd(), '../shared/agent-instructions')
            ].filter(Boolean);

            const findRegulationFile = (s: number): { path: string; begin: Date; end: Date } | null => {
                for (const d of candidateDirs) {
                    const regPath = path.join(d, `regulation_${s}.md`);
                    if (fs.existsSync(regPath)) {
                        try {
                            const content = fs.readFileSync(regPath, 'utf-8');
                            const beginMatch = content.match(/begin:\s*([0-9]{4}[/-][0-9]{1,2}[/-][0-9]{1,2})/);
                            const endMatch = content.match(/end:\s*([0-9]{4}[/-][0-9]{1,2}[/-][0-9]{1,2})/);
                            if (beginMatch && endMatch) {
                                const bp = beginMatch[1].replace(/\//g, '-').split('-').map(Number);
                                const ep = endMatch[1].replace(/\//g, '-').split('-').map(Number);
                                return {
                                    path: regPath,
                                    begin: new Date(bp[0], bp[1] - 1, bp[2]),
                                    end: new Date(ep[0], ep[1] - 1, ep[2])
                                };
                            }
                        } catch {}
                    }
                }
                return null;
            };

            const generateForSeason = (s: number, start: Date, end: Date) => {
                const lines: string[] = ['日付,相手名,メモ,自S1,敵S1,自S2,敵S2,自S3,敵S3,結果,獲得Pt'];
                const current = new Date(start.getFullYear(), start.getMonth(), start.getDate());
                const endLimit = new Date(end.getFullYear(), end.getMonth(), end.getDate());

                while (current <= endLimit) {
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
                const targetDirs = [instructionsDir, '/root/gakumas-workspace/gakumas-tools/agent-instructions'];

                for (const d of targetDirs) {
                    if (!fs.existsSync(d)) {
                        try { fs.mkdirSync(d, { recursive: true }); } catch {}
                    }
                    if (fs.existsSync(d)) {
                        const targetPath = path.join(d, `match_history_${s}.csv`);
                        fs.writeFileSync(targetPath, csvContent, 'utf-8');
                        console.log(`Successfully generated match history template: ${targetPath}`);
                    }
                }
            };

            // 1. 引数なし: regulation_*.md をスキャンして未作成の CSV をすべて生成
            if (!seasonStr) {
                console.log('No season specified. Scanning regulation_*.md files for missing CSVs...');
                const foundSeasons = new Set<number>();
                for (const d of candidateDirs) {
                    if (fs.existsSync(d)) {
                        for (const f of fs.readdirSync(d)) {
                            const m = f.match(/^regulation_(\d+)\.md$/);
                            if (m) foundSeasons.add(parseInt(m[1], 10));
                        }
                    }
                }

                let created = 0;
                for (const s of Array.from(foundSeasons).sort((a, b) => a - b)) {
                    const exists = candidateDirs.some(d => fs.existsSync(path.join(d, `match_history_${s}.csv`)));
                    if (!exists) {
                        const reg = findRegulationFile(s);
                        if (reg) {
                            console.log(`Found regulation_${s}.md (${reg.begin.toISOString().slice(0, 10)} - ${reg.end.toISOString().slice(0, 10)}). Generating CSV...`);
                            generateForSeason(s, reg.begin, reg.end);
                            created++;
                        }
                    }
                }
                if (created === 0) {
                    console.log('All regulations already have matching match_history CSV files.');
                }
                return;
            }

            // 2. season 指定あり
            const season = parseInt(seasonStr, 10);
            if (isNaN(season)) {
                console.error('Error: season must be a number');
                process.exit(1);
            }

            let start: Date;
            let end: Date;

            if (startDateStr && endDateStr) {
                start = new Date(startDateStr);
                end = new Date(endDateStr);
                if (isNaN(start.getTime()) || isNaN(end.getTime())) {
                    console.error('Error: Invalid start or end date');
                    process.exit(1);
                }
                if (start > end) {
                    console.error('Error: Start date must be before end date');
                    process.exit(1);
                }
            } else {
                // regulation_XX.md から自動取得
                const reg = findRegulationFile(season);
                if (!reg) {
                    console.error(`Error: Could not find regulation_${season}.md and dates were not provided.`);
                    console.error(`Usage: pnpm cli match-history ${season} <startDate> <endDate>`);
                    process.exit(1);
                }
                const formatDateStr = (d: Date) => {
                    const y = d.getFullYear();
                    const m = String(d.getMonth() + 1).padStart(2, '0');
                    const day = String(d.getDate()).padStart(2, '0');
                    return `${y}-${m}-${day}`;
                };
                console.log(`Using dates from ${reg.path}: ${formatDateStr(reg.begin)} to ${formatDateStr(reg.end)}`);
                start = reg.begin;
                end = reg.end;
            }

            generateForSeason(season, start, end);
        });
}
