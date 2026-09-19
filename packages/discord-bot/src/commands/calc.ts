import {
    SlashCommandBuilder,
    ChatInputCommandInteraction,
    EmbedBuilder,
    AttachmentBuilder
} from 'discord.js';
import { spawn } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

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

interface HifCalcRow {
    rank: string;
    target_rating: number;
    score: number | null;
}

interface HifCalcResult {
    inputs: {
        vo: number;
        da: number;
        vi: number;
        star: number;
        round1_score: number;
    };
    current_rating: number;
    current_rank: string;
    target_rows: HifCalcRow[];
    image_path: string | null;
}

async function runHifCalculator(
    vo: number,
    da: number,
    vi: number,
    star: number,
    round1Score: number
): Promise<{ result: HifCalcResult | null; imagePath: string | null; error?: string }> {
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
        const child = spawn('python3', args);
        let stdout = '';
        let stderr = '';

        child.stdout.on('data', d => { stdout += d.toString(); });
        child.stderr.on('data', d => { stderr += d.toString(); });

        child.on('close', (code) => {
            if (code === 0) {
                try {
                    const parsed: HifCalcResult = JSON.parse(stdout);
                    const finalImagePath = fs.existsSync(outputPath) ? outputPath : null;
                    resolve({ result: parsed, imagePath: finalImagePath });
                } catch (err: any) {
                    resolve({ result: null, imagePath: null, error: `JSONパース失敗: ${err.message}` });
                }
            } else {
                resolve({ result: null, imagePath: null, error: `計算スクリプト実行エラー (code ${code}): ${stderr}` });
            }
        });

        child.on('error', (err) => {
            resolve({ result: null, imagePath: null, error: `スクリプト起動失敗: ${err.message}` });
        });
    });
}

export const calcCommand = {
    data: new SlashCommandBuilder()
        .setName('calc')
        .setDescription('H.I.F編のプロデュース評価点およびラウンド2目標スコアを計算します')
        .addIntegerOption(opt =>
            opt.setName('vo')
                .setDescription('ボーカル パラメータ (0〜3200)')
                .setRequired(true)
                .setMinValue(0)
                .setMaxValue(3200)
        )
        .addIntegerOption(opt =>
            opt.setName('da')
                .setDescription('ダンス パラメータ (0〜3200)')
                .setRequired(true)
                .setMinValue(0)
                .setMaxValue(3200)
        )
        .addIntegerOption(opt =>
            opt.setName('vi')
                .setDescription('ビジュアル パラメータ (0〜3200)')
                .setRequired(true)
                .setMinValue(0)
                .setMaxValue(3200)
        )
        .addIntegerOption(opt =>
            opt.setName('star')
                .setDescription('ラウンド2前のスター数 (★)')
                .setRequired(true)
                .setMinValue(0)
                .setMaxValue(1500)
        )
        .addIntegerOption(opt =>
            opt.setName('round1-score')
                .setDescription('ラウンド1スコア (順位発表画面の×1.2ボーナス込み表示値)')
                .setRequired(true)
                .setMinValue(0)
                .setMaxValue(2000000)
        ),

    async execute(interaction: ChatInputCommandInteraction) {
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

        const embed = new EmbedBuilder()
            .setColor(0xF59E0B)
            .setTitle('🏆 H.I.F プロデュース評価')
            .setDescription(
                `現在の評価点: **${result.current_rating.toLocaleString()}** (${result.current_rank})\n` +
                `入力: \`Vo: ${vo} / Da: ${da} / Vi: ${vi} / ★: ${star} / R1: ${round1Score.toLocaleString()}\``
            )
            .setFooter({ text: 'Gakumas Tools H.I.F Calculator' })
            .setTimestamp();

        // 画像がある場合は添付
        if (imagePath) {
            const filename = 'hif_produce_rating.png';
            const attachment = new AttachmentBuilder(imagePath, { name: filename });
            embed.setImage(`attachment://${filename}`);

            await interaction.editReply({
                embeds: [embed],
                files: [attachment]
            });

            try { fs.unlinkSync(imagePath); } catch {}
        } else {
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

