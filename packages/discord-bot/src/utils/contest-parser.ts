import sharp from 'sharp';
import { config } from '../config';

export interface StageResult {
    myScore: number;
    enemyScore: number;
    result: 'WIN' | 'LOSE' | 'DRAW';
}

export interface OpponentCandidate {
    position: number; // 1: top, 2: middle, 3: bottom
    name: string;
    expectedPt: number;
    totalPower: number;
}

export interface ContestAnalysisResult {
    remainingMatches: number; // e.g. 5 (from 5/5)
    matchIndex: number; // 1 to 5 (5/5 -> 1, 4/5 -> 2, ..., 1/5 -> 5)
    opponent: {
        name: string;
        grade: number; // 1 to 3
    };
    overallResult: 'WIN' | 'LOSE';
    earnedPt: number;
    stages: {
        stage1: StageResult;
        stage2: StageResult;
        stage3: StageResult;
    };
    extra: {
        fans: number;
        coins: number;
        currentPt: number;
        currentRank: number;
    };
}

interface RawGeminiOutput {
    remainingAttemptsStr: string; // e.g. "5/5"
    candidates: {
        position: number;
        name: string;
        totalPower: number;
        expectedPt: number;
    }[];
    stage1: {
        myScore: number;
        enemyScore: number;
        result: 'WIN' | 'LOSE';
    };
    stage2: {
        myScore: number;
        enemyScore: number;
        result: 'WIN' | 'LOSE';
    };
    stage3: {
        myScore: number;
        enemyScore: number;
        result: 'WIN' | 'LOSE';
    };
    overallResult: 'WIN' | 'LOSE';
    earnedPt: number;
    coins: number;
    fans: number;
    currentPt: number;
    currentRank: number;
}

/**
 * 3枚のコンテストスクリーンショットからGemini APIを用いて結果を構造化抽出する
 * @param imageBuffers [画像①(対戦相手), 画像②(対戦結果), 画像③(獲得Pt)]
 * @param apiKey Gemini API Key (省略時は config.geminiApiKey を使用)
 */
