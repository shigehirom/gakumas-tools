import { CAC } from 'cac';
import * as fs from 'fs';
import * as path from 'path';

export function registerMatchHistoryCommand(cli: CAC) {
    cli.command('match-history <season> <startDate> <endDate>', 'Generate a template CSV file for match history')
        .action(async (seasonStr: string, startDateStr: string, endDateStr: string) => {
            const season = parseInt(seasonStr, 10);
            if (isNaN(season)) {
                console.error('Error: season must be a number');
                process.exit(1);
            }

            const start = new Date(startDateStr);
            const end = new Date(endDateStr);

            if (isNaN(start.getTime())) {
                console.error(`Error: Invalid start date "${startDateStr}"`);
                process.exit(1);
            }
            if (isNaN(end.getTime())) {
                console.error(`Error: Invalid end date "${endDateStr}"`);
                process.exit(1);
            }
            if (start >= end) {
                console.error('Error: Start date must be before end date');
                process.exit(1);
            }

            // Get target directory from environment variable or fallback
            const instructionsDir = process.env.CLI_INSTRUCTIONS_DIR || '/root/gakumas-workspace/shared/agent-instructions';
            if (!fs.existsSync(instructionsDir)) {
                fs.mkdirSync(instructionsDir, { recursive: true });
            }

            const targetFilePath = path.join(instructionsDir, `match_history_${season}.csv`);

            // Generate CSV content
            const lines: string[] = ['日付,相手名,メモ,獲得Pt,自S1,敵S1,自S2,敵S2,自S3,敵S3,結果'];

            // Loop through each date
            let current = new Date(start);
            while (current < end) {
                const yy = String(current.getFullYear()).slice(-2);
                const mm = String(current.getMonth() + 1).padStart(2, '0');
                const dd = String(current.getDate()).padStart(2, '0');
                const formattedDate = `${yy}/${mm}/${dd}`;

                // 5 rounds per day
                for (let i = 0; i < 5; i++) {
                    lines.push(`${formattedDate},,3,,,,,,,,WIN LOSE`);
                }

                // Advance by 1 day
                current.setDate(current.getDate() + 1);
            }

            const csvContent = lines.join('\n') + '\n';

            try {
                fs.writeFileSync(targetFilePath, csvContent, 'utf-8');
                console.log(`Successfully generated match history template: ${targetFilePath}`);
            } catch (error) {
                console.error(`Failed to write CSV file:`, error);
                process.exit(1);
            }
        });
}
