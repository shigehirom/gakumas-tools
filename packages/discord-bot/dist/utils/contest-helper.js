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
exports.getCurrentSeason = getCurrentSeason;
exports.getOptimizedDeckFromFiles = getOptimizedDeckFromFiles;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const config_1 = require("../config");
const master_data_1 = require("./master-data");
/**
 * 現在開催中の最新コンテストシーズンを取得します
 */
function getCurrentSeason() {
    const allStages = master_data_1.MasterData.getStages();
    const contestStages = allStages.filter((s) => s.type === 'contest');
    if (contestStages.length === 0)
        return 50;
    // 最大のシーズン番号を返す
    const seasons = contestStages.map((s) => s.season).filter((n) => typeof n === 'number');
    return Math.max(...seasons);
}
/**
 * 最新の最適化デッキ Markdown ファイルを探索して指定ステージの編成を抽出
 */
function getOptimizedDeckFromFiles(stageNum) {
    const searchDirs = [
        process.env.CLI_DOCS_DIR,
        '/root/gakumas-workspace/shared/documents',
        '/shared/documents',
        '/app/documents',
        '/app/shared/documents',
        path.resolve(process.cwd(), '../../shared/documents'),
        path.resolve(process.cwd(), '../shared/documents'),
        path.resolve(process.cwd(), 'shared/documents'),
        path.resolve(process.cwd(), 'documents'),
        path.resolve(process.cwd(), 'packages/cli'),
        path.resolve(__dirname, '../../../../shared/documents'),
        path.resolve(__dirname, '../../../cli'),
        config_1.config.docsDir
    ].filter(Boolean);
    let allFiles = [];
    for (const dir of searchDirs) {
        if (fs.existsSync(dir)) {
            try {
                const found = fs.readdirSync(dir)
                    .filter(f => f.endsWith('_optimized.md'))
                    .map(f => ({ fullPath: path.join(dir, f), filename: f }));
                allFiles.push(...found);
            }
            catch { }
        }
    }
    if (allFiles.length === 0)
        return null;
    // ファイル名で降順ソート (最新の日付・シーズンのものを取得)
    allFiles.sort((a, b) => b.filename.localeCompare(a.filename));
    const latestFile = allFiles[0].fullPath;
    const content = fs.readFileSync(latestFile, 'utf-8');
    // 総合期待中央値を抽出
    let overallScore;
    const overallMatch = content.match(/総合期待中央値：約\s*([\d,]+)\s*Pt/);
    if (overallMatch) {
        overallScore = parseInt(overallMatch[1].replace(/,/g, ''), 10);
    }
    // 指定ステージのセクションを抽出
    // ### ■ ステージ1
    const stagePattern = new RegExp(`###\\s+■\\s+ステージ${stageNum}([\\s\\S]*?)(?=###\\s+■\\s+ステージ|$)`, 'i');
    const stageMatch = content.match(stagePattern);
    if (!stageMatch)
        return null;
    const stageSection = stageMatch[1];
    let totalScore = 0;
    const totalMatch = stageSection.match(/合計期待中央値：約\s*([\d,]+)\s*Pt/);
    if (totalMatch) {
        totalScore = parseInt(totalMatch[1].replace(/,/g, ''), 10);
    }
    const idols = [];
    const lines = stageSection.split('\n');
    for (const line of lines) {
        // | アイドル | #1 | メイン | サブ | 54000 |
        if (line.startsWith('|') && !line.includes('アイドル') && !line.includes(':---')) {
            const cols = line.split('|').map(c => c.trim()).filter(c => c.length > 0);
            if (cols.length >= 5) {
                const idol = cols[0];
                const rank = cols[1];
                const mainMem = cols[2];
                const subMem = cols[3];
                const medianScore = parseInt(cols[4].replace(/,/g, ''), 10) || 0;
                idols.push({ idol, rank, mainMem, subMem, medianScore });
            }
        }
    }
    return {
        stageNum,
        totalExpectedScore: totalScore,
        idols,
        overallScore,
        sourceFile: path.basename(latestFile)
    };
}
