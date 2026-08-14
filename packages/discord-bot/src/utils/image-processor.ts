import * as fs from 'fs';
import * as path from 'path';
import sharp from 'sharp';
import * as ort from 'onnxruntime-node';
import { createWorker } from 'tesseract.js';
import { MasterData } from './master-data';

function getPublicDir(): string {
    const candidatePaths = [
        path.resolve(__dirname, '../../../../gakumas-tools/public'),
        path.resolve(process.cwd(), 'gakumas-tools/public'),
        path.resolve(process.cwd(), 'public'),
        '/app/gakumas-tools/public',
        '/root/gakumas-workspace/gakumas-tools/gakumas-tools/public'
    ];
    for (const p of candidatePaths) {
        if (fs.existsSync(p) && fs.existsSync(path.join(p, 'skill_card_model.onnx'))) {
            return p;
        }
    }
    return path.resolve(process.cwd(), 'gakumas-tools/public');
}

const PUBLIC_DIR = getPublicDir();
const TESSERACT_CACHE = path.join(process.cwd(), '.tesseract-cache');

const SKILL_CARD_MODEL = path.join(PUBLIC_DIR, 'skill_card_model.onnx');
const SKILL_CARD_CLASSES = path.join(PUBLIC_DIR, 'skill_card_classes.json');
const P_ITEM_MODEL = path.join(PUBLIC_DIR, 'p_item_model.onnx');
const P_ITEM_CLASSES = path.join(PUBLIC_DIR, 'p_item_classes.json');
const ICON_SIZE = 64;

const PARAMS_REGEXP = /^\s*\d+\s+\d+\s+\d+\s+\d+\s*$/;

let _models: {
    skillCard: { session: ort.InferenceSession; classes: string[] };
    pItem: { session: ort.InferenceSession; classes: string[] };
} | null = null;

async function getModels() {
    if (!_models) {
        const [skillCard, pItem] = await Promise.all([
            ort.InferenceSession.create(SKILL_CARD_MODEL),
            ort.InferenceSession.create(P_ITEM_MODEL),
        ]);
        _models = {
            skillCard: {
                session: skillCard,
                classes: JSON.parse(fs.readFileSync(SKILL_CARD_CLASSES, 'utf8')),
            },
            pItem: {
                session: pItem,
                classes: JSON.parse(fs.readFileSync(P_ITEM_CLASSES, 'utf8')),
            },
        };
    }
    return _models;
}

let _ocrWorker: any = null;
async function getOcrWorker() {
    if (!_ocrWorker) {
        if (!fs.existsSync(TESSERACT_CACHE)) {
            fs.mkdirSync(TESSERACT_CACHE, { recursive: true });
        }
        _ocrWorker = await createWorker('eng', 1, { cachePath: TESSERACT_CACHE });
    }
    return _ocrWorker;
}

function getPItemBoundingBoxes(anchorPoint: { x: number; y: number }, contentWidth: number) {
    const pItemsTL = {
        x: anchorPoint.x - contentWidth * 0.006,
        y: anchorPoint.y + contentWidth * 0.03,
    };
    const pItemsWidth = contentWidth * 0.147;
    const pItemsGap = contentWidth * 0.023;
    const pItemBoxes = [];
    for (let i = 0; i < 4; i++) {
        pItemBoxes.push({
            x: pItemsTL.x + i * (pItemsWidth + pItemsGap),
            y: pItemsTL.y,
            width: pItemsWidth,
            height: pItemsWidth,
        });
    }
    return pItemBoxes;
}

function getSkillCardBoundingBoxes(anchorPoint: { x: number; y: number }, contentWidth: number) {
    const skillCardsTL = {
        x: anchorPoint.x - contentWidth * 0.003,
        y: anchorPoint.y + contentWidth * 0.302,
    };
    const skillCardsWidth = contentWidth * 0.248;
    const skillCardsHGap = contentWidth * 0.023;
    const skillCardsVGap = contentWidth * 0.067;
    const skillCardBoxes = [];
    for (let i = 0; i < 6; i++) {
        skillCardBoxes.push({
            x: skillCardsTL.x + (i % 4) * (skillCardsWidth + skillCardsHGap),
            y: skillCardsTL.y + Math.floor(i / 4) * (skillCardsWidth + skillCardsVGap),
            width: skillCardsWidth,
            height: skillCardsWidth,
        });
    }
    return skillCardBoxes;
}

