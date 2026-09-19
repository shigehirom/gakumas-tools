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
Object.defineProperty(exports, "__esModule", { value: true });
exports.calcCommand = void 0;
const discord_js_1 = require("discord.js");
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const os = __importStar(require("os"));
function resolvePythonScript(scriptName) {
    const candidatePaths = [
        path.resolve(__dirname, `../../../../gakumas-agent-bot/${scriptName}`),
        path.resolve(__dirname, `../../../gakumas-agent-bot/${scriptName}`),
        `/app/gakumas-agent-bot/${scriptName}`,
        `/root/gakumas-workspace/gakumas-agent-bot/${scriptName}`,
        `/root/gakumas-workspace/gakumas-tools/gakumas-agent-bot/${scriptName}`,
    ];
    return candidatePaths.find(p => fs.existsSync(p)) || candidatePaths[0];
}
async function runHifCalculator(vo, da, vi, star, round1Score) {
    const scriptPath = resolvePythonScript('hif_calculator.py');
    if (!fs.existsSync(scriptPath)) {
        return { result: null, imagePath: null, error: `hif_calculator.py が見つかりませんでした: ${scriptPath}` };
    }
    const tmpDir = os.tmpdir();
    const outputPath = path.join(tmpDir, `hif_calc_${Date.now()}_${Math.random().toString(36).slice(2)}.png`);
    const args = [
        scriptPath,
        '--vo', vo.toString(),
        '--da', da.toString(),
        '--vi', vi.toString(),
        '--star', star.toString(),
        '--round1-score', round1Score.toString(),
        '--out-image', outputPath,
        '--json'
    ];
    return new Promise((resolve) => {
        const child = (0, child_process_1.spawn)('python3', args);
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', d => { stdout += d.toString(); });
        child.stderr.on('data', d => { stderr += d.toString(); });
        child.on('close', (code) => {
            if (code === 0) {
                try {
                    const parsed = JSON.parse(stdout);
                    const finalImagePath = fs.existsSync(outputPath) ? outputPath : null;
                    resolve({ result: parsed, imagePath: finalImagePath });
                }
                catch (err) {
                    resolve({ result: null, imagePath: null, error: `JSONパース失敗: ${err.message}` });
                }
            }
            else {
                resolve({ result: null, imagePath: null, error: `計算スクリプト実行エラー (code ${code}): ${stderr}` });
            }
        });
        child.on('error', (err) => {
            resolve({ result: null, imagePath: null, error: `スクリプト起動失敗: ${err.message}` });
        });
    });
}
exports.calcCommand = {
    data: new discord_js_1.SlashCommandBuilder()
        .setName('calc')
        .setDescription('H.I.F編のプロデュース評価点およびラウンド2目標スコアを計算します')
        .addIntegerOption(opt => opt.setName('vo')
        .setDescription('ボーカル パラメータ (0〜3200)')
        .setRequired(true)
        .setMinValue(0)
        .setMaxValue(3200))
        .addIntegerOption(opt => opt.setName('da')
        .setDescription('ダンス パラメータ (0〜3200)')
        .setRequired(true)
        .setMinValue(0)
        .setMaxValue(3200))
        .addIntegerOption(opt => opt.setName('vi')
        .setDescription('ビジュアル パラメータ (0〜3200)')
        .setRequired(true)
        .setMinValue(0)
        .setMaxValue(3200))
        .addIntegerOption(opt => opt.setName('star')
        .setDescription('ラウンド2前のスター数 (★)')
        .setRequired(true)
        .setMinValue(0)
        .setMaxValue(1500))
        .addIntegerOption(opt => opt.setName('round1-score')
        .setDescription('ラウンド1スコア (順位発表画面の×1.2ボーナス込み表示値)')
        .setRequired(true)
        .setMinValue(0)
        .setMaxValue(2000000)),
    async execute(interaction) {
        await interaction.deferReply();
        const vo = interaction.options.getInteger('vo', true);
        const da = interaction.options.getInteger('da', true);
        const vi = interaction.options.getInteger('vi', true);
        const star = interaction.options.getInteger('star', true);
        const round1Score = interaction.options.getInteger('round1-score') ?? interaction.options.getInteger('round1_score', true);
        const { result, imagePath, error } = await runHifCalculator(vo, da, vi, star, round1Score);
        if (error || !result) {
            await interaction.editReply({
                content: `❌ **評価値計算エラー**: ${error || '不明なエラーが発生しました'}`
            });
            return;
        }
        const embed = new discord_js_1.EmbedBuilder()
            .setColor(0xF59E0B)
            .setTitle('🏆 H.I.F プロデュース評価')
            .setDescription(`現在の評価点: **${result.current_rating.toLocaleString()}** (${result.current_rank})\n` +
            `入力: \`Vo: ${vo} / Da: ${da} / Vi: ${vi} / ★: ${star} / R1: ${round1Score.toLocaleString()}\``)
            .setFooter({ text: 'Gakumas Tools H.I.F Calculator' })
            .setTimestamp();
        // 画像がある場合は添付
        if (imagePath) {
            const filename = 'hif_produce_rating.png';
            const attachment = new discord_js_1.AttachmentBuilder(imagePath, { name: filename });
            embed.setImage(`attachment://${filename}`);
            await interaction.editReply({
                embeds: [embed],
                files: [attachment]
            });
            try {
                fs.unlinkSync(imagePath);
            }
            catch { }
        }
        else {
            // 画像が生成できなかった場合のフォールバック（テキストテーブル）
            let table = '```\n';
            table += 'ランク (目標評価)  必要R2スコア\n';
            table += '--------------------------------\n';
            for (const row of result.target_rows) {
                const sStr = row.score === 0 ? '到達済み' : (row.score == null ? '∞ (到達不可)' : row.score.toLocaleString());
                const rStr = `${row.rank} (${row.target_rating.toLocaleString()})`.padEnd(16);
                table += `${rStr} ${sStr}\n`;
            }
            table += '```';
            embed.addFields({ name: '目標ランク別 必要ラウンド2スコア', value: table });
            await interaction.editReply({ embeds: [embed] });
        }
    }
};
