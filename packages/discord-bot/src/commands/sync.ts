import { SlashCommandBuilder, ChatInputCommandInteraction, EmbedBuilder } from 'discord.js';
import { spawn } from 'child_process';
import path from 'path';
import * as fs from 'fs';
import { syncContestMatchesBidirectional } from '../utils/match-history-updater';

export const syncCommand = {
    data: new SlashCommandBuilder()
        .setName('sync')
        .setDescription('GoogleスプレッドシートとMongoDBのデータ（コンテスト対戦記録・インベントリ）を同期します')
        .addStringOption(option =>
            option.setName('target')
                .setDescription('同期する対象 (デフォルト: コンテスト対戦記録)')
                .setRequired(false)
                .addChoices(
                    { name: '🏆 コンテスト対戦記録 (Contest 双方向同期)', value: 'contest' },
                    { name: '📦 全インベントリ (Pアイドル + サポカ)', value: 'all' },
                    { name: '🃏 サポートカード (Support-Cards)', value: 'support' },
                    { name: '🌟 Pアイドル (P-Idols)', value: 'pidol' }
                )
        ),

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const target = interaction.options.getString('target') || 'contest';

        // ── 1. コンテスト対戦記録の双方向同期 ──
        if (target === 'contest') {
            try {
                console.log('[sync] Starting bidirectional contest sync...');
                const result = await syncContestMatchesBidirectional();

                if (!result.success) {
                    const embed = new EmbedBuilder()
                        .setTitle('❌ コンテスト記録の同期に失敗しました')
                        .setDescription(`**エラー内容**:\n\`\`\`\n${(result.error || '不明なエラー').slice(0, 500)}\n\`\`\``)
                        .addFields({
                            name: '💡 対処法',
                            value: 'Google Sheets OAuth トークンが失効している可能性があります。\nSandbox ターミナルで `node packages/cli/scripts/reauth-sheets.mjs` を実行して再認証を行ってください。'
                        })
                        .setColor(0xEF4444)
                        .setTimestamp();

                    await interaction.followUp({ embeds: [embed] });
                    return;
                }

                const embed = new EmbedBuilder()
                    .setTitle('✅ コンテスト記録の双方向同期が完了しました')
                    .setDescription(`Google スプレッドシート（Contest）と MongoDB の対戦履歴を相互に最新化しました。\n\`\`\`\n${(result.output || '同期完了').slice(0, 1000)}\n\`\`\``)
                    .setColor(0x10B981)
                    .setTimestamp();

                await interaction.followUp({ embeds: [embed] });
                return;

            } catch (err: any) {
                console.error('[sync] Contest sync error:', err);
                await interaction.followUp({ content: `❌ 同期中にエラーが発生しました: ${err.message}` });
                return;
            }
        }

        // ── 2. インベントリ (Pアイドル / サポカ) の同期 ──
        let scriptName = 'sync-all.mjs';
        if (target === 'support') scriptName = 'sync-support-cards.mjs';
        else if (target === 'pidol') scriptName = 'sync-p-idols.mjs';

        const scriptCandidates = [
            path.resolve(process.cwd(), 'scripts', scriptName),
            path.resolve(__dirname, '../scripts', scriptName),
            path.resolve(__dirname, '../../scripts', scriptName),
            path.resolve(__dirname, '../../../..', 'packages/cli/scripts', scriptName),
            path.resolve(__dirname, '../../..', 'cli/scripts', scriptName),
            path.resolve(__dirname, '../../../..', 'scripts', scriptName),
            `/app/packages/cli/scripts/${scriptName}`,
            `/app/scripts/${scriptName}`,
        ];

        const scriptPath = scriptCandidates.find(p => fs.existsSync(p));
        if (!scriptPath) {
            await interaction.followUp({ content: `❌ 同期スクリプトが見つかりませんでした: ${scriptName}` });
            return;
        }

        const runCwd = path.dirname(path.dirname(scriptPath));
        const proc = spawn('node', [scriptPath], {
            cwd: runCwd,
            env: { ...process.env }
        });

        let stdout = '';
        let stderr = '';

        proc.stdout.on('data', data => { stdout += data.toString(); });
        proc.stderr.on('data', data => { stderr += data.toString(); });

        proc.on('close', async (code) => {
            if (code !== 0) {
                const embed = new EmbedBuilder()
                    .setTitle('❌ インベントリ同期に失敗しました')
                    .setDescription(`\`\`\`\n${(stderr || stdout).slice(0, 1000)}\n\`\`\``)
                    .setColor(0xEF4444)
                    .setTimestamp();
                await interaction.followUp({ embeds: [embed] });
            } else {
                const embed = new EmbedBuilder()
                    .setTitle('✅ インベントリ同期が完了しました')
                    .setDescription(`スプレッドシートから MongoDB への同期が正常に完了しました。\n\`\`\`\n${stdout.slice(0, 1000)}\n\`\`\``)
                    .setColor(0x10B981)
                    .setTimestamp();
                await interaction.followUp({ embeds: [embed] });
            }
        });
    }
};
