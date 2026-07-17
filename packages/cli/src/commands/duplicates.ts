import { runScript } from '../utils/runner';

export function registerDuplicatesCommand(cli: any) {
    cli.command('duplicates [plan] [idol] [threshold]', 'Find similar or duplicate memories')
        .action(async (plan?: string, idol?: string, threshold?: string) => {
            const args = [];
            if (plan) args.push(plan);
            if (idol) args.push(idol);
            if (threshold) args.push(threshold);

            try {
                // boot-duplicates.mjs wraps find-duplicates.mjs
                await runScript('boot-duplicates.mjs', args);
            } catch (error) {
                console.error('Duplicates command failed:', error);
                process.exit(1);
            }
        });
}
