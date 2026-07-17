import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CACHE_FILE = path.join(__dirname, '.github-upstream-last-commit');
const PROJECT_ROOT = path.join(__dirname, '..');

// Read environment variables from .env or .env.local manually to avoid external dependency
function loadEnv() {
  const envFiles = [
    path.join(PROJECT_ROOT, '.env.local'),
    path.join(PROJECT_ROOT, '.env')
  ];

  for (const envFile of envFiles) {
    if (fs.existsSync(envFile)) {
      const content = fs.readFileSync(envFile, 'utf8');
      const lines = content.split('\n');
      for (const line of lines) {
        // Match key=value pattern, ignoring comments
        const match = line.match(/^\s*([^#=]+)\s*=\s*(.*)$/);
        if (match) {
          const key = match[1].trim();
          let value = match[2].trim();
          // Remove quotes if present
          if ((value.startsWith('"') && value.endsWith('"')) || 
              (value.startsWith("'") && value.endsWith("'"))) {
            value = value.substring(1, value.length - 1);
          }
          if (!process.env[key]) {
            process.env[key] = value;
          }
        }
      }
    }
  }
}

loadEnv();

const webhookUrl = process.env.DISCORD_WEBHOOK_URL;
if (!webhookUrl) {
  console.error('Error: DISCORD_WEBHOOK_URL is not set in .env or .env.local');
  process.exit(1);
}

const UPSTREAM_REPO = 'surisuririsu/gakumas-tools';
const UPSTREAM_BRANCH = 'master';

async function fetchCommits() {
  const url = `https://api.github.com/repos/${UPSTREAM_REPO}/commits?sha=${UPSTREAM_BRANCH}`;
  const response = await fetch(url, {
    headers: {
      'User-Agent': 'gakumas-tools-upstream-notifier'
    }
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch commits from GitHub: ${response.status} ${response.statusText}`);
  }

  return await response.json();
}

async function sendDiscordNotification(embeds) {
  const payload = { embeds };
  const response = await fetch(webhookUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    let errorDetails = '';
    try {
      errorDetails = await response.text();
    } catch (e) {
      errorDetails = 'Could not read response body';
    }
    console.error('Failed Discord Webhook Payload:', JSON.stringify(payload, null, 2));
    throw new Error(`Failed to send Discord notification: ${response.status} ${response.statusText}. Details: ${errorDetails}`);
  }
}

function createEmbed(commitObj, embedTitle) {
  const commit = commitObj.commit;
  const authorName = commit.author?.name || 'Unknown';
  const authorDate = commit.author?.date || new Date().toISOString();
  const message = commit.message;
  const sha = commitObj.sha;
  const url = commitObj.html_url;

  // Format message: keep only the first line for the title, and put the rest in description
  const lines = message.split('\n');
  const summary = lines[0];
  const details = lines.slice(1).join('\n').trim();

  return {
    title: summary,
    url: url,
    description: details ? `\`\`\`\n${details}\n\`\`\`` : undefined,
    color: 5814783, // Purple
    fields: [
      {
        name: 'Repository',
        value: `surisuririsu/gakumas-tools`,
        inline: true
      },
      {
        name: 'Commit',
        value: `[\`${sha.substring(0, 7)}\`](${url})`,
        inline: true
      },
      {
        name: 'Author',
        value: authorName,
        inline: true
      }
    ],
    footer: {
      text: `${new Date(authorDate).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' })}`
    }
  };
}

async function main() {
  const isTest = process.argv.includes('--test');

  try {
    console.log(`[${new Date().toISOString()}] Checking upstream updates for ${UPSTREAM_REPO}...`);
    const commits = await fetchCommits();
    if (!commits || commits.length === 0) {
      console.log('No commits found.');
      return;
    }

    const latestCommitSha = commits[0].sha;
    
    if (isTest) {
      console.log('Test mode enabled. Sending the latest commit as a test notification...');
      const testEmbed = createEmbed(commits[0], 'Test Notification');
      // Add a test title override to identify the notification type
      testEmbed.title = `🧪 [TEST] ${testEmbed.title}`;
      await sendDiscordNotification([testEmbed]);
      console.log('Test notification sent successfully.');
      return;
    }

    let lastNotifiedSha = '';
    if (fs.existsSync(CACHE_FILE)) {
      lastNotifiedSha = fs.readFileSync(CACHE_FILE, 'utf8').trim();
    }

    if (!lastNotifiedSha) {
      console.log('No cache found. Initializing cache with the latest commit...');
      fs.writeFileSync(CACHE_FILE, latestCommitSha, 'utf8');
      
      // Notify starting monitoring
      const startEmbed = {
        title: '🔄 アップストリーム更新監視の開始',
        description: `\`${UPSTREAM_REPO}\` の監視を開始しました。\n現在の最新コミット: [\`${latestCommitSha.substring(0, 7)}\`](${commits[0].html_url})\n\n今後、新しい更新を検知した際にここに通知します。`,
        color: 3447003, // Blue
        timestamp: new Date().toISOString()
      };
      await sendDiscordNotification([startEmbed]);
      console.log(`Initialized cache to ${latestCommitSha} and sent initiation notification.`);
      return;
    }

    if (lastNotifiedSha === latestCommitSha) {
      console.log('No new updates. Upstream is up to date.');
      return;
    }

    // Find commits since the last notified one
    const index = commits.findIndex(c => c.sha === lastNotifiedSha);
    let newCommits = [];

    if (index === -1) {
      console.warn(`Last notified commit (${lastNotifiedSha}) not found in the recent commits list. Notifying the last 5 commits.`);
      newCommits = commits.slice(0, 5);
    } else {
      newCommits = commits.slice(0, index);
    }

    // Sort to show oldest first (chronological order)
    newCommits.reverse();

    console.log(`Found ${newCommits.length} new commit(s).`);

    // Discord message limits: max 10 embeds per message, and total size of all embeds must not exceed 6000 chars.
    function getEmbedSize(embed) {
      let size = 0;
      if (embed.title) size += embed.title.length;
      if (embed.description) size += embed.description.length;
      if (embed.footer && embed.footer.text) size += embed.footer.text.length;
      if (embed.author && embed.author.name) size += embed.author.name.length;
      if (embed.fields) {
        for (const f of embed.fields) {
          size += f.name.length + f.value.length;
        }
      }
      return size;
    }

    let currentEmbeds = [];
    let currentSize = 0;

    for (const commit of newCommits) {
      const embed = createEmbed(commit);
      let embedSize = getEmbedSize(embed);

      // 単一の embed が 5500文字を超える場合は、description を切り詰めて安全にする
      if (embedSize > 5500) {
        const excess = embedSize - 5500;
        if (embed.description && embed.description.length > excess) {
          embed.description = embed.description.substring(0, embed.description.length - excess - 20) + '... (truncated)';
          embedSize = getEmbedSize(embed);
        }
      }

      // 次の embed を加えた合計が 5800文字を超える、または 10件に達する場合は送信
      if (currentEmbeds.length >= 10 || (currentSize + embedSize) > 5800) {
        await sendDiscordNotification(currentEmbeds);
        currentEmbeds = [embed];
        currentSize = embedSize;
      } else {
        currentEmbeds.push(embed);
        currentSize += embedSize;
      }
    }

    if (currentEmbeds.length > 0) {
      await sendDiscordNotification(currentEmbeds);
    }

    fs.writeFileSync(CACHE_FILE, latestCommitSha, 'utf8');
    console.log(`Updated cache to ${latestCommitSha} and notified ${newCommits.length} commits.`);
  } catch (error) {
    console.error('Error in check-upstream script:', error);
    process.exit(1);
  }
}

main();
