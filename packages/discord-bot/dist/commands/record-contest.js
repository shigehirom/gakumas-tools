"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.recordContestCommand = void 0;
const discord_js_1 = require("discord.js");
const contest_parser_1 = require("../utils/contest-parser");
const match_history_updater_1 = require("../utils/match-history-updater");
exports.recordContestCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('record-contest')
        .setDescription('コンテスト結果のスクリーンショット3枚から結果を解析しCSVに自動登録します')
        .addAttachmentOption(option => option.setName('image1')
        .setDescription('1枚目: 対戦相手選択画面')
        .setRequired(true))
        .addAttachmentOption(option => option.setName('image2')
        .setDescription('2枚目: 対戦結果画面（各ステージスコア）')
        .setRequired(true))
        .addAttachmentOption(option => option.setName('image3')
        .setDescription('3枚目: 獲得Pt・報酬画面')
        .setRequired(true))
        .addStringOption(option => option.setName('date')
        .setDescription('登録対象の日付 (ドロップダウン選択または入力。省略時は当日)')
        .setRequired(false)
        .setAutocomplete(true))
        .addIntegerOption(option => option.setName('season')
        .setDescription('シーズン番号 (省略時は最新シーズン)')
        .setRequired(false)),
    async autocomplete(interaction) {
        try {
            const focused = interaction.options.getFocused(true);
            if (focused.name !== 'date')
                return;
            const focusedRaw = focused.value.trim();
            // JST 基準の今日の日付
            const now = new Date();
            const jstFormatter = new Intl.DateTimeFormat('ja-JP', {
                timeZone: 'Asia/Tokyo',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit'
            });
            const parts = jstFormatter.formatToParts(now);
            const y = parseInt(parts.find(p => p.type === 'year').value);
            const m = parseInt(parts.find(p => p.type === 'month').value) - 1;
            const d = parseInt(parts.find(p => p.type === 'day').value);
            const dayNames = ['日', '月', '火', '水', '木', '金', '土'];
            const choices = [];
            // シーズン51初日 (2026-08-25) まで、または直近14日分の候補を生成
            for (let i = 0; i < 14; i++) {
                const target = new Date(y, m, d - i, 12, 0, 0);
                const tYear = target.getFullYear();
                const tMonthNum = target.getMonth() + 1;
                const tDayNum = target.getDate();
                const tMonth = String(tMonthNum).padStart(2, '0');
                const tDay = String(tDayNum).padStart(2, '0');
                const val = `${tYear}/${tMonth}/${tDay}`;
                const valShortYear = `${String(tYear).slice(-2)}/${tMonth}/${tDay}`;
                const valNoZero = `${tMonthNum}/${tDayNum}`;
                const dayOfWeek = dayNames[target.getDay()];
                let relLabel = '';
                if (i === 0) {
                    relLabel = ' (今日)';
                }
                else if (i === 1) {
                    relLabel = ' (昨日)';
                }
                else {
                    relLabel = ` (${i}日前)`;
                }
                const displayName = `${val}(${dayOfWeek})${relLabel}`;
                choices.push({
                    name: displayName,
                    value: val,
                    searchKeywords: [
                        displayName.toLowerCase(),
                        val,
                        valShortYear,
                        valNoZero,
                        `${tYear}-${tMonth}-${tDay}`,
                        relLabel.toLowerCase()
                    ]
                });
            }
            let filtered = choices;
            if (focusedRaw) {
                const q = focusedRaw.toLowerCase();
                filtered = choices.filter(c => c.searchKeywords.some(kw => kw.includes(q)));
            }
            await interaction.respond(filtered.slice(0, 25).map(c => ({ name: c.name, value: c.value })));
        }
        catch (err) {
            console.error('[record-contest autocomplete error]', err);
        }
    },
    async execute(interaction) {
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
            const imageBuffers = await Promise.all(attachments.map(async (att, idx) => {
                const res = await fetch(att.url);
                if (!res.ok) {
                    throw new Error(`画像${idx + 1}のダウンロードに失敗しました: ${res.statusText}`);
                }
                const arrayBuffer = await res.arrayBuffer();
                return Buffer.from(arrayBuffer);
            }));
            await interaction.editReply({
                content: '⏳ **Gemini API で画像を解析中...**'
            });
            const analysis = await (0, contest_parser_1.parseContestImages)([
                imageBuffers[0],
                imageBuffers[1],
                imageBuffers[2]
            ]);
            const season = customSeason || (0, match_history_updater_1.getLatestSeasonNumber)();
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
                }
                else if (m2) {
                    targetDate = new Date(2000 + parseInt(m2[1]), parseInt(m2[2]) - 1, parseInt(m2[3]), 12, 0, 0);
                }
                else if (m3) {
                    targetDate = new Date(jstYear, parseInt(m3[1]) - 1, parseInt(m3[2]), 12, 0, 0);
                }
            }
            // CSV更新 + MongoDB保存
            const csvResult = await (0, match_history_updater_1.updateMatchHistoryCsv)(analysis, {
                season,
                date: targetDate,
                userId: interaction.user.id
            });
            const formattedDate = `${targetDate.getFullYear()}/${String(targetDate.getMonth() + 1).padStart(2, '0')}/${String(targetDate.getDate()).padStart(2, '0')}`;
            const isWin = analysis.overallResult === 'WIN';
            const embed = new discord_js_1.EmbedBuilder()
                .setTitle(`📊 ${formattedDate} のコンテスト結果 (${analysis.matchIndex}/5)`)
                .setColor(isWin ? 0x22c55e : 0xef4444)
                .setDescription(`**対戦相手**: **${analysis.opponent.name}** (枠/グレード: ${analysis.opponent.grade})\n` +
                `**勝敗結果**: ${isWin ? '🏆 **WIN**' : '❌ **LOSE**'} (+${analysis.earnedPt}Pt)\n\n` +
                `**各ステージ結果**:\n` +
                `・**ステージ1**: 自 \`${analysis.stages.stage1.myScore.toLocaleString()}\` vs 敵 \`${analysis.stages.stage1.enemyScore.toLocaleString()}\` (${analysis.stages.stage1.result})\n` +
                `・**ステージ2**: 自 \`${analysis.stages.stage2.myScore.toLocaleString()}\` vs 敵 \`${analysis.stages.stage2.enemyScore.toLocaleString()}\` (${analysis.stages.stage2.result})\n` +
                `・**ステージ3**: 自 \`${analysis.stages.stage3.myScore.toLocaleString()}\` vs 敵 \`${analysis.stages.stage3.enemyScore.toLocaleString()}\` (${analysis.stages.stage3.result})\n\n` +
                `**その他データ**:\n` +
                `・ファン数: \`+${analysis.extra.fans.toLocaleString()}\` | コイン: \`+${analysis.extra.coins.toLocaleString()}\`\n` +
                `・現在Pt: \`${analysis.extra.currentPt.toLocaleString()}Pt\` (${analysis.extra.currentRank}位)`)
                .setFooter({
                text: `✅ match_history_${season}.csv の ${analysis.matchIndex}戦目を更新しました (${csvResult.filePath})`
            })
                .setTimestamp();
            await interaction.editReply({
                content: null,
                embeds: [embed]
            });
        }
        catch (error) {
            console.error('Failed to record contest result:', error);
            await interaction.editReply({
                content: `❌ **エラーが発生しました**: ${error.message}`
            });
        }
    }
};
