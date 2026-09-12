"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.memoryStatsCommand = void 0;
const discord_js_1 = require("discord.js");
const mongodb_1 = require("mongodb");
const master_data_1 = require("../utils/master-data");
const config_1 = require("../config");
const IDOL_DEFINITIONS = [
    { key: 'saki', id: 1, name: '花海 咲季' },
    { key: 'temari', id: 2, name: '月村 手毬' },
    { key: 'kotone', id: 3, name: '藤田 ことね' },
    { key: 'mao', id: 4, name: '有村 麻央' },
    { key: 'lilja', id: 5, name: '葛城 リーリヤ' },
    { key: 'china', id: 6, name: '倉本 千奈' },
    { key: 'sumika', id: 7, name: '紫雲 清夏' },
    { key: 'hiro', id: 8, name: '篠澤 広' },
    { key: 'rinami', id: 9, name: '姫崎 莉波' },
    { key: 'ume', id: 10, name: '花海 佑芽' },
    { key: 'sena', id: 11, name: '十王 星南' },
    { key: 'misuzu', id: 12, name: '秦谷 美鈴' },
    { key: 'tsubame', id: 13, name: '雨夜 燕' },
];
const PLAN_NAMES = {
    sense: 'センス',
    logic: 'ロジック',
    anomaly: 'アノマリー',
};
const EFFECT_NAMES = {
    goodConditionTurns: '好調',
    concentration: '集中',
    goodImpressionTurns: '好印象',
    motivation: 'やる気',
    strength: '強気',
    preservation: '温存',
    fullPower: '全力',
};
const PLAN_ORDER = {
    sense: 1,
    logic: 2,
    anomaly: 3,
};
const EFFECT_ORDER = {
    goodConditionTurns: 1,
    concentration: 2,
    goodImpressionTurns: 3,
    motivation: 4,
    strength: 5,
    preservation: 6,
    fullPower: 7,
};
function getStringWidth(str) {
    let width = 0;
    for (const char of str) {
        const code = char.codePointAt(0) || 0;
        // CJK, Hiragana, Katakana, Fullwidth punctuation
        if ((code >= 0x3000 && code <= 0x9FFF) ||
            (code >= 0xF900 && code <= 0xFAFF) ||
            (code >= 0xFF01 && code <= 0xFF60) ||
            (code >= 0xFFE0 && code <= 0xFFE6)) {
            width += 2;
        }
        else {
            width += 1;
        }
    }
    return width;
}
function padRight(str, targetWidth) {
    const currentWidth = getStringWidth(str);
    return str + ' '.repeat(Math.max(0, targetWidth - currentWidth));
}
function padLeft(str, targetWidth) {
    const currentWidth = getStringWidth(str);
    return ' '.repeat(Math.max(0, targetWidth - currentWidth)) + str;
}
exports.memoryStatsCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('memory-stats')
        .setDescription('登録されているメモリーの所持状況（プラン別・楽曲別枚数）を集計して表示します')
        .addStringOption(option => option.setName('idol')
        .setDescription('アイドル名（省略時は全アイドルのサマリー表を表示）')
        .setRequired(false)
        .addChoices(...IDOL_DEFINITIONS.map(i => ({
        name: `${i.name} (${i.key})`,
        value: i.key
    })))),
    async execute(interaction) {
        await interaction.deferReply();
        const selectedIdolKey = interaction.options.getString('idol');
        const client = new mongodb_1.MongoClient(config_1.config.mongoUri);
        try {
            await client.connect();
            const db = client.db(config_1.config.mongoDb);
            const collection = db.collection('memories');
            // pIdolId ごとの枚数を集計
            const aggregateResults = await collection.aggregate([
                {
                    $group: {
                        _id: "$pIdolId",
                        count: { $sum: 1 }
                    }
                }
            ]).toArray();
            const countMap = new Map();
            for (const row of aggregateResults) {
                if (row._id != null) {
                    countMap.set(Number(row._id), row.count);
                }
            }
            const allPIdols = master_data_1.MasterData.getPIdols();
            if (!selectedIdolKey) {
                // --- 全アイドルのメモリー状況 ---
                const rows = [];
                let totalSense = 0;
                let totalLogic = 0;
                let totalAnomaly = 0;
                let grandTotal = 0;
                for (const idolDef of IDOL_DEFINITIONS) {
                    const idolPIdols = allPIdols.filter(p => p.idolId === idolDef.id);
                    let sense = 0;
                    let logic = 0;
                    let anomaly = 0;
                    for (const p of idolPIdols) {
                        const count = countMap.get(p.id) || 0;
                        if (p.plan === 'sense')
                            sense += count;
                        else if (p.plan === 'logic')
                            logic += count;
                        else if (p.plan === 'anomaly')
                            anomaly += count;
                    }
                    const subtotal = sense + logic + anomaly;
                    rows.push({
                        name: idolDef.name,
                        sense,
                        logic,
                        anomaly,
                        subtotal,
                    });
                    totalSense += sense;
                    totalLogic += logic;
                    totalAnomaly += anomaly;
                    grandTotal += subtotal;
                }
                // コードブロックで等幅・桁揃えした表を作成
                const colNameW = 14;
                const colSenseW = 6;
                const colLogicW = 8;
                const colAnomW = 10;
                const colSubW = 5;
                const sep = `${'-'.repeat(colNameW)} ${'-'.repeat(colSenseW)} ${'-'.repeat(colLogicW)} ${'-'.repeat(colAnomW)} ${'-'.repeat(colSubW)}`;
                let tableText = '```\n';
                tableText += `${padRight('アイドル名', colNameW)} ${padLeft('センス', colSenseW)} ${padLeft('ロジック', colLogicW)} ${padLeft('アノマリー', colAnomW)} ${padLeft('計', colSubW)}\n`;
                tableText += `${sep}\n`;
                for (const r of rows) {
                    tableText += `${padRight(r.name, colNameW)} ${padLeft(r.sense.toString(), colSenseW)} ${padLeft(r.logic.toString(), colLogicW)} ${padLeft(r.anomaly.toString(), colAnomW)} ${padLeft(r.subtotal.toString(), colSubW)}\n`;
                }
                tableText += `${sep}\n`;
                tableText += `${padRight('合計', colNameW)} ${padLeft(totalSense.toString(), colSenseW)} ${padLeft(totalLogic.toString(), colLogicW)} ${padLeft(totalAnomaly.toString(), colAnomW)} ${padLeft(grandTotal.toString(), colSubW)}\n`;
                tableText += '```';
                const embed = new discord_js_1.EmbedBuilder()
                    .setColor(0x5865F2)
                    .setTitle('📊 全アイドル メモリー所持状況')
                    .setDescription(tableText)
                    .setFooter({ text: `総登録枚数: ${grandTotal}枚` })
                    .setTimestamp();
                await interaction.editReply({ embeds: [embed] });
            }
            else {
                // --- 個別アイドルのメモリー状況 ---
                const targetDef = IDOL_DEFINITIONS.find(i => i.key === selectedIdolKey);
                if (!targetDef) {
                    await interaction.editReply({
                        content: `⚠️ アイドルが見つかりませんでした: \`${selectedIdolKey}\``
                    });
                    return;
                }
                // 対象アイドルの全実装済み PIdol を取得（未実装タイトル空欄を除く）
                const idolPIdols = allPIdols
                    .filter(p => p.idolId === targetDef.id && p.title && p.title.trim() !== '')
                    .sort((a, b) => {
                    const planDiff = (PLAN_ORDER[a.plan] || 99) - (PLAN_ORDER[b.plan] || 99);
                    if (planDiff !== 0)
                        return planDiff;
                    const effectDiff = (EFFECT_ORDER[a.recommendedEffect] || 99) - (EFFECT_ORDER[b.recommendedEffect] || 99);
                    if (effectDiff !== 0)
                        return effectDiff;
                    return a.id - b.id;
                });
                const items = idolPIdols.map(p => {
                    const count = countMap.get(p.id) || 0;
                    return {
                        plan: PLAN_NAMES[p.plan] || p.plan,
                        effect: EFFECT_NAMES[p.recommendedEffect] || p.recommendedEffect || '-',
                        title: p.title,
                        count
                    };
                });
                let subtotal = 0;
                let maxTitleWidth = 6;
                for (const item of items) {
                    subtotal += item.count;
                    const w = getStringWidth(item.title);
                    if (w > maxTitleWidth)
                        maxTitleWidth = w;
                }
                const colPlanW = 10;
                const colEffectW = 8;
                const colTitleW = Math.max(maxTitleWidth + 2, 10);
                const colCountW = 5;
                const sep = `${'-'.repeat(colPlanW)} ${'-'.repeat(colEffectW)} ${'-'.repeat(colTitleW)} ${'-'.repeat(colCountW)}`;
                let tableText = '```\n';
                tableText += `${padRight('タイプ', colPlanW)} ${padRight('効果', colEffectW)} ${padRight('楽曲名', colTitleW)} ${padLeft('枚数', colCountW)}\n`;
                tableText += `${sep}\n`;
                for (const item of items) {
                    tableText += `${padRight(item.plan, colPlanW)} ${padRight(item.effect, colEffectW)} ${padRight(item.title, colTitleW)} ${padLeft(item.count.toString(), colCountW)}\n`;
                }
                tableText += `${sep}\n`;
                tableText += `${padRight('合計', colPlanW)} ${padRight('', colEffectW)} ${padRight('', colTitleW)} ${padLeft(subtotal.toString(), colCountW)}\n`;
                tableText += '```';
                const embed = new discord_js_1.EmbedBuilder()
                    .setColor(0xFEE75C)
                    .setTitle(`📊 ${targetDef.name} メモリー所持状況`)
                    .setDescription(tableText)
                    .setFooter({ text: `所持枚数: ${subtotal}枚` })
                    .setTimestamp();
                await interaction.editReply({ embeds: [embed] });
            }
        }
        catch (error) {
            console.error('Failed to fetch memory stats:', error);
            await interaction.editReply({
                content: `❌ **メモリー統計取得エラー**: ${error.message || error}`
            });
        }
        finally {
            await client.close();
        }
    }
};
