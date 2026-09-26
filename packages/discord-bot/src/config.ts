import * as dotenv from 'dotenv';
import * as fs from 'fs';
import * as path from 'path';

// Load .env / .env.local from potential paths
const possiblePaths = [
    path.resolve(process.cwd(), '.env'),
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
    instructionsDir: process.env.CLI_INSTRUCTIONS_DIR || '/root/gakumas-workspace/shared/agent-instructions',
    geminiApiKey: process.env.GEMINI_API_KEY || '',
    userId: process.env.CLI_USER_ID || '755794545861591082',
    syncSheetId: process.env.SYNC_SHEET_ID || '',
    mcpServerUrl: process.env.MCP_SERVER_URL || 'http://192.168.100.32:30081/sse',
};


