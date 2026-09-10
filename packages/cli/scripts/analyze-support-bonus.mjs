import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

export function getBonusForLevel(lv) {
  if (lv >= 60) return 0.10;
  if (lv >= 50) return 0.08;
  if (lv >= 40) return 0.06;
  if (lv >= 30) return 0.04;
  if (lv >= 20) return 0.02;
  if (lv >= 10) return 0.01;
  return 0.00;
}

export function getMaxLv(rarity, uncap) {
  if (rarity === 'SSR') return 40 + uncap * 5;
  if (rarity === 'SR') return 30 + uncap * 5;
  if (rarity === 'R') return 20 + uncap * 5;
  return 60;
}

async function main() {
  const auth = await getAuthClient();
  const sheets = google.sheets({ version: 'v4', auth });
  const SHEET_ID = process.env.SYNC_SHEET_ID;

  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: SHEET_ID,
    range: 'Support-Cards!A:Z'
  });
  const rows = res.data.values;
  if (!rows || rows.length === 0) {
    console.error('No data found in Support-Cards sheet.');
    return;
  }

  const headers = rows[0].map(h => h.trim());
  const idxMap = {};
  headers.forEach((h, i) => idxMap[h] = i);

  let totalBonus = 0;
  let ownedCount = 0;
  let currentUncapMaxBonus = 0;
  let theoreticalMaxBonus = 0;

  const rarityStats = {
    SSR: { count: 0, bonus: 0, maxPotential: 0, lvs: {} },
    SR:  { count: 0, bonus: 0, maxPotential: 0, lvs: {} },
    R:   { count: 0, bonus: 0, maxPotential: 0, lvs: {} }
  };

  const upgradeOpportunities = [];

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row) continue;
    const name = row[idxMap['card_name']] || '';
    const rarity = row[idxMap['rarity']] || 'SSR';
    const isOwned = (row[idxMap['is_owned']] || '').trim().toLowerCase() === 'true';
    const uncap = parseInt(row[idxMap['uncap']] || '0', 10);
    const lv = parseInt(row[idxMap['lv']] || '1', 10);

    const maxLv = getMaxLv(rarity, uncap);
    const curBonus = getBonusForLevel(lv);
    const maxBonus = getBonusForLevel(maxLv);
    const fullUncapBonus = (rarity === 'SSR' ? 0.10 : rarity === 'SR' ? 0.08 : 0.06);

    theoreticalMaxBonus += fullUncapBonus;

    if (isOwned) {
      ownedCount++;
      totalBonus += curBonus;
      currentUncapMaxBonus += maxBonus;

      if (!rarityStats[rarity]) {
        rarityStats[rarity] = { count: 0, bonus: 0, maxPotential: 0, lvs: {} };
      }
      rarityStats[rarity].count++;
      rarityStats[rarity].bonus += curBonus;
      rarityStats[rarity].maxPotential += maxBonus;
      rarityStats[rarity].lvs[lv] = (rarityStats[rarity].lvs[lv] || 0) + 1;

      if (lv < maxLv && maxBonus > curBonus) {
        upgradeOpportunities.push({
          name,
          rarity,
          lv,
          uncap,
          maxLv,
          gain: Number((maxBonus - curBonus).toFixed(4))
        });
      }
    }
  }

  console.log('\n================================================================');
  console.log('            📘 学マス サポートボーナス 分析レポート');
  console.log('================================================================');
  console.log(` 所持サポートカード総数   : ${ownedCount} / ${rows.length - 1} 枚`);
  console.log(` 現在の合計サポートボーナス : ${totalBonus.toFixed(4)}%  (乗算補正: ×${(1 + totalBonus / 100).toFixed(6)})`);
  console.log(` 現凸での最大ポテンシャル : ${currentUncapMaxBonus.toFixed(4)}%  (伸び代: +${(currentUncapMaxBonus - totalBonus).toFixed(4)}%)`);
  console.log(` 全カード完凸理論上限     : ${theoreticalMaxBonus.toFixed(4)}%`);
  console.log('----------------------------------------------------------------');
  console.log(' [レアリティ別内訳]');
  for (const [r, s] of Object.entries(rarityStats)) {
    console.log(`  - ${r.padEnd(3)}: ${String(s.count).padStart(3)} 枚 | ボーナス: ${s.bonus.toFixed(4)}% | 現上限時: ${s.maxPotential.toFixed(4)}%`);
    console.log(`        Lv分布: ${JSON.stringify(s.lvs)}`);
  }
  console.log('----------------------------------------------------------------');
  console.log(` [現在の凸数でレベル上げによりボーナスが増加するカード: ${upgradeOpportunities.length} 枚]`);
  upgradeOpportunities.sort((a, b) => b.gain - a.gain || a.lv - b.lv);
  for (const op of upgradeOpportunities) {
    console.log(`  ・${op.name} [${op.rarity}] (現在Lv ${op.lv} / 凸${op.uncap} ➔ 上限Lv ${op.maxLv}) : +${op.gain.toFixed(2)}%`);
  }
  console.log('================================================================\n');
}

main().catch(console.error);
