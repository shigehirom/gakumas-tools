"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.IDOL_KEY_TO_COLOR = exports.IDOL_COLORS = void 0;
exports.getIdolColor = getIdolColor;
exports.IDOL_COLORS = {
    1: { id: 1, name: '花海 咲季', key: 'saki', colorName: 'スカーレット / レッド', hex: '#DE3839', rgb: [222, 56, 57], decimal: 0xDE3839 },
    2: { id: 2, name: '月村 手毬', key: 'temari', colorName: 'アイランドグリーン / 青緑', hex: '#1E7B85', rgb: [30, 123, 133], decimal: 0x1E7B85 },
    3: { id: 3, name: '藤田 ことね', key: 'kotone', colorName: 'イエロー / サンフラワー', hex: '#F8B600', rgb: [248, 182, 0], decimal: 0xF8B600 },
    4: { id: 4, name: '有村 麻央', key: 'mao', colorName: 'ワインレッド / マゼンタ', hex: '#9B1E42', rgb: [155, 30, 66], decimal: 0x9B1E42 },
    5: { id: 5, name: '葛城 リーリヤ', key: 'lilja', colorName: 'スノーホワイト / アイスブルー', hex: '#89C3EB', rgb: [137, 195, 235], decimal: 0x89C3EB },
    6: { id: 6, name: '倉本 千奈', key: 'china', colorName: 'オレンジ / マリーゴールド', hex: '#ED6D1F', rgb: [237, 109, 31], decimal: 0xED6D1F },
    7: { id: 7, name: '紫雲 清夏', key: 'sumika', colorName: 'ライムグリーン / ミント', hex: '#78C13F', rgb: [120, 193, 63], decimal: 0x78C13F },
    8: { id: 8, name: '篠澤 広', key: 'hiro', colorName: 'ライトブルー / アクア', hex: '#98D9E8', rgb: [152, 217, 232], decimal: 0x98D9E8 },
    9: { id: 9, name: '姫崎 莉波', key: 'rinami', colorName: 'コーラルピンク / サクラ', hex: '#EA7299', rgb: [234, 114, 153], decimal: 0xEA7299 },
    10: { id: 10, name: '花海 佑芽', key: 'ume', colorName: 'サンセットオレンジ / バーミリオン', hex: '#F05A28', rgb: [240, 90, 40], decimal: 0xF05A28 },
    11: { id: 11, name: '十王 星南', key: 'sena', colorName: 'ロイヤルゴールド / シャインイエロー', hex: '#D4A017', rgb: [212, 160, 23], decimal: 0xD4A017 },
    12: { id: 12, name: '秦谷 美鈴', key: 'misuzu', colorName: 'バイオレット / ラベンダー', hex: '#8C7BB8', rgb: [140, 123, 184], decimal: 0x8C7BB8 },
    13: { id: 13, name: '雨夜 燕', key: 'tsubame', colorName: 'スチールブルー / インディゴ', hex: '#3A6998', rgb: [58, 105, 152], decimal: 0x3A6998 },
};
exports.IDOL_KEY_TO_COLOR = Object.values(exports.IDOL_COLORS).reduce((acc, cur) => {
    acc[cur.key] = cur;
    return acc;
}, {});
function getIdolColor(keyOrId) {
    if (typeof keyOrId === 'number') {
        return exports.IDOL_COLORS[keyOrId];
    }
    return exports.IDOL_KEY_TO_COLOR[keyOrId.toLowerCase()];
}
