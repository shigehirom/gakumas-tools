import { 
    SlashCommandBuilder, 
    ChatInputCommandInteraction, 
    EmbedBuilder 
} from 'discord.js';
import { MongoClient } from 'mongodb';
import { MasterData } from '../utils/master-data';
import { config } from '../config';

export const recentMemoriesCommand = {
    data: new SlashCommandBuilder()
        .setName('recent-memories')
        .setDescription('データベースに登録された最新のメモリー（最新10件）を表示します')
        .addIntegerOption(option =>
            option.setName('count')
                .setDescription('表示件数 (デフォルト: 10, 最大: 25)')
                .setRequired(false)
                .setMinValue(1)
                .setMaxValue(25)
        ),

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const count = interaction.options.getInteger('count') || 10;
        const client = new MongoClient(config.mongoUri);

        try {
            await client.connect();
            const db = client.db(config.mongoDb);
            const collection = db.collection('memories');

            // すべてのメモリーを取得して名前順（YY/MM/DD...）でソート
            // 名前が null または空のものを除外
            const memories = await collection.find({ name: { $exists: true, $ne: '' } }).toArray();

            if (memories.length === 0) {
                await interaction.editReply({
                    content: '⚠️ **登録されているメモリーが見つかりませんでした。**'
                });
                return;
            }

            // 名前（先頭の日付形式）でソートして最新のものを取得
            memories.sort((a, b) => (b.name || '').localeCompare(a.name || ''));
            const recent = memories.slice(0, count);

            const embed = new EmbedBuilder()
                .setColor(0xFEE75C)
                .setTitle(`🗂️ 最新登録メモリー一覧 (最新 ${recent.length} 件)`)
                .setDescription(`\`cli list | sort | tail -${count}\` 相当の最新メモリー情報です。`)
                .setTimestamp();

            recent.forEach((mem, idx) => {
                const pIdol = mem.pIdolId ? MasterData.getPIdolById(mem.pIdolId) : null;
                const idol = pIdol ? MasterData.getIdolById(pIdol.idolId) : null;
                const idolLabel = idol ? `${idol.name}【${pIdol?.title || '不明'}】` : 'アイドル未設定';
                
                // パラメータ情報
                const params = mem.data?.params;
                const paramsStr = params && Array.isArray(params) && params.length >= 3
                    ? `Vo: ${params[0]} | Da: ${params[1]} | Vi: ${params[2]} | HP: ${params[3] || 0}`
                    : '';

                let valueText = `• **アイドル**: ${idolLabel}`;
                if (paramsStr) {
                    valueText += `\n• **ステータス**: \`${paramsStr}\``;
                }

                embed.addFields({
                    name: `${idx + 1}. \`${mem.name}\``,
                    value: valueText,
                    inline: false
                });
            });

            await interaction.editReply({ embeds: [embed] });

        } catch (error: any) {
            console.error('Failed to fetch recent memories:', error);
            await interaction.editReply({
                content: `❌ **メモリー取得エラー**: ${error.message || error}`
            });
        } finally {
            await client.close();
        }
    }
};
