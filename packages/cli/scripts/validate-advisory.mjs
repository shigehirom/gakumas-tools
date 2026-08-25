import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const jsonDir = path.resolve(__dirname, '../../gakumas-data/json');

// マスタデータの読み込み
const idols = JSON.parse(fs.readFileSync(path.join(jsonDir, 'idols.json'), 'utf8'));
const pIdols = JSON.parse(fs.readFileSync(path.join(jsonDir, 'p_idols.json'), 'utf8'));
const pItems = JSON.parse(fs.readFileSync(path.join(jsonDir, 'p_items.json'), 'utf8'));
const skillCards = JSON.parse(fs.readFileSync(path.join(jsonDir, 'skill_cards.json'), 'utf8'));

// 辞書・ルックアップセットの構築
const idolKeyMap = {
  saki: '花海 咲季',
  temari: '月村 手毬',
  kotone: '藤田 ことね',
  tsubame: '雨夜 燕',
  misuzu: '十王 星南',
  sena: '有村 麻央', // または十王星南
  sumika: '紫雲 清夏',
  rinami: '姫崎 莉波',
  lilja: '葛城 リーリヤ',
  china: '倉本 千奈',
  hiro: '篠澤 広',
  ume: '花海 佑芽',
  aoi: '秦谷 美鈴',
};
idols.forEach(i => {
  if (i.name) {
    const romaji = i.name.toLowerCase();
    idolKeyMap[i.id] = i.name;
  }
});

// Levenshtein 距離計算（あいまいサジェスト用）
function levenshtein(a, b) {
  const matrix = [];
  for (let i = 0; i <= b.length; i++) matrix[i] = [i];
  for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1) === a.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }
  return matrix[b.length][a.length];
}

function findClosest(target, candidates) {
  let closest = '';
  let minDistance = Infinity;
  for (const c of candidates) {
    const d = levenshtein(target, c);
    if (d < minDistance) {
      minDistance = d;
      closest = c;
    }
  }
  return minDistance <= 3 ? closest : null;
}

const allPIdolTitles = [...new Set(pIdols.map(p => p.title))];
const allPItemNames = [...new Set(pItems.map(p => p.name))];
const allSkillCardNames = [...new Set(skillCards.map(s => s.name))];

