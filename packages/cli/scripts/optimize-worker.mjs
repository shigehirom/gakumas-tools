
import { parentPort, workerData } from 'worker_threads';
import { IdolConfig, StageConfig, IdolStageConfig, StageEngine, StagePlayer, STRATEGIES } from "gakumas-engine";

// Receive static data (stage info) from workerData
const { contestStage, numRuns } = workerData;
const stageConfig = new StageConfig(contestStage);

parentPort.on('message', async (task) => {
    // task: { id, combinations: [{ main, sub, sub2 }, ...] }
    const { id, combinations } = task;
    const results = [];
    let pendingCount = 0;

    // Process chunk
    for (const comb of combinations) {
        const { main, sub, sub2 } = comb;

        const loadout = {
            stageId: contestStage.id,
            supportBonus: 0.04,
            params: [0, 0, 0, 0],
            pItemIds: [],
            skillCardIdGroups: [],
            customizationGroups: [],
        };

        // Apply Main
        loadout.params = [...main.data.params];
        loadout.pItemIds = [...(main.data.pItemIds || [])];
        loadout.skillCardIdGroups.push(main.data.skillCardIds || []);
        loadout.customizationGroups.push(main.data.customizations || [{}, {}, {}, {}, {}, {}]);

        // Apply Sub
        const multiplier = 0.2;
        if (sub) {
            loadout.params = loadout.params.map((p, i) => p + Math.floor((sub.data.params[i] || 0) * multiplier));
            if (sub.data.pItemIds) loadout.pItemIds.push(...sub.data.pItemIds);
            loadout.skillCardIdGroups.push(sub.data.skillCardIds || []);
            loadout.customizationGroups.push(sub.data.customizations || [{}, {}, {}, {}, {}, {}]);
        }

        // Apply Sub2
        if (sub2) {
            loadout.params = loadout.params.map((p, i) => p + Math.floor((sub2.data.params[i] || 0) * multiplier));
            if (sub2.data.pItemIds) loadout.pItemIds.push(...sub2.data.pItemIds);
            loadout.skillCardIdGroups.push(sub2.data.skillCardIds || []);
            loadout.customizationGroups.push(sub2.data.customizations || [{}, {}, {}, {}, {}, {}]);
        }

        // Setup Engine
        const idolConfig = new IdolConfig(loadout);
        const config = new IdolStageConfig(idolConfig, stageConfig);

        const runScores = [];

        for (let i = 0; i < numRuns; i++) {
            const engine = new StageEngine(config);
            const StrategyClass = STRATEGIES["HeuristicStrategy"];
            const strategy = new StrategyClass(engine);
            engine.strategy = strategy;
            const player = new StagePlayer(engine, strategy);

            try {
                const result = await player.play();
                runScores.push(result.score);
            } catch (e) {
                // Ignore errors
            }
        }

        if (runScores.length === 0) {
            results.push({
                mainFilename: main.filename,
                mainName: main.data.name,
                subFilename: sub ? sub.filename : undefined,
                subName: sub ? sub.data.name : undefined,
                sub2Filename: sub2 ? sub2.filename : undefined,
                sub2Name: sub2 ? sub2.data.name : undefined,
                score: 0,
                min: 0,
                max: 0,
                median: 0
            });
            parentPort.postMessage({ type: 'progress', count: 1 });
            continue;
        }

        runScores.sort((a, b) => a - b);
        const totalScore = runScores.reduce((acc, s) => acc + s, 0);
        const avgScore = totalScore / runScores.length;
        const minScore = runScores[0];
        const maxScore = runScores[runScores.length - 1];
        const mid = Math.floor(runScores.length / 2);
        const medianScore = runScores.length % 2 !== 0 ? runScores[mid] : (runScores[mid - 1] + runScores[mid]) / 2;

        results.push({
            mainFilename: main.filename,
            mainName: main.data.name,
            mainHash: main.hash,
            subFilename: sub ? sub.filename : undefined,
            subName: sub ? sub.data.name : undefined,
            subHash: sub ? sub.hash : undefined,
            sub2Filename: sub2 ? sub2.filename : undefined,
            sub2Name: sub2 ? sub2.data.name : undefined,
            sub2Hash: sub2 ? sub2.hash : undefined,
            score: avgScore,
            min: minScore,
            max: maxScore,
            median: medianScore,
            meta: main.meta // Pass through metadata
        });

        // Notify progress (batched)
        pendingCount++;
        if (pendingCount >= 10) {
            parentPort.postMessage({ type: 'progress', count: pendingCount });
            pendingCount = 0;
        }
    }

    if (pendingCount > 0) {
        parentPort.postMessage({ type: 'progress', count: pendingCount });
    }

    // Send back results
    parentPort.postMessage({ type: 'done', results });
});
