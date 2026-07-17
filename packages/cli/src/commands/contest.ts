import { spawn } from 'child_process';
import { LOCAL_SCRIPTS_DIR, GAKUMAS_TOOLS_ROOT } from '../utils/runner';
import * as fs from 'fs';
import * as path from 'path';
import importHandlebars from 'handlebars';
import { parseJsonStream } from '../utils/json-stream';

const Handlebars = importHandlebars;

export function registerContestCommand(cli: any) {
    cli.command('contest <stage> [runs] [idolName] [plan]', 'Optimize memories using remote DB')
        .option('--synth', 'Simulate card synthesis')
        .option('--showWorst', 'Show worst combinations')
        .option('--json', 'Output results as JSON')
        .option('--compare <pattern>', 'Compare memories matching pattern (e.g. "再生成*")')
        .option('--force', 'Force re-calculate and overwrite cache')
        .option('--save [count]', 'Save the top N combinations to loadouts (default: 1, max: 5)')
        .option('--name <name>', 'Name for the saved loadout')
        .option('--userId <id>', 'User ID to save the loadout for')
        .option('--supportBonus <value>', 'Support bonus value (default: 0.04)')
        .option('--step', 'Enable two-phase simulation (screening + high-precision)')
        .option('--allResults', 'Return all combinations results')
        .option('--filterHashes <hashes>', 'Filter candidates by hashes (JSON array string)')
        .action(async (stage: string, runs?: string, idolName?: string, plan?: string, options?: any) => {
            // Check if runs is actually idolName (if user skipped runs e.g. "contest 37-3 hiro")
            if (runs && isNaN(Number(runs))) {
                plan = idolName;
                idolName = runs;
                runs = undefined;
            }
            // opt-remote is a wrapper around optimize-memories-parallel.mjs
            // checking env vars
            if (!process.env.MONGODB_URI) {
                console.error('Error: MONGODB_URI is not set in environment (check .env.local)');
                process.exit(1);
            }

            // Construct arguments with positional args as expected by NEW upstream optimize-memories-parallel.mjs
            // formatting: <source> <season-stage> <num_runs> [options]
            const args = [process.env.MONGODB_URI!, stage];

            // runs is now required positionally or we pass default? 
            // The script says <num_runs> is required in usage, but code might output error.
            // Let's pass runs or default 1000 if undefined?
            // CLI arg runs is optional.
            args.push(runs || "1000");

            if (idolName) args.push(`--idolName`, idolName);
            if (plan) args.push(`--plan`, plan);

            // Pass synth/showWorst
            if (options.synth) args.push('--synth');
            if (options.showWorst) args.push('--showWorst');
            if (options.compare) args.push('--compare', options.compare);
            if (options.force) args.push('--force');
            if (options.save) {
                args.push('--save');
                if (typeof options.save === 'number' || typeof options.save === 'string') {
                    args.push(String(options.save));
                }
            }
            if (options.name) args.push('--name', options.name);
            // Preserve string precision for userId
            let userIdStr = undefined;
            const argIdx = process.argv.indexOf('--userId');
            if (argIdx !== -1 && process.argv.length > argIdx + 1) {
                userIdStr = process.argv[argIdx + 1];
            } else {
                const eqArg = process.argv.find(a => a.startsWith('--userId='));
                if (eqArg) userIdStr = eqArg.split('=')[1];
            }
            if (userIdStr) args.push('--userId', userIdStr);
            else if (options.userId) args.push('--userId', String(options.userId));

            if (options.supportBonus) {
                args.push('--supportBonus', options.supportBonus);
            } else if (process.env.SUPPORT_BONUS) {
                args.push('--supportBonus', process.env.SUPPORT_BONUS);
            }

            if (options.allResults) args.push('--allResults');
            if (options.filterHashes) args.push('--filterHashes', options.filterHashes);
            if (options.step) args.push('--step');

            // Always use JSON if we want to template it.
            // But we only want to suppress console output if we are templating.
            // If the user did NOT pass --json to CLI, we still run with --json to capture output,
            // but then we render the template.

            args.push('--json');

            try {
                // Determine template if not raw JSON
                let template: any;
                if (!options.json) {
                    Handlebars.registerHelper('round', function (value: any) {
                        return isNaN(value) ? value : Math.round(value);
                    });
                    Handlebars.registerHelper('inc', function (value: any) {
                        return parseInt(value) + 1;
                    });
                    const templatePath = path.join(__dirname, '../templates/contest.hbs');
                    const templateContent = fs.readFileSync(templatePath, 'utf-8');
                    template = Handlebars.compile(templateContent);
                }

                const scriptPath = path.join(LOCAL_SCRIPTS_DIR, 'boot-contest.mjs');
                const child = spawn('node', ['--max-old-space-size=4096', '--no-warnings', '--loader', './scripts/extensionless-loader.mjs', scriptPath, ...args], {
                    cwd: GAKUMAS_TOOLS_ROOT,
                    stdio: ['inherit', 'pipe', 'inherit'],
                    env: { ...process.env }
                });

                let outputBuffer = '';
                let parsedCount = 0;
                let allResults: any[] = [];

                if (options.json) {
                    child.stdout.pipe(process.stdout);
                } else {
                    child.stdout.on('data', (data) => {
                        outputBuffer += data.toString();

                        // Extract and parse complete JSON objects
                        let start = outputBuffer.indexOf('{');
                        while (start !== -1) {
                            let depth = 0;
                            let end = -1;
                            let inString = false;
                            let escaped = false;

                            for (let i = start; i < outputBuffer.length; i++) {
                                const char = outputBuffer[i];
                                if (!inString) {
                                    if (char === '{') depth++;
                                    else if (char === '}') {
                                        depth--;
                                        if (depth === 0) {
                                            end = i;
                                            break;
                                        }
                                    } else if (char === '"') inString = true;
                                } else {
                                    if (escaped) escaped = false;
                                    else if (char === '\\') escaped = true;
                                    else if (char === '"') inString = false;
                                }
                            }

                            if (end !== -1) {
                                const jsonStr = outputBuffer.substring(start, end + 1);
                                try {
                                    const itemData = JSON.parse(jsonStr);
                                    
                                    // If there are no results (e.g. no valid memories found), skip printing the template
                                    if (itemData.best && itemData.best.score !== undefined && itemData.best.score !== null) {
                                        if (parsedCount > 0) console.log('\n\n');
                                        
                                        if (idolName === 'all' || idolName?.includes('all')) {
                                            if (itemData.topCombinations && itemData.topCombinations.length > 0) {
                                                const top = itemData.topCombinations[0];
                                                allResults.push({
                                                    idol: itemData.best.idolName,
                                                    score: top.median || itemData.best.score,
                                                    mainMem: { id: top.mainName, song: top.mainTitle },
                                                    subMem: { id: top.subName, song: top.subTitle }
                                                });
                                            }
                                        }

                                        if (options.compare) {
                                            (itemData as any).isCompare = true;
                                            (itemData as any).comparePattern = options.compare;
                                            const pattern = new RegExp(options.compare.replace(/\*/g, '.*'));
                                            (itemData as any).compareResults = (itemData as any).worstCombinations.filter((c: any) =>
                                                c.mainName && pattern.test(c.mainName)
                                            );
                                            (itemData as any).compareResults.sort((a: any, b: any) => b.score - a.score);
                                        }

                                        console.log(template(itemData));
                                        parsedCount++;
                                    }
                                } catch (e) {
                                    // console.error("Failed to parse JSON chunk:", e);
                                }
                                // Truncate buffer
                                outputBuffer = outputBuffer.substring(end + 1);
                                start = outputBuffer.indexOf('{');
                            } else {
                                break; // Incomplete JSON
                            }
                        }
                    });
                }

                await new Promise<void>((resolve, reject) => {
                    child.on('close', (code) => {
                        if (code === 0) resolve();
                        else reject(new Error(`Script exited with code ${code}`));
                    });
                    child.on('error', reject);
                });
                
                if (!options.json && (idolName === 'all' || idolName?.includes('all')) && allResults.length >= 3) {
                    allResults.sort((a, b) => b.score - a.score);
                    const combs = [];
                    const n = allResults.length;
                    for (let i = 0; i < n; i++) {
                        for (let j = i + 1; j < n; j++) {
                            for (let k = j + 1; k < n; k++) {
                                const i1 = allResults[i];
                                const i2 = allResults[j];
                                const i3 = allResults[k];
                                if (i1.idol !== i2.idol && i2.idol !== i3.idol && i1.idol !== i3.idol) {
                                    combs.push({ score: i1.score + i2.score + i3.score, items: [i1, i2, i3] });
                                }
                            }
                        }
                    }
                    if (combs.length > 0) {
                        combs.sort((a, b) => b.score - a.score);
                        const bestCombo = combs[0];
                        console.log(`\n\n### ■ 単一ステージ最適化 (Top 3)\n`);
                        console.log(`**合計期待中央値：約 ${bestCombo.score.toLocaleString()} Pt**\n`);
                        console.log(`| アイドル | ファイル内順位 | メインメモリー (ID) | サブメモリー (ID) | 中央値 ($Q_2$) |`);
                        console.log(`| :--- | :---: | :--- | :--- | ---: |`);
                        for (const item of bestCombo.items) {
                            console.log(`| ${item.idol} | #1 | ${item.mainMem.id}【${item.mainMem.song}】 | ${item.subMem.id}【${item.subMem.song}】 | ${item.score.toLocaleString()} |`);
                        }
                    }
                }

            } catch (error) {
                console.error('Remote optimization failed:', error);
                process.exit(1);
            }
        });
}
