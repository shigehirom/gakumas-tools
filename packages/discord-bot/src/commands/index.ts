import { contestCommand } from './contest';
import { deckCommand } from './deck';
import { recentMemoriesCommand } from './recent-memories';
import { importMemoryCommand } from './import-memory';

export const commands = [
    contestCommand,
    deckCommand,
    recentMemoriesCommand,
    importMemoryCommand
];

export const commandMap = new Map(commands.map(cmd => [cmd.data.name, cmd]));
