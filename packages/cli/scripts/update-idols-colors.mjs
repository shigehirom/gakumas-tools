import { getAuthClient, loadEnvLocal } from './utils/sheetsAuth.mjs';
import { google } from 'googleapis';

const IDOL_COLORS = [
    { id: 1, name: '花海 咲季', role: '生徒', colorName: 'スカーレット / レッド', hex: '#DE3839', rgb: 'rgb(222, 56, 57)' },
    { id: 2, name: '月村 手毬', role: '生徒', colorName: 'アイランドグリーン / 青緑', hex: '#1E7B85', rgb: 'rgb(30, 123, 133)' },
    { id: 3, name: '藤田 ことね', role: '生徒', colorName: 'イエロー / サンフラワー', hex: '#F8B600', rgb: 'rgb(248, 182, 0)' },
    { id: 4, name: '有村 麻央', role: '生徒', colorName: 'ワインレッド / マゼンタ', hex: '#9B1E42', rgb: 'rgb(155, 30, 66)' },
    { id: 5, name: '葛城 リーリヤ', role: '生徒', colorName: 'スノーホワイト / アイスブルー', hex: '#89C3EB', rgb: 'rgb(137, 195, 235)' },
    { id: 6, name: '倉本 千奈', role: '生徒', colorName: 'オレンジ / マリーゴールド', hex: '#ED6D1F', rgb: 'rgb(237, 109, 31)' },
    { id: 7, name: '紫雲 清夏', role: '生徒', colorName: 'ライムグリーン / ミント', hex: '#78C13F', rgb: 'rgb(120, 193, 63)' },
    { id: 8, name: '篠澤 広', role: '生徒', colorName: 'ライトブルー / アクア', hex: '#98D9E8', rgb: 'rgb(152, 217, 232)' },
    { id: 9, name: '姫崎 莉波', role: '生徒', colorName: 'コーラルピンク / サクラ', hex: '#EA7299', rgb: 'rgb(234, 114, 153)' },
    { id: 10, name: '花海 佑芽', role: '生徒', colorName: 'サンセットオレンジ / バーミリオン', hex: '#F05A28', rgb: 'rgb(240, 90, 40)' },
    { id: 11, name: '十王 星南', role: '生徒', colorName: 'ロイヤルゴールド / シャインイエロー', hex: '#D4A017', rgb: 'rgb(212, 160, 23)' },
    { id: 12, name: '秦谷 美鈴', role: '生徒', colorName: 'バイオレット / ラベンダー', hex: '#8C7BB8', rgb: 'rgb(140, 123, 184)' },
    { id: 13, name: '雨夜 燕', role: '生徒', colorName: 'スチールブルー / インディゴ', hex: '#3A6998', rgb: 'rgb(58, 105, 152)' },
    { id: 14, name: '根緒 亜紗里', role: '教員', colorName: 'ミントグリーン / ペールエメラルド', hex: '#92DEBB', rgb: 'rgb(146, 222, 187)' },
];

export async function updateIdolColors(execute = false) {
    loadEnvLocal();
    const auth = await getAuthClient();
    const sheets = google.sheets({ version: 'v4', auth });
    const spreadsheetId = process.env.SYNC_SHEET_ID;

    // 現在の Idols シートを取得
    const res = await sheets.spreadsheets.values.get({
        spreadsheetId,
        range: 'Idols!A1:Z30',
    });

    const rows = res.data.values || [];
    if (rows.length === 0) {
        console.error('Idols sheet is empty.');
        return;
    }

    const header = [...rows[0]];
    // 列ヘッダーの確認
    let roleIdx = header.indexOf('区分');
    let colNameIdx = header.indexOf('カラー系統・名称');
    let hexIdx = header.indexOf('HEX');
    let rgbIdx = header.indexOf('RGB');

    if (roleIdx === -1) {
        roleIdx = header.length;
        header.push('区分');
    }
    if (colNameIdx === -1) {
        colNameIdx = header.length;
        header.push('カラー系統・名称');
    }
    if (hexIdx === -1) {
        hexIdx = header.length;
        header.push('HEX');
    }
    if (rgbIdx === -1) {
        rgbIdx = header.length;
        header.push('RGB');
    }

    const newRows = [header];

    for (let i = 1; i < rows.length; i++) {
        const row = [...rows[i]];
        // パディング
        while (row.length < header.length) {
            row.push('');
        }
        const id = parseInt(row[0], 10);
        const idol = IDOL_COLORS.find(c => c.id === id);
        if (idol) {
            row[roleIdx] = idol.role;
            row[colNameIdx] = idol.colorName;
            row[hexIdx] = idol.hex;
            row[rgbIdx] = idol.rgb;
        }
        newRows.push(row);
    }

    console.log('Result preview:');
    newRows.forEach((r, idx) => console.log(`Row ${idx + 1}:`, r.join(' | ')));

    if (!execute) {
        console.log('\n[Dry Run] Specify --execute to apply changes to Google Sheet.');
        return;
    }

    await sheets.spreadsheets.values.update({
        spreadsheetId,
        range: `Idols!A1:${String.fromCharCode(65 + header.length - 1)}${newRows.length}`,
        valueInputOption: 'USER_ENTERED',
        requestBody: {
            values: newRows,
        },
    });

    console.log('\n[+] Google Sheet Idols updated successfully!');
}

const isMain = process.argv[1] && process.argv[1].includes('update-idols-colors.mjs');
if (isMain) {
    const execute = process.argv.includes('--execute');
    updateIdolColors(execute).catch(err => {
        console.error('Error:', err);
        process.exit(1);
    });
}
