import * as fs from 'fs';
import * as path from 'path';

export function registerOptimizeDeckCommand(cli: any) {
    cli.command('optimize-deck <prefix>', 'Optimize contest deck across 3 stages based on generated local MD reports')
        .action((prefix: string, options?: any) => {
            const baseDir = process.env.CLI_DOCS_DIR
                ? path.resolve(process.env.INIT_CWD || process.cwd(), process.env.CLI_DOCS_DIR)
                : (process.env.INIT_CWD || process.cwd());
            
            const file1 = path.join(baseDir, `${prefix}-1_all.md`);
            const file2 = path.join(baseDir, `${prefix}-2_all.md`);
            const file3 = path.join(baseDir, `${prefix}-3_all.md`);
            
            if (!fs.existsSync(file1)) {
                console.error(`Error: File not found: ${file1}`);
                process.exit(1);
            }
            if (!fs.existsSync(file2)) {
                console.error(`Error: File not found: ${file2}`);
                process.exit(1);
            }
            if (!fs.existsSync(file3)) {
                console.error(`Error: File not found: ${file3}`);
                process.exit(1);
            }
            
            const stage1 = parseMarkdown(file1);
            const stage2 = parseMarkdown(file2);
            const stage3 = parseMarkdown(file3);
            
            const bestCombo = solveOptimization(stage1, stage2, stage3);
            
            if (!bestCombo) {
                console.log("制約を満たす組み合わせが見つかりませんでした。");
                return;
            }
            
            const totalExpected = bestCombo[0].score + bestCombo[1].score + bestCombo[2].score;
            
            let report = `# コンテスト最適編成報告\n\n`;
            report += `**総合期待中央値：約 ${totalExpected.toLocaleString()} Pt**\n\n`;
            
            report += formatTable(1, bestCombo[0]) + "\n";
            report += formatTable(2, bestCombo[1]) + "\n";
            report += formatTable(3, bestCombo[2]) + "\n";
            
            report += `### ■ 戦略的アナライズ・要注目箇所の解説\n`;
            report += `1. **最適化ロジックの適用結果**: 全ステージ間での「同一アイドルかつ同一衣装」の重複を排除しつつ、理論上の最大中央値（$Q_2$）を達成する組み合わせを算出しました。\n`;
            
            console.log(report);
        });
}

function parseMarkdown(filepath: string) {
    const results: any[] = [];
    const content = fs.readFileSync(filepath, 'utf-8');
    const lines = content.split('\n');
    
    let currentIdol = "";
    
    for (const line of lines) {
        // ## 47677 - 花海咲季 【古今東西ちょちょいのちょい】【Campus mode!!】
        const headerMatch = line.match(/^##\s+[\d,]+\s+-\s+([^\s]+)\s+【(.*?)】【(.*?)】/);
        if (headerMatch) {
            currentIdol = headerMatch[1];
            continue;
        }
        
        // | 1 | 26/01/23＿14877【古今東西ちょちょいのちょい】 | 25/08/28🛠️14502【Campus mode!!】 | ... | 46415 | ...
        const rankMatch = line.match(/^\|\s*1\s*\|/);
        if (rankMatch && currentIdol) {
            const cols = line.split('|').map(c => c.trim());
            if (cols.length >= 10) {
                const mainMemRaw = cols[2];
                const subMemRaw = cols[3];
                const medianScore = parseInt(cols[6].replace(/,/g, ''), 10);
                
                const parseMem = (raw: string) => {
                    const m = raw.match(/^(.*?)【(.*?)】$/);
                    if (m) {
                        return { id: m[1], song: m[2] };
                    }
                    return { id: raw, song: "" };
                };
                
                const mainMem = parseMem(mainMemRaw);
                const subMem = parseMem(subMemRaw);
                
                results.push({
                    idol: currentIdol,
                    score: medianScore,
                    mainMem: mainMem,
                    subMem: subMem
                });
            }
            currentIdol = ""; // Only process Rank 1
        }
    }
    
    return results.sort((a, b) => b.score - a.score);
}

function solveOptimization(stage1: any[], stage2: any[], stage3: any[]) {
    let bestScore = -1;
    let bestCombination: any[] | null = null;

    const getMemStrings = (item: any) => {
        return [
            `${item.idol}【${item.mainMem.song}】`,
            `${item.idol}【${item.subMem.song}】`
        ];
    };

    const getStageCombinations = (stageData: any[]) => {
        const combs: any[] = [];
        const n = stageData.length;
        for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
                for (let k = j + 1; k < n; k++) {
                    const i1 = stageData[i];
                    const i2 = stageData[j];
                    const i3 = stageData[k];
                    if (i1.idol !== i2.idol && i2.idol !== i3.idol && i1.idol !== i3.idol) {
                        const totalScore = i1.score + i2.score + i3.score;
                        combs.push({
                            score: totalScore,
                            items: [i1, i2, i3]
                        });
                    }
                }
            }
        }
        return combs.sort((a, b) => b.score - a.score);
    };

    const s1Combs = getStageCombinations(stage1);
    const s2Combs = getStageCombinations(stage2);
    const s3Combs = getStageCombinations(stage3);

    for (const c1 of s1Combs) {
        const memSet1 = new Set<string>();
        for (const item of c1.items) {
            getMemStrings(item).forEach(s => memSet1.add(s));
        }

        for (const c2 of s2Combs) {
            let overlap2 = false;
            for (const item of c2.items) {
                const mems = getMemStrings(item);
                if (memSet1.has(mems[0]) || memSet1.has(mems[1])) {
                    overlap2 = true;
                    break;
                }
            }
            if (overlap2) continue;
            
            if (bestCombination && (c1.score + c2.score + s3Combs[0].score) <= bestScore) {
                break; 
            }

            const memSet12 = new Set(memSet1);
            for (const item of c2.items) {
                getMemStrings(item).forEach(s => memSet12.add(s));
            }

            for (const c3 of s3Combs) {
                let overlap3 = false;
                for (const item of c3.items) {
                    const mems = getMemStrings(item);
                    if (memSet12.has(mems[0]) || memSet12.has(mems[1])) {
                        overlap3 = true;
                        break;
                    }
                }
                if (overlap3) continue;

                const totalScore = c1.score + c2.score + c3.score;
                if (totalScore > bestScore) {
                    bestScore = totalScore;
                    bestCombination = [c1, c2, c3];
                }
                break; 
            }
        }
    }

    return bestCombination;
}

function formatTable(stageNum: number, combination: any) {
    let output = `### ■ ステージ${stageNum}\n`;
    output += `**合計期待中央値：約 ${combination.score.toLocaleString()} Pt**\n\n`;
    output += `| アイドル | ファイル内順位 | メインメモリー (ID) | サブメモリー (ID) | 中央値 ($Q_2$) |\n`;
    output += `| :--- | :---: | :--- | :--- | ---: |\n`;
    
    for (const item of combination.items) {
        output += `| ${item.idol} | #1 | ${item.mainMem.id}【${item.mainMem.song}】 | ${item.subMem.id}【${item.subMem.song}】 | ${item.score.toLocaleString()} |\n`;
    }
    
    return output;
}
