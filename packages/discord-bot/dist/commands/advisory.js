"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.advisoryCommand = void 0;
exports.renderChecklistText = renderChecklistText;
exports.renderChecklistFromOptions = renderChecklistFromOptions;
exports.buildChecklistSelectMenu = buildChecklistSelectMenu;
exports.handleAdvisoryChecklistInteraction = handleAdvisoryChecklistInteraction;
const discord_js_1 = require("discord.js");
const mcp_client_1 = require("../utils/mcp-client");
function renderChecklistText(checklist, checkedSet) {
    const lines = [];
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
            if (isChecked)
                checkedCount++;
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
            if (isChecked)
                checkedCount++;
            const mark = isChecked ? '☑️' : '⬜';
            lines.push(`${mark} **#${idx + 1}** ${card.name}`);
            if (card.customizations && card.customizations.length > 0) {
                card.customizations.forEach((cust, cIdx) => {
                    totalCount++;
                    const cKey = `cust:${idx}:${cIdx}`;
                    const isCustChecked = checkedSet.has(cKey);
                    if (isCustChecked)
                        checkedCount++;
                    const cMark = isCustChecked ? '☑️' : '⬜';
                    lines.push(`　 ${cMark} └ ${cust}`);
                });
            }
        });
    }
    lines.push(`\n*(達成状況: ${checkedCount} / ${totalCount} 項目)*`);
    return lines.join('\n');
}
function renderChecklistFromOptions(options, checkedSet) {
    const lines = [];
    lines.push('━━━━━━━━━━━━━━━━━━━━');
    lines.push('📋 **【育成達成状況チェックリスト】**');
    let totalCount = 0;
    let checkedCount = 0;
    let inPItems = false;
    let inSkillCards = false;
    for (const opt of options) {
        totalCount++;
        const isChecked = checkedSet.has(opt.value);
        if (isChecked)
            checkedCount++;
        const mark = isChecked ? '☑️' : '⬜';
        if (opt.value.startsWith('item:')) {
            if (!inPItems) {
                lines.push('\n**◆ お勧めPアイテム**');
                inPItems = true;
            }
            const itemName = opt.label.replace(/^\[Pアイテム\]\s*/, '');
            lines.push(`${mark} ${itemName}`);
        }
        else if (opt.value.startsWith('card:')) {
            if (!inSkillCards) {
                lines.push('\n**◆ お勧めスキルカード**');
                inSkillCards = true;
            }
            const cardMatch = opt.label.match(/^\[スキル\s*#(\d+)\]\s*(.*)$/);
            if (cardMatch) {
                lines.push(`${mark} **#${cardMatch[1]}** ${cardMatch[2]}`);
            }
            else {
                lines.push(`${mark} ${opt.label}`);
            }
        }
        else if (opt.value.startsWith('cust:')) {
            const custMatch = opt.label.match(/\[カスタム\]\s*(.*?)(?:\s*\(#\d+\))?$/);
            const custName = custMatch ? custMatch[1] : opt.label;
            lines.push(`　 ${mark} └ ${custName}`);
        }
    }
    lines.push(`\n*(達成状況: ${checkedCount} / ${totalCount} 項目)*`);
    return lines.join('\n');
}
function buildChecklistSelectMenu(checklist, checkedSet, customId) {
    const options = [];
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
    const selectMenu = new discord_js_1.StringSelectMenuBuilder()
        .setCustomId(customId)
        .setPlaceholder(`達成した条件を選択してください (0〜${maxVal}件)`)
        .setMinValues(0)
        .setMaxValues(maxVal)
        .addOptions(trimmedOptions);
    return new discord_js_1.ActionRowBuilder().addComponents(selectMenu);
}
async function handleAdvisoryChecklistInteraction(interaction) {
    if (!interaction.customId.startsWith('advisory_cl:'))
        return;
    const ownerId = interaction.customId.split(':')[1];
    if (ownerId && interaction.user.id !== ownerId) {
        await interaction.reply({
            content: '⚠️ このチェックリストはコマンド実行者本人のみ操作可能です。',
            ephemeral: true
        });
        return;
    }
    const checkedSet = new Set(interaction.values);
    const currentOptions = interaction.component.options || [];
    const newOptions = currentOptions.map((opt) => ({
        label: opt.label,
        value: opt.value,
        description: opt.description,
        default: checkedSet.has(opt.value)
    }));
    const newSelectMenu = new discord_js_1.StringSelectMenuBuilder()
        .setCustomId(interaction.customId)
        .setPlaceholder(`達成した条件を選択してください (0〜${newOptions.length}件)`)
        .setMinValues(0)
        .setMaxValues(newOptions.length)
        .addOptions(newOptions);
    const newRow = new discord_js_1.ActionRowBuilder().addComponents(newSelectMenu);
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
function formatRequiredSupportCards(images) {
    if (!images || images.length === 0)
        return '';
    const cardMap = new Map();
    for (const img of images) {
        for (const it of (img.p_items_details || [])) {
            if (!it.card_label || it.card_label === '推奨Pアイテム')
                continue;
            if (!cardMap.has(it.card_label)) {
                cardMap.set(it.card_label, { sources: new Set(), isOwned: it.is_owned !== false });
            }
            const entry = cardMap.get(it.card_label);
            entry.sources.add(`Pアイテム: ${it.item_name}`);
            if (it.is_owned === false)
                entry.isOwned = false;
        }
        for (const sc of (img.skill_cards_details || [])) {
            if (!sc.card_label)
                continue;
            if (!cardMap.has(sc.card_label)) {
                cardMap.set(sc.card_label, { sources: new Set(), isOwned: sc.is_owned !== false });
            }
            const entry = cardMap.get(sc.card_label);
            entry.sources.add(`スキル: ${sc.card_name}`);
            if (sc.is_owned === false)
                entry.isOwned = false;
        }
    }
    if (cardMap.size === 0)
        return '';
    const lines = [];
    let hasUnowned = false;
    for (const [label, info] of cardMap.entries()) {
        const sourceStr = Array.from(info.sources).join(' / ');
        const unownedTag = !info.isOwned ? ' ⚠️**【未所持】**' : '';
        if (!info.isOwned)
            hasUnowned = true;
        lines.push(`・\`${label}\`${unownedTag} （${sourceStr}）`);
    }
    let res = lines.join('\n');
    if (hasUnowned) {
        res += '\n\n💡 **注**: ⚠️【未所持】のサポートカードは、育成時にフレンド等のレンタル枠での補完や代替カードをご検討ください。';
    }
    return res;
}
function formatStageSupportCombinations(combinations, asariIdols) {
    if (!combinations || combinations.length === 0)
        return '';
    const blocks = [];
    let hasUnowned = false;
    for (const comb of combinations) {
        const lines = [];
        lines.push(`■ **${comb.index}. ${comb.name}**`);
        if (comb.p_items && comb.p_items.length > 0) {
            lines.push('・Pアイテム枠:');
            for (const it of comb.p_items) {
                const label = it.card_label || '推奨Pアイテム';
                const unownedTag = it.is_owned === false ? ' ⚠️**【未所持】**' : '';
                if (it.is_owned === false)
                    hasUnowned = true;
                lines.push(`  - \`${label}\`${unownedTag}（${it.item_name}）`);
            }
        }
        if (comb.skill_cards && comb.skill_cards.length > 0) {
            lines.push('・スキルカード枠:');
            for (const sc of comb.skill_cards) {
                const label = sc.card_label || 'サポートスキル';
                const unownedTag = sc.is_owned === false ? ' ⚠️**【未所持】**' : '';
                if (sc.is_owned === false)
                    hasUnowned = true;
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
exports.advisoryCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('advisory')
        .setDescription('コンテスト推奨のPアイテム・スキルカード構成画像（Pixel 10 Pro Fold最適化）を出力します')
        .addStringOption(option => option.setName('source')
        .setDescription('推奨データソース (Human: あじふらい氏推奨 / AI: AI自律導出)')
        .setRequired(true)
        .addChoices({ name: 'あじふらい氏推奨 (Human - おすすめ順・楽曲名表記)', value: 'human' }, { name: 'AI自律導出 (AI Auto-Advisory - アイドル名表記)', value: 'ai' }))
        .addIntegerOption(option => option.setName('stage')
        .setDescription('ステージ番号 (1, 2, 3)')
        .setRequired(true)
        .addChoices({ name: 'Stage 1 (センス / Vo特化等)', value: 1 }, { name: 'Stage 2 (ロジック / Vi特化等)', value: 2 }, { name: 'Stage 3 (アノマリー / Vo特化等)', value: 3 }))
        .addStringOption(option => option.setName('idol')
        .setDescription('アイドル名または衣装名 (省略時は汎用および個別推奨構成を一括出力)')
        .setRequired(false)
        .setAutocomplete(true))
        .addIntegerOption(option => option.setName('season')
        .setDescription('シーズン番号 (省略時は最新シーズン)')
        .setRequired(false)),
    async autocomplete(interaction) {
        const focusedOption = interaction.options.getFocused(true);
        const focusedValue = (focusedOption.value || '').toLowerCase();
        const stage = interaction.options.getInteger('stage') || 1;
        const season = interaction.options.getInteger('season');
        const source = interaction.options.getString('source') || 'human';
        try {
            const raw = await (0, mcp_client_1.callMcpTool)('get_stage_idols', {
                stage,
                season: season || null,
                source
            });
            let choices = [];
            if (Array.isArray(raw)) {
                choices = raw;
            }
            else if (raw?.content?.[0]?.text) {
                choices = JSON.parse(raw.content[0].text);
            }
            const filtered = choices.filter(c => c.name.toLowerCase().includes(focusedValue) ||
                c.value.toLowerCase().includes(focusedValue));
            await interaction.respond(filtered.slice(0, 25));
        }
        catch (err) {
            console.error('[advisory] MCP autocomplete error:', err);
            await interaction.respond([]);
        }
    },
    async execute(interaction) {
        await interaction.deferReply();
        const source = interaction.options.getString('source', true);
        const stage = interaction.options.getInteger('stage', true);
        const idol = interaction.options.getString('idol') || '';
        const season = interaction.options.getInteger('season');
        try {
            const raw = await (0, mcp_client_1.callMcpTool)('get_contest_advisory_report', {
                stage,
                idol,
                season: season || null,
                source,
                columns: 1
            });
            let result = null;
            if (raw?.content?.[0]?.text) {
                result = JSON.parse(raw.content[0].text);
            }
            else if (raw && typeof raw === 'object' && raw.success !== undefined) {
                result = raw;
            }
            if (!result || !result.success || !result.images || result.images.length === 0) {
                await interaction.followUp({ content: `⚠️ ${result?.error || 'アドバイザリデータの取得に失敗しました。'}` });
                return;
            }
            const attachments = [];
            for (const imgData of result.images) {
                if (imgData.image_base64) {
                    const buf = Buffer.from(imgData.image_base64, 'base64');
                    attachments.push(new discord_js_1.AttachmentBuilder(buf, {
                        name: imgData.filename || 'advisory.png'
                    }));
                }
            }
            if (attachments.length === 0) {
                await interaction.followUp({ content: '⚠️ 生成された画像データの読み込みに失敗しました。' });
                return;
            }
            const first = result.images[0];
            const curSeason = first.season || 52;
            const components = [];
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
                    const checkedSet = new Set();
                    const checklistText = renderChecklistText(first.checklist_items, checkedSet);
                    msg += '\n\n' + checklistText;
                    const selectMenuRow = buildChecklistSelectMenu(first.checklist_items, checkedSet, customId);
                    components.push(selectMenuRow);
                }
            }
            else {
                const supportReqs = (result.support_combinations && result.support_combinations.length > 0)
                    ? formatStageSupportCombinations(result.support_combinations, result.asari_idols)
                    : formatRequiredSupportCards(result.images);
                let configListStr = result.images.map((img) => {
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
                    configListStr = result.images.slice(0, 3).map((img) => {
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
        }
        catch (e) {
            console.error('[advisory] Execution error:', e);
            await interaction.followUp({ content: `⚠️ エラーが発生しました: ${e.message}` });
        }
    }
};
