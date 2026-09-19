import {
    SlashCommandBuilder,
    ChatInputCommandInteraction,
    AttachmentBuilder,
    AutocompleteInteraction,
    ActionRowBuilder,
    StringSelectMenuBuilder,
    StringSelectMenuInteraction,
    SelectMenuComponentOptionData
} from 'discord.js';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { config } from '../config';

export interface ChecklistData {
    p_items: string[];
    skill_cards: Array<{
        name: string;
        customizations: string[];
    }>;
}

export function renderChecklistText(checklist: ChecklistData, checkedSet: Set<string>): string {
    const lines: string[] = [];
    lines.push('━━━━━━━━━━━━━━━━━━━━');
    lines.push('📋 **【育成達成状況チェックリスト】**');

    let totalCount = 0;
    let checkedCount = 0;

    if (checklist.p_items && checklist.p_items.length > 0) {
        lines.push('\n**◆ お勧めPアイテム**');
        checklist.p_items.forEach((item, idx) => {
            totalCount++;
            const key = `item:${idx}`;
            const isChecked = checkedSet.has(key);
            if (isChecked) checkedCount++;
            const mark = isChecked ? '☑️' : '⬜';
            lines.push(`${mark} ${item}`);
        });
    }

    if (checklist.skill_cards && checklist.skill_cards.length > 0) {
        lines.push('\n**◆ お勧めスキルカード**');
        checklist.skill_cards.forEach((card, idx) => {
            totalCount++;
            const key = `card:${idx}`;
            const isChecked = checkedSet.has(key);
            if (isChecked) checkedCount++;
            const mark = isChecked ? '☑️' : '⬜';
            lines.push(`${mark} **#${idx + 1}** ${card.name}`);

            if (card.customizations && card.customizations.length > 0) {
                card.customizations.forEach((cust, cIdx) => {
                    totalCount++;
                    const cKey = `cust:${idx}:${cIdx}`;
                    const isCustChecked = checkedSet.has(cKey);
                    if (isCustChecked) checkedCount++;
                    const cMark = isCustChecked ? '☑️' : '⬜';
                    lines.push(`　 ${cMark} └ ${cust}`);
                });
            }
        });
    }

    lines.push(`\n*(達成状況: ${checkedCount} / ${totalCount} 項目)*`);
    return lines.join('\n');
}

