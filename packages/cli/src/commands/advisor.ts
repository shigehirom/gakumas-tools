import { spawn } from 'child_process';
import { LOCAL_SCRIPTS_DIR, GAKUMAS_TOOLS_ROOT } from '../utils/runner';
import * as path from 'path';

export function registerAdvisorCommand(cli: any) {
    cli.command('advisor <stage> [runs] [idolName] [plan]', 'Memory tuning and target setting advisor')
        .option('--mode <mode>', 'Advisor mode: params or cards')
        .option('--supportBonus <value>', 'Support bonus value (default: 0.04)')
        .option('--discord', 'Send summary report to Discord Webhook')
        .option('--sort <order>', 'Sort order of report: normal or reverse')
        .action(async (stage: string, runs?: string, idolName?: string, plan?: string, options?: any) => {
            if (runs && isNaN(Number(runs))) {
                plan = idolName;
                idolName = runs;
                runs = undefined;
            }

            if (!options.mode || (options.mode !== 'params' && options.mode !== 'cards')) {
                console.error('Error: --mode is required and must be either "params" or "cards"');
                process.exit(1);
            }

            if (!process.env.MONGODB_URI) {
                console.error('Error: MONGODB_URI is not set in environment (check .env.local)');
                process.exit(1);
            }

            const args = [process.env.MONGODB_URI, stage];
            args.push(runs || '500');

            if (idolName) args.push('--idolName', idolName);
            if (plan) args.push('--plan', plan);
            
            args.push('--mode', options.mode);

            if (options.supportBonus) {
                args.push('--supportBonus', options.supportBonus);
            } else if (process.env.SUPPORT_BONUS) {
                args.push('--supportBonus', process.env.SUPPORT_BONUS);
            }

            if (options.discord) {
                args.push('--discord');
            }

            if (options.sort) {
                args.push('--sort', options.sort);
            }

            try {
                const scriptPath = path.join(LOCAL_SCRIPTS_DIR, 'advisor-process.mjs');
                const child = spawn('node', [
                    '--max-old-space-size=4096',
                    '--no-warnings',
                    '--loader',
                    './scripts/extensionless-loader.mjs',
                    scriptPath,
                    ...args
                ], {
                    cwd: GAKUMAS_TOOLS_ROOT,
                    stdio: ['inherit', 'pipe', 'inherit'],
                    env: { ...process.env }
                });

                child.stdout.pipe(process.stdout);

                await new Promise<void>((resolve, reject) => {
                    child.on('close', (code) => {
                        if (code === 0) resolve();
                        else reject(new Error(`Script exited with code ${code}`));
                    });
                    child.on('error', reject);
                });

            } catch (error) {
                console.error('Advisor run failed:', error);
                process.exit(1);
            }
        });
}
