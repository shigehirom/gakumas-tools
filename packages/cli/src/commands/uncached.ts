
import { CAC } from 'cac';
import { runScript } from '../utils/runner';

export function registerUncachedCommand(cli: CAC) {
    cli.command('uncached <seasonStage>', 'List memories not yet cached for the stage')
        .option('--runs <num>', 'Number of runs', { default: 3000 })
        .option('--supportBonus <value>', 'Support bonus (e.g., 0.04)')
        .action(async (seasonStage, options) => {
            const args = [seasonStage];
            if (options.runs) args.push(String(options.runs));
            if (options.supportBonus) args.push(String(options.supportBonus));

            try {
                await runScript('boot-uncached.mjs', args);
            } catch (error) {
                console.error('Uncached command failed:', error);
                process.exit(1);
            }
        });
}