export function renderChecklistFromOptions(options: any[], checkedSet: Set<string>): string {
    const lines: string[] = [];
    lines.push('━━━━━━━━━━━━━━━━━━━━');
    lines.push('📋 **【育成達成状況チェックリスト】**');

    let totalCount = 0;
    let checkedCount = 0;
    let inPItems = false;
    let inSkillCards = false;

    for (const opt of options) {
        totalCount++;
        const isChecked = checkedSet.has(opt.value);
        if (isChecked) checkedCount++;
        const mark = isChecked ? '☑️' : '⬜';

        if (opt.value.startsWith('item:')) {
            if (!inPItems) {
                lines.push('\n**◆ お勧めPアイテム**');
                inPItems = true;
            }
            const itemName = opt.label.replace(/^\[Pアイテム\]\s*/, '');
            lines.push(`${mark} ${itemName}`);
        } else if (opt.value.startsWith('card:')) {
            if (!inSkillCards) {
                lines.push('\n**◆ お勧めスキルカード**');
                inSkillCards = true;
            }
            const cardMatch = opt.label.match(/^\[スキル\s*#(\d+)\]\s*(.*)$/);
            if (cardMatch) {
                lines.push(`${mark} **#${cardMatch[1]}** ${cardMatch[2]}`);
            } else {
                lines.push(`${mark} ${opt.label}`);
            }
        } else if (opt.value.startsWith('cust:')) {
            const custMatch = opt.label.match(/\[カスタム\]\s*(.*?)(?:\s*\(#\d+\))?$/);
            const custName = custMatch ? custMatch[1] : opt.label;
            lines.push(`　 ${mark} └ ${custName}`);
        }
    }

    lines.push(`\n*(達成状況: ${checkedCount} / ${totalCount} 項目)*`);
    return lines.join('\n');
}

export function buildChecklistSelectMenu(
    checklist: ChecklistData,
    checkedSet: Set<string>,
    customId: string
): ActionRowBuilder<StringSelectMenuBuilder> {
    const options: SelectMenuComponentOptionData[] = [];

    if (checklist.p_items) {
        checklist.p_items.forEach((item, idx) => {
            const key = `item:${idx}`;
            options.push({
                label: `[Pアイテム] ${item}`.slice(0, 100),
                value: key,
                description: `Pアイテム: ${item}`.slice(0, 100),
                default: checkedSet.has(key)
            });
        });
    }

    if (checklist.skill_cards) {
        checklist.skill_cards.forEach((card, idx) => {
            const key = `card:${idx}`;
            options.push({
                label: `[スキル #${idx + 1}] ${card.name}`.slice(0, 100),
                value: key,
                description: `スキルカード #${idx + 1}`.slice(0, 100),
                default: checkedSet.has(key)
            });

            if (card.customizations) {
                card.customizations.forEach((cust, cIdx) => {
                    const cKey = `cust:${idx}:${cIdx}`;
                    options.push({
                        label: `└ [カスタム] ${cust} (#${idx + 1})`.slice(0, 100),
                        value: cKey,
                        description: `${card.name} のカスタマイズ効果`.slice(0, 100),
                        default: checkedSet.has(cKey)
                    });
                });
            }
        });
    }

    const trimmedOptions = options.slice(0, 25);
    const maxVal = trimmedOptions.length;

    const selectMenu = new StringSelectMenuBuilder()
        .setCustomId(customId)
        .setPlaceholder(`達成した条件を選択してください (0〜${maxVal}件)`)
        .setMinValues(0)
        .setMaxValues(maxVal)
        .addOptions(trimmedOptions);

    return new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(selectMenu);
}

export async function handleAdvisoryChecklistInteraction(interaction: StringSelectMenuInteraction) {
    if (!interaction.customId.startsWith('advisory_cl:')) return;

    const ownerId = interaction.customId.split(':')[1];
    if (ownerId && interaction.user.id !== ownerId) {
        await interaction.reply({
            content: '⚠️ このチェックリストはコマンド実行者本人のみ操作可能です。',
            ephemeral: true
        });
        return;
    }

    const checkedSet = new Set(interaction.values);
    const currentOptions = (interaction.component as any).options || [];

    const newOptions = currentOptions.map((opt: any) => ({
        label: opt.label,
        value: opt.value,
        description: opt.description,
        default: checkedSet.has(opt.value)
    }));

    const newSelectMenu = new StringSelectMenuBuilder()
        .setCustomId(interaction.customId)
        .setPlaceholder(`達成した条件を選択してください (0〜${newOptions.length}件)`)
        .setMinValues(0)
        .setMaxValues(newOptions.length)
        .addOptions(newOptions);

    const newRow = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(newSelectMenu);

    const content = interaction.message.content || '';
    const parts = content.split('━━━━━━━━━━━━━━━━━━━━');
    const baseMsg = parts[0].trim();
    const newChecklistText = renderChecklistFromOptions(currentOptions, checkedSet);
    const newContent = `${baseMsg}\n\n${newChecklistText}`;

    await interaction.update({
        content: newContent,
        components: [newRow]
    });
}

function resolvePythonScript(scriptName: string): string {
    const candidatePaths = [
        path.resolve(__dirname, `../../../../gakumas-agent-bot/${scriptName}`),
        path.resolve(__dirname, `../../../gakumas-agent-bot/${scriptName}`),
        `/app/gakumas-agent-bot/${scriptName}`,
        `/root/gakumas-workspace/gakumas-agent-bot/${scriptName}`,
        `/root/gakumas-workspace/gakumas-tools/gakumas-agent-bot/${scriptName}`,
    ];
    return candidatePaths.find(p => fs.existsSync(p)) || candidatePaths[0];
}

function formatRequiredSupportCards(images: any[]): string {
    if (!images || images.length === 0) return '';

    const cardMap = new Map<string, { sources: Set<string>; isOwned: boolean }>();

    for (const img of images) {
        for (const it of (img.p_items_details || [])) {
            if (!it.card_label || it.card_label === '推奨Pアイテム') continue;
            if (!cardMap.has(it.card_label)) {
                cardMap.set(it.card_label, { sources: new Set(), isOwned: it.is_owned !== false });
            }
            const entry = cardMap.get(it.card_label)!;
            entry.sources.add(`Pアイテム: ${it.item_name}`);
            if (it.is_owned === false) entry.isOwned = false;
        }
        for (const sc of (img.skill_cards_details || [])) {
            if (!sc.card_label) continue;
            if (!cardMap.has(sc.card_label)) {
                cardMap.set(sc.card_label, { sources: new Set(), isOwned: sc.is_owned !== false });
            }
            const entry = cardMap.get(sc.card_label)!;
            entry.sources.add(`スキル: ${sc.card_name}`);
            if (sc.is_owned === false) entry.isOwned = false;
        }
    }

    if (cardMap.size === 0) return '';

    const lines: string[] = [];
    let hasUnowned = false;
    for (const [label, info] of cardMap.entries()) {
        const sourceStr = Array.from(info.sources).join(' / ');
        const unownedTag = !info.isOwned ? ' ⚠️**【未所持】**' : '';
        if (!info.isOwned) hasUnowned = true;
        lines.push(`・\`${label}\`${unownedTag} （${sourceStr}）`);
    }

    let res = lines.join('\n');
    if (hasUnowned) {
        res += '\n\n💡 **注**: ⚠️【未所持】のサポートカードは、育成時にフレンド等のレンタル枠での補完や代替カードをご検討ください。';
    }
    return res;
}

function formatStageSupportCombinations(combinations: any[], asariIdols?: string[]): string {
    if (!combinations || combinations.length === 0) return '';

    const blocks: string[] = [];
    let hasUnowned = false;

    for (const comb of combinations) {
        const lines: string[] = [];
        lines.push(`■ **${comb.index}. ${comb.name}**`);

        if (comb.p_items && comb.p_items.length > 0) {
            lines.push('・Pアイテム枠:');
            for (const it of comb.p_items) {
                const label = it.card_label || '推奨Pアイテム';
                const unownedTag = it.is_owned === false ? ' ⚠️**【未所持】**' : '';
                if (it.is_owned === false) hasUnowned = true;
                lines.push(`  - \`${label}\`${unownedTag}（${it.item_name}）`);
            }
        }

        if (comb.skill_cards && comb.skill_cards.length > 0) {
            lines.push('・スキルカード枠:');
            for (const sc of comb.skill_cards) {
                const label = sc.card_label || 'サポートスキル';
                const unownedTag = sc.is_owned === false ? ' ⚠️**【未所持】**' : '';
                if (sc.is_owned === false) hasUnowned = true;
                lines.push(`  - \`${label}\`${unownedTag}（${sc.card_name}）`);
            }
        }

        const totalReq = comb.total_required || 0;
        const freeSlots = Math.max(0, 6 - totalReq);
        lines.push(`※必須サポカ: **${totalReq}枚**（残り自由枠: **${freeSlots}枚**）`);

        blocks.push(lines.join('\n'));
    }

    let result = blocks.join('\n\n');

    if (asariIdols && asariIdols.length > 0) {
        const sampleAsari = asariIdols.slice(0, 3).join('、') + (asariIdols.length > 3 ? ' 等' : '');
        result += `\n\n📌 **注**: 根緒亜紗里必須（\`with_asari\`）のアイドル（${sampleAsari}）は、上記に加え \`[SSR] きみは、自慢の生徒です (サポ)\` が必須となります。`;
    }

    if (hasUnowned) {
        result += '\n\n💡 **注**: ⚠️【未所持】のサポートカードは、育成時にフレンド等のレンタル枠での補完や代替カードをご検討ください。';
    }

    return result;
}

export const advisoryCommand = {
    data: new SlashCommandBuilder()
        .setName('advisory')
        .setDescription('コンテスト推奨のPアイテム・スキルカード構成画像（Pixel 10 Pro Fold最適化）を出力します')
        .addStringOption(option =>
            option.setName('source')
                .setDescription('推奨データソース (Human: あじふらい氏推奨 / AI: AI自律導出)')
                .setRequired(true)
                .addChoices(
                    { name: 'あじふらい氏推奨 (Human - おすすめ順・楽曲名表記)', value: 'human' },
                    { name: 'AI自律導出 (AI Auto-Advisory - アイドル名表記)', value: 'ai' }
                )
        )
        .addIntegerOption(option =>
            option.setName('stage')
                .setDescription('ステージ番号 (1, 2, 3)')
                .setRequired(true)
                .addChoices(
                    { name: 'Stage 1 (センス / Vo特化等)', value: 1 },
                    { name: 'Stage 2 (ロジック / Vi特化等)', value: 2 },
                    { name: 'Stage 3 (アノマリー / Vo特化等)', value: 3 }
                )
        )
        .addStringOption(option =>
            option.setName('idol')
                .setDescription('アイドル名または衣装名 (省略時は汎用および個別推奨構成を一括出力)')
                .setRequired(false)
                .setAutocomplete(true)
        )
        .addIntegerOption(option =>
            option.setName('season')
                .setDescription('シーズン番号 (省略時は最新シーズン)')
                .setRequired(false)
        )
        .addIntegerOption(option =>
            option.setName('columns')
                .setDescription('表示列数 (1: 縦型スリム[デフォルト], 2: 2列ワイド)')
                .setRequired(false)
                .addChoices(
                    { name: '1列 (縦型スリム・スマホ最適 [デフォルト])', value: 1 },
                    { name: '2列 (2列グリッド・ワイド表示)', value: 2 }
                )
        ),

    async autocomplete(interaction: AutocompleteInteraction) {
        const focusedOption = interaction.options.getFocused(true);
        const focusedValue = (focusedOption.value || '').toLowerCase();
        const stage = interaction.options.getInteger('stage') || 1;
        const season = interaction.options.getInteger('season');
        const source = interaction.options.getString('source') || 'human';

        const scriptPath = resolvePythonScript('cli_get_stage_idols.py');
        if (!fs.existsSync(scriptPath)) {
            await interaction.respond([]);
            return;
        }

        const args = [
            scriptPath,
            '--stage', stage.toString(),
            '--mongo-uri', config.mongoUri,
            '--source', source
        ];
        if (season) {
            args.push('--season', season.toString());
        }

        try {
            const child = spawn('python3', args);
            let stdout = '';
            child.stdout.on('data', d => { stdout += d.toString(); });
            child.on('close', async (code) => {
                if (code !== 0 || !stdout.trim()) {
                    await interaction.respond([]);
                    return;
                }
                try {
                    const choices: Array<{ name: string; value: string }> = JSON.parse(stdout);
                    const filtered = choices.filter(c =>
                        c.name.toLowerCase().includes(focusedValue) ||
                        c.value.toLowerCase().includes(focusedValue)
                    );
                    await interaction.respond(filtered.slice(0, 25));
                } catch {
                    await interaction.respond([]);
                }
            });
        } catch {
            await interaction.respond([]);
        }
    },

    async execute(interaction: ChatInputCommandInteraction) {
        await interaction.deferReply();

        const source = interaction.options.getString('source', true);
        const stage = interaction.options.getInteger('stage', true);
        const idol = interaction.options.getString('idol');
        const season = interaction.options.getInteger('season');
        const columns = interaction.options.getInteger('columns') || 1;

        const scriptPath = resolvePythonScript('cli_advisory_image.py');

        const args = [
            scriptPath,
            '--stage', stage.toString(),
            '--mongo-uri', config.mongoUri,
            '--columns', columns.toString(),
            '--source', source
        ];
        if (idol) {
            args.push('--idol', idol);
        }
        if (season) {
            args.push('--season', season.toString());
        }

        try {
            const child = spawn('python3', args, {
                env: { ...process.env }
            });

            let stdout = '';
            let stderr = '';

            child.stdout.on('data', (d) => { stdout += d.toString(); });
            child.stderr.on('data', (d) => { stderr += d.toString(); });

            child.on('close', async (code) => {
                if (code !== 0 || !stdout.trim()) {
                    let errMsg = '画像の生成に失敗しました。';
                    try {
                        const parsed = JSON.parse(stdout);
                        if (parsed.error) errMsg = parsed.error;
                    } catch {
                        if (stderr) errMsg += `\n\`${stderr.slice(0, 200)}\``;
                    }
                    await interaction.followUp({ content: `⚠️ ${errMsg}` });
                    return;
                }

                try {
                    const result = JSON.parse(stdout);
                    if (!result.success || !result.images || result.images.length === 0) {
                        await interaction.followUp({ content: `⚠️ ${result.error || '画像ファイルが見つかりませんでした。'}` });
                        return;
                    }

                    const attachments: AttachmentBuilder[] = [];
                    const titles: string[] = [];

                    for (const imgData of result.images) {
                        if (fs.existsSync(imgData.image_path)) {
                            attachments.push(new AttachmentBuilder(imgData.image_path, {
                                name: path.basename(imgData.image_path)
                            }));
                            titles.push(imgData.full_title);
                        }
                    }

                    if (attachments.length === 0) {
                        await interaction.followUp({ content: '⚠️ 生成された画像ファイルの読み込みに失敗しました。' });
                        return;
                    }

                    const first = result.images[0];
                    const curSeason = first.season || 51;
                    const components: any[] = [];
                    let msg = '';

                    const sourceTitle = source === 'ai' ? '🤖 AI自律推奨構成 (AI Auto-Advisory)' : 'あじふらい氏推奨構成';
                    const sourceDesc = source === 'ai' ? 'シミュレータ主導のビームサーチ探索によって自律導出された' : 'あじふらい氏アドバイスに基づく';

                    if (result.mode === 'single') {
                        msg = `📋 **[${sourceTitle}レポート]** シーズン${curSeason} Stage ${stage}：**${first.full_title}**\n` +
                            `${sourceDesc}推奨Pアイテムおよびスキルカードの構成画像を出力しました。`;
                        const supportReqs = formatRequiredSupportCards([first]);
                        if (supportReqs) {
                            msg += `\n\n💡 **推奨構成に必要なサポートカード一覧**:\n${supportReqs}`;
                        }

                        if (first.checklist_items) {
                            const customId = `advisory_cl:${interaction.user.id}`;
                            const checkedSet = new Set<string>();

                            const checklistText = renderChecklistText(first.checklist_items, checkedSet);
                            msg += '\n\n' + checklistText;

                            const selectMenuRow = buildChecklistSelectMenu(first.checklist_items, checkedSet, customId);
                            components.push(selectMenuRow);
                        }
                    } else {
                        const supportReqs = (result.support_combinations && result.support_combinations.length > 0)
                            ? formatStageSupportCombinations(result.support_combinations, result.asari_idols)
                            : formatRequiredSupportCards(result.images);

                        let configListStr = result.images.map((img: any) => {
                            const icon = img.config_type === 'common' ? '📌' : '🌟';
                            let str = `${icon} **${img.full_title}**`;
                            if (img.target_idols_short && img.target_idols_short.length > 0) {
                                str += `\n　└ *対象Pアイドル*: ${img.target_idols_short.join('、')}`;
                            }
                            return str;
                        }).join('\n');
                        let header = `📋 **[${sourceTitle}レポート]** シーズン${curSeason} Stage ${stage}（汎用構成 ＆ 個別推奨構成 全${attachments.length}種）\n` +
                            `${sourceDesc}推奨構成画像を出力しました（添付画像参照）：\n${configListStr}\n\n`;

                        // 2000文字制限セーフティ
                        if ((header + supportReqs).length > 1900) {
                            configListStr = result.images.slice(0, 3).map((img: any) => {
                                const icon = img.config_type === 'common' ? '📌' : '🌟';
                                let str = `${icon} **${img.full_title}**`;
                                if (img.target_idols_short && img.target_idols_short.length > 0) {
                                    str += `\n　└ *対象*: ${img.target_idols_short.slice(0, 5).join('、')}${img.target_idols_short.length > 5 ? ' 等' : ''}`;
                                }
                                return str;
                            }).join('\n') + (result.images.length > 3 ? `\n・...他 ${result.images.length - 3}種` : '');
                            header = `📋 **[${sourceTitle}レポート]** シーズン${curSeason} Stage ${stage}（汎用構成 ＆ 個別推奨構成 全${attachments.length}種）\n` +
                                `${configListStr}\n\n`;
                        }

                        msg = header + `💡 **【ステージ必須サポートカード構成の組合せ】**:\n\n` + supportReqs;
                        if (msg.length > 1950) {
                            msg = msg.slice(0, 1940) + '\n...（文字数制限のため一部省略）';
                        }
                    }

                    await interaction.followUp({
                        content: msg,
                        files: attachments,
                        components
                    });
                } catch (e: any) {
                    await interaction.followUp({ content: `⚠️ 結果の処理中にエラーが発生しました: ${e.message}` });
                }
            });

            child.on('error', async (err) => {
                await interaction.followUp({ content: `⚠️ Pythonスクリプトの起動に失敗しました: ${err.message}` });
            });

        } catch (e: any) {
            await interaction.followUp({ content: `⚠️ エラーが発生しました: ${e.message}` });
        }
    }
};

