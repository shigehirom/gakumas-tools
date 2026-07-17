import { Worker } from 'node:worker_threads';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const worker = new Worker(path.join(__dirname, 'packages/cli/scripts/worker-boot.mjs'), {
  workerData: {
    idolId: 'saki',
    plan: 'sense',
    stageId: '47-1',
    memories: [],
    runs: 1,
    progressInterval: 100,
    options: { step: true }
  },
  execArgv: ['--no-warnings', '--loader', './scripts/extensionless-loader.mjs']
});

worker.on('message', msg => console.log('Message:', msg));
worker.on('error', err => console.error('Error:', err));
worker.on('exit', code => console.log('Exit:', code));
