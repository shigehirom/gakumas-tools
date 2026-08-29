import fs from 'fs';
import path from 'path';
import sharp from 'sharp';
import * as ort from 'onnxruntime-node';

const IMAGE_PATH = '/root/.gemini/antigravity/brain/cae9532c-1904-41f9-a833-34514aec8867/.user_uploaded/media_1787660320737.png';
const PUBLIC_DIR = '/root/gakumas-workspace/gakumas-tools/gakumas-tools/public';
const SKILL_CARD_MODEL = path.join(PUBLIC_DIR, 'skill_card_model.onnx');
const SKILL_CARD_CLASSES = path.join(PUBLIC_DIR, 'skill_card_classes.json');
const P_ITEM_MODEL = path.join(PUBLIC_DIR, 'p_item_model.onnx');
const P_ITEM_CLASSES = path.join(PUBLIC_DIR, 'p_item_classes.json');
const ICON_SIZE = 64;

// マスタデータ読み込み
const SKILL_CARDS_JSON = '/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/json/skill_cards.json';
const P_ITEMS_JSON = '/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/json/p_items.json';

const skillCardsMaster = JSON.parse(fs.readFileSync(SKILL_CARDS_JSON, 'utf8'));
const pItemsMaster = JSON.parse(fs.readFileSync(P_ITEMS_JSON, 'utf8'));

const skillCardMap = new Map(skillCardsMaster.map(c => [c.id, c.name]));
const pItemMap = new Map(pItemsMaster.map(i => [i.id, i.name]));

async function classifyBox(image, box, session, classes) {
    const left = Math.max(0, Math.round(box.x));
    const top = Math.max(0, Math.round(box.y));
    const w = Math.min(image.width - left, Math.round(box.width));
    const h = Math.min(image.height - top, Math.round(box.height));

    const { data } = await sharp(image.pixels, { raw: image.raw })
        .extract({ left, top, width: w, height: h })
        .resize(ICON_SIZE, ICON_SIZE, { fit: 'fill' })
        .removeAlpha()
        .raw()
        .toBuffer({ resolveWithObject: true });

    const input = new Float32Array(3 * ICON_SIZE * ICON_SIZE);
    for (let j = 0; j < ICON_SIZE * ICON_SIZE; j++) {
        input[j] = data[j * 3] / 255;
        input[j + ICON_SIZE * ICON_SIZE] = data[j * 3 + 1] / 255;
        input[j + 2 * ICON_SIZE * ICON_SIZE] = data[j * 3 + 2] / 255;
    }
    const tensor = new ort.Tensor('float32', input, [1, 3, ICON_SIZE, ICON_SIZE]);
    const output = await session.run({ input: tensor });
    const logits = output.classifier.data;
    
    // Top 3 候補を取得
    const indexed = Array.from(logits).map((score, idx) => ({ score, idx }));
    indexed.sort((a, b) => b.score - a.score);

    const top3 = indexed.slice(0, 3).map(item => {
        const idStr = classes[item.idx].split('_')[0];
        const id = idStr === '0' ? 0 : parseInt(idStr, 10);
        return {
            id,
            className: classes[item.idx],
            name: (session === skillCardSession ? skillCardMap.get(id) : pItemMap.get(id)) || '(なし/未登録)',
            score: item.score
        };
    });

    return { top1: top3[0], top2: top3[1], top3: top3[2] };
}

let skillCardSession, pItemSession;

