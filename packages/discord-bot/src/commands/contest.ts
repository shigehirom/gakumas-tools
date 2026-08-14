import { 
    SlashCommandBuilder, 
    ChatInputCommandInteraction, 
    EmbedBuilder, 
    AttachmentBuilder 
} from 'discord.js';
import { MongoClient } from 'mongodb';
import { getCurrentSeason } from '../utils/contest-helper';
import { MasterData } from '../utils/master-data';
import { config } from '../config';
import { runCli } from '../utils/runner';

const IDOL_CHOICES = [
    { name: '🌟 全アイドル順次計算 (all)', value: 'all' },
    { name: '花海 咲季 (saki)', value: 'saki' },
    { name: '月村 手毬 (temari)', value: 'temari' },
    { name: '藤田 ことね (kotone)', value: 'kotone' },
    { name: '有村 麻央 (mao)', value: 'mao' },
    { name: '葛城 リーリヤ (lilja)', value: 'lilja' },
    { name: '倉本 千奈 (china)', value: 'china' },
    { name: '紫雲 清夏 (sumika)', value: 'sumika' },
    { name: '篠澤 広 (hiro)', value: 'hiro' },
    { name: '姫崎 莉波 (rinami)', value: 'rinami' },
    { name: '花海 佑芽 (ume)', value: 'ume' },
    { name: '十王 星南 (sena)', value: 'sena' },
    { name: '秦谷 美鈴 (misuzu)', value: 'misuzu' },
    { name: '雨夜 燕 (tsubame)', value: 'tsubame' }
];

interface MemoryDetails {
    name: string;
    paramsText: string;
    itemsText: string;
    cardsText: string;
}

async function fetchMemoryDetails(memoryName: string): Promise<MemoryDetails | null> {
    if (!memoryName) return null;
    const client = new MongoClient(config.mongoUri);
    try {
        await client.connect();
        const db = client.db(config.mongoDb);
        const mem = await db.collection('memories').findOne({ name: memoryName.trim() });
        if (!mem) return null;

        const params = mem.data?.params;
        const paramsText = params 
            ? `Vo: **${params.vo ?? '-'}** | Da: **${params.da ?? '-'}** | Vi: **${params.vi ?? '-'}** | HP: **${params.hp ?? '-'}**`
            : '不明';

        // PItem
        const pItemIds = mem.data?.pItemIds || [];
        const itemNames = pItemIds.map((id: number) => {
            const item = MasterData.getPItemById(id);
            return item ? item.name : `Item #${id}`;
        });
        const itemsText = itemNames.length > 0 ? itemNames.join(' / ') : 'なし';

        // Skill Cards
        const skillCardIds = mem.data?.skillCardIds || [];
        const cardNames = skillCardIds.map((id: number) => {
            const card = MasterData.getSkillCardById(id);
            return card ? `${card.name}${card.upgraded ? '+' : ''}` : `Card #${id}`;
        });
        const cardsText = cardNames.length > 0 ? cardNames.join(', ') : 'なし';

        return {
            name: mem.name,
            paramsText,
            itemsText,
            cardsText
        };
    } catch (e) {
        console.warn('Failed to fetch memory details from DB:', e);
        return null;
    } finally {
        await client.close();
    }
}

