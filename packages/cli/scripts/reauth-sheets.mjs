import fs from 'fs';
import path from 'path';
import readline from 'readline';
import os from 'os';
import { google } from 'googleapis';
import { loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();

const CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;

if (!CLIENT_ID || !CLIENT_SECRET) {
  console.error("Error: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is not set in .env.local");
  process.exit(1);
}

const SCOPES = ['https://www.googleapis.com/auth/spreadsheets'];
const oAuth2Client = new google.auth.OAuth2(
  CLIENT_ID,
  CLIENT_SECRET,
  'urn:ietf:wg:oauth:2.0:oob'
);

const authUrl = oAuth2Client.generateAuthUrl({
  access_type: 'offline',
  prompt: 'consent',
  scope: SCOPES,
});

console.log('\n================================================================');
console.log('🔗 以下のURLをブラウザで開き、Googleアカウントで認証してください:');
console.log(authUrl);
console.log('================================================================\n');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

rl.question('📋 ブラウザに表示された認証コードをここに貼り付けて Enter を押してください: ', async (code) => {
  rl.close();
  try {
    const { tokens } = await oAuth2Client.getToken(code.trim());
    oAuth2Client.setCredentials(tokens);

    const tokenPaths = [
      path.join(os.homedir(), '.config', 'gakumas-tools', 'sheets_tokens.json'),
      path.resolve(process.cwd(), '.config/gakumas-tools/sheets_tokens.json'),
      path.resolve('/root/gakumas-workspace/gakumas-tools/.config/gakumas-tools/sheets_tokens.json'),
    ];

    for (const p of tokenPaths) {
      try {
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, JSON.stringify(tokens, null, 2), 'utf-8');
        console.log('✅ トークンを保存しました:', p);
      } catch (e) {}
    }

    console.log('\n🎉 Google Sheets OAuth の再認証が完了しました！');
  } catch (err) {
    console.error('❌ トークンの取得に失敗しました:', err);
    process.exit(1);
  }
});
