import { deserializeEffectSequence } from "gakumas-data";

const effect1 = "at:afterCardUsed[mental] { if:goodConditionTurns>=5 { effectCounter+=1; if:effectCounter%3==2 { goodConditionTurns+=7; cardUsesRemaining+=1; limit:3 } } }";
const effect2 = "at:stanceChanged { if:isFullPower & fullPowerTimes>=2 { setScoreBuff(0.8,2); nullifyGenkiTurns+=1; target:effect(fullPowerCharge) { g.score+=20 }; limit:4 } }";

console.log(JSON.stringify(deserializeEffectSequence(effect1), null, 2));
console.log(JSON.stringify(deserializeEffectSequence(effect2), null, 2));
