import { 
    SlashCommandBuilder, 
    ChatInputCommandInteraction, 
    EmbedBuilder 
} from 'discord.js';
import { parseContestImages } from '../utils/contest-parser';
import { updateMatchHistoryCsv, getLatestSeasonNumber } from '../utils/match-history-updater';

export const recordContestCommand = {
    data: new SlashCommandBuilder()
        .setName('record-contest')
        .setDescription('コンテスト結果のスクリーンショット3枚から結果を解析しCSVに自動登録します')
        .addAttachmentOption(option =>
            option.setName('image1')
                .setDescription('1枚目: 対戦相手選択画面')
                .setRequired(true)
        )
        .addAttachmentOption(option =>
            option.setName('image2')
                .setDescription('2枚目: 対戦結果画面（各ステージスコア）')
                .setRequired(true)
        )
        .addAttachmentOption(option =>
            option.setName('image3')
                .setDescription('3枚目: 獲得Pt・報酬画面')
                .setRequired(true)
        )
        .addIntegerOption(option =>
            option.setName('season')
                .setDescription('シーズン番号 (省略時は最新シーズン)')
                .setRequired(false)
        )
        .addStringOption(option =>
            option.setName('date')
                .setDescription('登録対象の日付 (例: 2026/08/26, 26/08/26, 8/26。省略時は当日)')
                .setRequired(false)
        ),

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const attachment1 = interaction.options.getAttachment('image1', true);
        const attachment2 = interaction.options.getAttachment('image2', true);
        const attachment3 = interaction.options.getAttachment('image3', true);
        const customSeason = interaction.options.getInteger('season');
        const customDateStr = interaction.options.getString('date');

        const attachments = [attachment1, attachment2, attachment3];
        for (let i = 0; i < attachments.length; i++) {
            if (!attachments[i].contentType?.startsWith('image/')) {
                await interaction.editReply({
                    content: `⚠️ **画像${i + 1}枚目が画像ファイルではありません（PNG / JPEG / WebP 等を指定してください）。**`
                });
                return;
            }
        }

        try {
            await interaction.editReply({
                content: '⏳ **画像3枚をダウンロード中...**'
            });

            const imageBuffers = await Promise.all(
                attachments.map(async (att, idx) => {
                    const res = await fetch(att.url);
                    if (!res.ok) {
                        throw new Error(`画像${idx + 1}のダウンロードに失敗しました: ${res.statusText}`);
                    }
                    const arrayBuffer = await res.arrayBuffer();
                    return Buffer.from(arrayBuffer);
                })
            );

            await interaction.editReply({
                content: '⏳ **Gemini API で画像を解析中...**'
            });

            const analysis = await parseContestImages([
                imageBuffers[0],
                imageBuffers[1],
                imageBuffers[2]
            ]);

            const season = customSeason || getLatestSeasonNumber();

            // 日付の解析
            let targetDate = new Date();
            if (customDateStr) {
                const cleaned = customDateStr.trim();
                // JST 基準の現在年を取得（コンテナがUTC環境でも正しく動作させるため）
                const jstFormatter = new Intl.DateTimeFormat('ja-JP', {
                    timeZone: 'Asia/Tokyo',
                    year: 'numeric'
                });
                const jstYear = parseInt(jstFormatter.format(new Date()));

                const m1 = cleaned.match(/^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/);
                const m2 = cleaned.match(/^(\d{2})[/-](\d{1,2})[/-](\d{1,2})$/);
                const m3 = cleaned.match(/^(\d{1,2})[/-](\d{1,2})$/);
                if (m1) {
                    targetDate = new Date(parseInt(m1[1]), parseInt(m1[2]) - 1, parseInt(m1[3]), 12, 0, 0);
                } else if (m2) {
                    targetDate = new Date(2000 + parseInt(m2[1]), parseInt(m2[2]) - 1, parseInt(m2[3]), 12, 0, 0);
                } else if (m3) {
                    targetDate = new Date(jstYear, parseInt(m3[1]) - 1, parseInt(m3[2]), 12, 0, 0);
                }
            }

            // CSV更新 + MongoDB保存
            const csvResult = await updateMatchHistoryCsv(analysis, {
                season,
                date: targetDate,
                userId: interaction.user.id
            });


            const isWin = analysis.overallResult === 'WIN';
            const embed = new EmbedBuilder()
                .setTitle(`📊 本日のコンテスト結果 (${analysis.matchIndex}/5)`)
                .setColor(isWin ? 0x22c55e : 0xef4444)
                .setDescription(
                    `**対戦相手**: **${analysis.opponent.name}** (枠/グレード: ${analysis.opponent.grade})\n` +
                    `**勝敗結果**: ${isWin ? '🏆 **WIN**' : '❌ **LOSE**'} (+${analysis.earnedPt}Pt)\n\n` +
                    `**各ステージ結果**:\n` +
                    `・**ステージ1**: 自 \`${analysis.stages.stage1.myScore.toLocaleString()}\` vs 敵 \`${analysis.stages.stage1.enemyScore.toLocaleString()}\` (${analysis.stages.stage1.result})\n` +
                    `・**ステージ2**: 自 \`${analysis.stages.stage2.myScore.toLocaleString()}\` vs 敵 \`${analysis.stages.stage2.enemyScore.toLocaleString()}\` (${analysis.stages.stage2.result})\n` +
                    `・**ステージ3**: 自 \`${analysis.stages.stage3.myScore.toLocaleString()}\` vs 敵 \`${analysis.stages.stage3.enemyScore.toLocaleString()}\` (${analysis.stages.stage3.result})\n\n` +
                    `**その他データ**:\n` +
                    `・ファン数: \`+${analysis.extra.fans.toLocaleString()}\` | コイン: \`+${analysis.extra.coins.toLocaleString()}\`\n` +
                    `・現在Pt: \`${analysis.extra.currentPt.toLocaleString()}Pt\` (${analysis.extra.currentRank}位)`
                )
                .setFooter({
                    text: `✅ match_history_${season}.csv の ${analysis.matchIndex}戦目を更新しました (${csvResult.filePath})`
                })
                .setTimestamp();

            await interaction.editReply({
                content: null,
                embeds: [embed]
            });

        } catch (error: any) {
            console.error('Failed to record contest result:', error);
            await interaction.editReply({
                content: `❌ **エラーが発生しました**: ${error.message}`
            });
        }
    }
};
