"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.deckCommand = void 0;
const discord_js_1 = require("discord.js");
const contest_helper_1 = require("../utils/contest-helper");
exports.deckCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('deck')
        .setDescription('現在コンテスト用に最適化されているステージ別3人編成を表示します')
        .addIntegerOption(option => option.setName('stage')
        .setDescription('ステージ番号 (1, 2, 3)')
        .setRequired(true)
        .addChoices({ name: 'ステージ 1', value: 1 }, { name: 'ステージ 2', value: 2 }, { name: 'ステージ 3', value: 3 })),
    async execute(interaction) {
        const stageNum = interaction.options.getInteger('stage', true);
        const currentSeason = (0, contest_helper_1.getCurrentSeason)();
        const result = (0, contest_helper_1.getOptimizedDeckFromFiles)(stageNum);
        if (!result || result.idols.length === 0) {
            await interaction.reply({
                content: `⚠️ **最適化デッキ情報が見つかりませんでした。**\n最新の最適化レポート (\`*_optimized.md\`) が存在するかご確認ください。\n（\`pnpm cli optimize-deck <prefix>\` で生成できます）`,
                ephemeral: true
            });
            return;
        }
        const embed = new discord_js_1.EmbedBuilder()
            .setColor(0x5865F2)
            .setTitle(`🛡️ コンテスト最適化デッキ (シーズン${currentSeason} ステージ${stageNum})`)
            .setDescription(`**ステージ${stageNum} 合計期待中央値**: **約 ${result.totalExpectedScore.toLocaleString()} Pt**\n` +
            (result.overallScore ? `**3ステージ総合期待中央値**: **約 ${result.overallScore.toLocaleString()} Pt**\n` : '') +
            (result.sourceFile ? `*参照元: \`${result.sourceFile}\`*` : ''))
            .setTimestamp();
        result.idols.forEach((idol, idx) => {
            embed.addFields({
                name: `👤 枠 ${idx + 1}: ${idol.idol}`,
                value: [
                    `• **期待中央値 ($Q_2$)**: \`${idol.medianScore.toLocaleString()} Pt\``,
                    `• **メインメモリー**: ${idol.mainMem}`,
                    `• **サブメモリー**: ${idol.subMem}`
                ].join('\n'),
                inline: false
            });
        });
        await interaction.reply({ embeds: [embed] });
    }
};
