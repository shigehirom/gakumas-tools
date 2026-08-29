import { 
    SlashCommandBuilder, 
    ChatInputCommandInteraction, 
    AttachmentBuilder, 
    AutocompleteInteraction,
    EmbedBuilder 
} from 'discord.js';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { processMemoryImage, ParsedMemoryData } from '../utils/image-processor';
import { MasterData } from '../utils/master-data';

interface AdvisoryCard {
    name: string;
    customizations: string[];
}

interface AdvisoryData {
    season: number;
    stage: number;
    regulation: {
        criteria: string;
        plan: string;
        plan_jp: string;
        turns: number;
    };
    p_idol: {
        idol_key: string;
        idol_name: string;
        title: string;
        extra: string;
    };
    p_items: string[];
    skill_cards: AdvisoryCard[];
}

export const compareMemoryCommand = {
    data: new SlashCommandBuilder()
        .setName('compare-memory')
        .setDescription('プロデュース後のメモリー選択画像（2〜3枚）を比較し、推奨構成に近い方を判定します')
        .addIntegerOption(option =>
            option.setName('stage')
                .setDescription('判定対象のステージ番号 (1, 2, 3)')
                .setRequired(true)
                .addChoices(
                    { name: 'Stage 1 (センス / Vo特化等)', value: 1 },
                    { name: 'Stage 2 (ロジック / Vi特化等)', value: 2 },
                    { name: 'Stage 3 (アノマリー / Vo特化等)', value: 3 }
                )
        )
        .addAttachmentOption(option =>
            option.setName('image1')
                .setDescription('1枚目のメモリースクリーンショット（例: 再生成前）')
                .setRequired(true)
        )
        .addAttachmentOption(option =>
            option.setName('image2')
                .setDescription('2枚目のメモリースクリーンショット（例: 再生成1回目）')
                .setRequired(true)
        )
        .addAttachmentOption(option =>
            option.setName('image3')
                .setDescription('3枚目のメモリースクリーンショット（例: 再生成2回目、任意）')
                .setRequired(false)
        )
        .addStringOption(option =>
            option.setName('idol')
                .setDescription('アイドル名または衣装名（省略時は画像から自動判別）')
                .setRequired(false)
                .setAutocomplete(true)
        )
        .addIntegerOption(option =>
            option.setName('season')
                .setDescription('シーズン番号 (省略時は最新シーズン)')
                .setRequired(false)
        ),

    async autocomplete(interaction: AutocompleteInteraction) {
        const focusedValue = interaction.options.getFocused().toLowerCase();
        const idolChoices = [
            { name: 'ことね (藤田ことね)', value: 'ことね' },
            { name: '広 (篠澤広)', value: '広' },
            { name: '千奈 (倉本千奈)', value: '千奈' },
            { name: '美鈴 (秦谷美鈴)', value: '美鈴' },
            { name: '星南 (十王星南)', value: '星南' },
            { name: '手毬 (月村手毬)', value: '手毬' },
            { name: '燕 (雨夜燕)', value: '燕' },
            { name: 'リーリヤ (葛城リーリヤ)', value: 'リーリヤ' },
            { name: '清夏 (紫雲清夏)', value: '清夏' },
            { name: '咲季 (花海咲季)', value: '咲季' },
            { name: '佑芽 (花海佑芽)', value: '佑芽' },
            { name: '麻央 (有村麻央)', value: '麻央' },
            { name: '莉波 (姫崎莉波)', value: '莉波' }
        ];

        const filtered = idolChoices.filter(choice =>
            choice.name.toLowerCase().includes(focusedValue) || choice.value.includes(focusedValue)
        );
        await interaction.respond(filtered.slice(0, 10));
    },

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const stage = interaction.options.getInteger('stage', true);
        const image1 = interaction.options.getAttachment('image1', true);
        const image2 = interaction.options.getAttachment('image2', true);
        const image3 = interaction.options.getAttachment('image3');
        const customIdol = interaction.options.getString('idol');
        const customSeason = interaction.options.getInteger('season');

        const attachments = [image1, image2];
        if (image3) attachments.push(image3);

        const memoryLabels = ['A (画像1)', 'B (画像2)', 'C (画像3)'];

        try {
            // 1. 各画像のダウンロード & 解析
            const parsedMemories: {
                label: string;
                parsed: ParsedMemoryData;
                pItemNames: string[];
                skillCardNames: string[];
                pIdolName: string;
                pIdolTitle: string;
            }[] = [];

            for (let i = 0; i < attachments.length; i++) {
                const att = attachments[i];
                if (!att.contentType?.startsWith('image/')) {
                    await interaction.followUp({ content: `⚠️ 画像${i + 1}が有効な画像ファイルではありません。` });
                    return;
                }

                const res = await fetch(att.url);
                if (!res.ok) {
                    throw new Error(`画像${i + 1}のダウンロードに失敗しました: ${res.statusText}`);
                }
                const arrayBuffer = await res.arrayBuffer();
                const buffer = Buffer.from(arrayBuffer);

                const parsed = await processMemoryImage(buffer);

                const pIdol = parsed.pIdolId ? MasterData.getPIdolById(parsed.pIdolId) : null;
                const idol = pIdol ? MasterData.getIdolById(pIdol.idolId) : null;

                const pItemNames = parsed.pItemIds.map(id => {
                    const it = MasterData.getPItemById(id);
                    return it ? it.name : (id === 0 ? '' : `ID:${id}`);
                }).filter(Boolean);

                const skillCardNames = parsed.skillCardIds.map(id => {
                    const sc = MasterData.getSkillCardById(id);
                    return sc ? sc.name : (id === 0 ? '' : `ID:${id}`);
                }).filter(Boolean);

                parsedMemories.push({
                    label: memoryLabels[i],
                    parsed,
                    pItemNames,
                    skillCardNames,
                    pIdolName: idol?.name || '',
                    pIdolTitle: pIdol?.title || ''
                });
            }

            // 2. アイドル名の決定
            let targetIdol = customIdol;
            if (!targetIdol) {
                targetIdol = parsedMemories[0].pIdolName || parsedMemories[0].pIdolTitle || '手毬';
            }

            // 3. あじふらい氏アドバイスデータの取得 (CLI)
            const candidatePaths = [
                path.resolve(__dirname, '../../../../gakumas-agent-bot/cli_get_advisory.py'),
                path.resolve(__dirname, '../../../gakumas-agent-bot/cli_get_advisory.py'),
                '/app/gakumas-agent-bot/cli_get_advisory.py',
                '/root/gakumas-workspace/gakumas-agent-bot/cli_get_advisory.py',
                '/root/gakumas-workspace/gakumas-tools/gakumas-agent-bot/cli_get_advisory.py',
            ];
            const scriptPath = candidatePaths.find(p => fs.existsSync(p)) || candidatePaths[0];

            const args = ['--stage', stage.toString(), '--idol', targetIdol];
            if (customSeason) args.push('--season', customSeason.toString());

            const advisoryData: AdvisoryData | null = await new Promise((resolve) => {
                const child = spawn('python3', [scriptPath, ...args], { env: { ...process.env } });
                let stdout = '';
                child.stdout.on('data', d => { stdout += d.toString(); });
                child.on('close', code => {
                    if (code === 0 && stdout.trim()) {
                        try {
                            const res = JSON.parse(stdout);
                            if (res.success && res.data) {
                                resolve(res.data);
                                return;
                            }
                        } catch {}
                    }
                    resolve(null);
                });
                child.on('error', () => resolve(null));
            });

            if (!advisoryData) {
                await interaction.followUp({
                    content: `⚠️ Stage ${stage} / アイドル「${targetIdol}」のあじふらい氏アドバイスデータが見つかりませんでした。`
                });
                return;
            }

            const recItems = advisoryData.p_items || [];
            const recCards = (advisoryData.skill_cards || []).map(c => c.name);

            // 4. 各メモリーのスコアリング
            const scoredMemories = parsedMemories.map(mem => {
                let score = 0;
                const matchedItems: string[] = [];
                const matchedCards: { name: string; isPlus: boolean }[] = [];

                // Pアイテムマッチング
                for (const it of mem.pItemNames) {
                    if (recItems.some(ri => it.includes(ri) || ri.includes(it))) {
                        matchedItems.push(it);
                        score += 35; // 推奨Pアイテムは極めて高価値
                    }
                }

                // スキルカードマッチング
                for (const c of mem.skillCardNames) {
                    const isPlus = c.endsWith('+');
                    const baseName = c.replace(/\+$/, '');

                    const exactMatch = recCards.find(rc => rc === c);
                    const baseMatch = recCards.find(rc => rc.replace(/\+$/, '') === baseName);

                    if (exactMatch) {
                        matchedCards.push({ name: c, isPlus });
                        score += isPlus ? 25 : 15;
                    } else if (baseMatch) {
                        matchedCards.push({ name: c, isPlus });
                        score += isPlus ? 18 : 12;
                    }
                }

                // パラメータ合計点（微小加点）
                const paramsSum = (mem.parsed.params[0] || 0) + (mem.parsed.params[1] || 0) + (mem.parsed.params[2] || 0);
                if (paramsSum > 0) {
                    score += Math.round(paramsSum / 500);
                }

                return {
                    ...mem,
                    score,
                    matchedItems,
                    matchedCards
                };
            });

            // スコア順にソート（同点の場合はmatchedCards数、+版数）
            const sorted = [...scoredMemories].sort((a, b) => b.score - a.score);
            const best = sorted[0];

            // 5. 選定理由の生成
            const reasons: string[] = [];
            if (best.matchedItems.length > 0) {
                reasons.push(`推奨Pアイテム『${best.matchedItems.join('』『')}』を保持`);
            }
            if (best.matchedCards.length > 0) {
                const plusCards = best.matchedCards.filter(c => c.isPlus).map(c => c.name);
                if (plusCards.length > 0) {
                    reasons.push(`重要スキルカード『${plusCards.join('』『')}』が【+強化版】で付与`);
                } else {
                    reasons.push(`推奨スキルカード『${best.matchedCards.map(c => c.name).join('』『')}』を保持`);
                }
            }
            if (reasons.length === 0) {
                reasons.push('汎用カード構成およびパラメータバランスがより優位');
            }

            const reasonText = reasons.join('。\n・') + '。';

            // 6. Embed の構築
            const idolDisplayName = advisoryData.p_idol.idol_name + (advisoryData.p_idol.title ? `【${advisoryData.p_idol.title}】` : '');
            const embed = new EmbedBuilder()
                .setTitle(`🏆【メモリー選択判定】シーズン${advisoryData.season} Stage ${stage}`)
                .setDescription(`**対象アイドル:** ${idolDisplayName}\n**審査基準:** ${advisoryData.regulation.criteria} (${advisoryData.regulation.turns}T) ｜ プラン: **${advisoryData.regulation.plan_jp}**`)
                .setColor(0x34A853);

            embed.addFields({
                name: `💡 推奨判定: 【メモリー ${best.label}】の選択を推奨します！`,
                value: `**【選定理由】**\n・${reasonText}`,
                inline: false
            });

            // 各メモリーの詳細フィールド
            for (const mem of scoredMemories) {
                const isBest = mem.label === best.label;
                const badge = isBest ? ' ⭐ [推奨]' : '';

                // アイテムのハイライト
                const itemStr = mem.pItemNames.map(it => {
                    const isRec = recItems.some(ri => it.includes(ri) || ri.includes(it));
                    return isRec ? `**🟢${it}**` : it;
                }).join(', ') || 'なし';

                // スキルカードのハイライト
                const cardStr = mem.skillCardNames.map(c => {
                    const isRecExact = recCards.includes(c);
                    const isRecBase = recCards.some(rc => rc.replace(/\+$/, '') === c.replace(/\+$/, ''));
                    if (isRecExact) return `**🟢${c}**`;
                    if (isRecBase) return `**🟡${c}**`;
                    return c;
                }).join(', ') || 'なし';

                const p = mem.parsed.params;
                const statusStr = (p[0] || p[1] || p[2]) 
                    ? `Vo ${p[0]} / Da ${p[1]} / Vi ${p[2]} / 体力 ${p[3]}`
                    : `コンテストパワー: ${mem.parsed.contestPower || '未判定'}`;

                embed.addFields({
                    name: `📋 メモリー ${mem.label}${badge} ［評価点: ${mem.score}点］`,
                    value: `・**ステータス:** ${statusStr}\n・**Pアイテム:** ${itemStr}\n・**スキルカード:** ${cardStr}`,
                    inline: false
                });
            }

            embed.setFooter({
                text: `My Gakumas Tools ｜ 基于 @fried_aji3 アドバイス (S${advisoryData.season} Stage ${stage})`
            });

            await interaction.followUp({ embeds: [embed] });

        } catch (e: any) {
            console.error('[compare-memory] Error:', e);
            await interaction.followUp({
                content: `⚠️ メモリー比較処理中にエラーが発生しました: \`${e.message}\``
            });
        }
    }
};
