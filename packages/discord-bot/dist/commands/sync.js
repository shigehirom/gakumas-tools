"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.syncCommand = void 0;
const discord_js_1 = require("discord.js");
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
exports.syncCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('sync')
        .setDescription('GoogleスプレッドシートからMongoDBへインベントリ（Pアイドル・所持サポカ）を同期します')
        .addStringOption(option => option.setName('target')
        .setDescription('同期する対象')
        .setRequired(false)
        .addChoices({ name: '📦 全インベントリ (Pアイドル + サポカ)', value: 'all' }, { name: '🃏 サポートカード (Support-Cards)', value: 'support' }, { name: '🌟 Pアイドル (P-Idols)', value: 'pidol' }, { name: '🏆 コンテスト対戦記録 (Contest)', value: 'contest' })),
    async execute(interaction) {
        await interaction.deferReply();
        const target = interaction.options.getString('target') || 'all';
        const rootDir = path_1.default.resolve(__dirname, '../../../..');
        const cliScriptsDir = path_1.default.resolve(__dirname, '../../../../packages/cli/scripts');
        let scOutput = '';
        let scError = '';
        let piOutput = '';
        let piError = '';
        let ctOutput = '';
        let ctError = '';
        const runNodeScript = (scriptName, extraArgs = []) => {
            return new Promise((resolve) => {
                const scriptPath = path_1.default.join(cliScriptsDir, scriptName);
                const child = (0, child_process_1.spawn)('node', [scriptPath, ...extraArgs], {
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
            // 3. コンテスト対戦記録同期（双方向: スプレッドシート ⇔ MongoDB）
            if (target === 'contest') {
                const res = await runNodeScript('sync-contest-matches.mjs', ['--mode', 'bidirectional', '--execute']);
                ctOutput = res.stdout;
                ctError = res.stderr;
            }
            const embed = new discord_js_1.EmbedBuilder()
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
                }
                else {
                    const insMatch = scOutput.match(/Inserted[^:]*:\s*(\d+)/i) || scOutput.match(/新規[^:]*:\s*(\d+)/i);
                    const updMatch = scOutput.match(/Updated[^:]*:\s*(\d+)/i) || scOutput.match(/更新[^:]*:\s*(\d+)/i);
                    const delMatch = scOutput.match(/Deleted[^:]*:\s*(\d+)/i) || scOutput.match(/削除[^:]*:\s*(\d+)/i);
                    const bonusMatch = scOutput.match(/SupportBonus:\s*([0-9.]+%[^\n]*)/i);
                    const ins = insMatch ? insMatch[1] : '0';
                    const upd = updMatch ? updMatch[1] : '0';
                    const del = delMatch ? delMatch[1] : '0';
                    const bonusStr = bonusMatch ? bonusMatch[1] : '';
                    let valueStr = `・新規追加: \`${ins}\` 件\n・レベル/凸更新: \`${upd}\` 件\n・除外: \`${del}\` 件`;
                    if (bonusStr) {
                        valueStr += `\n・最新サポートボーナス: **${bonusStr}**`;
                    }
                    embed.addFields({
                        name: '🃏 サポートカード (Support-Cards ➔ MongoDB)',
                        value: valueStr,
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
                }
                else {
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
            // コンテスト同期結果
            if (target === 'contest') {
                if (ctError && !ctOutput.includes('rows written') && !ctOutput.includes('documents')) {
                    embed.addFields({
                        name: '🏆 コンテスト対戦記録 (MongoDB ➔ Contest シート)',
                        value: `⚠️ エラー: ${ctError.slice(0, 300)}`,
                        inline: false
                    });
                }
                else {
                    const rowMatch = ctOutput.match(/(\d+)\s+rows?\s+written/i);
                    const rows = rowMatch ? rowMatch[1] : '?';
                    embed.addFields({
                        name: '🏆 コンテスト対戦記録 (MongoDB ➔ Contest シート)',
                        value: `・書き込み: \`${rows}\` 行\n\`/sync contest\` でシートを最新状態に更新しました。`,
                        inline: false
                    });
                }
                embed.setTitle('🏆 コンテスト対戦記録 同期完了');
                embed.setDescription('MongoDB → Google Sheets `Contest` タブへの同期処理を実行しました。');
            }
            embed.setFooter({ text: '初星学園 データベース同期システム' });
            embed.setTimestamp();
            await interaction.editReply({ embeds: [embed] });
        }
        catch (err) {
            console.error('[Sync Command Error]', err);
            await interaction.editReply({
                content: `⚠️ 同期コマンドの実行中に例外が発生しました: \`${err.message}\``
            });
        }
    }
};
