import { Stages, PIdols, PItems, SkillCards } from 'gakumas-data';
import { IdolConfig, StageConfig, IdolStageConfig, StageEngine, StagePlayer, STRATEGIES } from 'gakumas-engine';
import { MongoClient } from 'mongodb';

async function main() {
  const client = new MongoClient('mongodb://192.168.100.4:27017');
  const db = client.db('gakumas-tools');

  // S51-1 ステージ (Stages クラスから取得)
  const stageData = Stages.getAll().find(s => s.season === 51 && s.stage === 1);
  if (!stageData) throw new Error('Stage 51-1 not found');
  const stageConfig = new StageConfig(stageData);

  // 麻央【Fluorite】
  const pIdol = PIdols.getAll().find(p => p.idolId === 10 && p.title.includes('Fluorite')) || PIdols.getById(63);

  // 現状手持ちペアのメモリー取得
  const m1 = await db.collection('memories').findOne({ name: /26\/05\/22＿19383/ });
  const m2 = await db.collection('memories').findOne({ name: /26\/06\/02＿19125/ });

  // 理想カード10枚 (あじふらい氏)
  const idealCardNames = [
    'シュプレヒコール+', '一発勝負+', '大胆不敵+', '精神統一+',
    '国民的アイドル', 'ほぐれるひととき+', 'ひと呼吸', '精神集中+',
    '脚光+', '天賦の才+'
  ];
  const idealCards = idealCardNames.map(name => SkillCards.getAll().find(c => c.name === name)).filter(Boolean);

  // 理想アイテム2種
  const idealItem1 = PItems.getAll().find(i => i.name === '得体のしれないモノ');
  const idealItem2 = PItems.getAll().find(i => i.name === 'とろけた時間');

  // 現状カード10枚
  const currentCards = [
    ...(m1?.skillCardIds?.map(id => SkillCards.getById(id)) || []),
    ...(m2?.skillCardIds?.map(id => SkillCards.getById(id)) || [])
  ].filter(Boolean);
  const currentItem1 = PItems.getById(m1?.pItemId) || idealItem1;
  const currentItem2 = PItems.getById(m2?.pItemId) || idealItem2;

  async function simulateDeck(label, cards, item1, item2, runs = 1000) {
    const loadout = {
      pIdolId: pIdol.id,
      params: [1700, 1700, 1700, 40],
      supportBonus: 0.1383,
      pItemIds: [item1?.id, item2?.id].filter(Boolean),
      skillCardIdGroups: [
        cards.slice(0, 5).map(c => c.id),
        cards.slice(5, 10).map(c => c.id)
      ],
      customizationGroups: [[{}, {}, {}, {}, {}], [{}, {}, {}, {}, {}]]
    };

    const idolConfig = new IdolConfig(loadout);
    const idolStageConfig = new IdolStageConfig(idolConfig, stageConfig);
    const scores = [];
    const StrategyClass = STRATEGIES["HeuristicStrategy"];

    for (let r = 0; r < runs; r++) {
      const engine = new StageEngine(idolStageConfig);
      const strategy = new StrategyClass(engine);
      engine.strategy = strategy;
      const player = new StagePlayer(engine, strategy);
      const res = await player.play();
      scores.push(res.score);
    }

    scores.sort((a, b) => a - b);
    const min = scores[0];
    const max = scores[scores.length - 1];
    const median = scores[Math.floor(scores.length / 2)];
    const avg = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
    const q1 = scores[Math.floor(scores.length * 0.25)];
    const q3 = scores[Math.floor(scores.length * 0.75)];

    return { label, min, q1, median, q3, max, avg, count: cards.length };
  }

  console.log('Running comparison simulations (1,000 runs each)...');
  const resCurrent = await simulateDeck('① 現状手持ちペア (6/10 一致)', currentCards, currentItem1, currentItem2, 1000);
  const resIdeal = await simulateDeck('② あじふらい氏 理想構成 (10/10 一致 + 理想Pアイテム2種)', idealCards, idealItem1, idealItem2, 1000);

  console.log('\n================== シミュレーション比較結果 (S51-1: 有村麻央) ==================');
  console.log(JSON.stringify({ resCurrent, resIdeal }, null, 2));

  await client.close();
}

main().catch(console.error);
