import {
    SlashCommandBuilder,
    ChatInputCommandInteraction,
    AttachmentBuilder
} from 'discord.js';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { getCurrentSeason } from '../utils/contest-helper';

function findScriptPath(): string {
    const candidates = [
        path.resolve(process.cwd(), '../gakumas-agent-bot/generate_contest_boxplot.py'),
        path.resolve(process.cwd(), 'gakumas-agent-bot/generate_contest_boxplot.py'),
        '/root/gakumas-workspace/gakumas-agent-bot/generate_contest_boxplot.py',
        '/app/gakumas-agent-bot/generate_contest_boxplot.py',
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    return candidates[0];
}

export const contestChartCommand = {
    data: new SlashCommandBuilder()
        .setName('contest-chart')
        .setDescription('コンテストシミュレーション結果（全アイドル横方向箱ひげ図）を出力します')
        .addIntegerOption(option =>
            option.setName('stage')
                .setDescription('ステージ番号 (1, 2, 3)')
                .setRequired(true)
                .addChoices(
                    { name: 'Stage 1 (センス / Vo特化等)', value: 1 },
                    { name: 'Stage 2 (ロジック / Vi特化等)', value: 2 },
                    { name: 'Stage 3 (アノマリー / Vo特化等)', value: 3 }
                )
        )
        .addIntegerOption(option =>
            option.setName('season')
                .setDescription('シーズン番号 (省略時は現在/最新シーズン)')
                .setRequired(false)
        )
        .addStringOption(option =>
            option.setName('date')
                .setDescription('シミュレーション日付 (YY-MM-DD、省略時は最新)')
                .setRequired(false)
        ),

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const stage = interaction.options.getInteger('stage', true);
        const season = interaction.options.getInteger('season') || getCurrentSeason();
        const dateStr = interaction.options.getString('date') || '';

        const scriptPath = findScriptPath();
        if (!fs.existsSync(scriptPath)) {
            await interaction.followUp({ content: `⚠️ 画像生成スクリプトが見つかりませんでした: \`${scriptPath}\`` });
            return;
        }

        const outDir = path.resolve(process.cwd(), 'shared/documents');
        if (!fs.existsSync(outDir)) {
            try {
                fs.mkdirSync(outDir, { recursive: true });
            } catch {
                // ignore
            }
        }

        const timestamp = Date.now();
        const outFileName = `contest_chart_s${season}_stage${stage}_${timestamp}.png`;
        const outFilePath = path.join(outDir, outFileName);

        const args = [
            scriptPath,
            '--stage', String(stage),
            '--season', String(season),
            '--output', outFilePath
        ];
        if (dateStr) {
            args.push('--date', dateStr);
        }

        const pythonCmd = 'python3';
        const proc = spawn(pythonCmd, args);

        let stderr = '';
        let stdout = '';

        proc.stdout.on('data', data => {
            stdout += data.toString();
        });

        proc.stderr.on('data', data => {
            stderr += data.toString();
        });

        proc.on('close', async code => {
            if (code !== 0 || !fs.existsSync(outFilePath)) {
                console.error(`[contest_chart] Python script exited with code ${code}: ${stderr || stdout}`);
                await interaction.followUp({
                    content: `⚠️ グラフ生成に失敗しました (code ${code})。\n\`\`\`\n${(stderr || stdout).slice(0, 300)}\n\`\`\``
                });
                return;
            }

            try {
                const attachment = new AttachmentBuilder(outFilePath, {
                    name: `contest_boxplot_s${season}_stage${stage}.png`
                });

                const msg = `📊 **シーズン${season} Stage ${stage} コンテストリハーサル推計**\n全13アイドルのスコア分布グラフ（横方向箱ひげ図）を出力しました。`;

                await interaction.followUp({
                    content: msg,
                    files: [attachment]
                });

                // 一時ファイルのクリーンアップ（少し待ってから削除）
                setTimeout(() => {
                    try {
                        if (fs.existsSync(outFilePath)) fs.unlinkSync(outFilePath);
                    } catch {
                        // ignore
                    }
                }, 60000);

            } catch (err: any) {
                console.error('[contest_chart] Discord reply error:', err);
                await interaction.followUp({ content: `⚠️ Discord送信中にエラーが発生しました: ${err.message}` });
            }
        });
    }
};

