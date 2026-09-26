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
exports.config = void 0;
const dotenv = __importStar(require("dotenv"));
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
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
exports.config = {
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
