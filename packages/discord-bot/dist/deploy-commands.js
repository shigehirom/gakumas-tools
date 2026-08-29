"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.deployCommands = deployCommands;
const discord_js_1 = require("discord.js");
const config_1 = require("./config");
const commands_1 = require("./commands");
async function deployCommands() {
    if (!config_1.config.token) {
        console.error('Error: DISCORD_BOT_TOKEN is not set in environment.');
        process.exit(1);
    }
    if (!config_1.config.clientId) {
        console.error('Error: DISCORD_CLIENT_ID is not set in environment.');
        process.exit(1);
    }
    const rest = new discord_js_1.REST().setToken(config_1.config.token);
    const body = commands_1.commands.map(c => c.data.toJSON());
    try {
        console.log(`[Deploy] Started refreshing ${body.length} application (/) commands.`);
        if (config_1.config.guildId) {
            // Guild specific registration (instant update)
            await rest.put(discord_js_1.Routes.applicationGuildCommands(config_1.config.clientId, config_1.config.guildId), { body });
            console.log(`[Deploy] Successfully registered commands to Guild: ${config_1.config.guildId}`);
        }
        else {
            // Global registration (may take up to an hour for Discord to propagate globally)
            await rest.put(discord_js_1.Routes.applicationCommands(config_1.config.clientId), { body });
            console.log('[Deploy] Successfully registered global commands.');
        }
    }
    catch (error) {
        console.error('[Deploy] Error registering commands:', error);
        throw error;
    }
}
if (require.main === module) {
    deployCommands()
        .then(() => process.exit(0))
        .catch(() => process.exit(1));
}
