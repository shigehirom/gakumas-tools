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
exports.runCli = runCli;
const child_process_1 = require("child_process");
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
function resolveCliPath() {
    const candidateRoots = [
        path.resolve(__dirname, '../../../..'), // from /app/packages/discord-bot/src/utils -> /app
        path.resolve(process.cwd()), // current working directory (/app or /root/gakumas-workspace/gakumas-tools)
        path.resolve(__dirname, '../../../../gakumas-tools'), // dev workspace
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
function runCli(args) {
    const { rootDir, cliPath } = resolveCliPath();
    return new Promise((resolve, reject) => {
        // ts-node バイナリまたは直接 ts-node コマンドを起動
        const tsNodeBin = path.join(rootDir, 'node_modules/.bin/ts-node');
        const executable = fs.existsSync(tsNodeBin) ? tsNodeBin : 'ts-node';
        const child = (0, child_process_1.spawn)(executable, [cliPath, ...args], {
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
