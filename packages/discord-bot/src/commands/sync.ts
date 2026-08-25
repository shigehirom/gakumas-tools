import { SlashCommandBuilder, ChatInputCommandInteraction, EmbedBuilder } from 'discord.js';
import { spawn } from 'child_process';
import path from 'path';

export const syncCommand = {
    data: new SlashCommandBuilder()
        .setName('sync')
        .setDescription('GoogleスプレッドシートからMongoDBへインベントリ（Pアイドル・所持サポカ）を同期します')
        .addStringOption(option =>
            option.setName('target')
                .setDescription('同期する対象')
                .setRequired(false)
                .addChoices(
                    { name: '📦 全インベントリ (Pアイドル + サポカ)', value: 'all' },
                    { name: '🃏 サポートカード (Support-Cards)', value: 'support' },
                    { name: '🌟 Pアイドル (P-Idols)', value: 'pidol' }
                )
        ),
    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const target = interaction.options.getString('target') || 'all';
        const rootDir = path.resolve(__dirname, '../../../..');
        const cliScriptsDir = path.resolve(__dirname, '../../../../packages/cli/scripts');

        let scOutput = '';
        let scError = '';
        let piOutput = '';
        let piError = '';

        const runNodeScript = (scriptName: string): Promise<{ stdout: string; stderr: string; code: number }> => {
            return new Promise((resolve) => {
                const scriptPath = path.join(cliScriptsDir, scriptName);
                const child = spawn('node', [scriptPath], {
                    cwd: rootDir,
                    env: { ...process.env }
                });

                let stdout = '';
                let stderr = '';

                child.stdout.on('data', (d) => { stdout += d.toString(); });
                child.stderr.on('data', (d) => { stderr += d.toString(); });

                child.on('close', (code) => {
                    resolve({ stdout, stderr, code: code ?? 0 });
                });
                child.on('error', (err) => {
                    resolve({ stdout: '', stderr: err.message, code: 1 });
                });
            });
        };

        try {
            // 1. Support-Cards 同期
            if (target === 'all' || target === 'support') {
                const res = await runNodeScript('sync-support-cards.mjs');
                scOutput = res.stdout;
                scError = res.stderr;
            }

            // 2. P-Idols 同期
            if (target === 'all' || target === 'pidol') {
                const res = await runNodeScript('sync-p-idols.mjs');
                piOutput = res.stdout;
                piError = res.stderr;
            }

            const embed = new EmbedBuilder()
                .setTitle('📦 インベントリ同期完了')
                .setDescription('Googleスプレッドシートから MongoDB への同期処理を実行しました。')
                .setColor(0x34A853);

            // サポカ結果のパース・整形
            if (target === 'all' || target === 'support') {
                if (scError && !scOutput.includes('Updated') && !scOutput.includes('Inserted')) {
                    embed.addFields({
                        name: '🃏 サポートカード (Support-Cards ➔ MongoDB)',
                        value: `⚠️ エラー: ${scError.slice(0, 300)}`,
                        inline: false
                    });
                } else {
                    const insMatch = scOutput.match(/Inserted[^:]*:\s*(\d+)/i) || scOutput.match(/新規[^:]*:\s*(\d+)/i);
                    const updMatch = scOutput.match(/Updated[^:]*:\s*(\d+)/i) || scOutput.match(/更新[^:]*:\s*(\d+)/i);
                    const delMatch = scOutput.match(/Deleted[^:]*:\s*(\d+)/i) || scOutput.match(/削除[^:]*:\s*(\d+)/i);
                    
                    const ins = insMatch ? insMatch[1] : '0';
                    const upd = updMatch ? updMatch[1] : '0';
                    const del = delMatch ? delMatch[1] : '0';

                    embed.addFields({
                        name: '🃏 サポートカード (Support-Cards ➔ MongoDB)',
                        value: `・新規追加: \`${ins}\` 件\n・更新: \`${upd}\` 件\n・除外: \`${del}\` 件`,
                        inline: false
                    });
                }
            }

            // Pアイドル結果のパース・整形
            if (target === 'all' || target === 'pidol') {
                if (piError && !piOutput.includes('Updated') && !piOutput.includes('Inserted')) {
                    embed.addFields({
                        name: '🌟 Pアイドル (P-Idols ➔ MongoDB)',
                        value: `⚠️ エラー: ${piError.slice(0, 300)}`,
                        inline: false
                    });
                } else {
                    const insMatch = piOutput.match(/Inserted[^:]*:\s*(\d+)/i) || piOutput.match(/新規[^:]*:\s*(\d+)/i);
                    const updMatch = piOutput.match(/Updated[^:]*:\s*(\d+)/i) || piOutput.match(/更新[^:]*:\s*(\d+)/i);
                    const delMatch = piOutput.match(/Deleted[^:]*:\s*(\d+)/i) || piOutput.match(/削除[^:]*:\s*(\d+)/i);

                    const ins = insMatch ? insMatch[1] : '0';
                    const upd = updMatch ? updMatch[1] : '0';
                    const del = delMatch ? delMatch[1] : '0';

                    embed.addFields({
                        name: '🌟 Pアイドル (P-Idols ➔ MongoDB)',
                        value: `・新規追加: \`${ins}\` 件\n・更新: \`${upd}\` 件\n・除外: \`${del}\` 件`,
                        inline: false
                    });
                }
            }

            embed.setFooter({ text: '初星学園 データベース同期システム' });
            embed.setTimestamp();

            await interaction.editReply({ embeds: [embed] });
        } catch (err: any) {
            console.error('[Sync Command Error]', err);
            await interaction.editReply({
                content: `⚠️ 同期コマンドの実行中に例外が発生しました: \`${err.message}\``
            });
        }
    }
};
