
import { MongoClient } from 'mongodb';
import { StageEngine, StagePlayer, STRATEGIES } from 'gakumas-engine';
import { Stages, PItems, SkillCards } from 'gakumas-data';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function loadEnv(filePath) {
  if (fs.existsSync(filePath)) {
    const envFile = fs.readFileSync(filePath, 'utf-8');
    envFile.split('\n').forEach(line => {
      const parts = line.split('=');
      if (parts.length === 2) {
        process.env[parts[0].trim()] = parts[1].trim();
      }
    });
  }
}

async function run() {
  loadEnv(path.join(__dirname, '../../gakumas-tools/.env.local'));
  const MONGODB_URI = process.env.MONGODB_URI;
  const MONGODB_DB = process.env.MONGODB_DB || 'gakumas-tools';

  if (!MONGODB_URI) {
    console.error('MONGODB_URI is not set');
    process.exit(1);
  }

  const client = new MongoClient(MONGODB_URI);
  try {
    await client.connect();
    const db = client.db(MONGODB_DB);
    const memoryName = '26/04/03＿15063';
    const memory = await db.collection('memories').findOne({ name: memoryName });

    if (!memory) {
      console.error(`Memory ${memoryName} not found`);
      process.exit(1);
    }

    console.log(`Memory found: ${memory.name} (ID: ${memory._id})`);
    console.log(`P-Items in memory: ${memory.pItemIds.join(', ')}`);
    
    // Check if 415 is in pItems
    const has415 = memory.pItemIds.includes(415);
    console.log(`Contains 415 (おかいものバッグ): ${has415}`);

    if (has415) {
      const pItem = PItems.getById(415);
      console.log(`P-Item 415 Definition: ${pItem ? JSON.stringify(pItem) : 'MISSING'}`);
    }

    // Stage 42-3 (ID: 150)
    const stageId = 150;
    const stage = Stages.getById(stageId);
    if (!stage) {
      console.error(`Stage ${stageId} not found`);
      process.exit(1);
    }
    console.log(`Stage: ${stage.name}`);

    // Setup simulation
    const loadout = {
      stageId: stageId,
      supportBonus: 0.04,
      params: memory.params,
      pItemIds: memory.pItemIds,
      skillCardIdGroups: [memory.skillCardIds, []],
      customizationGroups: [memory.customizations, []]
    };

    const numRuns = 100;
    const scores = [];

    console.log(`Starting ${numRuns} simulations...`);
    for (let i = 0; i < numRuns; i++) {
        // We use the same parameters as simulate-loadout-worker.mjs
        const { IdolConfig, StageConfig, IdolStageConfig } = await import('gakumas-engine');
        const idolConfig = new IdolConfig(loadout);
        const stageConfig = new StageConfig(stage);
        const config = new IdolStageConfig(idolConfig, stageConfig);
        const engine = new StageEngine(config);
        const strategy = new STRATEGIES.HeuristicStrategy(engine);
        engine.strategy = strategy;
        const player = new StagePlayer(engine, strategy);
        
        const result = await player.play();
        scores.push(result.score);
    }

    scores.sort((a, b) => a - b);
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    console.log(`\n--- Results for ${memoryName} ---`);
    console.log(`Min Score: ${scores[0]}`);
    console.log(`Avg Score: ${avg.toFixed(2)}`);
    console.log(`Max Score: ${scores[scores.length - 1]}`);
    console.log(`Median: ${scores[Math.floor(scores.length / 2)]}`);

  } catch (e) {
    console.error(e);
  } finally {
    await client.close();
  }
}

run();
