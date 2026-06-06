import fs from "fs";
import path from "path";
import { spawn } from "child_process";
import { Idols, PIdols } from "gakumas-data";
import { sendDiscordMessage } from "./discord";

const GDRIVE_DOCS_DIR = process.env.GDRIVE_DOCS_DIR;

/**
 * Finds the latest contest definition file (e.g., 41_コンテスト対策.md).
 */
function findLatestContestFile() {
  if (!fs.existsSync(GDRIVE_DOCS_DIR)) {
    console.error("Google Drive directory not found:", GDRIVE_DOCS_DIR);
    return null;
  }

  const files = fs.readdirSync(GDRIVE_DOCS_DIR);
  const contestFiles = files
    .filter((f) => f.endsWith("_コンテスト対策.md"))
    .map((f) => ({
      name: f,
      number: parseInt(f.split("_")[0], 10),
    }))
    .filter((f) => !isNaN(f.number))
    .sort((a, b) => b.number - a.number);

  if (contestFiles.length === 0) return null;
  return path.join(GDRIVE_DOCS_DIR, contestFiles[0].name);
}

/**
 * Parses the contest Markdown file to extract stages and idols.
 */
function parseContestMarkdown(filePath) {
  const text = fs.readFileSync(filePath, "utf-8");
  const sections = text.split(/^# /m).filter((s) => s.trim());
  const stages = [];

  for (const section of sections) {
    const lines = section.split("\n").map((l) => l.trimEnd());
    const titleMatch = lines[0].match(/シーズン\s*(\d+)\s*ステージ(\d+)/);
    if (!titleMatch) continue;

    const season = titleMatch[1];
    const stageNum = titleMatch[2];
    const stageId = `${season}-${stageNum}`;

    let currentSection = "";
    const idols = [];

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i];
      const headerMatch = line.match(/^##\s+(.*)/);
      if (headerMatch) {
        if (headerMatch[1].startsWith("アイドル")) currentSection = "idols";
        else currentSection = "";
        continue;
      }

      if (currentSection === "idols" && line.startsWith("- ")) {
        let idolStr = line.substring(2).trim();
        // Extract base name before any brackets
        const baseNameMatch = idolStr.match(/^(.*?)【/);
        const name = baseNameMatch ? baseNameMatch[1].trim() : idolStr.split(" ")[0].trim();
        idols.push(name);
      }
    }

    stages.push({ stageId, idols });
  }

  return stages;
}

/**
 * Triggers automation for newly added memories.
 */
export async function triggerAutomation(memories) {
  const contestFile = findLatestContestFile();
  if (!contestFile) {
    console.log("No contest definition file found.");
    return;
  }

  const stages = parseContestMarkdown(contestFile);
  if (stages.length === 0) {
    console.log("No stages found in the contest file.");
    return;
  }

  const triggeredIdols = new Set();
  const tasks = [];

  for (const memory of memories) {
    const pIdol = PIdols.getById(memory.pIdolId);
    if (!pIdol) continue;
    const idol = Idols.getById(pIdol.idolId);
    if (!idol) continue;

    const idolName = idol.name;

    for (const stage of stages) {
      if (stage.idols.some((name) => idolName.includes(name) || name.includes(idolName))) {
        const key = `${stage.stageId}_${idol.slug}`;
        if (!triggeredIdols.has(key)) {
          triggeredIdols.add(key);
          tasks.push({
            stageId: stage.stageId,
            idolSlug: idol.slug,
            idolName: idol.name,
          });
        }
      }
    }
  }

  if (tasks.length === 0) {
    console.log("No applicable stages found for the new memories.");
    return;
  }

  console.log(`Triggering ${tasks.length} simulations...`);

  for (const task of tasks) {
    // Run simulation in the background
    runSimulation(task);
  }
}

async function runSimulation(task) {
  const { stageId, idolSlug, idolName } = task;
  const cliDir = path.resolve(process.cwd(), "../packages/cli");
  
  // Command: yarn cli contest <stage> --idolName <slug> --gdrive --force
  // Note: Using --force to ensure we recalculate with the new memory
  const args = ["cli", "contest", stageId, "1000", idolSlug, "--gdrive", "--force"];

  console.log(`Running: yarn ${args.join(" ")}`);

  await sendDiscordMessage(`⏳ シミュレーション開始: ${stageId} (${idolName})`);

  const child = spawn("yarn", args, {
    cwd: path.resolve(process.cwd(), ".."),
    stdio: "ignore",
    env: { ...process.env },
  });

  child.on("close", async (code) => {
    if (code === 0) {
      await sendDiscordMessage(`✅ シミュレーション完了: ${stageId} (${idolName})\nGoogle Drive に結果が保存されました。`);
    } else {
      await sendDiscordMessage(`❌ シミュレーション失敗: ${stageId} (${idolName}) (Exit code: ${code})`);
    }
  });
}
