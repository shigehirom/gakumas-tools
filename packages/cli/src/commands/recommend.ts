import { spawn } from 'child_process';
import { LOCAL_SCRIPTS_DIR, GAKUMAS_TOOLS_ROOT } from '../utils/runner';
import * as fs from 'fs';
import * as path from 'path';
import importHandlebars from 'handlebars';

const Handlebars = importHandlebars;

export function registerRecommendCommand(cli: any) {
    cli.command('recommend <file>', 'Recommend output based on Markdown ideal file')
        .action(async (file: string, options?: any) => {
            if (!process.env.MONGODB_URI) {
                console.error('Error: MONGODB_URI is not set in environment (check .env.local)');
                process.exit(1);
            }

            if (!fs.existsSync(file)) {
                console.error(`Error: File not found: ${file}`);
                process.exit(1);
            }

            const args = [process.env.MONGODB_URI!, file];

            try {
                const templatePath = path.join(__dirname, '../templates/recommend.hbs');
                const templateContent = fs.readFileSync(templatePath, 'utf-8');

                const template = Handlebars.compile(templateContent);

                const scriptPath = path.join(LOCAL_SCRIPTS_DIR, 'boot-recommend.mjs');
                const child = spawn(process.execPath, [scriptPath, ...args], {
                    cwd: GAKUMAS_TOOLS_ROOT,
                    stdio: ['inherit', 'pipe', 'inherit'],
                    env: { ...process.env }
                });

                let outputBuffer = '';

                child.stdout.on('data', (data) => {
                    outputBuffer += data.toString();
                });

                await new Promise<void>((resolve, reject) => {
                    child.on('close', (code) => {
                        if (code === 0) resolve();
                        else reject(new Error(`Script exited with code ${code}`));
                    });
                    child.on('error', reject);
                });

                try {
                    const resultData = JSON.parse(outputBuffer.trim());
                    if (resultData.length === 0) {
                        console.warn("警告: 有効なセクション（'# シーズン X ステージ Y' の形式）がマークダウンから見つかりませんでした。");
                    }
                    for (const stageData of resultData) {
                        console.log(template(stageData));
                        console.log('\n');
                    }
                } catch (e) {
                    console.error("Failed to parse script output:", outputBuffer);
                    process.exit(1);
                }

            } catch (error) {
                console.error('Recommend command failed:', error);
                process.exit(1);
            }
        });
}
