import { contestCommand } from './contest';
import { deckCommand } from './deck';
import { recentMemoriesCommand } from './recent-memories';
import { importMemoryCommand } from './import-memory';
import { syncCommand } from './sync';

export const commands = [
    contestCommand,
    deckCommand,
    recentMemoriesCommand,
    importMemoryCommand,
    syncCommand
];

export const commandMap = new Map(commands.map(cmd => [cmd.data.name, cmd]));
