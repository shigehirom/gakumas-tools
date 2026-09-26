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

function optimizeDeckForIdol(
  allMemories: ProduceMemoryDoc[],
  focus: string,
  requiredCards: string[],
  topCount: number,
  verbose: boolean,
  idolDisplayName: string
) {
  if (allMemories.length < 4) {
    console.log(`⚠️ ${idolDisplayName}: メモリー不足 (${allMemories.length} 件、最低4件必要)`);
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

  console.log(`\n=== 🏆 [${idolDisplayName}] Top ${Math.min(topCount, combinations.length)} Recommended Produce Decks ===\n`);

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
}

export function registerProduceDeckCommand(cli: any) {
  cli.command('produce-deck', 'Optimize produce memory set (4 cards) for S4+ evaluation')
    .option('-f, --focus <type>', 'Target parameter focus: vo, da, vi, total, balanced (default: vo)', { default: 'vo' })
    .option('-i, --idol <name>', 'Filter by idol name (e.g. 咲季, 広, 清夏)')
    .option('-c, --cards <names>', 'Required skill cards to bring (comma separated)')
    .option('--stage-only', 'Only use memories that have matching stage memory')
    .option('-n, --top <number>', 'Number of top deck builds to display (default: 3)', { default: 3 })
    .option('--target-step4, --asari', 'Auto-target STEP4 & non-S4+ idols with prima_stella & anomaly (fullPower)')
    .option('--all-step4-targets', 'Auto-target all STEP4 & non-S4+ idols (including non-anomaly/no prima_stella)')
    .option('--ignore-prima-stella', 'Include idols even if they do not own the prima_stella song')
    .option('-v, --verbose', 'Show detailed ability breakdowns')
    .action(async (options: any) => {
      const focus = (options.focus || 'vo').toLowerCase();
      const idol = options.idol || '';
      const requiredCards = options.cards ? options.cards.split(',').map((s: string) => s.trim()).filter(Boolean) : [];
      const includeOnlyStage = !!options.stageOnly;
      const topCount = parseInt(options.top, 10) || 3;
      const verbose = !!options.verbose;
      const targetStep4 = !!options.targetStep4 || !!options.asari;
      const allStep4Targets = !!options.allStep4Targets;
      const isTargetMode = targetStep4 || allStep4Targets;
      const anomalyOnly = targetStep4 && !allStep4Targets;
      const primaStellaOnly = !options.ignorePrimaStella && !allStep4Targets;

      console.log(`=== S4+ Produce Deck Optimizer ===`);
      console.log(`Target Focus: ${focus.toUpperCase()}`);
      if (idol) console.log(`Idol Filter: ${idol}`);
      if (isTargetMode) {
        console.log(`Target Mode: STEP4 & S4+未達成 アイドル抽出 (PrimaStella=${primaStellaOnly}, Anomaly=${anomalyOnly})`);
      }
      if (requiredCards.length > 0) console.log(`Required Cards: ${requiredCards.join(', ')}`);

      if (requiredCards.length > 4) {
        console.error(`Cannot require more than 4 cards.`);
        return;
      }

      const mongoUri = process.env.MONGODB_URI || 'mongodb://192.168.100.4:27017';
      const mongoDb = process.env.MONGODB_DB || 'gakumas-tools';

      const client = new MongoClient(mongoUri);
      await client.connect();
      const db = client.db(mongoDb);
      const produceMemCol = db.collection('produce_memories');
      const ownedIdolsCol = db.collection('owned_idols');
      const ownedPIdolsCol = db.collection('owned_p_idols');

      if (!isTargetMode) {
        const query: any = {};
        if (idol) {
          query.idolName = { $regex: idol };
        }
        if (includeOnlyStage) {
          query.hasStageMemory = true;
        }

        const allMemories = (await produceMemCol.find(query).toArray()) as ProduceMemoryDoc[];
        console.log(`Found ${allMemories.length} memories matching query.`);
        optimizeDeckForIdol(allMemories, focus, requiredCards, topCount, verbose, idol || 'All Idols');
      } else {
        const step4Docs = await ownedIdolsCol.find({
          step: 4,
          produce_rank: { $ne: 'S4+' },
          ichibanboshi: { $ne: true }
        }).toArray();

        console.log(`\n📋 STEP4 かつ S4+未達成アイドル: ${step4Docs.length} 名`);
        let targetIdols: Array<{ name: string; anomalyCards: any[]; primaCards: any[] }> = [];

        for (const idDoc of step4Docs) {
          // Check owned prima_stella cards
          const primaCards = await ownedPIdolsCol.find({
            idolId: idDoc.id,
            prima_stella: true
          }).toArray();
          const hasPrima = primaCards.length > 0;

          // Check owned anomaly fullPower P-idols
          const anomalyPIdols = await ownedPIdolsCol.find({
            idolId: idDoc.id,
            plan: 'anomaly',
            $or: [
              { recommendedEffect: 'fullPower' },
              { recommended_effect: '全力' }
            ]
          }).toArray();
          const hasAnomaly = anomalyPIdols.length > 0;

          const statusStr = `[${idDoc.name}] STEP: ${idDoc.step} | P評価: ${idDoc.produce_rank || '未評価'} | 一番星: ${idDoc.ichibanboshi ? 'TRUE' : 'FALSE'}`;
          const primaStr = hasPrima ? `一番星楽曲: ⭕ (${primaCards.map(p => `【${p.title}】`).join(', ')})` : `一番星楽曲: ❌ 未所有`;
          const anomalyStr = hasAnomaly ? `アノマリー(全力): ⭕ (${anomalyPIdols.map(p => `【${p.title}】`).join(', ')})` : `アノマリー(全力): ❌`;

          const meetsPrima = !primaStellaOnly || hasPrima;
          const meetsAnomaly = !anomalyOnly || hasAnomaly;

          if (hasPrima && hasAnomaly) {
            console.log(`  ⭐ ${statusStr} -> ${primaStr} | ${anomalyStr} => 【最優先対象】`);
          } else if (hasPrima) {
            console.log(`  ⚪ ${statusStr} -> ${primaStr} | ${anomalyStr}`);
          } else {
            console.log(`  ⚠️ ${statusStr} -> ${primaStr} | ${anomalyStr} (一番星楽曲未所持)`);
          }

          if (meetsPrima && meetsAnomaly) {
            targetIdols.push({
              name: idDoc.name,
              primaCards,
              anomalyCards: anomalyPIdols
            });
          }
        }

        if (idol) {
          targetIdols = targetIdols.filter(t => t.name.includes(idol));
        }

        if (targetIdols.length === 0) {
          console.log('\n該当するターゲットアイドルが見つかりませんでした。');
          await client.close();
          return;
        }

        console.log(`\n🚀 対象アイドル ${targetIdols.length} 名の最適編成探索を開始します...`);
        for (const target of targetIdols) {
          const idolShort = target.name.split(' ')[1] || target.name;
          const query: any = { idolName: { $regex: idolShort } };
          if (includeOnlyStage) {
            query.hasStageMemory = true;
          }
          const memories = (await produceMemCol.find(query).toArray()) as ProduceMemoryDoc[];
          const cardInfo = target.anomalyCards.length > 0 ? ` (所持: ${target.anomalyCards.map(c => c.title).join(', ')})` : '';
          optimizeDeckForIdol(memories, focus, requiredCards, topCount, verbose, `${target.name}${cardInfo}`);
        }
      }

      await client.close();
    });
}