function binarizeForOcr(image: { pixels: Buffer; width: number; height: number; raw: any }) {
    const { pixels, width, height } = image;
    const out = Buffer.alloc(width * height * 3);
    for (let i = 0, o = 0; i < pixels.length; i += 4, o += 3) {
        const r = pixels[i];
        const g = pixels[i + 1];
        const b = pixels[i + 2];
        const avg = (r + g + b) / 3;
        const isText =
            (Math.abs(r - avg) < 8 &&
                Math.abs(g - avg) < 8 &&
                Math.abs(b - avg) < 8 &&
                r < 185 &&
                g < 185 &&
                b < 185) ||
            (r > 70 && r < 120 && g > 70 && g < 120 && b > 90 && b < 130);
        const v = isText ? 0 : 255;
        out[o] = v;
        out[o + 1] = v;
        out[o + 2] = v;
    }
    const margin = Math.ceil(width * 0.012);
    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            if (
                x >= margin &&
                x < width - margin &&
                y >= margin &&
                y < height - margin
            ) {
                continue;
            }
            const o = (y * width + x) * 3;
            out[o] = out[o + 1] = out[o + 2] = 255;
        }
    }
    return sharp(out, { raw: { width, height, channels: 3 } }).png().toBuffer();
}

function extractLines(result: any) {
    return result.data.blocks
        .map((b: any) => b.paragraphs.map((p: any) => p.lines))
        .flat(2);
}

async function classifyBox(
    image: { pixels: Buffer; width: number; height: number; raw: any },
    box: { x: number; y: number; width: number; height: number },
    session: ort.InferenceSession,
    classes: string[]
): Promise<number> {
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
    const logits = output.classifier.data as Float32Array;
    let argmax = 0;
    for (let k = 1; k < logits.length; k++) {
        if (logits[k] > logits[argmax]) argmax = k;
    }
    const idStr = classes[argmax].split('_')[0];
    return idStr === '0' ? 0 : parseInt(idStr, 10);
}

export interface ParsedMemoryData {
    params: number[];
    pItemIds: number[];
    skillCardIds: number[];
    pIdolId: number | null;
    contestPower: number;
}

export async function processMemoryImage(imageBuffer: Buffer): Promise<ParsedMemoryData> {
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

    const [{ skillCard, pItem }, ocrWorker] = await Promise.all([
        getModels(),
        getOcrWorker(),
    ]);

    const ocrInput = await binarizeForOcr(image);
    const result = await ocrWorker.recognize(ocrInput, {}, { blocks: true });
    const lines = extractLines(result);

    const idx = lines.findIndex((l: any) => PARAMS_REGEXP.test(l.text));
    if (idx < 0 || !lines[idx + 1]) {
        throw new Error('Vo/Da/Vi/HP パラメータ行を検出できませんでした。メモリーのスクリーンショット画像かご確認ください。');
    }

    const paramsLine = lines[idx];
    const pItemsLabelLine = lines[idx + 1];
    const contentWidth = paramsLine.bbox.x1 - pItemsLabelLine.bbox.x0;
    const anchor = { x: pItemsLabelLine.bbox.x0, y: pItemsLabelLine.bbox.y1 };

    const rawParams = (paramsLine.text.match(/\d+/g) || []).map((n: string) => parseInt(n, 10));
    const params = [rawParams[0] || 0, rawParams[1] || 0, rawParams[2] || 0, rawParams[3] || 0];

    const pItemBoxes = getPItemBoundingBoxes(anchor, contentWidth);
    const skillCardBoxes = getSkillCardBoundingBoxes(anchor, contentWidth);

    const pItemIds: number[] = [];
    for (const box of pItemBoxes) {
        const id = await classifyBox(image, box, pItem.session, pItem.classes);
        pItemIds.push(id);
    }
    // 常に4要素に揃える
    while (pItemIds.length < 4) {
        pItemIds.push(0);
    }

    const skillCardIds: number[] = [];
    for (const box of skillCardBoxes) {
        const id = await classifyBox(image, box, skillCard.session, skillCard.classes);
        skillCardIds.push(id);
    }
    // 常に6要素に揃える
    while (skillCardIds.length < 6) {
        skillCardIds.push(0);
    }

    // PアイドルIDの推定
    // 1. Pアイテムの pIdolId から探索
    let pIdolId: number | null = null;
    for (const pId of pItemIds) {
        if (!pId) continue;
        const item = MasterData.getPItemById(pId);
        if (item && item.pIdolId) {
            pIdolId = typeof item.pIdolId === 'number' ? item.pIdolId : parseInt(String(item.pIdolId), 10);
            if (pIdolId > 0) break;
        }
    }

    // 2. スキルカードの pIdolId から探索 (フォールバック)
    if (!pIdolId) {
        for (const sId of skillCardIds) {
            if (!sId) continue;
            const card = MasterData.getSkillCardById(sId);
            if (card && card.pIdolId) {
                pIdolId = typeof card.pIdolId === 'number' ? card.pIdolId : parseInt(String(card.pIdolId), 10);
                if (pIdolId > 0) break;
            }
        }
    }

    // 3. それでも見つからない場合のセーフティフォールバック (null 回避)
    if (!pIdolId) {
        const firstPIdol = MasterData.getPIdols()[0];
        pIdolId = firstPIdol ? firstPIdol.id : 1;
    }

    const contestPower = MasterData.calculateContestPower(params, pItemIds, skillCardIds);

    return {
        params,
        pItemIds,
        skillCardIds,
        pIdolId,
        contestPower,
    };
}
