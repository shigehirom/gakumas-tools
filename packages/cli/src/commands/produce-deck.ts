import { MongoClient } from 'mongodb';

interface ProduceMemoryDoc {
  _id: any;
  userId?: string;
  name: string;
  idolName: string;
  song?: string;
  hasStageMemory: boolean;
  sourceType: string;
  scenario: string;
  difficulty: string;
  event?: string;
  skillCard?: {
    id: number;
    name: string;
    timing: string;
    customization: Record<string, number>;
  };
  abilities?: Array<{
    slotIndex: number;
    rawText: string;
    dsl: string;
  }>;
  bonuses?: {
    voBonus?: number;
    daBonus?: number;
    viBonus?: number;
    initVo?: number;
    initDa?: number;
    initVi?: number;
    initCoin?: number;
    hifCardName?: string;
    hifCardId?: number;
    hifEffect?: string;
    healType?: string;
    healProb?: number;
    healAmount?: number;
  };
  _indScore?: number;
}

export function registerProduceDeckCommand(cli: any) {
  cli.command('produce-deck', 'Optimize produce memory set (4 cards) for S4+ evaluation')
    .option('-f, --focus <type>', 'Target parameter focus: vo, da, vi, total, balanced (default: vo)', { default: 'vo' })
    .option('-i, --idol <name>', 'Filter by idol name (e.g. 咲季, 広, 清夏)')
    .option('-c, --cards <names>', 'Required skill cards to bring (comma separated)')
    .option('--stage-only', 'Only use memories that have matching stage memory')
    .option('-n, --top <number>', 'Number of top deck builds to display (default: 3)', { default: 3 })
    .option('-v, --verbose', 'Show detailed ability breakdowns')
    .action(async (options: any) => {
      const focus = (options.focus || 'vo').toLowerCase();
      const idol = options.idol || '';
      const requiredCards = options.cards ? options.cards.split(',').map((s: string) => s.trim()).filter(Boolean) : [];
      const includeOnlyStage = !!options.stageOnly;
      const topCount = parseInt(options.top, 10) || 3;
      const verbose = !!options.verbose;

      console.log(`=== S4+ Produce Deck Optimizer ===`);
      console.log(`Target Focus: ${focus.toUpperCase()}`);
      if (idol) console.log(`Idol Filter: ${idol}`);
      if (requiredCards.length > 0) console.log(`Required Cards: ${requiredCards.join(', ')}`);

      const mongoUri = process.env.MONGODB_URI || 'mongodb://192.168.100.4:27017';
      const mongoDb = process.env.MONGODB_DB || 'gakumas-tools';

      const client = new MongoClient(mongoUri);
      await client.connect();
      const db = client.db(mongoDb);
      const produceMemCol = db.collection('produce_memories');

      const query: any = {};
      if (idol) {
        query.idolName = { $regex: idol };
      }
      if (includeOnlyStage) {
        query.hasStageMemory = true;
      }

      const allMemories = (await produceMemCol.find(query).toArray()) as ProduceMemoryDoc[];
      console.log(`Found ${allMemories.length} memories matching query.`);

      if (allMemories.length < 4) {
        console.error(`Not enough memories (${allMemories.length} found, minimum 4 required).`);
        await client.close();
        return;
      }

      if (requiredCards.length > 4) {
        console.error(`Cannot require more than 4 cards.`);
        await client.close();
        return;
      }

      // Check required cards existence
      for (const rc of requiredCards) {
        const hasCard = allMemories.some(m => m.skillCard && m.skillCard.name && m.skillCard.name.includes(rc));
        if (!hasCard) {
          console.warn(`[Warning] No memory found with required card: "${rc}"`);
        }
      }

      // Pre-score and prune memories to keep combination search fast
      allMemories.forEach(m => {
        const b = m.bonuses || {};
        let indScore = 0;
        if (focus === 'vo') indScore = (b.voBonus || 0) * 100 + (b.initVo || 0);
        else if (focus === 'da') indScore = (b.daBonus || 0) * 100 + (b.initDa || 0);
        else if (focus === 'vi') indScore = (b.viBonus || 0) * 100 + (b.initVi || 0);
        else indScore = (b.voBonus || 0) + (b.daBonus || 0) + (b.viBonus || 0);

        if (m.skillCard?.name && requiredCards.some((rc: string) => m.skillCard!.name.includes(rc))) {
          indScore += 100000;
        }
        m._indScore = indScore;
      });

      allMemories.sort((a, b) => (b._indScore || 0) - (a._indScore || 0));

      // Group by skill card ID
      const candidatePool: ProduceMemoryDoc[] = [];
      const cardGroup = new Map<number, ProduceMemoryDoc[]>();

      for (const m of allMemories) {
        const cardId = m.skillCard?.id || 0;
        if (cardId === 0) {
          if (candidatePool.length < 50) candidatePool.push(m);
        } else {
          if (!cardGroup.has(cardId)) {
            cardGroup.set(cardId, []);
          }
          const list = cardGroup.get(cardId)!;
          if (list.length < 3) {
            list.push(m);
            candidatePool.push(m);
          }
        }
        if (candidatePool.length >= 60) break;
      }

      console.log(`Evaluated candidates pool size: ${candidatePool.length} memories.`);

      const combinations: Array<{ deck: ProduceMemoryDoc[]; stats: any }> = [];
      const N = candidatePool.length;

      function findCombos(startIndex: number, current: ProduceMemoryDoc[]) {
        if (current.length === 4) {
          const seenCards = new Set<number>();
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

          if (valid && requiredCards.length > 0) {
            for (const rc of requiredCards) {
              const present = current.some(m => m.skillCard?.name && m.skillCard.name.includes(rc));
              if (!present) {
                valid = false;
                break;
              }
            }
          }

          if (valid) {
            const stats = calculateDeckScore(current, focus);
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

      combinations.sort((a, b) => b.stats.score - a.stats.score);

      console.log(`\n=== 🏆 Top ${Math.min(topCount, combinations.length)} Recommended Produce Decks ===\n`);

      for (let rank = 0; rank < Math.min(topCount, combinations.length); rank++) {
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
          if (verbose && m.abilities) {
            m.abilities.forEach(ab => {
              console.log(`     └ 📜 ${ab.rawText}`);
            });
          }
        });
        console.log('');
      }

      await client.close();
    });
}

function calculateDeckScore(deck: ProduceMemoryDoc[], focus: string) {
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
      primaryScore = voBonus * 1000 + (daBonus + viBonus) * 10 + (initVo * 2 + initDa + initVi);
      break;
    case 'da':
      primaryScore = daBonus * 1000 + (voBonus + viBonus) * 10 + (initDa * 2 + initVo + initVi);
      break;
    case 'vi':
      primaryScore = viBonus * 1000 + (voBonus + daBonus) * 10 + (initVi * 2 + initVo + initDa);
      break;
    case 'balanced':
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

