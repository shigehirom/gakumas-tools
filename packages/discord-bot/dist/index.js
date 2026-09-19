"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const discord_js_1 = require("discord.js");
const config_1 = require("./config");
const commands_1 = require("./commands");
const advisory_1 = require("./commands/advisory");
const deploy_commands_1 = require("./deploy-commands");
// プロセス全体のクラッシュ防止ガード
process.on('uncaughtException', (err) => {
    console.error('[Uncaught Exception]', err);
});
process.on('unhandledRejection', (reason, promise) => {
    console.error('[Unhandled Rejection at Promise]', reason);
});
async function main() {
    if (!config_1.config.token) {
        console.error('Error: DISCORD_BOT_TOKEN is not set.');
        console.error('Please set DISCORD_BOT_TOKEN and DISCORD_CLIENT_ID in your .env.local');
        process.exit(1);
    }
    const client = new discord_js_1.Client({
        intents: [
            discord_js_1.GatewayIntentBits.Guilds,
            discord_js_1.GatewayIntentBits.GuildMessages
        ]
    });
    client.once(discord_js_1.Events.ClientReady, (readyClient) => {
        console.log(`[Bot Ready] Logged in as ${readyClient.user.tag}`);
    });
    client.on(discord_js_1.Events.InteractionCreate, async (interaction) => {
        if (interaction.isAutocomplete()) {
            const command = commands_1.commandMap.get(interaction.commandName);
            if (!command || !('autocomplete' in command))
                return;
            try {
                await command.autocomplete(interaction);
            }
            catch (error) {
                console.error(`Error in autocomplete for /${interaction.commandName}:`, error);
            }
            return;
        }
        if (interaction.isStringSelectMenu()) {
            if (interaction.customId.startsWith('advisory_cl:')) {
                try {
                    await (0, advisory_1.handleAdvisoryChecklistInteraction)(interaction);
                }
                catch (error) {
                    console.error('Error in advisory checklist select menu:', error);
                }
                return;
            }
        }
        if (!interaction.isChatInputCommand())
            return;
        const command = commands_1.commandMap.get(interaction.commandName);
        if (!command) {
            console.error(`No command matching ${interaction.commandName} was found.`);
            return;
        }
        try {
            console.log(`[Command Executed] /${interaction.commandName} by ${interaction.user.tag}`);
            await command.execute(interaction);
        }
        catch (error) {
            console.error(`Error executing /${interaction.commandName}:`, error);
            try {
                const replyOptions = {
                    content: '⚠️ コマンド実行中にエラーが発生しました。'
                };
                if (interaction.replied || interaction.deferred) {
                    await interaction.followUp(replyOptions);
                }
                else {
                    await interaction.reply(replyOptions);
                }
            }
            catch (replyError) {
                console.error('Failed to send error reply to Discord:', replyError);
            }
        }
    });
    // Automatically register commands if client ID is provided
    if (config_1.config.clientId) {
        try {
            await (0, deploy_commands_1.deployCommands)();
        }
        catch (e) {
            console.warn('[Warning] Auto command deploy failed, will proceed to login:', e);
        }
    }
    await client.login(config_1.config.token);
}
main().catch((err) => {
    console.error('Bot startup error:', err);
    process.exit(1);
});
