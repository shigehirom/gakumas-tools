"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.syncCommand = void 0;
const discord_js_1 = require("discord.js");
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
const fs = __importStar(require("fs"));
const match_history_updater_1 = require("../utils/match-history-updater");
exports.syncCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('sync')
        .setDescription('GoogleスプレッドシートとMongoDBのデータ（コンテスト対戦記録・インベントリ）を同期します')
        .addStringOption(option => option.setName('target')
        .setDescription('同期する対象 (デフォルト: コンテスト対戦記録)')
        .setRequired(false)
        .addChoices({ name: '🏆 コンテスト対戦記録 (Contest 双方向同期)', value: 'contest' }, { name: '📦 全インベントリ (Pアイドル + サポカ)', value: 'all' }, { name: '🃏 サポートカード (Support-Cards)', value: 'support' }, { name: '🌟 Pアイドル (P-Idols)', value: 'pidol' })),
    async execute(interaction) {
        await interaction.deferReply();
        const target = interaction.options.getString('target') || 'contest';
        // ── 1. コンテスト対戦記録の双方向同期 ──
        if (target === 'contest') {
            try {
                console.log('[sync] Starting bidirectional contest sync...');
                const result = await (0, match_history_updater_1.syncContestMatchesBidirectional)();
                if (!result.success) {
                    const embed = new discord_js_1.EmbedBuilder()
                        .setTitle('❌ コンテスト記録の同期に失敗しました')
                        .setDescription(`**エラー内容**:\n\`\`\`\n${(result.error || '不明なエラー').slice(0, 500)}\n\`\`\``)
                        .addFields({
                        name: '💡 対処法',
                        value: 'Google Sheets OAuth トークンが失効している可能性があります。\nSandbox ターミナルで `node packages/cli/scripts/reauth-sheets.mjs` を実行して再認証を行ってください。'
                    })
                        .setColor(0xEF4444)
                        .setTimestamp();
                    await interaction.followUp({ embeds: [embed] });
                    return;
                }
                const embed = new discord_js_1.EmbedBuilder()
                    .setTitle('✅ コンテスト記録の双方向同期が完了しました')
                    .setDescription(`Google スプレッドシート（Contest）と MongoDB の対戦履歴を相互に最新化しました。\n\`\`\`\n${(result.output || '同期完了').slice(0, 1000)}\n\`\`\``)
                    .setColor(0x10B981)
                    .setTimestamp();
                await interaction.followUp({ embeds: [embed] });
                return;
            }
            catch (err) {
                console.error('[sync] Contest sync error:', err);
                await interaction.followUp({ content: `❌ 同期中にエラーが発生しました: ${err.message}` });
                return;
            }
        }
        // ── 2. インベントリ (Pアイドル / サポカ) の同期 ──
        let scriptName = 'sync-all.mjs';
        if (target === 'support')
            scriptName = 'sync-support-cards.mjs';
        else if (target === 'pidol')
            scriptName = 'sync-p-idols.mjs';
        const scriptCandidates = [
            path_1.default.resolve(process.cwd(), 'scripts', scriptName),
            path_1.default.resolve(__dirname, '../scripts', scriptName),
            path_1.default.resolve(__dirname, '../../scripts', scriptName),
            path_1.default.resolve(__dirname, '../../../..', 'packages/cli/scripts', scriptName),
            path_1.default.resolve(__dirname, '../../..', 'cli/scripts', scriptName),
            path_1.default.resolve(__dirname, '../../../..', 'scripts', scriptName),
            `/app/packages/cli/scripts/${scriptName}`,
            `/app/scripts/${scriptName}`,
        ];
        const scriptPath = scriptCandidates.find(p => fs.existsSync(p));
        if (!scriptPath) {
            await interaction.followUp({ content: `❌ 同期スクリプトが見つかりませんでした: ${scriptName}` });
            return;
        }
        const runCwd = path_1.default.dirname(path_1.default.dirname(scriptPath));
        const proc = (0, child_process_1.spawn)('node', [scriptPath], {
            cwd: runCwd,
            env: { ...process.env }
        });
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', data => { stdout += data.toString(); });
        proc.stderr.on('data', data => { stderr += data.toString(); });
        proc.on('close', async (code) => {
            if (code !== 0) {
                const embed = new discord_js_1.EmbedBuilder()
                    .setTitle('❌ インベントリ同期に失敗しました')
                    .setDescription(`\`\`\`\n${(stderr || stdout).slice(0, 1000)}\n\`\`\``)
                    .setColor(0xEF4444)
                    .setTimestamp();
                await interaction.followUp({ embeds: [embed] });
            }
            else {
                const embed = new discord_js_1.EmbedBuilder()
                    .setTitle('✅ インベントリ同期が完了しました')
                    .setDescription(`スプレッドシートから MongoDB への同期が正常に完了しました。\n\`\`\`\n${stdout.slice(0, 1000)}\n\`\`\``)
                    .setColor(0x10B981)
                    .setTimestamp();
                await interaction.followUp({ embeds: [embed] });
            }
        });
    }
};
