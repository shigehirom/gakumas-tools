import { StageEngine } from "gakumas-engine";
import { Stages, deserializeEffectSequence } from "gakumas-data";

const stageInfo = Stages.getById(164); // 47-1
console.log("Stage 47-1 Effects:", stageInfo.effects);

const engine = new StageEngine({});
console.log("Executor loaded:", engine.executor.constructor.name);

const effects = deserializeEffectSequence(stageInfo.effects);
console.log("Deserialized Actions count:", effects[0]?.actions?.length || 0);

const state = {
  phase: "afterCardUsed",
  stamina: 10,
  genki: 10,
  score: 0,
  goodConditionTurns: 6,
  effectCounter: 1,
  cardMap: {},
  effectCounters: {},
  currentEffectInstanceId: "123",
  unfreshPhase: false,
  freshBuffs: {}
};

try {
  console.log("Executing Actions...");
  engine.executor.executeActions(state, effects[0].actions, null);
  console.log("SUCCESS! State:", {
    goodConditionTurns: state.goodConditionTurns,
    effectCounters: state.effectCounters
  });
} catch (e) {
  console.error("FAIL:", e);
}
