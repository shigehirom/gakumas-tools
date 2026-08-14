import * as fs from 'fs';
import * as path from 'path';

const GAKUMAS_DATA_JSON_DIR = path.resolve(__dirname, '../../../../packages/gakumas-data/json');

export interface Idol {
    id: number;
    name: string;
}

export interface PIdol {
    id: number;
    idolId: number;
    title: string;
    rarity: string;
    plan: string;
    recommendedEffect: string;
}

export interface Stage {
    id: number;
    name: string;
    type: string;
    preview: boolean;
    season: number;
    stage: number;
    plan: string;
}

export interface PItem {
    id: number;
    name: string;
    rarity: string;
    upgraded: boolean;
    plan: string;
    sourceType: string;
    pIdolId?: number | string;
    welfare?: boolean;
}

export interface SkillCard {
    id: number;
    name: string;
    rarity: string;
    upgraded: boolean;
    plan: string;
    sourceType: string;
    pIdolId?: number | string;
    unlockPlv?: number;
}

function loadJson<T>(filename: string): T {
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

export const MasterData = {
    getIdols(): Idol[] {
        return loadJson<Idol[]>('idols.json');
    },
    getPIdols(): PIdol[] {
        return loadJson<PIdol[]>('p_idols.json');
    },
    getStages(): Stage[] {
        return loadJson<Stage[]>('stages.json');
    },
    getPItems(): PItem[] {
        return loadJson<PItem[]>('p_items.json');
    },
    getSkillCards(): SkillCard[] {
        return loadJson<SkillCard[]>('skill_cards.json');
    },
    getIdolById(id: number): Idol | undefined {
        return this.getIdols().find(i => i.id === id);
    },
    getPIdolById(id: number): PIdol | undefined {
        return this.getPIdols().find(p => p.id === id);
    },
    getPItemById(id: number): PItem | undefined {
        return this.getPItems().find(p => p.id === id);
    },
    getSkillCardById(id: number): SkillCard | undefined {
        return this.getSkillCards().find(s => s.id === id);
    },

    getPItemContestPower(pItem: PItem): number {
        if (pItem.sourceType === "pIdol") {
            if (pItem.rarity === "R") return pItem.upgraded ? 240 : 150;
            if (pItem.rarity === "SR") return pItem.upgraded ? 300 : 225;
            if (pItem.rarity === "SSR") return pItem.upgraded ? 420 : 300;
        } else if (pItem.sourceType === "support") {
            if (pItem.rarity === "SR") return 135;
            if (pItem.rarity === "SSR") return pItem.welfare ? 159 : 180;
        }
        return 0;
    },

    getSkillCardContestPower(skillCard: SkillCard): number {
        if (skillCard.sourceType === "pIdol") {
            return skillCard.upgraded ? 15 : 3;
        } else if (skillCard.sourceType === "support") {
            return skillCard.upgraded ? 126 : 96;
        } else if (skillCard.sourceType === "produce") {
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

    calculateContestPower(params: number[], pItemIds: number[], skillCardIds: number[]): number {
        const [vocal = 0, dance = 0, visual = 0, stamina = 0] = params;
        const paramPower = 3 * (vocal + dance + visual) + 24 * stamina;

        let pItemPower = 0;
        for (const id of pItemIds) {
            const item = this.getPItemById(id);
            if (item) pItemPower += this.getPItemContestPower(item);
        }

        let skillCardPower = 0;
        for (const id of skillCardIds) {
            const card = this.getSkillCardById(id);
            if (card) skillCardPower += this.getSkillCardContestPower(card);
        }

        return paramPower + pItemPower + skillCardPower;
    }
};