export function validateAdvisoryDsl(filePath) {
  if (!fs.existsSync(filePath)) {
    return { valid: false, errors: [`ファイルが存在しません: ${filePath}`] };
  }

  const content = fs.readFileSync(filePath, 'utf8');
  const lines = content.split(/\r?\n/);

  const errors = [];
  const warnings = [];

  let currentSection = '';
  let currentStage = 0;

  for (let i = 0; i < lines.length; i++) {
    const lineNum = i + 1;
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('# Stage:')) {
      if (trimmed.startsWith('# Stage:')) {
        currentStage = parseInt(trimmed.replace('# Stage:', '').trim(), 10);
      }
      continue;
    }

    if (trimmed.startsWith('## p_idol:')) {
      currentSection = 'p_idol';
      continue;
    } else if (trimmed.startsWith('## p_item:')) {
      currentSection = 'p_item';
      continue;
    } else if (trimmed.startsWith('## skill_card:')) {
      currentSection = 'skill_card';
      continue;
    }

    // ── 1. p_idol セクションの検証 ──
    if (currentSection === 'p_idol') {
      // sub: の場合
      const subMatch = trimmed.match(/^-\s*sub:\s*【([^】]+)】/);
      if (subMatch) {
        const title = subMatch[1].trim();
        if (!allPIdolTitles.includes(title)) {
          const sug = findClosest(title, allPIdolTitles);
          errors.push({
            line: lineNum,
            type: 'UNKNOWN_SUB_PIDOL',
            message: `サブPアイドルの二つ名 【${title}】 がデータベースに存在しません。` + (sug ? ` (もしかして: 【${sug}】 ?)` : '')
          });
        }
        continue;
      }

      // メインPアイドルの場合 (- idolKey: 【title】)
      const idolMatch = trimmed.match(/^-\s*([a-zA-Z0-9_]+):\s*【([^】]+)】/);
      if (idolMatch) {
        const idolKey = idolMatch[1].trim().toLowerCase();
        const title = idolMatch[2].trim();

        if (!allPIdolTitles.includes(title)) {
          const sug = findClosest(title, allPIdolTitles);
          errors.push({
            line: lineNum,
            type: 'UNKNOWN_PIDOL_TITLE',
            message: `Pアイドルの二つ名 【${title}】 がデータベースに存在しません。` + (sug ? ` (もしかして: 【${sug}】 ?)` : '')
          });
        }
        continue;
      }
    }

    // ── 2. p_item セクションの検証 ──
    if (currentSection === 'p_item') {
      if (trimmed.startsWith('- common:') || trimmed.match(/^-\s*([a-zA-Z0-9_]+):\s*【([^】]+)】/)) {
        // ヘッダー行
        const idolMatch = trimmed.match(/^-\s*([a-zA-Z0-9_]+):\s*【([^】]+)】/);
        if (idolMatch) {
          const title = idolMatch[2].trim();
          if (!allPIdolTitles.includes(title)) {
            const sug = findClosest(title, allPIdolTitles);
            errors.push({
              line: lineNum,
              type: 'UNKNOWN_PIDOL_TITLE',
              message: `Pアイテム指定のPアイドル 【${title}】 がデータベースに存在しません。` + (sug ? ` (もしかして: 【${sug}】 ?)` : '')
            });
          }
        }
        continue;
      }

      // Pアイテム名行 (- アイテム名)
      const itemMatch = trimmed.match(/^-\s*(.+)$/);
      if (itemMatch) {
        const itemName = itemMatch[1].trim();
        if (itemName && !allPItemNames.includes(itemName)) {
          const sug = findClosest(itemName, allPItemNames);
          errors.push({
            line: lineNum,
            type: 'UNKNOWN_P_ITEM',
            message: `Pアイテム名 '${itemName}' がデータベースに存在しません。` + (sug ? ` (もしかして: '${sug}' ?)` : '')
          });
        }
      }
      continue;
    }

    // ── 3. skill_card セクションの検証 ──
    if (currentSection === 'skill_card') {
      if (trimmed.startsWith('- common:') || trimmed.startsWith('- customize:')) {
        continue;
      }

      // Pアイドルヘッダー
      const idolMatch = trimmed.match(/^-\s*([a-zA-Z0-9_]+):\s*【([^】]+)】/);
      if (idolMatch) {
        const title = idolMatch[2].trim();
        if (!allPIdolTitles.includes(title)) {
          const sug = findClosest(title, allPIdolTitles);
          errors.push({
            line: lineNum,
            type: 'UNKNOWN_PIDOL_TITLE',
            message: `スキルカード指定のPアイドル 【${title}】 がデータベースに存在しません。` + (sug ? ` (もしかして: 【${sug}】 ?)` : '')
          });
        }
        continue;
      }

      // 差分置換記法 (/- /元カード/新カード/)
      const replaceMatch = trimmed.match(/^-\s*\/([^\/]+)\/([^\/]+)\//);
      if (replaceMatch) {
        const fromCard = replaceMatch[1].trim();
        const toCard = replaceMatch[2].trim();

        if (!allSkillCardNames.includes(fromCard)) {
          const sug = findClosest(fromCard, allSkillCardNames);
          errors.push({
            line: lineNum,
            type: 'UNKNOWN_SKILL_CARD',
            message: `置換元スキルカード '${fromCard}' がデータベースに存在しません。` + (sug ? ` (もしかして: '${sug}' ?)` : '')
          });
        }
        if (!allSkillCardNames.includes(toCard)) {
          const sug = findClosest(toCard, allSkillCardNames);
          errors.push({
            line: lineNum,
            type: 'UNKNOWN_SKILL_CARD',
            message: `置換先スキルカード '${toCard}' がデータベースに存在しません。` + (sug ? ` (もしかして: '${sug}' ?)` : '')
          });
        }
        continue;
      }

      // 通常のスキルカード名行 (- カード名)
      const cardMatch = trimmed.match(/^-\s*(.+)$/);
      if (cardMatch) {
        const cardName = cardMatch[1].trim();
        if (cardName && !cardName.startsWith('customize:') && !allSkillCardNames.includes(cardName)) {
          const sug = findClosest(cardName, allSkillCardNames);
          errors.push({
            line: lineNum,
            type: 'UNKNOWN_SKILL_CARD',
            message: `スキルカード名 '${cardName}' がデータベースに存在しません。` + (sug ? ` (もしかして: '${sug}' ?)` : '')
          });
        }
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings
  };
}

// CLI 直接実行時
if (process.argv[1] && process.argv[1].endsWith('validate-advisory.mjs')) {
  const targetFile = process.argv[2] || path.resolve(__dirname, '../../shared/agent-instructions/fried_aji3_advisory_51.md');
  console.log(`🔍 Validating Advisory DSL: ${targetFile}\n`);
  const res = validateAdvisoryDsl(targetFile);

  if (res.valid) {
    console.log('✅ すべてのPアイドル名・楽曲二つ名・Pアイテム名・スキルカード名がデータベースと完全一致しました！');
  } else {
    console.log(`⚠️  ${res.errors.length} 件の不一致・エラーを検出しました:\n`);
    res.errors.forEach(err => {
      console.log(`  [Line ${err.line}] ❌ ${err.message}`);
    });
    process.exit(1);
  }
}
