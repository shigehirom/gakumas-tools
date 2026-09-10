import path from 'path';
import { MongoClient } from 'mongodb';
import { loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://192.168.100.4:27017';
const MONGODB_DB = process.env.MONGODB_DB || 'gakumas-tools';

function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    focus: 'vo',       // vo | da | vi | total | balanced
    idol: '',          // idol name or partial
    requiredCards: [], // card names
    includeOnlyStage: false,
    top: 3,
    verbose: false
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--focus' || arg === '-f') {
      options.focus = args[++i]?.toLowerCase() || 'vo';
    } else if (arg === '--idol' || arg === '-i') {
      options.idol = args[++i] || '';
    } else if (arg === '--cards' || arg === '-c') {
      const cardsStr = args[++i] || '';
      options.requiredCards = cardsStr.split(',').map(s => s.trim()).filter(Boolean);
    } else if (arg === '--stage-only') {
      options.includeOnlyStage = true;
    } else if (arg === '--top' || arg === '-n') {
      options.top = parseInt(args[++i], 10) || 3;
    } else if (arg === '--verbose' || arg === '-v') {
      options.verbose = true;
    } else if (arg === '--help' || arg === '-h') {
      console.log(`
Usage: node scripts/optimize-produce-deck.mjs [options]

Options:
  --focus, -f <vo|da|vi|total|balanced>  Target parameter focus (default: vo)
  --idol, -i <name>                     Filter by idol name (e.g. 咲季, 広, 清夏)
  --cards, -c <c1,c2...>                Required skill cards to bring
  --stage-only                          Only use memories that have matching stage memory
  --top, -n <number>                    Number of top deck builds to display (default: 3)
  --verbose, -v                         Show detailed ability breakdowns
      `);
      process.exit(0);
    }
  }
  return options;
}

// Calculate deck score based on focus mode
function calculateDeckScore(deck, focus) {
  let voBonus = 0, daBonus = 0, viBonus = 0;
  let initVo = 0, initDa = 0, initVi = 0, initCoin = 0;
  let extraTurns = 0;

  for (const m of deck) {
    const b = m.bonuses || {};
    voBonus += b.voBonus || 0;
    daBonus += b.daBonus || 0;
    viBonus += b.viBonus || 0;
    initVo += b.initVo || 0;
    initDa += b.initDa || 0;
    initVi += b.initVi || 0;
    initCoin += b.initCoin || 0;
    if (b.hifEffect && b.hifEffect.includes('使用数')) {
      extraTurns++;
    }
  }

  let primaryScore = 0;
  switch (focus) {
    case 'vo':
      // Heavily weigh Vo bonus, tie-break with other bonuses
      primaryScore = voBonus * 1000 + (daBonus + viBonus) * 10 + (initVo * 2 + initDa + initVi);
      break;
    case 'da':
      primaryScore = daBonus * 1000 + (voBonus + viBonus) * 10 + (initDa * 2 + initVo + initVi);
      break;
    case 'vi':
      primaryScore = viBonus * 1000 + (voBonus + daBonus) * 10 + (initVi * 2 + initVo + initDa);
      break;
    case 'balanced':
      // Maximize the lowest bonus and sum
      const minBonus = Math.min(voBonus, daBonus, viBonus);
      primaryScore = minBonus * 1000 + (voBonus + daBonus + viBonus) * 10;
      break;
    case 'total':
    default:
      primaryScore = (voBonus + daBonus + viBonus) * 100 + (initVo + initDa + initVi);
      break;
  }

  return {
    score: primaryScore,
    voBonus: parseFloat(voBonus.toFixed(1)),
    daBonus: parseFloat(daBonus.toFixed(1)),
    viBonus: parseFloat(viBonus.toFixed(1)),
    totalBonus: parseFloat((voBonus + daBonus + viBonus).toFixed(1)),
    initVo,
    initDa,
    initVi,
    initCoin,
    extraTurns
  };
}

