import {
    SlashCommandBuilder,
    ChatInputCommandInteraction,
    EmbedBuilder
} from 'discord.js';
import { MongoClient } from 'mongodb';
import { MasterData, PIdol } from '../utils/master-data';
import { config } from '../config';

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

const PLAN_NAMES: Record<string, string> = {
    sense: 'センス',
    logic: 'ロジック',
    anomaly: 'アノマリー',
};

const EFFECT_NAMES: Record<string, string> = {
    goodConditionTurns: '好調',
    concentration: '集中',
    goodImpressionTurns: '好印象',
    motivation: 'やる気',
    strength: '強気',
    preservation: '温存',
    fullPower: '全力',
};

const PLAN_ORDER: Record<string, number> = {
    sense: 1,
    logic: 2,
    anomaly: 3,
};

const EFFECT_ORDER: Record<string, number> = {
    goodConditionTurns: 1,
    concentration: 2,
    goodImpressionTurns: 3,
    motivation: 4,
    strength: 5,
    preservation: 6,
    fullPower: 7,
};

export const memoryStatsCommand = {
    data: new SlashCommandBuilder()
        .setName('memory-stats')
        .setDescription('登録されているメモリーの所持状況（プラン別・楽曲別枚数）を集計して表示します')
        .addStringOption(option =>
            option.setName('idol')
                .setDescription('アイドル名（省略時は全アイドルのサマリー表を表示）')
                .setRequired(false)
                .addChoices(
                    ...IDOL_DEFINITIONS.map(i => ({
                        name: `${i.name} (${i.key})`,
                        value: i.key
                    }))
                )
        ),

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const selectedIdolKey = interaction.options.getString('idol');
        const client = new MongoClient(config.mongoUri);

        try {
            await client.connect();
            const db = client.db(config.mongoDb);
            const collection = db.collection('memories');

            // pIdolId ごとの枚数を集計
            const aggregateResults = await collection.aggregate<{ _id: number; count: number }>([
                {
                    $group: {
                        _id: "$pIdolId",
                        count: { $sum: 1 }
                    }
                }
            ]).toArray();

            const countMap = new Map<number, number>();
            for (const row of aggregateResults) {
                if (row._id != null) {
                    countMap.set(Number(row._id), row.count);
                }
            }

            const allPIdols = MasterData.getPIdols();

            if (!selectedIdolKey) {
                // --- 全アイドルのメモリー状況 ---
                const rows: Array<{
                    name: string;
                    sense: number;
                    logic: number;
                    anomaly: number;
                    subtotal: number;
                }> = [];

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
                        if (p.plan === 'sense') sense += count;
                        else if (p.plan === 'logic') logic += count;
                        else if (p.plan === 'anomaly') anomaly += count;
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

                // Markdown 表形式を作成
                let markdownTable = '| アイドル名 | センス | ロジック | アノマリー | 計 |\n';
                markdownTable += '| :-- | --: | --: | --: | --: |\n';

                for (const r of rows) {
                    markdownTable += `| ${r.name} | ${r.sense} | ${r.logic} | ${r.anomaly} | ${r.subtotal} |\n`;
                }

                // 合計行
                markdownTable += `| **合計** | **${totalSense}** | **${totalLogic}** | **${totalAnomaly}** | **${grandTotal}** |\n`;

                const embed = new EmbedBuilder()
                    .setColor(0x5865F2)
                    .setTitle('📊 全アイドル メモリー所持状況')
                    .setDescription(markdownTable)
                    .setFooter({ text: `総登録枚数: ${grandTotal}枚` })
                    .setTimestamp();

                await interaction.editReply({ embeds: [embed] });

            } else {
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
                        if (planDiff !== 0) return planDiff;

                        const effectDiff = (EFFECT_ORDER[a.recommendedEffect] || 99) - (EFFECT_ORDER[b.recommendedEffect] || 99);
                        if (effectDiff !== 0) return effectDiff;

                        return a.id - b.id;
                    });

                let markdownTable = '| タイプ | 効果 | 楽曲名 | 枚数 |\n';
                markdownTable += '| :-- | :-- | :-- | --: |\n';

                let subtotal = 0;
                for (const p of idolPIdols) {
                    const count = countMap.get(p.id) || 0;
                    subtotal += count;

                    const planText = PLAN_NAMES[p.plan] || p.plan;
                    const effectText = EFFECT_NAMES[p.recommendedEffect] || p.recommendedEffect || '-';
                    const titleText = p.title;

                    markdownTable += `| ${planText} | ${effectText} | ${titleText} | ${count} |\n`;
                }

                // 合計行
                markdownTable += `| **合計** | | | **${subtotal}** |\n`;

                const embed = new EmbedBuilder()
                    .setColor(0xFEE75C)
                    .setTitle(`📊 ${targetDef.name} メモリー所持状況`)
                    .setDescription(markdownTable)
                    .setFooter({ text: `所持枚数: ${subtotal}枚` })
                    .setTimestamp();

                await interaction.editReply({ embeds: [embed] });
            }

        } catch (error: any) {
            console.error('Failed to fetch memory stats:', error);
            await interaction.editReply({
                content: `❌ **メモリー統計取得エラー**: ${error.message || error}`
            });
        } finally {
            await client.close();
        }
    }
};
