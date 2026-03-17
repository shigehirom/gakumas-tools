import fs from "fs";
import { SkillCards, PIdols, PItems, Customizations, Idols } from "gakumas-data";

export function parseMarkdown(filePath) {
    const text = fs.readFileSync(filePath, "utf-8");
    const sections = text.split(/^# /m).filter(s => s.trim());
    
    let parsedData = [];

    for (const section of sections) {
        const lines = section.split("\n").map(l => l.trimEnd());
        const titleMatch = lines[0].match(/シーズン\s*(\d+)\s*ステージ(\d+)/);
        if (!titleMatch) continue;
        
        const season = parseInt(titleMatch[1], 10);
        const stage = parseInt(titleMatch[2], 10);
        
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
                idols.push(line.substring(2));
            } else if (currentSection === "pitems") {
                const itemMatch = line.match(/^\d+\.\s+(.*)/);
                if (itemMatch) {
                    const itemName = itemMatch[1].trim();
                    if (currentSubTarget === "汎用") {
                        genericPItems.push(itemName);
                    } else {
                        if (!specialPItems[currentSubTarget]) specialPItems[currentSubTarget] = [];
                        specialPItems[currentSubTarget].push(itemName);
                    }
                }
            } else if (currentSection === "memories") {
                const memMatch = line.match(/^\d+\.\s+(.*)/);
                if (memMatch) {
                    const memStr = memMatch[1].trim();
                    const memInfo = parseMemoryStr(memStr);
                    if (currentSubTarget === "汎用") {
                        genericMemories.push(memInfo);
                        lastMemoryIdx = genericMemories.length - 1;
                    } else {
                        // Normally this doesn't happen in the example provided, but supported anyway
                        if (!specialMemories[currentSubTarget]) specialMemories[currentSubTarget] = [];
                        specialMemories[currentSubTarget].push(memInfo);
                        lastMemoryIdx = specialMemories[currentSubTarget].length - 1;
                    }
                } else if (line.match(/^\s+-\s+(.*)/)) {
                    // Indented specific override
                    const subMemMatch = line.match(/^\s+-\s+(.*?)\s+\[(.*?)\]/);
                    if (subMemMatch) {
                        const memInfo = parseMemoryStr(subMemMatch[1].trim());
                        const targetIdol = subMemMatch[2].trim();
                        if (!specialMemories[targetIdol]) specialMemories[targetIdol] = {};
                        specialMemories[targetIdol][lastMemoryIdx] = memInfo; // Maps which index it overrides
                    } else {
                        // No specific idol, just alternative? The current example has idols in braces
                        const subMemMatchAlt = line.match(/^\s+-\s+(.*)/);
                        if (subMemMatchAlt) {
                            // If it's just an alternative without brackets, we can store it somehow
                        }
                    }
                }
            }
        }

        parsedData.push({
            season, stage, idols, genericPItems, specialPItems, genericMemories, specialMemories
        });
    }

    return parsedData;
}

function parseMemoryStr(str) {
    const orig = str;
    let cardName = str;
    let customNames = [];
    const parenMatch = str.match(/\((.*?)\)/);
    if (parenMatch) {
        customNames = parenMatch[1].split(",").map(s => s.trim());
        cardName = str.substring(0, str.indexOf("(")).trim();
    }
    return { name: cardName, customizations: customNames, original: orig };
}

console.log(JSON.stringify(parseMarkdown(process.argv[2]), null, 2));
