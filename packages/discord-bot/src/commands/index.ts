import { contestCommand } from './contest';
import { deckCommand } from './deck';
import { recentMemoriesCommand } from './recent-memories';
import { importMemoryCommand } from './import-memory';
import { syncCommand } from './sync';
import { advisoryCommand } from './advisory';
import { compareMemoryCommand } from './compare-memory';
import { recordContestCommand } from './record-contest';
import { syncContestCommand } from './sync-contest';
import { memoryStatsCommand } from './memory-stats';

export const commands = [
    contestCommand,
    deckCommand,
    recentMemoriesCommand,
    importMemoryCommand,
    syncCommand,
    advisoryCommand,
    compareMemoryCommand,
    recordContestCommand,
    syncContestCommand,
    memoryStatsCommand
];

export const commandMap = new Map(commands.map(cmd => [cmd.data.name, cmd]));



