import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';

loadEnvLocal();
const auth = await getAuthClient();
const sheets = google.sheets({ version: 'v4', auth });
const res = await sheets.spreadsheets.values.get({
  spreadsheetId: process.env.SYNC_SHEET_ID,
  range: 'Idols!A1:Z20',
});
console.log('Current Idols sheet data:');
res.data.values.forEach((r, i) => console.log(i, r));

