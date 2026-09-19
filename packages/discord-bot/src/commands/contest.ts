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

            const targetUserId = interaction.user?.id || config.userId;
            const cliArgs = ['contest', stageArg, '2000', idol, '--step', '--save', '1', '--userId', targetUserId];
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

            // 各アイドルブロックの抽出
            const idolSections = output.split(/(?=^##\s+[\d,]+\s+-)/m);
            interface ParsedIdol {
                score: number; // 平均スコア
                medianScore: number;
                idolName: string;
                mainTitle: string;
                subTitle: string;
                mainMemId: string;
                subMemId: string;
                combinations: Array<{
                    rank: number;
                    main: string;
                    sub: string;
                    median: number;
                    mean: number;
                }>;
            }

            const parsedIdols: ParsedIdol[] = [];

            for (const sec of idolSections) {
                const headerMatch = sec.match(/^##\s+([\d,]+)\s+-\s+([^\s]+)\s+【(.*?)】【(.*?)】/m);
                if (!headerMatch) continue;

                const score = parseInt(headerMatch[1].replace(/,/g, ''), 10);
                const idolName = headerMatch[2];
                const mainTitle = headerMatch[3];
                const subTitle = headerMatch[4];

                const memMatch = sec.match(/### メモリー\s*\n-\s*メイン:\s*(.*?)\s*\((.*?)\)\s*\n-\s*サブ[：:]\s*(.*?)\s*\((.*?)\)/);
                const mainMemId = memMatch ? memMatch[2].trim() : '';
                const subMemId = memMatch ? memMatch[4].trim() : '';

                const combMatches = Array.from(sec.matchAll(/^\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|/gm));
                const combinations = combMatches.map(m => ({
                    rank: parseInt(m[1], 10),
                    main: m[2].trim(),
                    sub: m[3].trim(),
                    median: parseInt(m[6].replace(/,/g, ''), 10),
                    mean: parseInt(m[9].replace(/,/g, ''), 10),
                }));

                const medianScore = combinations.length > 0 ? combinations[0].median : score;

                parsedIdols.push({
                    score,
                    medianScore,
                    idolName,
                    mainTitle,
                    subTitle,
                    mainMemId,
                    subMemId,
                    combinations,
                });
            }

            // スコア（中央値）降順ソート
            parsedIdols.sort((a, b) => b.medianScore - a.medianScore);

            // 単一ステージTop3 の抽出
            const top3Section = output.match(/### ■ 単一ステージ最適化 \(Top 3\)[\s\S]*?\*\*合計期待中央値：約\s*([\d,\.]+)\s*Pt\*\*([\s\S]*?)(?:$|\n---|\n##)/);
            let top3Items: Array<{ idol: string; rank: string; main: string; sub: string; median: number }> = [];
            let top3TotalFormatted = '';

            if (top3Section) {
                const totalNum = Math.round(parseFloat(top3Section[1].replace(/,/g, '')));
                top3TotalFormatted = totalNum.toLocaleString();
                const tableRows = Array.from(top3Section[2].matchAll(/^\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([\d,\.]+)\s*\|/gm));
                top3Items = tableRows
                    .filter(r => !r[1].includes('アイドル') && !r[1].includes(':---'))
                    .map(r => ({
                        idol: r[1].trim(),
                        rank: r[2].trim(),
                        main: r[3].trim(),
                        sub: r[4].trim(),
                        median: Math.round(parseFloat(r[5].replace(/,/g, ''))),
                    }));
            }

            if (idol === 'all') {
                // ── 全アイドル実行時 ──
                // 1. 単一ステージ最適Top3 編成
                if (top3Items.length > 0) {
                    const medals = ['🥇', '🥈', '🥉'];
                    const top3Text = top3Items.map((item, idx) => {
                        const medal = medals[idx] || `#${idx + 1}`;
                        return `${medal} **${item.idol}**: **${item.median.toLocaleString()} Pt**\n  ┣ メイン: \`${item.main}\`\n  ┗ サブ: \`${item.sub}\``;
                    }).join('\n\n');

                    embed.addFields({
                        name: `🎯 単一ステージ 最適Top3 編成 (合計期待中央値: 約 ${top3TotalFormatted} Pt)`,
                        value: top3Text,
                        inline: false,
                    });
                } else if (top3TotalFormatted) {
                    embed.addFields({
                        name: '🎯 単一ステージ 最適Top3 合計期待中央値',
                        value: `**${top3TotalFormatted} Pt**`,
                        inline: false,
                    });
                }

                // 2. 各アイドル ベストスコアランキング (上位5名)
                if (parsedIdols.length > 0) {
                    const ranks = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'];
                    const highlights = parsedIdols.slice(0, 5).map((p, idx) => {
                        const badge = ranks[idx] || `#${idx + 1}`;
                        const mainInfo = p.mainMemId ? `\`${p.mainMemId}\` 【${p.mainTitle}】` : `【${p.mainTitle}】`;
                        const subInfo = p.subMemId ? `\`${p.subMemId}\` 【${p.subTitle}】` : `【${p.subTitle}】`;
                        return `${badge} **${p.idolName}**: 中央値 **${p.medianScore.toLocaleString()} Pt** (平均: ${p.score.toLocaleString()} Pt)\n  ┣ メイン: ${mainInfo}\n  ┗ サブ: ${subInfo}`;
                    }).join('\n\n');

                    embed.addFields({
                        name: `📊 各アイドル ベスト期待スコア (上位${Math.min(5, parsedIdols.length)}件)`,
                        value: highlights,
                        inline: false,
                    });
                }
            } else {
                // ── 単一アイドル指定時 ──
                const target = parsedIdols[0];
                if (target) {
                    const mainInfo = target.mainMemId ? `\`${target.mainMemId}\` 【${target.mainTitle}】` : `【${target.mainTitle}】`;
                    const subInfo = target.subMemId ? `\`${target.subMemId}\` 【${target.subTitle}】` : `【${target.subTitle}】`;

                    embed.addFields({
                        name: '🎯 ベスト期待スコア & メモリー構成',
                        value: `中央値: **${target.medianScore.toLocaleString()} Pt** ｜ 平均: **${target.score.toLocaleString()} Pt**\n┣ **メイン**: ${mainInfo}\n┗ **サブ**: ${subInfo}`,
                        inline: false,
                    });

                    if (target.mainMemId) {
                        const mainMemDetails = await fetchMemoryDetails(target.mainMemId);
                        if (mainMemDetails) {
                            embed.addFields({
                                name: `🎴 メインメモリー詳細 (\`${target.mainMemId}\`)`,
                                value: `📊 **ステータス**: ${mainMemDetails.paramsText}\n🎁 **Pアイテム**: ${mainMemDetails.itemsText}\n🃏 **スキルカード**: ${mainMemDetails.cardsText}`,
                                inline: false,
                            });
                        }
                    }

                    if (target.combinations.length > 0) {
                        const medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'];
                        const topCombs = target.combinations.slice(0, 5).map((m, idx) => {
                            const medal = medals[idx] || `#${m.rank}`;
                            return `${medal} **#${m.rank}** [中央値: **${m.median.toLocaleString()} Pt** / 平均: ${m.mean.toLocaleString()} Pt]\n• メイン: \`${m.main}\`\n• サブ: \`${m.sub}\``;
                        }).join('\n\n');

                        embed.addFields({
                            name: `🏆 組合せベスト Top ${Math.min(5, target.combinations.length)}`,
                            value: topCombs,
                            inline: false,
                        });
                    }
                }
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
