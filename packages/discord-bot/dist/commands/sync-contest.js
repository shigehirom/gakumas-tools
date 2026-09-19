"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.syncContestCommand = void 0;
const discord_js_1 = require("discord.js");
const match_history_updater_1 = require("../utils/match-history-updater");
exports.syncContestCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('sync-contest')
        .setDescription('Googleスプレッドシート(Contest)とMongoDBの対戦記録を双方向同期します'),
    async execute(interaction) {
        await interaction.deferReply();
        try {
            console.log('[sync_contest] Starting bidirectional sync...');
            const result = await (0, match_history_updater_1.syncContestMatchesBidirectional)();
            if (!result.success) {
                const embed = new discord_js_1.EmbedBuilder()
                    .setTitle('❌ コンテスト記録の同期に失敗しました')
                    .setDescription(`**エラー内容**:\n\`\`\`\n${(result.error || '不明なエラー').slice(0, 500)}\n\`\`\``)
                    .addFields({
                    name: '💡 対処法',
                    value: 'Google Sheets OAuth トークンが失効している可能性があります。\nSandbox ターミナルで `node packages/cli/scripts/reauth-sheets.mjs` を実行して再認証を行ってください。'
                })
                    .setColor(0xEF4444)
                    .setTimestamp();
                await interaction.editReply({ embeds: [embed] });
                return;
            }
            // 出力から行数などをパース
            const output = result.output || '';
            const upsertMatch = output.match(/Upserted\s+(\d+)\s+documents/i);
            const upsertedCount = upsertMatch ? upsertMatch[1] : '0';
            const writeMatch = output.match(/updated:\s*(\d+)\s*rows/i);
            const totalRows = writeMatch ? writeMatch[1] : '400';
            const embed = new discord_js_1.EmbedBuilder()
                .setTitle('📊 コンテスト記録 双方向同期完了')
                .setDescription('Googleスプレッドシート（`Contest` タブ）と MongoDB 間の同期が正常に完了しました。')
                .setColor(0x22C55E)
                .addFields({
                name: '📥 スプレッドシート ➔ MongoDB',
                value: `手動入力・補完データ取り込み: **${upsertedCount}** 件`,
                inline: true
            }, {
                name: '📤 MongoDB ➔ スプレッドシート',
                value: `最新対戦記録書き出し: **${totalRows}** 行 (1日5戦形式)`,
                inline: true
            })
                .setFooter({ text: '✅ スプレッドシート側の空欄行を埋めてから再同期すると、MongoDB に自動反映されます' })
                .setTimestamp();
            await interaction.editReply({ embeds: [embed] });
        }
        catch (error) {
            console.error('[sync_contest error]', error);
            await interaction.editReply({
                content: `❌ **予期しないエラーが発生しました**: ${error.message}`
            });
        }
    }
};
