import fs from 'fs';
import path from 'path';
import readline from 'readline';
import os from 'os';
import { google } from 'googleapis';

// Load environment variables from .env.local manually to avoid external dependencies
export function loadEnvLocal() {
  const envPath = path.resolve(process.cwd(), '.env.local');
  if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf8');
    envContent.split('\n').forEach(line => {
      const match = line.match(/^([^=]+)=(.*)$/);
      if (match) {
        let key = match[1].trim();
        let value = match[2].trim();
        if (value.startsWith('"') && value.endsWith('"')) {
          value = value.slice(1, -1);
        }
        process.env[key] = value;
      }
    });
  }
}

export async function getAuthClient() {
  loadEnvLocal();
  
  const CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
  const CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;

  if (!CLIENT_ID || !CLIENT_SECRET) {
    console.error("Error: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is not set in .env.local");
    process.exit(1);
  }

  const SCOPES = ['https://www.googleapis.com/auth/spreadsheets'];
  const TOKEN_DIR = path.join(os.homedir(), '.config', 'gakumas-tools');
  const TOKEN_PATH = path.join(TOKEN_DIR, 'sheets_tokens.json');

  const oAuth2Client = new google.auth.OAuth2(
    CLIENT_ID,
    CLIENT_SECRET,
    'urn:ietf:wg:oauth:2.0:oob'
  );

  try {
    if (fs.existsSync(TOKEN_PATH)) {
      const token = fs.readFileSync(TOKEN_PATH, 'utf-8');
      oAuth2Client.setCredentials(JSON.parse(token));
      return oAuth2Client;
    }
  } catch (e) {
    console.warn('Error reading stored token, requesting new one...');
  }

  const authUrl = oAuth2Client.generateAuthUrl({
    access_type: 'offline',
    scope: SCOPES,
  });

  console.log('\n==================================================');
  console.log('Authorize this app by visiting this url:');
  console.log(authUrl);
  console.log('==================================================\n');

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return new Promise((resolve, reject) => {
    rl.question('Enter the code from that page here: ', async (code) => {
      rl.close();
      try {
        const { tokens } = await oAuth2Client.getToken(code);
        oAuth2Client.setCredentials(tokens);

        if (!fs.existsSync(TOKEN_DIR)) {
          fs.mkdirSync(TOKEN_DIR, { recursive: true });
        }
        fs.writeFileSync(TOKEN_PATH, JSON.stringify(tokens));
        console.log('Token stored to', TOKEN_PATH);
        resolve(oAuth2Client);
      } catch (err) {
        console.error('Error retrieving access token', err);
        reject(err);
      }
    });
  });
}
