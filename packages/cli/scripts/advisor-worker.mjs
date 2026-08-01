import { parentPort, workerData } from 'worker_threads';
import { IdolConfig, StageConfig, IdolStageConfig, StageEngine, StagePlayer, STRATEGIES } from "gakumas-engine";
import { PIdols, SkillCards } from "gakumas-data";

const { contestStage, numRuns, supportBonus, loadouts } = workerData;
const stageConfig = new StageConfig(contestStage);

const NUM_BUCKETS = 40;

function summarizeScores(scores) {
    if (!scores || !scores.length) return null;
    const sorted = [...scores].sort((a, b) => a - b);
    const n = sorted.length;
    const min = sorted[0];
    const max = sorted[n - 1];
    const q = (p) => {
        const idx = (n - 1) * p;
        const lo = Math.floor(idx);
        const hi = Math.ceil(idx);
        if (lo === hi) return sorted[lo];
        return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
    };
    const q1 = q(0.25);
    const median = q(0.5);
    const q3 = q(0.75);
    const mean = sorted.reduce((a, b) => a + b, 0) / n;
    const variance = sorted.reduce((a, b) => a + (b - mean) ** 2, 0) / n;
    const stddev = Math.sqrt(variance);

    const range = max - min;
    let bucketSize = range > 0 ? Math.ceil(range / NUM_BUCKETS) : 1;
    const buckets = new Array(NUM_BUCKETS).fill(0);
    for (const s of sorted) {
        const idx = Math.min(NUM_BUCKETS - 1, Math.floor((s - min) / bucketSize));
        buckets[idx]++;
    }

    return {
        count: n,
        min,
        q1,
        median,
        mean,
        q3,
        max,
        stddev,
        bucketMin: min,
        bucketSize,
        buckets,
    };
}

// Find pIdolId from loadout
function inferPIdolId(loadout) {
    const firstGroup = loadout.skillCardIdGroups[0] || [];
    for (const id of firstGroup) {
        if (!id) continue;
        const card = SkillCards.getById(id);
        if (card?.sourceType === "pIdol") {
            return card.pIdolId;
        }
    }
    return null;
}

const results = [];

async function runSimulation() {
    const StrategyClass = STRATEGIES["HeuristicStrategy"];

    for (const loadout of loadouts) {
        const runScores = [];
        const pIdolId = inferPIdolId(loadout);

        const simLoadout = {
            stageId: contestStage.id,
            supportBonus: supportBonus !== undefined ? supportBonus : 0.04,
            params: loadout.params,
            pItemIds: loadout.pItemIds,
            skillCardIdGroups: loadout.skillCardIdGroups,
            customizationGroups: loadout.customizationGroups
        };

        for (let i = 0; i < numRuns; i++) {
            try {
                const idolConfig = new IdolConfig(simLoadout);

                if (pIdolId) {
                    const mainPIdol = PIdols.getById(pIdolId);
                    if (mainPIdol) {
                        idolConfig.pIdolId = mainPIdol.id;
                        idolConfig.idolId = mainPIdol.idolId;
                        idolConfig.plan = mainPIdol.plan;
                        idolConfig.recommendedEffect = mainPIdol.recommendedEffect;
                    }
                }

                const config = new IdolStageConfig(idolConfig, stageConfig);
                const engine = new StageEngine(config);

                // Disable logs for performance
                engine.logger.logs = [{}];
                engine.logger.log = () => 0;
                engine.logger.pushGraphData = () => {};
                engine.logger.debug = () => {};
                engine.logger.reset = () => {};

                const strategy = new StrategyClass(engine);
                const player = new StagePlayer(engine, strategy);

                const result = await player.play();
                if (result && typeof result.score === 'number') {
                    runScores.push(result.score);
                }
            } catch (e) {
                // Log and ignore errors to prevent crashing the whole batch
                if (i === 0) {
                    console.error(`[Advisor-Worker] Simulation failed: ${e.message}`);
                }
            }
        }

        if (runScores.length === 0) {
            results.push({
                id: loadout.id,
                score: 0, min: 0, max: 0, median: 0, q1: 0, q3: 0,
                stats: null
            });
            parentPort.postMessage({ type: 'progress', count: 1 });
            continue;
        }

        const stats = summarizeScores(runScores);

        results.push({
            id: loadout.id,
            score: stats.mean,
            min: stats.min,
            max: stats.max,
            median: stats.median,
            q1: stats.q1,
            q3: stats.q3,
            stats
        });
        parentPort.postMessage({ type: 'progress', count: 1 });
    }

    parentPort.postMessage({ type: 'done', results });
}

runSimulation().catch(err => {
    console.error("[Advisor-Worker] Fatal error:", err);
    process.exit(1);
});
