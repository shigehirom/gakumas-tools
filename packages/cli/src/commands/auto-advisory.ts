import { CAC } from 'cac';
import { runScript } from '../utils/runner';

export function registerAutoAdvisoryCommand(cli: CAC) {
    cli.command('auto-advisory [season]', 'Derive autonomous contest advisory DSL using simulation beam search')
        .action(async (season?: string) => {
            const args: string[] = [];
            if (season) {
                args.push(season);
            }
            await runScript('auto-advisory-generator.mjs', args);
        });
}