async function main() {
    const imageBuffer = fs.readFileSync(IMAGE_PATH);
    const imageMeta = await sharp(imageBuffer).metadata();
    const width = imageMeta.width;
    const height = imageMeta.height;

    const { data, info } = await sharp(imageBuffer)
        .ensureAlpha()
        .raw()
        .toBuffer({ resolveWithObject: true });

    const image = {
        pixels: data,
        width: info.width,
        height: info.height,
        raw: { width: info.width, height: info.height, channels: 4 },
    };

    [skillCardSession, pItemSession] = await Promise.all([
        ort.InferenceSession.create(SKILL_CARD_MODEL),
        ort.InferenceSession.create(P_ITEM_MODEL),
    ]);
    const skillCardClasses = JSON.parse(fs.readFileSync(SKILL_CARD_CLASSES, 'utf8'));
    const pItemClasses = JSON.parse(fs.readFileSync(P_ITEM_CLASSES, 'utf8'));

    console.log('================================================================');
    console.log('【選抜試験メモリー 抽出結果 vs 正解データ 比較検証】');
    console.log('================================================================\n');

    // ──────────────────────── 1. Pアイテム (5枠) ────────────────────────
    console.log('■ Pアイテム (5枠)');
    const expectedPItems = [
        '花もじゃ（黄）/ カスタム',
        '原点へのチケット / Pアイドル',
        'H.I.Fワッペン',
        '完全制覇でポン / サポート',
        '面白くて心配な子 / サポート'
    ];

    // Pアイテム枠
    const pItemStartX = 18;
    const pItemY = 512;
    const pItemW = 56;
    const pItemH = 56;
    const pItemStep = 87;

    for (let i = 0; i < 5; i++) {
        const box = {
            x: pItemStartX + i * pItemStep,
            y: pItemY,
            width: pItemW,
            height: pItemH
        };
        const res = await classifyBox(image, box, pItemSession, pItemClasses);
        console.log(`[Pアイテム ${i + 1}] 抽出: ID=${res.top1.id.toString().padStart(3, ' ')} 『${res.top1.name}』 (スコア: ${res.top1.score.toFixed(1)}) ｜ 正解: 『${expectedPItems[i]}』`);
    }

    // ──────────────────────── 2. スキルカード (19枚: 7 + 7 + 5) ────────────────────────
    console.log('\n■ スキルカード (19枚: 1行目 7枚 / 2行目 7枚 / 3行目 5枚)');
    const expectedCards = [
        // 1行目 (7枚)
        '日が差す方へ+ / Pアイドル',
        '立ち回りの基本',
        'ウォームアップの基本',
        '巻き返し+ / メモリー',
        '一心不乱+',
        'プライド+',
        '全身全霊+',
        // 2行目 (7枚)
        '涙の思い出',
        'エンターテイナー+ / メモリー',
        'インフルエンサー+ / メモリー',
        'タフネス+ / メモリー',
        'フルスロットル+',
        'アイドルになります+',
        'せーのでぱくっ！+ / サポート',
        // 3行目 (5枚)
        '達成感',
        '眠気',
        'スターライト+',
        '頂点へ+',
        'クライマックス+'
    ];

    // 7列グリッド
    const cardStartX = 16;
    const cardStartY = 624;
    const cardW = 54;
    const cardH = 54;
    const cardStepX = 61.5;
    const cardStepY = 72;

    let c = 0;
    for (let row = 0; row < 3; row++) {
        const colsInRow = row === 2 ? 5 : 7;
        for (let col = 0; col < colsInRow; col++) {
            const idx = c;
            c++;

            const box = {
                x: cardStartX + col * cardStepX,
                y: cardStartY + row * cardStepY,
                width: cardW,
                height: cardH
            };
            const res = await classifyBox(image, box, skillCardSession, skillCardClasses);
            const isMatch = res.top1.name && expectedCards[idx].includes(res.top1.name.replace('+', ''));
            const statusIcon = isMatch ? '✅' : '⚠️';
            console.log(`${statusIcon} [Card ${c.toString().padStart(2, ' ')}] (R${row + 1} C${col + 1}) 抽出: ID=${res.top1.id.toString().padStart(3, ' ')} 『${res.top1.name}』 (スコア: ${res.top1.score.toFixed(1)}) ｜ 正解: 『${expectedCards[idx]}』`);
        }
    }
}

main().catch(console.error);
