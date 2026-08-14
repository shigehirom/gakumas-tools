import * as dotenv from 'dotenv';
import * as fs from 'fs';
import * as path from 'path';

// Load .env.local from potential paths
const possiblePaths = [
    path.resolve(process.cwd(), '.env.local'),
    path.resolve(process.cwd(), '../../.env.local'),
    path.resolve(__dirname, '../../../.env.local'),
    path.resolve(__dirname, '../../../../.env.local'),
    path.resolve('/root/gakumas-workspace/gakumas-tools/.env.local')
];

for (const p of possiblePaths) {
    if (fs.existsSync(p)) {
        dotenv.config({ path: p });
        break;
    }
}

export const config = {
    token: process.env.DISCORD_BOT_TOKEN || '',
    clientId: process.env.DISCORD_CLIENT_ID || '',
    guildId: process.env.DISCORD_GUILD_ID || '',
    mongoUri: process.env.MONGODB_URI || 'mongodb://localhost:27017',
    mongoDb: process.env.MONGODB_DB || 'gakumas-tools',
    docsDir: process.env.CLI_DOCS_DIR 
        ? path.resolve(process.cwd(), process.env.CLI_DOCS_DIR)
        : path.resolve('/root/gakumas-workspace/gakumas-tools/packages/cli'),
    userId: process.env.CLI_USER_ID || '755794545861591082'
};
