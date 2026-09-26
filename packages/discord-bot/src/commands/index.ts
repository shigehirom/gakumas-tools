import { contestCommand } from './contest';
import { recordContestCommand } from './record-contest';
import { advisoryCommand } from './advisory';
import { memoryCommand } from './memory';
import { syncCommand } from './sync';

export const commands = [
    contestCommand,
    recordContestCommand,
    advisoryCommand,
    memoryCommand,
    syncCommand,
];

export const commandMap = new Map(commands.map(cmd => [cmd.data.name, cmd]));