export const contestCommand = {
    data: new SlashCommandBuilder()
        .setName('contest')
        .setDescription('現在開催中コンテストのリハーサル・最適化シミュレーションを実行します (2000 runs, step実行)')
        .addIntegerOption(option =>
            option.setName('stage')
                .setDescription('ステージ番号 (1, 2, 3)')
                .setRequired(true)
                .addChoices(
                    { name: 'ステージ 1', value: 1 },
                    { name: 'ステージ 2', value: 2 },
                    { name: 'ステージ 3', value: 3 }
                )
        )
        .addStringOption(option =>
            option.setName('idol')
                .setDescription('対象アイドル (デフォルト: 全アイドル)')
                .setRequired(false)
                .addChoices(...IDOL_CHOICES)
        ),

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const stageNum = interaction.options.getInteger('stage', true);
        const idol = interaction.options.getString('idol') || 'all';
        const currentSeason = getCurrentSeason();
        const stageArg = `${currentSeason}-${stageNum}`;

        try {
            await interaction.editReply({
                content: `⏳ **【コンテスト リハーサル実行中】**\n- **対象**: シーズン ${currentSeason} ステージ ${stageNum} (\`${stageArg}\`)\n- **アイドル**: \`${idol}\`\n- **設定**: 2000 runs / 2段階ステップ実行 (\`--step\`)\n*計算が完了するまで少々お待ちください...*`
            });

            const cliArgs = ['contest', stageArg, '2000', idol, '--step'];
            const result = await runCli(cliArgs);

            if (result.exitCode !== 0 && (!result.stdout || result.stdout.trim().length === 0)) {
                await interaction.editReply({
                    content: `❌ **シミュレーション実行エラー** (Exit Code: ${result.exitCode})\n\`\`\`\n${result.stderr || 'Unknown error'}\n\`\`\``
                });
                return;
            }

            const output = result.stdout;

            // Embed 作成
            const embed = new EmbedBuilder()
                .setColor(0x00AE86)
                .setTitle(`🏆 コンテスト リハーサル結果 (シーズン${currentSeason} ステージ${stageNum})`)
                .setDescription(`**対象アイドル**: \`${idol}\` | **試行回数**: 2,000 runs (Step実行)`)
                .setTimestamp();

            // 単一ステージTop3 または ベストスコアの抽出
            const top3Match = output.match(/### ■ 単一ステージ最適化 \(Top 3\)[\s\S]*?\*\*合計期待中央値：約\s*([\d,]+)\s*Pt\*\*/);
            if (top3Match) {
                const totalFormatted = parseInt(top3Match[1].replace(/,/g, ''), 10).toLocaleString();
                embed.addFields({
                    name: '🎯 単一ステージ 最適Top3 合計期待中央値',
                    value: `**${totalFormatted} Pt**`,
                    inline: false
                });
            }

            // メイン/サブメモリーの抽出
            // - メイン: クライアイ (26/08/13＿16725)
            // - サブ： クライアイ (26/08/09＿17274)
            const memMatch = output.match(/### メモリー\s*\n-\s*メイン:\s*(.*?)\s*\((.*?)\)\s*\n-\s*サブ[：:]\s*(.*?)\s*\((.*?)\)/);
            let mainMemId = '';
            let mainTitle = '';
            let subMemId = '';
            let subTitle = '';
            if (memMatch) {
                mainTitle = memMatch[1];
                mainMemId = memMatch[2];
                subTitle = memMatch[3];
                subMemId = memMatch[4];
            }

            // 個別アイドルのベストスコアハイライト (## 150660 - 雨夜燕 【クライアイ】【クライアイ】)
            const bestMatches = Array.from(output.matchAll(/^##\s+([\d,]+)\s+-\s+([^\s]+)\s+【(.*?)】【(.*?)】/gm));
            if (bestMatches.length > 0) {
                const highlights = bestMatches.slice(0, 5).map(m => {
                    const scoreNum = parseInt(m[1].replace(/,/g, ''), 10);
                    const formattedScore = scoreNum.toLocaleString();
                    const mainInfo = mainMemId ? `\`${mainMemId}\` 【${m[3]}】` : `【${m[3]}】`;
                    const subInfo = subMemId ? `\`${subMemId}\` 【${m[4]}】` : `【${m[4]}】`;
                    return `• **${m[2]}**: **${formattedScore} Pt**\n  ┣ **メイン**: ${mainInfo}\n  ┗ **サブ**: ${subInfo}`;
                }).join('\n\n');

                embed.addFields({
                    name: `📊 上位アイドル ベスト期待スコア (上位${Math.min(5, bestMatches.length)}件)`,
                    value: highlights,
                    inline: false
                });
            }

            // 単一アイドル指定時：メインメモリーの詳細（ステータス・Pアイテム・スキルカード）を DB から取得して表示
            if (mainMemId) {
                const mainMemDetails = await fetchMemoryDetails(mainMemId);
                if (mainMemDetails) {
                    embed.addFields(
                        {
                            name: `🎴 メインメモリー詳細 (\`${mainMemId}\`)`,
                            value: `📊 **ステータス**: ${mainMemDetails.paramsText}\n🎁 **Pアイテム**: ${mainMemDetails.itemsText}\n🃏 **スキルカード**: ${mainMemDetails.cardsText}`,
                            inline: false
                        }
                    );
                }
            }

            // 組合せベスト Top 3 のテーブル抽出
            // | 1 | 26/08/13＿16725【クライアイ】 | 26/08/09＿17274【クライアイ】 | ... | ... | 150660 | ...
            const combMatches = Array.from(output.matchAll(/^\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|/gm));
            if (combMatches.length > 0) {
                const topCombs = combMatches.slice(0, 3).map(m => {
                    const rank = m[1];
                    const mainStr = m[2].trim();
                    const subStr = m[3].trim();
                    const median = parseInt(m[6].replace(/,/g, ''), 10).toLocaleString();
                    const avg = parseInt(m[9].replace(/,/g, ''), 10).toLocaleString();
                    return `**#${rank}** [中央値: **${median} Pt** / 平均: ${avg} Pt]\n• メイン: \`${mainStr}\`\n• サブ: \`${subStr}\``;
                }).join('\n\n');

                embed.addFields({
                    name: '🏆 組合せベスト Top 3',
                    value: topCombs,
                    inline: false
                });
            }

            // レポートファイルの添付
            const reportBuffer = Buffer.from(output, 'utf-8');
            const attachment = new AttachmentBuilder(reportBuffer, { name: `${stageArg}_${idol}_report.md` });

            await interaction.editReply({
                content: `✅ **シミュレーションが完了しました！**`,
                embeds: [embed],
                files: [attachment]
            });

        } catch (error: any) {
            console.error('Contest execution failed:', error);
            try {
                await interaction.editReply({
                    content: `❌ **予期せぬエラーが発生しました**: ${error.message || error}`
                });
            } catch {}
        }
    }
};
