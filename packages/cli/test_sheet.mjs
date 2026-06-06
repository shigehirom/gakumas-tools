import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './scripts/utils/sheetsAuth.mjs';
loadEnvLocal();
const SHEET_ID = process.env.SYNC_SHEET_ID;
async function run() {
  const auth = await getAuthClient();
  const sheets = google.sheets({ version: 'v4', auth });
  const res = await sheets.spreadsheets.values.get({ spreadsheetId: SHEET_ID, range: 'Support-Cards!A:Z' });
  const rows = res.data.values;
  const h = rows[0];
  const pIdx = h.indexOf('plan_restriction');
  const tIdx = h.indexOf('type');
  const nIdx = h.indexOf('card_name');
  for(let i=1; i<rows.length; i++) {
     if(rows[i] && rows[i][nIdx]) {
         const p = rows[i][pIdx];
         const t = rows[i][tIdx];
         if (!p || p.trim() === '' || !t || t.trim() === '') {
             console.log(`Empty PR/Type for ${rows[i][nIdx]} -> PR: ${p}, Type: ${t}`);
         }
     }
  }
}
run();