async function main() {
  const options = parseArgs();
  console.log(`=== S4+ Produce Deck Optimizer ===`);
  console.log(`Target Focus: ${options.focus.toUpperCase()}`);
  if (options.idol) console.log(`Idol Filter: ${options.idol}`);
  if (options.requiredCards.length > 0) console.log(`Required Cards: ${options.requiredCards.join(', ')}`);

  const client = new MongoClient(MONGODB_URI);
  await client.connect();
  const db = client.db(MONGODB_DB);
  const produceMemCol = db.collection('produce_memories');

  const query = {};
  if (options.idol) {
    query.idolName = { $regex: options.idol };
  }
  if (options.includeOnlyStage) {
    query.hasStageMemory = true;
  }

  const allMemories = await produceMemCol.find(query).toArray();
  console.log(`Found ${allMemories.length} memories matching query.`);

  if (allMemories.length < 4) {
    console.error(`Not enough memories (${allMemories.length} found, minimum 4 required).`);
    await client.close();
    return;
  }

  // Check required cards existence
  if (options.requiredCards.length > 4) {
    console.error(`Cannot require more than 4 cards.`);
    await client.close();
    return;
  }

  // Filter memories if required cards specified
  for (const rc of options.requiredCards) {
    const hasCard = allMemories.some(m => m.skillCard && m.skillCard.name && m.skillCard.name.includes(rc));
    if (!hasCard) {
      console.warn(`[Warning] No memory found with required card: "${rc}"`);
    }
  }

  // Pre-score and prune memories to keep combination search fast
  // Calculate individual evaluation score for pruning
  allMemories.forEach(m => {
    const b = m.bonuses || {};
    let indScore = 0;
    if (options.focus === 'vo') indScore = (b.voBonus || 0) * 100 + (b.initVo || 0);
    else if (options.focus === 'da') indScore = (b.daBonus || 0) * 100 + (b.initDa || 0);
    else if (options.focus === 'vi') indScore = (b.viBonus || 0) * 100 + (b.initVi || 0);
    else indScore = (b.voBonus || 0) + (b.daBonus || 0) + (b.viBonus || 0);

    // Give bonus to required cards so they aren't pruned
    if (m.skillCard?.name && options.requiredCards.some(rc => m.skillCard.name.includes(rc))) {
      indScore += 100000;
    }
    m._indScore = indScore;
  });

  allMemories.sort((a, b) => b._indScore - a._indScore);

  // Group by skill card ID to avoid having duplicate cards in pool
  // Keep top memories for each card, plus memories with no cards
  const candidatePool = [];
  const cardGroup = new Map();

  for (const m of allMemories) {
    const cardId = m.skillCard?.id || 0;
    if (cardId === 0) {
      if (candidatePool.length < 50) candidatePool.push(m);
    } else {
      if (!cardGroup.has(cardId)) {
        cardGroup.set(cardId, []);
      }
      const list = cardGroup.get(cardId);
      if (list.length < 3) { // keep up to 3 best memories per card ID
        list.push(m);
        candidatePool.push(m);
      }
    }
    if (candidatePool.length >= 60) break;
  }

  console.log(`Evaluated candidates pool size: ${candidatePool.length} memories.`);

  // Combinations generator of size 4
  const combinations = [];
  const N = candidatePool.length;

  function findCombos(startIndex, current) {
    if (current.length === 4) {
      // Validate unique skill card IDs (excluding 0)
      const seenCards = new Set();
      let valid = true;
      for (const m of current) {
        const cid = m.skillCard?.id || 0;
        if (cid !== 0) {
          if (seenCards.has(cid)) {
            valid = false;
            break;
          }
          seenCards.add(cid);
        }
      }

      // Validate required cards
      if (valid && options.requiredCards.length > 0) {
        for (const rc of options.requiredCards) {
          const present = current.some(m => m.skillCard?.name && m.skillCard.name.includes(rc));
          if (!present) {
            valid = false;
            break;
          }
        }
      }

      if (valid) {
        const stats = calculateDeckScore(current, options.focus);
        combinations.push({
          deck: [...current],
          stats
        });
      }
      return;
    }

    for (let i = startIndex; i < N; i++) {
      current.push(candidatePool[i]);
      findCombos(i + 1, current);
      current.pop();
    }
  }

  findCombos(0, []);

  // Sort by calculated score descending
  combinations.sort((a, b) => b.stats.score - a.stats.score);

  console.log(`\n=== 🏆 Top ${Math.min(options.top, combinations.length)} Recommended Produce Decks ===\n`);

  for (let rank = 0; rank < Math.min(options.top, combinations.length); rank++) {
    const res = combinations[rank];
    const s = res.stats;
    console.log(`------------------------------------------------------------`);
    console.log(`【 第 ${rank + 1} 位 】 スコア: ${s.score.toFixed(0)}`);
    console.log(`📊 パラボ合計: Vo +${s.voBonus}% | Da +${s.daBonus}% | Vi +${s.viBonus}% (合計: +${s.totalBonus}%)`);
    console.log(`⚡ 初期値合計: Vo +${s.initVo} | Da +${s.initDa} | Vi +${s.initVi} | 初期P +${s.initCoin}pt`);
    if (s.extraTurns > 0) {
      console.log(`✨ HIF追加カード使用権: +${s.extraTurns} 回分所持`);
    }

    console.log(`\n🎴 構成メモリー (4枚):`);
    res.deck.forEach((m, idx) => {
      const b = m.bonuses || {};
      const cardName = m.skillCard?.name ? `[${m.skillCard.name}]` : '(カードなし)';
      const timing = m.skillCard?.timing === 'middle' ? '中間' : '開始';
      const custKeys = Object.keys(m.skillCard?.customization || {});
      const custStr = custKeys.length > 0 ? ` [改]` : '';
      const stageTag = m.hasStageMemory ? '🏟️' : '🎓';

      const bonusesStr = [
        b.voBonus ? `Vo+${b.voBonus}%` : '',
        b.daBonus ? `Da+${b.daBonus}%` : '',
        b.viBonus ? `Vi+${b.viBonus}%` : '',
        b.initCoin ? `P+${b.initCoin}` : '',
        b.initVo ? `初期Vo+${b.initVo}` : '',
        b.initDa ? `初期Da+${b.initDa}` : '',
        b.initVi ? `初期Vi+${b.initVi}` : '',
      ].filter(Boolean).join(' ');

      console.log(`  ${idx + 1}. ${stageTag} ${m.name.padEnd(20)} | ${cardName} (${timing}${custStr}) | ${bonusesStr || 'ボーナスなし'}`);
      if (options.verbose && m.abilities) {
        m.abilities.forEach(ab => {
          console.log(`     └ 📜 ${ab.rawText}`);
        });
      }
    });
    console.log('');
  }

  await client.close();
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});

