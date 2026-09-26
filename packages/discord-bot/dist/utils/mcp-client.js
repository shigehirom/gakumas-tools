"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getMcpClient = getMcpClient;
exports.callMcpTool = callMcpTool;
exports.getMcpImage = getMcpImage;
const index_js_1 = require("@modelcontextprotocol/sdk/client/index.js");
const sse_js_1 = require("@modelcontextprotocol/sdk/client/sse.js");
const config_1 = require("../config");
let clientInstance = null;
let transportInstance = null;
let connectionPromise = null;
/**
 * MCP サーバーへの接続を取得（シングルトン管理・切断時自動再接続）
 */
async function getMcpClient() {
    if (clientInstance) {
        return clientInstance;
    }
    if (connectionPromise) {
        return connectionPromise;
    }
    connectionPromise = (async () => {
        try {
            console.log(`[mcp-client] Connecting to MCP server at ${config_1.config.mcpServerUrl}...`);
            const mcpUrl = new URL(config_1.config.mcpServerUrl);
            const transport = new sse_js_1.SSEClientTransport(mcpUrl);
            const client = new index_js_1.Client({
                name: 'gakumas-discord-bot',
                version: '1.0.0',
            }, {
                capabilities: {},
            });
            await client.connect(transport);
            clientInstance = client;
            transportInstance = transport;
            transport.onclose = () => {
                console.warn('[mcp-client] MCP connection closed.');
                clientInstance = null;
                transportInstance = null;
                connectionPromise = null;
            };
            transport.onerror = (err) => {
                console.error('[mcp-client] MCP transport error:', err);
                clientInstance = null;
                transportInstance = null;
                connectionPromise = null;
            };
            console.log('[mcp-client] Connected to MCP server successfully.');
            return client;
        }
        catch (err) {
            console.error('[mcp-client] Failed to connect to MCP server:', err);
            clientInstance = null;
            transportInstance = null;
            connectionPromise = null;
            throw err;
        }
    })();
    return connectionPromise;
}
/**
 * 汎用 MCP ツール呼び出し
 */
async function callMcpTool(name, args = {}) {
    const client = await getMcpClient();
    try {
        const result = await client.callTool({
            name,
            arguments: args,
        });
        return result;
    }
    catch (err) {
        // 切断されていた場合はインスタンスをリセットして1回だけ再試行
        console.warn(`[mcp-client] Error calling tool ${name}, retrying once:`, err);
        clientInstance = null;
        transportInstance = null;
        connectionPromise = null;
        const retryClient = await getMcpClient();
        return await retryClient.callTool({
            name,
            arguments: args,
        });
    }
}
/**
 * 画像生成ツールを呼び出し、Buffer またはエラーを返す
 */
async function getMcpImage(toolName, toolArgs) {
    try {
        const result = await callMcpTool(toolName, toolArgs);
        if (!result || !result.content || !Array.isArray(result.content)) {
            return { buffer: null, error: 'MCP サーバーからの応答が不正です。' };
        }
        // 画像コンテンツの探索
        for (const item of result.content) {
            if (item.type === 'image' && item.data) {
                const buf = Buffer.from(item.data, 'base64');
                return { buffer: buf };
            }
        }
        // テキストのみの場合はエラーメッセージとして扱う
        for (const item of result.content) {
            if (item.type === 'text' && item.text) {
                return { buffer: null, error: item.text };
            }
        }
        return { buffer: null, error: '画像データが含まれていませんでした。' };
    }
    catch (err) {
        return { buffer: null, error: `MCP ツール呼出エラー (${toolName}): ${err.message}` };
    }
}
