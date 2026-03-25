import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const loaderPath = path.join(__dirname, 'esm-loader.mjs');
const loaderUrl = pathToFileURL(loaderPath);

register(loaderUrl);

await import('./list-uncached.mjs');
