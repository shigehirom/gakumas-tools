import { 
    SlashCommandBuilder, 
    ChatInputCommandInteraction, 
    EmbedBuilder 
} from 'discord.js';
import { MongoClient } from 'mongodb';
import { MasterData } from '../utils/master-data';
import { processMemoryImage } from '../utils/image-processor';
import { config } from '../config';

export const importMemoryCommand = {
    data: new SlashCommandBuilder()
        .setName('import-memory')
        .setDescription('スクリーンショット画像からメモリーを自動解析しデータベースに登録します')
        .addAttachmentOption(option =>
            option.setName('image')
                .setDescription('メモリーのスクリーンショット画像')
                .setRequired(true)
        )
        .addStringOption(option =>
            option.setName('name')
                .setDescription('メモリー名 (省略時は YY/MM/DD＿<パワー> で自動命名)')
                .setRequired(false)
        ),

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const attachment = interaction.options.getAttachment('image', true);
        const customName = interaction.options.getString('name');

        if (!attachment.contentType?.startsWith('image/')) {
            await interaction.editReply({
                content: '⚠️ **画像ファイルを添付してください（PNG / JPEG / WebP 等）。**'
            });
            return;
        }

        try {
            await interaction.editReply({
                content: '⏳ **画像をダウンロード中...**'
            });

            const res = await fetch(attachment.url);
            if (!res.ok) {
                throw new Error(`画像ダウンロードに失敗しました: ${res.statusText}`);
            }
            const arrayBuffer = await res.arrayBuffer();
            const imageBuffer = Buffer.from(arrayBuffer);

            await interaction.editReply({
                content: '⏳ **画像を解析中... (Tesseract OCR & ONNXモデル推論)**'
            });

            const parsed = await processMemoryImage(imageBuffer);

            // メモリー名の決定 (YY/MM/DD＿<パワー> (FIXME))
            let memoryName = customName;
            if (!memoryName) {
                const now = new Date();
                const yy = String(now.getFullYear()).slice(2);
                const mm = String(now.getMonth() + 1).padStart(2, '0');
                const dd = String(now.getDate()).padStart(2, '0');
                memoryName = `${yy}/${mm}/${dd}＿${parsed.contestPower} (FIXME)`;
            }

            // MongoDB に保存
            const client = new MongoClient(config.mongoUri);
            try {
                await client.connect();
                const db = client.db(config.mongoDb);
                const collection = db.collection('memories');

                const doc = {
                    userId: config.userId,
                    name: memoryName,
                    pIdolId: parsed.pIdolId,
                    params: parsed.params,
                    pItemIds: parsed.pItemIds,
                    skillCardIds: parsed.skillCardIds,
                    customizations: [{}, {}, {}, {}, {}, {}],
                    updatedAt: new Date()
                };

                await collection.updateOne(
                    { name: memoryName, userId: config.userId },
                    { $set: doc },
                    { upsert: true }
                );
            } finally {
                await client.close();
            }

            // アイドル・Pアイドル情報の取得
            const pIdol = parsed.pIdolId ? MasterData.getPIdolById(parsed.pIdolId) : null;
            const idol = pIdol ? MasterData.getIdolById(pIdol.idolId) : null;
            const idolLabel = idol ? `${idol.name}【${pIdol?.title || '不明'}】` : '未特定';

            // Pアイテム・スキルカード名の整形
            const pItemNames = parsed.pItemIds
                .filter(id => id > 0)
                .map(id => {
                    const item = MasterData.getPItemById(id);
                    return item ? `${item.name}${item.upgraded ? '+' : ''}` : `不明(#${id})`;
                });

            const skillCardNames = parsed.skillCardIds
                .filter(id => id > 0)
                .map(id => {
                    const card = MasterData.getSkillCardById(id);
                    return card ? `${card.name}${card.upgraded ? '+' : ''}` : `不明(#${id})`;
                });

            const embed = new EmbedBuilder()
                .setColor(0x57F287)
                .setTitle(`✅ メモリー登録完了: \`${memoryName}\``)
                .setThumbnail(attachment.url)
                .addFields(
                    {
                        name: '👤 アイドル',
                        value: idolLabel,
                        inline: true
                    },
                    {
                        name: '⚡ コンテスト力 (計算値)',
                        value: `**${parsed.contestPower.toLocaleString()} Pt**`,
                        inline: true
                    },
                    {
                        name: '📊 ステータス',
                        value: `Vo: **${parsed.params[0]}** | Da: **${parsed.params[1]}** | Vi: **${parsed.params[2]}** | HP: **${parsed.params[3]}**`,
                        inline: false
                    },
                    {
                        name: '🎁 認識された Pアイテム',
                        value: pItemNames.length > 0 ? pItemNames.map(n => `• ${n}`).join('\n') : 'なし',
                        inline: false
                    },
                    {
                        name: '🃏 認識された スキルカード',
                        value: skillCardNames.length > 0 ? skillCardNames.map(n => `• ${n}`).join('\n') : 'なし',
                        inline: false
                    }
                )
                .setFooter({ text: `User ID: ${config.userId}` })
                .setTimestamp();

            await interaction.editReply({
                content: '🎉 **メモリーの解析とデータベース登録が完了しました！**',
                embeds: [embed]
            });

        } catch (error: any) {
            console.error('Import memory error:', error);
            await interaction.editReply({
                content: `❌ **メモリー解析・登録に失敗しました**: ${error.message || error}`
            });
        }
    }
};