export async function parseContestImages(
    imageBuffers: [Buffer, Buffer, Buffer],
    apiKey?: string
): Promise<ContestAnalysisResult> {
    const key = apiKey || config.geminiApiKey;
    if (!key) {
        throw new Error('Gemini APIキーが設定されていません。GEMINI_API_KEY を環境変数または .env.local に設定してください。');
    }

    // 画像をリサイズ & JPEG圧縮して送信サイズを軽量化（1枚2〜5MB -> 100〜150KB）
    const compressedImages = await Promise.all(
        imageBuffers.map(async (buf) => {
            try {
                return await sharp(buf)
                    .resize({ width: 1280, height: 1280, fit: 'inside', withoutEnlargement: true })
                    .jpeg({ quality: 80 })
                    .toBuffer();
            } catch (err) {
                console.warn('[contest-parser] sharp resize failed, using original buffer:', err);
                return buf;
            }
        })
    );

    const base64Images = compressedImages.map(buf => buf.toString('base64'));

    const prompt = `
You are analyzing 3 sequential screenshots from the mobile game "Gakuen Idolmaster (学園アイドルマスター)" contest mode.

Image 1 (First image): Opponent selection screen before the match.
Image 2 (Second image): Match result screen showing 3 stages.
Image 3 (Third image): Final points and rewards screen after the match.

Please extract the following information accurately:

1. From Image 1:
   - Remaining match count text on top-right (e.g., "5/5", "4/5", "3/5", "2/5", "1/5").
   - 3 opponent candidate cards (Top = position 1, Middle = position 2, Bottom = position 3):
     - position (1, 2, or 3)
     - name (the player name string under the total power)
     - totalPower (the integer of 総合力合計, e.g. 208791)
     - expectedPt (the integer of +XXXPt on the card, e.g. 142)

2. From Image 2:
   - Stage 1: myScore (left side integer, ignore comma), enemyScore (right side integer, ignore comma), result ("WIN" or "LOSE")
   - Stage 2: myScore (left side integer, ignore comma), enemyScore (right side integer, ignore comma), result ("WIN" or "LOSE")
   - Stage 3: myScore (left side integer, ignore comma), enemyScore (right side integer, ignore comma), result ("WIN" or "LOSE")

3. From Image 3:
   - overallResult ("WIN" or "LOSE" at the top)
   - earnedPt (the integer in +XX next to Pt, e.g. 90)
   - coins (the integer in +XX next to the coin/medal icon, e.g. 10)
   - fans (the integer in +XXX next to ファン数, e.g. 989)
   - currentPt (the integer of total Pt, e.g. 4649)
   - currentRank (the integer next to the crown icon, e.g. 203)

Respond strictly with valid JSON matching this schema:
{
  "remainingAttemptsStr": "5/5",
  "candidates": [
    { "position": 1, "name": "...", "totalPower": 0, "expectedPt": 0 },
    { "position": 2, "name": "...", "totalPower": 0, "expectedPt": 0 },
    { "position": 3, "name": "...", "totalPower": 0, "expectedPt": 0 }
  ],
  "stage1": { "myScore": 0, "enemyScore": 0, "result": "WIN" },
  "stage2": { "myScore": 0, "enemyScore": 0, "result": "LOSE" },
  "stage3": { "myScore": 0, "enemyScore": 0, "result": "WIN" },
  "overallResult": "WIN",
  "earnedPt": 0,
  "coins": 0,
  "fans": 0,
  "currentPt": 0,
  "currentRank": 0
}
`;

    const models = [
        'gemini-3.6-flash',
        'gemini-3.5-flash',
        'gemini-flash-latest',
        'gemini-3.7-flash',
        'gemini-3.8-flash'
    ];

    let lastError: Error | null = null;

    for (const model of models) {
        for (let attempt = 1; attempt <= 2; attempt++) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 45000);

                const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`;
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: controller.signal,
                    body: JSON.stringify({
                        contents: [{
                            parts: [
                                { inlineData: { mimeType: 'image/jpeg', data: base64Images[0] } },
                                { inlineData: { mimeType: 'image/jpeg', data: base64Images[1] } },
                                { inlineData: { mimeType: 'image/jpeg', data: base64Images[2] } },
                                { text: prompt }
                            ]
                        }],
                        generationConfig: {
                            responseMimeType: "application/json",
                            temperature: 0.1
                        }
                    })
                }).finally(() => clearTimeout(timeoutId));

                if (!res.ok) {
                    const errText = await res.text();
                    // 404 または 429 (クォータ超過): リトライせず即座に次のモデルへフォールバック
                    if (res.status === 404 || res.status === 429) {
                        console.warn(`[contest-parser] Model ${model} returned ${res.status} (${errText.slice(0, 80)}), skipping to next model immediately...`);
                        break;
                    }
                    // 503: 一時的高負荷のため1回だけ短時間待ってリトライ
                    if (res.status === 503) {
                        console.warn(`[contest-parser] ${model} attempt ${attempt} got 503, waiting before retry...`);
                        await new Promise(r => setTimeout(r, 1000 * attempt));
                        continue;
                    }
                    throw new Error(`Gemini API status ${res.status} (${model}): ${errText}`);
                }


                const data = await res.json() as any;
                const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;
                if (!text) {
                    throw new Error(`Empty response from Gemini API (${model})`);
                }

                const raw: RawGeminiOutput = JSON.parse(text);

                // Determine matchIndex from remainingAttemptsStr
                let matchIndex = 1;
                let remainingMatches = 5;
                if (raw.remainingAttemptsStr) {
                    const match = raw.remainingAttemptsStr.match(/(\d+)\s*\/\s*5/);
                    if (match) {
                        remainingMatches = parseInt(match[1], 10);
                        matchIndex = Math.max(1, Math.min(5, 6 - remainingMatches));
                    }
                }

                // Determine chosen opponent
                let chosenCandidate = raw.candidates?.find(c => c.position === 3) || {
                    position: 3,
                    name: 'Unknown',
                    totalPower: 0,
                    expectedPt: 0
                };

                if (raw.overallResult === 'WIN' && raw.candidates && raw.candidates.length > 0) {
                    const matched = raw.candidates.find(c => c.expectedPt === raw.earnedPt);
                    if (matched) {
                        chosenCandidate = matched;
                    } else {
                        const pos3 = raw.candidates.find(c => c.position === 3);
                        if (pos3) chosenCandidate = pos3;
                    }
                } else if (raw.candidates) {
                    const pos3 = raw.candidates.find(c => c.position === 3);
                    if (pos3) chosenCandidate = pos3;
                }

                return {
                    remainingMatches,
                    matchIndex,
                    opponent: {
                        name: chosenCandidate.name,
                        grade: chosenCandidate.position
                    },
                    overallResult: raw.overallResult,
                    earnedPt: raw.earnedPt,
                    stages: {
                        stage1: raw.stage1,
                        stage2: raw.stage2,
                        stage3: raw.stage3
                    },
                    extra: {
                        fans: raw.fans,
                        coins: raw.coins,
                        currentPt: raw.currentPt,
                        currentRank: raw.currentRank
                    }
                };
            } catch (e: any) {
                lastError = e;
                console.warn(`[contest-parser] ${model} attempt ${attempt} failed:`, e.message);
                if (attempt < 3) {
                    await new Promise(r => setTimeout(r, 1500 * attempt));
                }
            }
        }
    }


    throw lastError || new Error('All Gemini models failed to parse contest images');
}
