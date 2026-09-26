import { 
    SlashCommandBuilder, 
    ChatInputCommandInteraction, 
    EmbedBuilder 
} from 'discord.js';
import { callMcpTool } from '../utils/mcp-client';

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

export const memoryCommand = {
    data: new SlashCommandBuilder()
        .setName('memory')
        .setDescription('所持メモリーの最新一覧表示（最新10件）または統計情報を表示します')
        .addStringOption(option =>
            option.setName('mode')
                .setDescription('表示モード')
                .setRequired(true)
                .addChoices(
                    { name: '🕒 最新メモリー (最新10件表示)', value: 'recent' },
                    { name: '📊 メモリー統計 (登録数・属性・パラメータ統計)', value: 'stats' }
                )
        )
        .addStringOption(option =>
            option.setName('idol')
                .setDescription('特定アイドルで絞り込み（stats モード時）')
                .setRequired(false)
                .addChoices(
                    ...IDOL_DEFINITIONS.map(i => ({ name: i.name, value: String(i.id) }))
                )
        ),

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const mode = interaction.options.getString('mode', true);
        const idolFilterStr = interaction.options.getString('idol');
        const idolFilter = idolFilterStr ? parseInt(idolFilterStr, 10) : null;

        try {
            const raw = await callMcpTool('get_memory_summary', {
                mode,
                idol_id: idolFilter,
                limit: 10
            });

            let res: any = null;
            if (raw?.content?.[0]?.text) {
                res = JSON.parse(raw.content[0].text);
            } else if (raw && typeof raw === 'object' && raw.success !== undefined) {
                res = raw;
            }

            if (!res || !res.success) {
                await interaction.followUp(`⚠️ メモリー情報の取得に失敗しました: ${res?.error || '不明なエラー'}`);
                return;
            }

            if (mode === 'recent') {
                const memories = res.memories || [];
                if (memories.length === 0) {
                    await interaction.followUp('データベースにメモリーが登録されていません。');
                    return;
                }

                const embed = new EmbedBuilder()
                    .setTitle('🗂️ 最近登録されたメモリー (最新10件)')
                    .setColor(0x00A8FC)
                    .setTimestamp();

                for (let i = 0; i < memories.length; i++) {
                    const mem = memories[i];
                    const idolName = mem.idol_name || '不明なアイドル';
                    const costumeName = mem.costume_name || '不明な衣装';
                    const cardsText = (mem.cards && mem.cards.length > 0) ? mem.cards.join(', ') : 'なし';
                    const params = mem.params || [0, 0, 0, 0];
                    const paramText = `Vo: ${params[0]} / Da: ${params[1]} / Vi: ${params[2]} / HP: ${params[3]}`;

                    embed.addFields({
                        name: `${i + 1}. ${mem.name || '名称未設定'} (${idolName} - 【${costumeName}】)`,
                        value: `📊 ${paramText}\n🃏 **スキルカード**: ${cardsText}\nID: \`${mem.id}\``,
                        inline: false
                    });
                }

                await interaction.followUp({ embeds: [embed] });

            } else {
                // stats モード
                const totalCount = res.total || 0;
                const idolName = res.idol_name || '全アイドル';

                if (totalCount === 0) {
                    await interaction.followUp(`該当するメモリーが見つかりませんでした。 (条件: ${idolName})`);
                    return;
                }

                const topCards = (res.top_cards || [])
                    .map((c: any, idx: number) => `${idx + 1}. **${c.name}** (${c.count}枚)`)
                    .join('\n');

                const embed = new EmbedBuilder()
                    .setTitle(`📊 メモリーデータベース統計 (${idolName})`)
                    .setColor(0x10B981)
                    .addFields(
                        { name: '📦 総登録メモリー数', value: `**${totalCount}** 件`, inline: true },
                        { name: '❤️ 平均HP', value: `${res.avg_hp || 0}`, inline: true },
                        { name: '\u200B', value: '\u200B', inline: true },
                        { name: '🔴 平均 / 最大 Vo', value: `${res.avg_vo || 0} / **${res.max_vo || 0}**`, inline: true },
                        { name: '🔵 平均 / 最大 Da', value: `${res.avg_da || 0} / **${res.max_da || 0}**`, inline: true },
                        { name: '🟡 平均 / 最大 Vi', value: `${res.avg_vi || 0} / **${res.max_vi || 0}**`, inline: true },
                        { name: '🃏 頻出スキルカード Top 5', value: topCards || 'なし', inline: false }
                    )
                    .setTimestamp();

                await interaction.followUp({ embeds: [embed] });
            }

        } catch (error: any) {
            console.error('[memory] Error executing command:', error);
            await interaction.followUp(`エラーが発生しました: ${error.message}`);
        }
    }
};

