import { cac } from 'cac';
import { registerDumpCommand } from './commands/dump';
import { registerContestCommand } from './commands/contest';
import { registerStatsCommand } from './commands/stats';
import { registerListCommand } from './commands/list';
import { registerRmCommand } from './commands/rm';
import { registerRehearsalCommand } from './commands/rehearsal';
import { registerLoadoutCommand } from './commands/loadout';
import { registerDuplicatesCommand } from './commands/duplicates';
import { registerOptimizeDeckCommand } from './commands/optimize-deck';
import { registerMatchHistoryCommand } from './commands/match-history';
import * as fs from 'fs';
import * as path from 'path';
import { GlobalCapture } from './utils/capture';
import { GoogleDriveClient } from './utils/gdrive';

// Load .env.local
const possiblePaths = [
    path.resolve(process.cwd(), '.env.local'),
    path.resolve(__dirname, '../../.env.local'),
    path.resolve(__dirname, '../../../.env.local'),
    path.resolve(__dirname, '../../../gakumas-tools/.env.local'),
    path.resolve(process.cwd(), 'gakumas-tools/.env.local')
];

for (const p of possiblePaths) {
    if (fs.existsSync(p)) {
        const content = fs.readFileSync(p, 'utf-8');
        content.split('\n').forEach(line => {
            const match = line.match(/^([^=]+)=(.*)$/);
            if (match) {
                const key = match[1].trim();
                const val = match[2].trim().replace(/^["'](.*)["']$/, '$1');
                if (!process.env[key]) {
                    process.env[key] = val;
                }
            }
        });
        break;
    }
}

const cli = cac('yarn cli');

// Global options
cli.option('--gdrive [filename]', 'Upload standard output to Google Drive');
cli.option('--local [filename]', 'Save standard output to a local file');

// Filter out `--` which might be inserted by yarn workspace start
const filteredArgsForCac = process.argv[0].includes('node')
    ? [process.argv[0], process.argv[1], ...process.argv.slice(2).filter(a => a !== '--')]
    : process.argv.filter(a => a !== '--');

// Helper to check and enable capture
const parsed = cli.parse(filteredArgsForCac, { run: false });

const needsDefaultName = 
    parsed.options.gdrive === true || parsed.options.gdrive === '' ||
    parsed.options.local === true || parsed.options.local === '';

if (needsDefaultName) {
    const now = new Date();
    const yy = String(now.getFullYear()).slice(2);
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const datePrefix = `${yy}-${mm}-${dd}`;

    let defaultName = `${datePrefix}_output.md`;

    const cmdName = parsed.args[0];

    if (cmdName === 'contest') {
        const stage = parsed.args[1] || 'unknown';
        let idols = 'all';
        if (parsed.args.length > 3) {
            idols = parsed.args[3];
        } else if (parsed.args.length === 3 && isNaN(Number(parsed.args[2]))) {
            idols = parsed.args[2];
        }
        idols = idols.replace(/,/g, '+');
        defaultName = `${datePrefix}_${stage}_${idols}.md`;
    } else if (cmdName === 'rehearsal') {
        const decks = parsed.args.slice(2);
        if (decks.length > 0 && decks[0]) {
            const firstDeckParts = decks[0].split('_');
            const stagePart = firstDeckParts[1] || 'unknown';
            defaultName = `${datePrefix}_${stagePart}_rehearsal.md`;
        } else {
            defaultName = `${datePrefix}_rehearsal.md`;
        }
    } else if (cmdName === 'tournament') {
        const stage = parsed.args[1] || 'unknown';
        const idols = parsed.args[3] || 'all';
        defaultName = `${datePrefix}_tournament_${stage}_${idols.replace(/,/g, '+')}.md`;
    } else if (cmdName === 'list') {
        const idolFilter = parsed.args[1];
        if (idolFilter) {
            defaultName = `${datePrefix}_list_${idolFilter.replace(/,/g, '+')}.md`;
        } else {
            defaultName = `${datePrefix}_list.md`;
        }
    } else if (cmdName === 'dump') {
        const idolName = parsed.args[1];
        if (idolName) {
            defaultName = `${datePrefix}_dump_${idolName.replace(/,/g, '+')}.md`;
        } else {
            defaultName = `${datePrefix}_dump.md`;
        }
    } else if (cmdName === 'stats') {
        const idolFilter = parsed.args[1] || 'summary';
        defaultName = `${datePrefix}_stats_${idolFilter.replace(/,/g, '+')}.md`;
    } else if (cmdName === 'duplicates') {
        const plan = parsed.args[1] || 'all';
        const idol = parsed.args[2] || 'all';
        defaultName = `${datePrefix}_duplicates_${plan}_${idol.replace(/,/g, '+')}.md`;
    } else if (cmdName === 'optimize-deck') {
        const prefix = parsed.args[1] || 'unknown';
        defaultName = `${prefix}_optimized.md`;
    }

    if (parsed.options.gdrive === true || parsed.options.gdrive === '') {
        parsed.options.gdrive = defaultName;
    }
    if (parsed.options.local === true || parsed.options.local === '') {
        parsed.options.local = defaultName;
    }
}

if (parsed.options.gdrive || parsed.options.local) {
    GlobalCapture.enable();
    let uploaded = false;
    process.on('beforeExit', async () => {
        if (uploaded) return;
        uploaded = true;
        const output = GlobalCapture.getCapturedOutput();
        if (output && output.trim().length > 0) {
            let finalOutput = output;
            let gdriveUrl: string | undefined = undefined;

            if (parsed.options.gdrive) {
                try {
                    console.error(`\n[Gakumas CLI] Uploading report to Google Drive: ${parsed.options.gdrive}...`);
                    gdriveUrl = await GoogleDriveClient.uploadFile(parsed.options.gdrive, output);
                    if (gdriveUrl) {
                        console.error(`[Gakumas CLI] Upload successful! URL: ${gdriveUrl}`);
                        
                        // YAMLフロントマターを先頭に付与
                        const yamlFrontmatter = `---\nreference_url: "${gdriveUrl}"\n---\n\n`;
                        finalOutput = yamlFrontmatter + output;

                        // Google Drive上のファイルをYAMLフロントマター付きの内容で更新する
                        console.error(`[Gakumas CLI] Updating Google Drive file with YAML frontmatter...`);
                        await GoogleDriveClient.uploadFile(parsed.options.gdrive, finalOutput);
                        
                        // URLを .gdriveurl ファイルに保存
                        const baseDir = process.env.CLI_DOCS_DIR
                            ? path.resolve(process.env.INIT_CWD || process.cwd(), process.env.CLI_DOCS_DIR)
                            : (process.env.INIT_CWD || process.cwd());
                        const referenceName = parsed.options.local || parsed.options.gdrive;
                        const urlPath = path.resolve(baseDir, `${referenceName}.gdriveurl`);
                        
                        const outputDir = path.dirname(urlPath);
                        if (!fs.existsSync(outputDir)) {
                            fs.mkdirSync(outputDir, { recursive: true });
                        }
                        fs.writeFileSync(urlPath, gdriveUrl, 'utf-8');
                    } else {
                        console.error(`[Gakumas CLI] Upload successful, but URL could not be retrieved.`);
                    }
                } catch (e) {
                    console.error('[Gakumas CLI] Upload error in exit hook:', e);
                }
            }

            if (parsed.options.local) {
                try {
                    const baseDir = process.env.CLI_DOCS_DIR
                        ? path.resolve(process.env.INIT_CWD || process.cwd(), process.env.CLI_DOCS_DIR)
                        : (process.env.INIT_CWD || process.cwd());
                    const localPath = path.resolve(baseDir, parsed.options.local);
                    
                    const outputDir = path.dirname(localPath);
                    if (!fs.existsSync(outputDir)) {
                        fs.mkdirSync(outputDir, { recursive: true });
                    }

                    // YAMLフロントマター付きの最終出力をローカルに保存
                    fs.writeFileSync(localPath, finalOutput, 'utf-8');
                    console.error(`\n[Gakumas CLI] Saved report locally to: ${localPath}`);
                } catch (e) {
                    console.error('[Gakumas CLI] Local save error in exit hook:', e);
                }
            }
        }
    });
}

registerDumpCommand(cli);
registerContestCommand(cli);
registerStatsCommand(cli);
registerListCommand(cli);
registerRmCommand(cli);
registerRehearsalCommand(cli);
registerLoadoutCommand(cli);
registerDuplicatesCommand(cli);
registerOptimizeDeckCommand(cli);
registerMatchHistoryCommand(cli);

cli.help();
cli.version('0.1.0');

const parsedFinal = cli.parse(filteredArgsForCac);

if (!cli.matchedCommand && !parsedFinal.options.help && !parsedFinal.options.version) {
    cli.outputHelp();
}
