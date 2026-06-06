
import { CAC } from 'cac';
import { runScript } from '../utils/runner';

export function registerListCommand(cli: CAC) {
    cli.command('list [idolName]', 'List memory names')
        .option('--sort <type>', 'Sort by: name, score')
        .option('--cols <num>', 'Number of columns to display')
        .option('--asc', 'Sort in ascending order')
        .action(async (idolName, options) => {
            const args = [];
            if (idolName) args.push(idolName);
            if (options.sort) args.push('--sort', options.sort);
            if (options.cols) args.push('--cols', options.cols);
            if (options.asc) args.push('--asc');

            try {
                // list uses boot-list.mjs
                await runScript('boot-list.mjs', args);
            } catch (error) {
                console.error('List failed:', error);
                process.exit(1);
            }
        });
}
