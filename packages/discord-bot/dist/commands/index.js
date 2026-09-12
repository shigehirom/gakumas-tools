"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.commandMap = exports.commands = void 0;
const contest_1 = require("./contest");
const deck_1 = require("./deck");
const recent_memories_1 = require("./recent-memories");
const import_memory_1 = require("./import-memory");
const sync_1 = require("./sync");
const advisory_1 = require("./advisory");
const compare_memory_1 = require("./compare-memory");
const record_contest_1 = require("./record-contest");
const sync_contest_1 = require("./sync-contest");
const memory_stats_1 = require("./memory-stats");
exports.commands = [
    contest_1.contestCommand,
    deck_1.deckCommand,
    recent_memories_1.recentMemoriesCommand,
    import_memory_1.importMemoryCommand,
    sync_1.syncCommand,
    advisory_1.advisoryCommand,
    compare_memory_1.compareMemoryCommand,
    record_contest_1.recordContestCommand,
    sync_contest_1.syncContestCommand,
    memory_stats_1.memoryStatsCommand
];
exports.commandMap = new Map(exports.commands.map(cmd => [cmd.data.name, cmd]));
