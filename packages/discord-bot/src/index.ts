import { Client, GatewayIntentBits, Events } from 'discord.js';
import { config } from './config';
import { commandMap } from './commands';
import { deployCommands } from './deploy-commands';

// プロセス全体のクラッシュ防止ガード
process.on('uncaughtException', (err) => {
    console.error('[Uncaught Exception]', err);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('[Unhandled Rejection at Promise]', reason);
});

async function main() {
    if (!config.token) {
        console.error('Error: DISCORD_BOT_TOKEN is not set.');
        console.error('Please set DISCORD_BOT_TOKEN and DISCORD_CLIENT_ID in your .env.local');
        process.exit(1);
    }

    const client = new Client({
        intents: [
            GatewayIntentBits.Guilds,
            GatewayIntentBits.GuildMessages
        ]
    });

    client.once(Events.ClientReady, (readyClient) => {
        console.log(`[Bot Ready] Logged in as ${readyClient.user.tag}`);
    });

    client.on(Events.InteractionCreate, async (interaction) => {
        if (!interaction.isChatInputCommand()) return;

        const command = commandMap.get(interaction.commandName);
        if (!command) {
            console.error(`No command matching ${interaction.commandName} was found.`);
            return;
        }

        try {
            console.log(`[Command Executed] /${interaction.commandName} by ${interaction.user.tag}`);
            await command.execute(interaction);
        } catch (error) {
            console.error(`Error executing /${interaction.commandName}:`, error);
            try {
                const replyOptions = { 
                    content: '⚠️ コマンド実行中にエラーが発生しました。'
                };
                if (interaction.replied || interaction.deferred) {
                    await interaction.followUp(replyOptions);
                } else {
                    await interaction.reply(replyOptions);
                }
            } catch (replyError) {
                console.error('Failed to send error reply to Discord:', replyError);
            }
        }
    });

    // Automatically register commands if client ID is provided
    if (config.clientId) {
        try {
            await deployCommands();
        } catch (e) {
            console.warn('[Warning] Auto command deploy failed, will proceed to login:', e);
        }
    }

    await client.login(config.token);
}

main().catch((err) => {
    console.error('Bot startup error:', err);
    process.exit(1);
});
