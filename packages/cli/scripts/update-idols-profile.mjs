/**
 * update-idols-profile.mjs
 * Google スプレッドシートの `Idols` シート（G1:V15）に各アイドルの公式プロファイルを追記するスクリプト
 * - 年齢、身長、体重、3サイズ(B/W/H)は単位なしの数値として記録
 * - 誕生日は先頭にシングルクォートを付与してテキストとして記録（勝手に2026年の日付に変換されるのを防止）
 */

import { google } from 'googleapis';
import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';
import fs from 'fs';

loadEnvLocal();

const SHEET_ID = process.env.SYNC_SHEET_ID;
if (!SHEET_ID) {
    console.error('Error: SYNC_SHEET_ID must be set in .env.local');
    process.exit(1);
}

const args = process.argv.slice(2);
const execute = args.includes('--execute');

const profiles = JSON.parse(fs.readFileSync('/tmp/idols_profiles_clean.json', 'utf-8'));

// Header for G1:V1
const NEW_HEADERS = [
    'CV',
    '学年・クラス',
    '年齢',
    '誕生日',
    '血液型',
    '身長',
    '体重',
    'バスト',
    'ウエスト',
    'ヒップ',
    '利き手',
    '出身地',
    '居住地',
    '入学区分',
    '趣味',
    '特技'
];

async function updateProfiles() {
    console.log(`[update-idols-profile] Connecting to Google Sheets (${SHEET_ID})...`);
    const auth = await getAuthClient();
    const sheets = google.sheets({ version: 'v4', auth });

    // Read current rows to match by ID
    const res = await sheets.spreadsheets.values.get({
        spreadsheetId: SHEET_ID,
        range: 'Idols!A1:F15',
    });

    const rows = res.data.values || [];
    if (rows.length < 2) {
        console.error('Error: Idols sheet has no rows.');
        return;
    }

    const profileMap = new Map();
    for (const p of profiles) {
        profileMap.set(p.id, p);
    }

    const updateValues = [NEW_HEADERS];

    console.log(`\n--- Idols Profile Update Preview (${execute ? 'EXECUTE' : 'DRY RUN'}) ---`);
    console.log('Columns: G=' + NEW_HEADERS.join(', '));

    for (let i = 1; i < rows.length; i++) {
        const row = rows[i];
        const id = parseInt(row[0], 10);
        const name = row[1] || '';
        const p = profileMap.get(id);

        if (!p) {
            console.log(`[${id}] ${name}: (No profile data found)`);
            updateValues.push(Array(NEW_HEADERS.length).fill(''));
            continue;
        }

        const classStr = p.id === 14 ? '担任講師' : `${p.affiliation} ${p.class}`;

        // Parse numerics
        const ageMatch = p.age.match(/\d+/);
        const ageNum = ageMatch ? parseInt(ageMatch[0], 10) : '';

        const heightMatch = p.height.match(/\d+/);
        const heightNum = heightMatch ? parseInt(heightMatch[0], 10) : '';

        const weightMatch = p.weight.match(/\d+/);
        const weightNum = weightMatch ? parseInt(weightMatch[0], 10) : '';

        // B/W/H
        const bwhMatch = (p.bwh || '').match(/B(\d+)\s*\/\s*W(\d+)\s*\/\s*H(\d+)/);
        const bustNum = bwhMatch ? parseInt(bwhMatch[1], 10) : '';
        const waistNum = bwhMatch ? parseInt(bwhMatch[2], 10) : '';
        const hipNum = bwhMatch ? parseInt(bwhMatch[3], 10) : '';

        // Birthday: prefix with single quote to prevent Google Sheets from auto-converting to 2026-XX-XX
        let bdayStr = p.birthday || '';
        if (bdayStr && bdayStr !== '-') {
            // e.g. "04月02日" -> "'4月2日"
            bdayStr = bdayStr
                .replace(/^0(\d)月/, '$1月')
                .replace(/0(\d)日/, '$1日');
            bdayStr = `'${bdayStr}`;
        } else {
            bdayStr = '';
        }

        const rowData = [
            p.cv,
            classStr,
            ageNum,
            bdayStr,
            p.blood_type === '-' ? '' : p.blood_type,
            heightNum,
            weightNum,
            bustNum,
            waistNum,
            hipNum,
            p.dominant_hand === '-' ? '' : p.dominant_hand,
            p.hometown === '-' ? '' : p.hometown,
            p.residence === '-' ? '' : p.residence,
            p.enrollment,
            p.hobby === '-' ? '' : p.hobby,
            p.skill === '-' ? '' : p.skill
        ];

        updateValues.push(rowData);
        console.log(`[${id}] ${name}: CV=${p.cv} | ${classStr} | 年齢=${ageNum} | 誕=${bdayStr} | 身長=${heightNum} | 体重=${weightNum} | B=${bustNum} W=${waistNum} H=${hipNum}`);
    }

    if (execute) {
        console.log(`\nWriting to Google Sheets Idols!G1:V${updateValues.length}...`);
        await sheets.spreadsheets.values.update({
            spreadsheetId: SHEET_ID,
            range: `Idols!G1:V${updateValues.length}`,
            valueInputOption: 'USER_ENTERED',
            requestBody: {
                values: updateValues,
            },
        });
        console.log('[+] Successfully updated Idols profile columns (G to V) in Google Sheets!');
    } else {
        console.log('\n[Dry Run] Specify --execute to write changes to Google Sheets.');
    }
}

updateProfiles().catch(err => {
    console.error('Failed to update profiles:', err);
    process.exit(1);
});
