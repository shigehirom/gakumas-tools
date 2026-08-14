import { spawn } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

export interface CliRunResult {
    stdout: string;
    stderr: string;
    exitCode: number;
}

function resolveCliPath(): { rootDir: string; cliPath: string } {
    const candidateRoots = [
        path.resolve(__dirname, '../../../..'),                 // from /app/packages/discord-bot/src/utils -> /app
        path.resolve(process.cwd()),                          // current working directory (/app or /root/gakumas-workspace/gakumas-tools)
        path.resolve(__dirname, '../../../../gakumas-tools'),  // dev workspace
        '/app',
        '/root/gakumas-workspace/gakumas-tools'
    ];

    for (const root of candidateRoots) {
        const cliPath = path.join(root, 'packages/cli/src/index.ts');
        if (fs.existsSync(cliPath)) {
            return { rootDir: root, cliPath };
        }
    }

    return { 
        rootDir: process.cwd(), 
        cliPath: path.resolve(process.cwd(), 'packages/cli/src/index.ts') 
    };
}

export function runCli(args: string[]): Promise<CliRunResult> {
    const { rootDir, cliPath } = resolveCliPath();

    return new Promise((resolve, reject) => {
        // ts-node バイナリまたは直接 ts-node コマンドを起動
        const tsNodeBin = path.join(rootDir, 'node_modules/.bin/ts-node');
        const executable = fs.existsSync(tsNodeBin) ? tsNodeBin : 'ts-node';

        const child = spawn(executable, [cliPath, ...args], {
            cwd: rootDir,
            env: {
                ...process.env,
                TS_NODE_TRANSPILE_ONLY: 'true'
            }
        });

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        child.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        child.on('close', (code) => {
            resolve({
                stdout,
                stderr,
                exitCode: code ?? 0
            });
        });

        child.on('error', (err) => {
            reject(err);
        });
    });
}
