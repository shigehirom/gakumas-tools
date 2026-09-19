import { CAC } from 'cac';
import { spawn } from 'child_process';
import * as path from 'path';

export function registerMatchHistoryCommand(cli: CAC) {
    cli.command('match-history [season]', 'Sync contest match records between MongoDB and Google Sheets (CSV is deprecated)')
        .action(async () => {
            console.log('[match-history] Note: match_history CSV files have been deprecated.');
            console.log('[match-history] Running sync-contest-matches.mjs (bidirectional sync between MongoDB & Google Sheets)...');
            const scriptPath = path.resolve(__dirname, '../../scripts/sync-contest-matches.mjs');
            const child = spawn('node', [scriptPath, '--mode', 'bidirectional', '--execute'], {
                stdio: 'inherit',
                env: process.env,
            });
            child.on('close', (code) => {
                process.exit(code || 0);
            });
        });
}
