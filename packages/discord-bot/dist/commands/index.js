"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.commandMap = exports.commands = void 0;
const contest_1 = require("./contest");
const record_contest_1 = require("./record-contest");
const advisory_1 = require("./advisory");
const memory_1 = require("./memory");
const sync_1 = require("./sync");
exports.commands = [
    contest_1.contestCommand,
    record_contest_1.recordContestCommand,
    advisory_1.advisoryCommand,
    memory_1.memoryCommand,
    sync_1.syncCommand,
];
exports.commandMap = new Map(exports.commands.map(cmd => [cmd.data.name, cmd]));
