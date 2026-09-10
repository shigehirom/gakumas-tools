/**
 * 学園アイドルマスター サポートボーナス計算ユーティリティ
 * - サポートカードのレベルに応じて増加する乗算補正
 * - Lv10: 0.01%, Lv20: 0.01%, Lv30: 0.02%, Lv40: 0.02%, Lv50: 0.02%, Lv60: 0.02%
 * - Lv60最大: 0.10% (= 0.0010)
 */

export function getBonusForLevel(lv) {
  const level = parseInt(lv || '1', 10);
  if (level >= 60) return 0.10;
  if (level >= 50) return 0.08;
  if (level >= 40) return 0.06;
  if (level >= 30) return 0.04;
  if (level >= 20) return 0.02;
  if (level >= 10) return 0.01;
  return 0.00;
}

export function getMaxLvForUncap(rarity, uncap) {
  const uncapNum = parseInt(uncap || '0', 10);
  if (rarity === 'SSR') return 40 + uncapNum * 5;
  if (rarity === 'SR') return 30 + uncapNum * 5;
  if (rarity === 'R') return 20 + uncapNum * 5;
  return 60;
}

/**
 * MongoDB の owned_support_cards コレクションから現在の最新サポートボーナス（小数値: 例 0.1454）を算出
 * @param {import('mongodb').Db} db 
 * @param {number} fallback 
 * @returns {Promise<number>} サポートボーナス（小数値: 例 0.1454）
 */
export async function getLatestSupportBonus(db, fallback = 0.04) {
  if (!db) return fallback;
  try {
    const cards = await db.collection('owned_support_cards').find({}).toArray();
    if (!cards || cards.length === 0) return fallback;

    let totalBonusPct = 0;
    for (const card of cards) {
      totalBonusPct += getBonusForLevel(card.lv);
    }
    // 小数点第4位に正規化 (例: 14.54% -> 0.1454)
    return parseFloat((totalBonusPct / 100).toFixed(4));
  } catch (err) {
    console.warn(`[SupportBonus] Failed to calculate support bonus from DB: ${err.message}. Using fallback: ${fallback}`);
    return fallback;
  }
}
