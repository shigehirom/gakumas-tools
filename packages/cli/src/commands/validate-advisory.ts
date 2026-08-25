import { CAC } from 'cac';
import * as path from 'path';
import { runScript } from '../utils/runner';

export function registerValidateAdvisoryCommand(cli: CAC) {
    cli.command('validate-advisory [file]', 'Validate Contest Advisory DSL against master database')
        .action(async (file?: string) => {
            const targetFile = file || path.resolve(process.cwd(), 'shared/agent-instructions/fried_aji3_advisory_51.md');
            await runScript('validate-advisory.mjs', [targetFile]);
        });
}
