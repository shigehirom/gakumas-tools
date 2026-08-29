"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.MasterData = void 0;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const GAKUMAS_DATA_JSON_DIR = path.resolve(__dirname, '../../../../packages/gakumas-data/json');
function loadJson(filename) {
    const candidatePaths = [
        path.join(GAKUMAS_DATA_JSON_DIR, filename),
        path.resolve(process.cwd(), 'packages/gakumas-data/json', filename),
        path.resolve(__dirname, '../../../gakumas-data/json', filename),
        path.resolve('/app/packages/gakumas-data/json', filename),
        path.resolve('/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/json', filename)
    ];
    for (const p of candidatePaths) {
        if (fs.existsSync(p)) {
            return JSON.parse(fs.readFileSync(p, 'utf-8'));
        }
    }
    throw new Error(`Master data file not found: ${filename}`);
}
exports.MasterData = {
    getIdols() {
        return loadJson('idols.json');
    },
    getPIdols() {
        return loadJson('p_idols.json');
    },
    getStages() {
        return loadJson('stages.json');
    },
    getPItems() {
        return loadJson('p_items.json');
    },
    getSkillCards() {
        return loadJson('skill_cards.json');
    },
    getIdolById(id) {
        return this.getIdols().find(i => i.id === id);
    },
    getPIdolById(id) {
        return this.getPIdols().find(p => p.id === id);
    },
    getPItemById(id) {
        return this.getPItems().find(p => p.id === id);
    },
    getSkillCardById(id) {
        return this.getSkillCards().find(s => s.id === id);
    },
    getPItemContestPower(pItem) {
        if (pItem.sourceType === "pIdol") {
            if (pItem.rarity === "R")
                return pItem.upgraded ? 240 : 150;
            if (pItem.rarity === "SR")
                return pItem.upgraded ? 300 : 225;
            if (pItem.rarity === "SSR")
                return pItem.upgraded ? 420 : 300;
        }
        else if (pItem.sourceType === "support") {
            if (pItem.rarity === "SR")
                return 135;
            if (pItem.rarity === "SSR")
                return pItem.welfare ? 159 : 180;
        }
        return 0;
    },
    getSkillCardContestPower(skillCard) {
        if (skillCard.sourceType === "pIdol") {
            return skillCard.upgraded ? 15 : 3;
        }
        else if (skillCard.sourceType === "support") {
            return skillCard.upgraded ? 126 : 96;
        }
        else if (skillCard.sourceType === "produce") {
            const unlockPlv = skillCard.unlockPlv || 0;
            if (skillCard.rarity === "R") {
                return unlockPlv <= 2 ? (skillCard.upgraded ? 39 : 30) : (skillCard.upgraded ? 60 : 45);
            }
            if (skillCard.rarity === "SR") {
                return unlockPlv <= 2 ? (skillCard.upgraded ? 102 : 75) : (skillCard.upgraded ? 141 : 105);
            }
            if (skillCard.rarity === "SSR") {
                return skillCard.upgraded ? 204 : 150;
            }
        }
        return 0;
    },
    calculateContestPower(params, pItemIds, skillCardIds) {
        const [vocal = 0, dance = 0, visual = 0, stamina = 0] = params;
        const paramPower = 3 * (vocal + dance + visual) + 24 * stamina;
        let pItemPower = 0;
        for (const id of pItemIds) {
            const item = this.getPItemById(id);
            if (item)
                pItemPower += this.getPItemContestPower(item);
        }
        let skillCardPower = 0;
        for (const id of skillCardIds) {
            const card = this.getSkillCardById(id);
            if (card)
                skillCardPower += this.getSkillCardContestPower(card);
        }
        return paramPower + pItemPower + skillCardPower;
    }
};
