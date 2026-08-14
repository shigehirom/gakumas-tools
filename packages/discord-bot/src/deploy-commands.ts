import { REST, Routes } from 'discord.js';
import { config } from './config';
import { commands } from './commands';

export async function deployCommands() {
    if (!config.token) {
        console.error('Error: DISCORD_BOT_TOKEN is not set in environment.');
        process.exit(1);
    }
    if (!config.clientId) {
        console.error('Error: DISCORD_CLIENT_ID is not set in environment.');
        process.exit(1);
    }

    const rest = new REST().setToken(config.token);
    const body = commands.map(c => c.data.toJSON());

    try {
        console.log(`[Deploy] Started refreshing ${body.length} application (/) commands.`);

        if (config.guildId) {
            // Guild specific registration (instant update)
            await rest.put(
                Routes.applicationGuildCommands(config.clientId, config.guildId),
                { body }
            );
            console.log(`[Deploy] Successfully registered commands to Guild: ${config.guildId}`);
        } else {
            // Global registration (may take up to an hour for Discord to propagate globally)
            await rest.put(
                Routes.applicationCommands(config.clientId),
                { body }
            );
            console.log('[Deploy] Successfully registered global commands.');
        }
    } catch (error) {
        console.error('[Deploy] Error registering commands:', error);
        throw error;
    }
}

if (require.main === module) {
    deployCommands()
        .then(() => process.exit(0))
        .catch(() => process.exit(1));
}
