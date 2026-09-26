"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.contestCommand = void 0;
const discord_js_1 = require("discord.js");
const mongodb_1 = require("mongodb");
const config_1 = require("../config");
const contest_helper_1 = require("../utils/contest-helper");
const idol_colors_1 = require("../utils/idol-colors");
const mcp_client_1 = require("../utils/mcp-client");
const IDOL_CHOICES = [
    { name: '🌟 全体 (全アイドル箱ひげ図チャート [デフォルト])', value: 'all' },
    { name: '花海 咲季', value: 'saki' },
    { name: '月村 手毬', value: 'temari' },
    { name: '藤田 ことね', value: 'kotone' },
    { name: '有村 麻央', value: 'mao' },
    { name: '葛城 リーリヤ', value: 'lilja' },
    { name: '倉本 千奈', value: 'china' },
    { name: '紫雲 清夏', value: 'sumika' },
    { name: '篠澤 広', value: 'hiro' },
    { name: '姫崎 莉波', value: 'rinami' },
    { name: '花海 佑芽', value: 'ume' },
    { name: '十王 星南', value: 'sena' },
    { name: '秦谷 美鈴', value: 'misuzu' },
    { name: '雨夜 燕', value: 'tsubame' },
];
async function generateSingleImage(type, stage, season, idol) {
    if (type === 'chart') {
        return await (0, mcp_client_1.getMcpImage)('get_contest_boxplot_image', { stage, season });
    }
    else {
        return await (0, mcp_client_1.getMcpImage)('get_loadout_image', { stage, idol_name: idol });
    }
}
exports.contestCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('contest')
        .setDescription('コンテストの全アイドル箱ひげ図チャート、または個別アイドルの最新デッキ詳細を表示します')
        .addIntegerOption(option => option.setName('stage')
        .setDescription('ステージ番号 (1, 2, 3)')
        .setRequired(true)
        .addChoices({ name: 'Stage 1 (センス / Vo特化等)', value: 1 }, { name: 'Stage 2 (ロジック / Vi特化等)', value: 2 }, { name: 'Stage 3 (アノマリー / Vo特化等)', value: 3 }))
        .addStringOption(option => option.setName('idol')
        .setDescription('表示対象アイドル (省略時: all＝全アイドル箱ひげ図チャート)')
        .setRequired(false)
        .addChoices(...IDOL_CHOICES))
        .addIntegerOption(option => option.setName('season')
        .setDescription('シーズン番号 (省略時は最新)')
        .setRequired(false)),
    async execute(interaction) {
        await interaction.deferReply();
        const stage = interaction.options.getInteger('stage', true);
        const idol = interaction.options.getString('idol') || 'all';
        const season = interaction.options.getInteger('season') || (0, contest_helper_1.getCurrentSeason)();
        try {
            // ── パターン 1: 全体チャート表示 (idol === 'all') ──
            if (idol === 'all') {
                const { buffer, error } = await generateSingleImage('chart', stage, season, '');
                if (!buffer || buffer.length === 0) {
                    await interaction.followUp({
                        content: `⚠️ 箱ひげ図チャートの生成に失敗しました。\n\`\`\`\n${(error || '画像データが空です').slice(0, 500)}\n\`\`\``
                    });
                    return;
                }
                // サポートボーナス取得
                let supportBonusStr = '+14.68%';
                const client = new mongodb_1.MongoClient(config_1.config.mongoUri);
                try {
                    await client.connect();
                    const db = client.db(config_1.config.mongoDb);
                    const sample = await db.collection('loadouts').findOne({ 'derived.season': season, supportBonus: { $exists: true, $gt: 0 } }, { sort: { createdAt: -1 } });
                    if (sample?.supportBonus) {
                        const sb = sample.supportBonus;
                        const sbPct = sb < 1.0 ? sb * 100 : sb;
                        supportBonusStr = `+${sbPct.toFixed(2)}%`;
                    }
                }
                catch (e) {
                    console.warn('[contest] DB supportBonus fetch error:', e);
                }
                finally {
                    await client.close();
                }
                const fileName = `chart_s${season}_stage${stage}.png`;
                const file = new discord_js_1.AttachmentBuilder(buffer, { name: fileName });
                const embed = new discord_js_1.EmbedBuilder()
                    .setTitle(`📊 シーズン${season} ステージ${stage} 全アイドル箱ひげ図チャート`)
                    .setDescription(`最新シミュレーション結果（試行回数 2,000回）に基づく全アイドルのスコア分布推計です。(サポートボーナス: ${supportBonusStr})`)
                    .setImage(`attachment://${fileName}`)
                    .setColor(0x10B981) // エメラルドグリーン
                    .setTimestamp();
                await interaction.followUp({
                    embeds: [embed],
                    files: [file]
                });
                return;
            }
            // ── パターン 2: 個別アイドルのデッキ詳細表示 (idol !== 'all') ──
            const idolColor = (0, idol_colors_1.getIdolColor)(idol);
            const idolName = idolColor ? idolColor.name : idol;
            const embedColor = idolColor ? idolColor.decimal : 0x3B82F6;
            // MongoDB から当該アイドルの期待中央値スコアとサポートボーナスを取得
            let medianScoreStr = '未計算';
            let supportBonusStr = '+14.68%';
            const client = new mongodb_1.MongoClient(config_1.config.mongoUri);
            try {
                await client.connect();
                const db = client.db(config_1.config.mongoDb);
                const stageId = 180 + stage;
                // 当該アイドルのドキュメントを検索
                const idolId = idolColor?.id;
                const query = { stageId };
                if (idolId) {
                    query['derived.idolId'] = idolId;
                }
                const doc = await db.collection('loadouts').findOne(query, { sort: { createdAt: -1, 'stats.median': -1 } });
                if (doc?.stats?.median) {
                    medianScoreStr = `${Math.round(doc.stats.median).toLocaleString()} Pt`;
                }
                if (doc?.supportBonus) {
                    const sb = doc.supportBonus;
                    const sbPct = sb < 1.0 ? sb * 100 : sb;
                    supportBonusStr = `+${sbPct.toFixed(2)}%`;
                }
            }
            catch (dbErr) {
                console.warn('[contest] DB score fetch error:', dbErr);
            }
            finally {
                await client.close();
            }
            const { buffer, error } = await generateSingleImage('deck', stage, season, idol);
            if (!buffer || buffer.length === 0) {
                await interaction.followUp({
                    content: `⚠️ **${idolName}** のステージ ${stage} デッキ画像生成に失敗しました。\n\`\`\`\n${(error || '編成データが見つかりませんでした').slice(0, 500)}\n\`\`\``
                });
                return;
            }
            const fileName = `deck_s${season}_stage${stage}_${idol}.png`;
            const file = new discord_js_1.AttachmentBuilder(buffer, { name: fileName });
            const embed = new discord_js_1.EmbedBuilder()
                .setTitle(`🏆 コンテスト シーズン${season} ステージ${stage} 【${idolName}】`)
                .setDescription(`**期待中央値スコア**: \`${medianScoreStr}\` (サポートボーナス: ${supportBonusStr})\n最新かつ最高の中央値スコアを記録した編成詳細（メモリー・Pアイテム・スキルカード）です。`)
                .setImage(`attachment://${fileName}`)
                .setColor(embedColor) // アイドル固有色！
                .setTimestamp();
            await interaction.followUp({
                embeds: [embed],
                files: [file]
            });
        }
        catch (err) {
            console.error('[contest] Error executing command:', err);
            await interaction.followUp({
                content: `❌ エラーが発生しました: ${err.message}`
            });
        }
    }
};
