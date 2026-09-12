"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.advisoryCommand = void 0;
const discord_js_1 = require("discord.js");
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
const fs_1 = __importDefault(require("fs"));
const config_1 = require("../config");
function resolvePythonScript(scriptName) {
    const candidatePaths = [
        path_1.default.resolve(__dirname, `../../../../gakumas-agent-bot/${scriptName}`),
        path_1.default.resolve(__dirname, `../../../gakumas-agent-bot/${scriptName}`),
        `/app/gakumas-agent-bot/${scriptName}`,
        `/root/gakumas-workspace/gakumas-agent-bot/${scriptName}`,
        `/root/gakumas-workspace/gakumas-tools/gakumas-agent-bot/${scriptName}`,
    ];
    return candidatePaths.find(p => fs_1.default.existsSync(p)) || candidatePaths[0];
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
                cardMap.set(it.card_label, new Set());
            }
            cardMap.get(it.card_label).add(`Pアイテム: ${it.item_name}`);
        }
        for (const sc of (img.skill_cards_details || [])) {
            if (!sc.card_label)
                continue;
            if (!cardMap.has(sc.card_label)) {
                cardMap.set(sc.card_label, new Set());
            }
            cardMap.get(sc.card_label).add(`スキル: ${sc.card_name}`);
        }
    }
    if (cardMap.size === 0)
        return '';
    const lines = [];
    for (const [label, sources] of cardMap.entries()) {
        const sourceStr = Array.from(sources).join(' / ');
        lines.push(`・\`${label}\` （${sourceStr}）`);
    }
    return lines.join('\n');
}
exports.advisoryCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('advisory')
        .setDescription('あじふらい氏推奨のPアイテム・スキルカード構成画像（Pixel 10 Pro Fold最適化）を出力します')
        .addIntegerOption(option => option.setName('stage')
        .setDescription('ステージ番号 (1, 2, 3)')
        .setRequired(true)
        .addChoices({ name: 'Stage 1 (センス / Vo特化等)', value: 1 }, { name: 'Stage 2 (ロジック / Vi特化等)', value: 2 }, { name: 'Stage 3 (アノマリー / Vo特化等)', value: 3 }))
        .addStringOption(option => option.setName('idol')
        .setDescription('アイドル名または衣装名 (省略時は所持おすすめPアイドルを一括出力)')
        .setRequired(false)
        .setAutocomplete(true))
        .addIntegerOption(option => option.setName('season')
        .setDescription('シーズン番号 (省略時は最新シーズン)')
        .setRequired(false))
        .addIntegerOption(option => option.setName('columns')
        .setDescription('表示列数 (1: 縦型スリム[デフォルト], 2: 2列ワイド)')
        .setRequired(false)
        .addChoices({ name: '1列 (縦型スリム・スマホ最適 [デフォルト])', value: 1 }, { name: '2列 (2列グリッド・ワイド表示)', value: 2 })),
    async autocomplete(interaction) {
        const focusedOption = interaction.options.getFocused(true);
        const focusedValue = (focusedOption.value || '').toLowerCase();
        const stage = interaction.options.getInteger('stage') || 1;
        const season = interaction.options.getInteger('season');
        const scriptPath = resolvePythonScript('cli_get_stage_idols.py');
        if (!fs_1.default.existsSync(scriptPath)) {
            await interaction.respond([]);
            return;
        }
        const args = [scriptPath, '--stage', stage.toString(), '--mongo-uri', config_1.config.mongoUri];
        if (season) {
            args.push('--season', season.toString());
        }
        try {
            const child = (0, child_process_1.spawn)('python3', args);
            let stdout = '';
            child.stdout.on('data', d => { stdout += d.toString(); });
            child.on('close', async (code) => {
                if (code !== 0 || !stdout.trim()) {
                    await interaction.respond([]);
                    return;
                }
                try {
                    const choices = JSON.parse(stdout);
                    const filtered = choices.filter(c => c.name.toLowerCase().includes(focusedValue) ||
                        c.value.toLowerCase().includes(focusedValue));
                    await interaction.respond(filtered.slice(0, 25));
                }
                catch {
                    await interaction.respond([]);
                }
            });
        }
        catch {
            await interaction.respond([]);
        }
    },
    async execute(interaction) {
        await interaction.deferReply();
        const stage = interaction.options.getInteger('stage', true);
        const idol = interaction.options.getString('idol');
        const season = interaction.options.getInteger('season');
        const columns = interaction.options.getInteger('columns') || 1;
        const scriptPath = resolvePythonScript('cli_advisory_image.py');
        const args = [
            scriptPath,
            '--stage', stage.toString(),
            '--mongo-uri', config_1.config.mongoUri,
            '--columns', columns.toString()
        ];
        if (idol) {
            args.push('--idol', idol);
        }
        if (season) {
            args.push('--season', season.toString());
        }
        try {
            const child = (0, child_process_1.spawn)('python3', args, {
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
                        if (parsed.error)
                            errMsg = parsed.error;
                    }
                    catch {
                        if (stderr)
                            errMsg += `\n\`${stderr.slice(0, 200)}\``;
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
                    const attachments = [];
                    const titles = [];
                    for (const imgData of result.images) {
                        if (fs_1.default.existsSync(imgData.image_path)) {
                            attachments.push(new discord_js_1.AttachmentBuilder(imgData.image_path, {
                                name: path_1.default.basename(imgData.image_path)
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
                    let msg = '';
                    if (result.mode === 'single') {
                        msg = `📋 **[推奨構成レポート]** シーズン${curSeason} Stage ${stage}：**${first.full_title}**\n` +
                            `あじふらい氏アドバイスに基づく推奨Pアイテムおよびスキルカードの構成画像を出力しました。`;
                        const supportReqs = formatRequiredSupportCards([first]);
                        if (supportReqs) {
                            msg += `\n\n💡 **推奨構成に必要なサポートカード一覧**:\n${supportReqs}`;
                        }
                    }
                    else {
                        msg = `📋 **[推奨構成レポート]** シーズン${curSeason} Stage ${stage}（所持おすすめPアイドル ${attachments.length}名）\n` +
                            `あじふらい氏推奨の所持Pアイドル構成画像を出力しました：\n` +
                            titles.map(t => `・**${t}**`).join('\n');
                        const supportReqs = formatRequiredSupportCards(result.images);
                        if (supportReqs) {
                            msg += `\n\n💡 **推奨構成に必要なサポートカード一覧 (Stage ${stage})**:\n${supportReqs}`;
                        }
                    }
                    await interaction.followUp({
                        content: msg,
                        files: attachments
                    });
                }
                catch (e) {
                    await interaction.followUp({ content: `⚠️ 結果の処理中にエラーが発生しました: ${e.message}` });
                }
            });
            child.on('error', async (err) => {
                await interaction.followUp({ content: `⚠️ Pythonスクリプトの起動に失敗しました: ${err.message}` });
            });
        }
        catch (e) {
            await interaction.followUp({ content: `⚠️ エラーが発生しました: ${e.message}` });
        }
    }
};
