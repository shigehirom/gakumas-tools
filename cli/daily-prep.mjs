import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

// .env.local から設定を読み込む簡易関数
function loadEnv(filePath) {
    if (!fs.existsSync(filePath)) return {};
    const content = fs.readFileSync(filePath, 'utf-8');
    const env = {};
    content.split('\n').forEach(line => {
        const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*)?\s*$/);
        if (match) {
            let value = match[2] || '';
            if (value.startsWith('"') && value.endsWith('"')) value = value.slice(1, -1);
            env[match[1]] = value;
        }
    });
    return env;
}

const env = loadEnv('gakumas-tools/.env.local');
// process.env も更新して、execSync で実行される子プロセスが環境変数を継承できる様にする
for (const key in env) {
    process.env[key] = env[key];
}

const SUPPORT_BONUS = env.SUPPORT_BONUS || '0';
const CONTEST_RUNS = env.DAILY_CONTEST_RUNS || '100';
const REHEARSAL_RUNS = env.DAILY_REHEARSAL_RUNS || '2000';

console.error(`設定読み込み完了: SUPPORT_BONUS=${SUPPORT_BONUS}, CONTEST_RUNS=${CONTEST_RUNS}, REHEARSAL_RUNS=${REHEARSAL_RUNS}`);

// 最新シーズンの特定
const stagesPath = 'packages/gakumas-data/json/stages.json';
const stages = JSON.parse(fs.readFileSync(stagesPath, 'utf8'));
const latestSeason = Math.max(...stages.filter(s => s.type === 'contest').map(s => s.season));
console.error(`対象シーズン: ${latestSeason}`);

const now = new Date();
const dateStr = `${String(now.getFullYear()).slice(-2)}/${String(now.getMonth() + 1).padStart(2, '0')}/${String(now.getDate()).padStart(2, '0')}`;

// 各ステージ (1, 2, 3) について処理
for (const stageNum of [1, 2, 3]) {
    const stageId = `${latestSeason}-${stageNum}`;
    console.error(`\n========== ステージ ${stageId} の処理開始 ==========`);

    // 1. 全アイドルのシミュレーション実行 (JSON出力)
    console.error(`ステップ1: 全アイドルのシミュレーション実行中...`);
    const contestCmd = `yarn cli contest ${stageId} ${CONTEST_RUNS} all --json --supportBonus ${SUPPORT_BONUS}`;
    const contestOutput = execSync(contestCmd, { encoding: 'utf-8' });
    const results = JSON.parse(contestOutput);

    // 2. 上位3名のアイドルを特定 (平均スコア順)
    // 結果が配列でない場合は単体オブジェクトとして扱う
    const resultArray = Array.isArray(results) ? results : [results];
    const topIdols = resultArray
        .filter(r => r.metadata && r.metadata.idolName && r.best && r.best.score !== undefined)
        .sort((a, b) => b.best.score - a.best.score)
        .slice(0, 3);

    if (topIdols.length === 0) {
        console.error(`警告: 上位3名のアイドルを特定できませんでした (0名のみ)。`);
        continue;
    }

    const topIdolNames = topIdols.map(r => r.metadata.idolName);
    console.error(`上位3名: ${topIdolNames.join(', ')}`);

    // 3. 上位3名のロードアウトを保存
    // 命名規則: YY/MM/DD_42-1_saki (半角)
    const loadoutNames = [];
    for (const idol of topIdolNames) {
        const loadoutName = `${dateStr}_${stageId}_${idol}`;
        loadoutNames.push(loadoutName);
        console.error(`ステップ2: ロードアウト保存中 (${loadoutName})...`);
        const saveCmd = `yarn cli contest ${stageId} ${CONTEST_RUNS} ${idol} --save 1 --name ${loadoutName} --supportBonus ${SUPPORT_BONUS}`;
        execSync(saveCmd, { stdio: 'inherit' });
    }

    // 4. リハーサル実行
    console.error(`ステップ3: リハーサル実行中...`);
    const rehearsalCmd = `yarn cli rehearsal ${REHEARSAL_RUNS} ${loadoutNames.join(' ')} --gdrive`;
    execSync(rehearsalCmd, { stdio: 'inherit' });
}

console.error(`\n全ステージの自動処理が完了しました。`);
