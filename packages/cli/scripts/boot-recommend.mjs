import fs from "fs";
import { MongoClient } from "mongodb";
import { Stages, PIdols, Idols, PItems, SkillCards, Customizations } from "gakumas-data";

function parseMarkdown(filePath) {
    const text = fs.readFileSync(filePath, "utf-8");
    const sections = text.split(/^# /m).filter(s => s.trim());
    
    let parsedData = [];
    for (const section of sections) {
        const lines = section.split("\n").map(l => l.trimEnd());
        const titleMatch = lines[0].match(/シーズン\s*(\d+)\s*ステージ(\d+)/);
        if (!titleMatch) continue;
        
        const season = parseInt(titleMatch[1], 10);
        const stage = parseInt(titleMatch[2], 10);
        const planMatch = lines[0].match(/\((.*?)\)/);
        const plan = planMatch ? planMatch[1] : "不明";

        let idols = [];
        let genericPItems = [];
        let specialPItems = {};
        let genericMemories = [];
        let specialMemories = {};

        let currentSection = "";
        let currentSubTarget = null;
        let lastMemoryIdx = -1;

        for (let i = 1; i < lines.length; i++) {
            const line = lines[i];
            const headerMatch = line.match(/^##\s+(.*)/);
            if (headerMatch) {
                const h = headerMatch[1];
                if (h.startsWith("アイドル")) currentSection = "idols";
                else if (h.startsWith("Pアイテム")) {
                    currentSection = "pitems";
                    const m = h.match(/\[(.*?)\]/);
                    currentSubTarget = m ? m[1] : "汎用";
                }
                else if (h.startsWith("メモリー")) {
                    currentSection = "memories";
                    const m = h.match(/\[(.*?)\]/);
                    currentSubTarget = m ? m[1] : "汎用";
                }
                continue;
            }

            if (!line.trim()) continue;

            if (currentSection === "idols" && line.startsWith("- ")) {
                let idolStr = line.substring(2).trim();
                idolStr = idolStr.replace(/\s+\[.*?\]$/, "");
                idols.push(idolStr);
            } else if (currentSection === "pitems") {
                const itemMatch = line.match(/^\d+\.\s+(.*)/);
                if (itemMatch) {
                    let itemName = itemMatch[1].trim();
                    itemName = itemName.replace(/\s+\[.*?\]$/, "");
                    if (currentSubTarget === "汎用") genericPItems.push(itemName);
                    else {
                        if (!specialPItems[currentSubTarget]) specialPItems[currentSubTarget] = [];
                        specialPItems[currentSubTarget].push(itemName);
                    }
                }
            } else if (currentSection === "memories") {
                const memMatch = line.match(/^\d+\.\s+(.*)/);
                if (memMatch) {
                    let memStr = memMatch[1].trim();
                    memStr = memStr.replace(/\s+\[.*?\]$/, "");
                    const memInfo = parseMemoryStr(memStr);
                    if (currentSubTarget === "汎用") {
                        genericMemories.push(memInfo);
                        lastMemoryIdx = genericMemories.length - 1;
                    } else {
                        if (!specialMemories[currentSubTarget]) specialMemories[currentSubTarget] = [];
                        specialMemories[currentSubTarget].push(memInfo);
                        lastMemoryIdx = specialMemories[currentSubTarget].length - 1;
                    }
                } else if (line.match(/^\s+-\s+(.*)/)) {
                    const subMemMatch = line.match(/^\s+-\s+(.*?)\s+\[(.*?)\]/);
                    if (subMemMatch) {
                        const memInfo = parseMemoryStr(subMemMatch[1].trim());
                        const targetIdol = subMemMatch[2].trim();
                        if (!specialMemories[targetIdol]) specialMemories[targetIdol] = {};
                        specialMemories[targetIdol][lastMemoryIdx] = memInfo;
                    }
                }
            }
        }
        parsedData.push({ season, stage, plan, idols, genericPItems, specialPItems, genericMemories, specialMemories });
    }
    return parsedData;
}

function parseMemoryStr(str) {
    let cardName = str;
    let customNames = [];
    const parenMatch = str.match(/\((.*?)\)/);
    if (parenMatch) {
        customNames = parenMatch[1].split(",").map(s => s.trim());
        cardName = str.substring(0, str.indexOf("(")).trim();
    }
    return { name: cardName, customizations: customNames, original: str };
}

// Map helper
function getPItemIdsByName(name) {
    const isPlus = name.endsWith("+");
    const baseName = isPlus ? name.slice(0, -1) : name;
    // Just find matching names
    return PItems.getAll().filter(p => p.name === baseName || p.name === name).map(p => p.id);
}
function getCardInfoByName(name) {
    const isPlus = name.endsWith("+");
    const baseName = isPlus ? name.slice(0, -1) : name;
    return SkillCards.getAll().find(c => c.name === name || c.name === baseName);
}

function resolveCustomizationId(nameCandidate) {
    const customs = Customizations.getAll();
    const exact = customs.find(c => c.name === nameCandidate);
    if (exact) return exact.id;
    const partial = customs.filter(c => c.name.includes(nameCandidate) || nameCandidate.includes(c.name));
    if (partial.length > 0) return partial[0].id;
    return null; // fallback
}

function getBaseIdolName(fullStr) {
    const idx = fullStr.indexOf("【");
    return idx > 0 ? fullStr.substring(0, idx).trim() : fullStr;
}

function matchMemoryToIdeal(dbMem, idealCardsArray) {
    // Return score and matched indices
    let score = 0;
    const matchedIndices = [];
    const matchedItems = [];

    // Map dbMem cards
    const dbCardDefs = [];
    for (let j = 0; j < dbMem.skillCardIds.length; j++) {
        const cId = dbMem.skillCardIds[j];
        if (!cId) continue;
        const card = SkillCards.getById(cId);
        if (card && card.sourceType === "pIdol") continue; // Ignore signature cards
        
        let customArray = [];
        if (dbMem.customizations && dbMem.customizations[j]) {
             customArray = Object.keys(dbMem.customizations[j]);
        }
        dbCardDefs.push({ id: cId, name: card ? card.name : "", customizations: customArray, cardObj: card });
    }

    // Try to match dbCardDefs (up to 5) to idealCardsArray (up to 10)
    for (const dbC of dbCardDefs) {
        let bestMatchIdx = -1;
        let bestMatchScore = -1;

        for (let i = 0; i < idealCardsArray.length; i++) {
            if (matchedIndices.includes(i)) continue; // Already matched
            const ideal = idealCardsArray[i];
            
            // Allow matching base name if plus isn't req/met exactly
            const idealBase = ideal.name.replace("+", "");
            const dbBase = dbC.name.replace("+", "");

            if (idealBase === dbBase) {
                let currentScore = 10; // Base match
                if (ideal.name === dbC.name) currentScore += 5; // Exact name match (e.g. both have +)

                // Customizations check
                let customScore = 0;
                for (const expectedCustStr of ideal.customizations) {
                    const expectedCId = resolveCustomizationId(expectedCustStr);
                    if (expectedCId && dbC.customizations.includes(expectedCId)) {
                        customScore += 5;
                    }
                }
                currentScore += customScore;

                if (currentScore > bestMatchScore) {
                    bestMatchScore = currentScore;
                    bestMatchIdx = i;
                }
            }
        }

        if (bestMatchIdx !== -1) {
            score += bestMatchScore;
            matchedIndices.push(bestMatchIdx);
            matchedItems.push(dbC); // What we actually have
        }
    }

    return { score, matchedIndices, matchedItems };
}

async function run() {
    const uri = process.argv[2];
    const markdownFile = process.argv[3];
    if (!markdownFile) {
        console.error("No markdown file specified.");
        process.exit(1);
    }
    if (!process.env.MONGODB_URI) {
        console.error("MONGODB_URI not set.");
        process.exit(1);
    }

    const client = new MongoClient(process.env.MONGODB_URI);
    try {
        await client.connect();
        const db = client.db(process.env.MONGODB_DB || "gakumas-tools");
        const collection = db.collection("memories");

        const parsedData = parseMarkdown(markdownFile);
        const results = [];

        for (const stageData of parsedData) {
            const stageOutput = {
                season: stageData.season,
                stage: stageData.stage,
                plan: stageData.plan,
                idols: []
            };

            for (const idolDefStr of stageData.idols) {
                const idolBaseName = getBaseIdolName(idolDefStr);
                const dbIdolNameMatch = Idols.getAll().find(i => i.name.replace(/\s+/g, '') === idolBaseName.replace(/\s+/g, '') || i.name === idolBaseName);
                
                if (!dbIdolNameMatch) {
                    console.error("Idol not found for:", idolBaseName);
                    continue;
                }

                // Get ideal elements for this idol
                // PItems
                let idealPItems = [...stageData.genericPItems];
                for (const key in stageData.specialPItems) {
                    if (key.includes(idolBaseName)) {
                        idealPItems = [...stageData.specialPItems[key]];
                    }
                }

                // Memories (10 cards)
                let idealCards = [...stageData.genericMemories];
                for (let i = 0; i < idealCards.length; i++) {
                    for (const key in stageData.specialMemories) {
                        if (key.includes(idolBaseName) && stageData.specialMemories[key][i]) {
                             idealCards[i] = stageData.specialMemories[key][i];
                        }
                    }
                }

                // Fetch DB memories
                const targetPIdols = PIdols.getAll().filter(p => p.idolId === dbIdolNameMatch.id);
                const pIdolIds = targetPIdols.map(p => p.id);
                
                const dbMemories = await collection.find({ pIdolId: { $in: pIdolIds } }).toArray();

                let bestMem1 = null;
                let bestScore = -1;

                for (const mem of dbMemories) {
                    // Check PItems
                    let pItemScore = 0;
                    for (const idealItemStr of idealPItems) {
                        const ids = getPItemIdsByName(idealItemStr);
                        if (mem.pItemIds && mem.pItemIds.some(id => ids.includes(id))) {
                            pItemScore += 20; // High value for PItems
                        }
                    }

                    const matchRes = matchMemoryToIdeal(mem, idealCards);
                    const totalScore = pItemScore + matchRes.score;

                    if (totalScore > bestScore) {
                        bestScore = totalScore;
                        bestMem1 = {
                            dbDoc: mem,
                            matchedIndices: matchRes.matchedIndices,
                            matchedItems: matchRes.matchedItems,  // DB actual items matched
                            pItemsMatched: mem.pItemIds?.filter(id => {
                                 // check if this id maps to idealPItems
                                 const name = PItems.getById(id)?.name;
                                 return idealPItems.some(i => name && (i === name || i.startsWith(name)));
                            }) || []
                        };
                    }
                }

                if (bestMem1 && bestScore > 0) {
                    // Calculate Memory 2 (unmatched)
                    const unmatchedCards = [];
                    for (let i = 0; i < idealCards.length; i++) {
                        if (!bestMem1.matchedIndices.includes(i)) {
                            unmatchedCards.push(idealCards[i]);
                        }
                    }
                    
                    const unmatchedPItems = idealPItems.filter(idealI => {
                         const ids = getPItemIdsByName(idealI);
                         return !bestMem1.pItemsMatched.some(id => ids.includes(id));
                    });

                    // Format Memory 1 items
                    const memory1CardsArr = bestMem1.matchedItems.map(item => {
                        const card = SkillCards.getById(item.id);
                        const rarity = card ? `[${card.rarity}] ` : "";
                        let name = `${rarity}${item.name}`;
                        if (item.customizations && item.customizations.length > 0) {
                            const cnames = item.customizations.map(cid => Customizations.getById(cid)?.name).filter(x => x).join(", ");
                            if(cnames) name += ` (${cnames})`;
                        }
                        return name;
                    });
                    
                    // Add signature card to Memory 1
                    let sigName1 = "[固有札]";
                    const sig1 = bestMem1.dbDoc.skillCardIds.find(cId => SkillCards.getById(cId)?.sourceType === "pIdol");
                    if (sig1) {
                        const card = SkillCards.getById(sig1);
                        sigName1 = `[${card.rarity}] ${card.name}`;
                    }

                    const titleData = PIdols.getById(bestMem1.dbDoc.pIdolId);
                    const mainTitle = titleData ? titleData.title : "Unknown";

                    stageOutput.idols.push({
                        idolNameFull: idolDefStr,
                        idolNameBase: dbIdolNameMatch.name,
                        targetMem1Title: mainTitle,
                        mem1Name: bestMem1.dbDoc.name || `Memory(${bestMem1.dbDoc._id.toString().substring(0,8)})`,
                        pItemsMatched: bestMem1.pItemsMatched.map(id => {
                            const item = PItems.getById(id);
                            return item ? `[${item.rarity}] ${item.name}` : "";
                        }),
                        pItemsTarget: unmatchedPItems.map(name => {
                            const items = getPItemIdsByName(name);
                            if (items.length > 0) {
                                const item = PItems.getById(items[0]);
                                return `[${item.rarity}] ${name}`;
                            }
                            return name;
                        }),
                        mem1Sig: sigName1,
                        mem1Cards: memory1CardsArr,
                        mem2Cards: unmatchedCards.slice(0, 5).map(c => {
                            const card = getCardInfoByName(c.name);
                            const rarity = card ? `[${card.rarity}] ` : "";
                            return `${rarity}${c.original}`;
                        })
                    });
                } else {
                    // No memory found
                     stageOutput.idols.push({
                        idolNameFull: idolDefStr,
                        idolNameBase: dbIdolNameMatch.name,
                        targetMem1Title: "不明",
                        mem1Name: "条件に合うメモリーなし",
                        pItemsMatched: [],
                        pItemsTarget: idealPItems.map(name => {
                            const items = getPItemIdsByName(name);
                            if (items.length > 0) {
                                const item = PItems.getById(items[0]);
                                return `[${item.rarity}] ${name}`;
                            }
                            return name;
                        }),
                        mem1Sig: "[固有札]", 
                        mem1Cards: [], 
                        mem2Cards: idealCards.slice(0, 5).map(c => {
                            const card = getCardInfoByName(c.name);
                            const rarity = card ? `[${card.rarity}] ` : "";
                            return `${rarity}${c.original}`;
                        })
                    });
                }
            }
            results.push(stageOutput);
        }

        console.log(JSON.stringify(results));
    } finally {
        await client.close();
    }
}

run().catch(console.error);
