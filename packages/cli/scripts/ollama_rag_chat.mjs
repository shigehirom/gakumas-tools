import fs from 'fs/promises';
import readline from 'readline';

async function run() {
    const availableFiles = [
        { name: "01_Game_Mechanics.md", desc: "ゲームの基本ルール (約3KB)" },
        { name: "02_P_Idols.md", desc: "Pアイドル一覧と固有スキル (約15KB)" },
        { name: "03_Skill_Cards.md", desc: "全スキルカード詳細 (約135KB)" },
        { name: "04_Support_Cards.md", desc: "サポートカード詳細 (約127KB)" },
        { name: "05_P_Items.md", desc: "Pアイテム詳細 (約53KB)" }
    ];

    const baseDir = "/Users/shigehiro/Library/CloudStorage/GoogleDrive-shigehiro.miyashita@gmail.com/マイドライブ/Documents/学園アイドルマスター/notebookLM/";
    
    console.log("読み込むナレッジ（知識データ）を選択してください。（カンマ区切りで複数選択可、例: 1,3）");
    console.log("※ メモリ不足を避けるため、用途に合わせて1〜2つに絞ることをお勧めします。");
    availableFiles.forEach((f, i) => console.log(`${i + 1}: ${f.name} - ${f.desc}`));
    
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    
    const selection = await new Promise(resolve => {
        rl.question("> ", answer => resolve(answer.trim()));
    });
    
    const selectedIndexes = selection.split(',').map(s => parseInt(s.trim(), 10) - 1).filter(i => i >= 0 && i < availableFiles.length);
    if (selectedIndexes.length === 0) {
        console.log("有効な選択がなかったため、デフォルトで 01_Game_Mechanics.md を読み込みます。");
        selectedIndexes.push(0);
    }
    
    const filesToLoad = selectedIndexes.map(i => availableFiles[i].name);
    
    console.log(`\n以下のデータを読み込んでいます: ${filesToLoad.join(", ")}...`);
    let systemContent = "あなたは「学園アイドルマスター」の専門家エージェントです。以下の提供されたデータに基づき、ユーザーの質問に正確に答えてください。\n\n";
    
    for (const file of filesToLoad) {
        try {
            const content = await fs.readFile(baseDir + file, 'utf8');
            systemContent += `--- ${file} ---\n${content}\n\n`;
        } catch (e) {
            console.error(`${file} の読み込みに失敗しました: ${e.message}`);
        }
    }
    
    const messages = [
        { role: "system", content: systemContent }
    ];
    
    console.log("✨ Ollama (gemma:latest) のRAGチャット準備が完了しました！");
    console.log("学園アイドルマスターに関する何でも質問してください。（終了するには exit と入力）\n");


    const askQuestion = () => {
        rl.question("あなた: ", async (userInput) => {
            if (userInput.toLowerCase() === 'exit') {
                console.log("チャットを終了します。");
                rl.close();
                return;
            }
            if (!userInput.trim()) {
                askQuestion();
                return;
            }

            messages.push({ role: "user", content: userInput });
            process.stdout.write("Ollama: ");

            try {
                const response = await fetch("http://127.0.0.1:11434/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        model: "gemma:latest",
                        messages: messages,
                        stream: true,
                        options: {
                            num_ctx: 131072
                        }
                    })
                });

                if (!response.ok) {
                    const errText = await response.text();
                    throw new Error(`API Error ${response.status}: ${errText}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let fullResponse = "";
                let buffer = "";

                let chunkCount = 0;
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) {
                        if (buffer.trim()) {
                            try {
                                const parsed = JSON.parse(buffer);
                                if (parsed.message && parsed.message.content) {
                                    process.stdout.write(parsed.message.content);
                                    fullResponse += parsed.message.content;
                                }
                            } catch(e) {}
                        }
                        break;
                    }
                    
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // 最後の不完全なチャンクをバッファに残す
                    
                    for (const line of lines) {
                        if (!line.trim()) continue;
                        try {
                            const parsed = JSON.parse(line);
                            chunkCount++;
                            if (parsed.message && parsed.message.content) {
                                process.stdout.write(parsed.message.content);
                                fullResponse += parsed.message.content;
                            }
                            if (parsed.error) {
                                throw new Error(parsed.error);
                            }
                        } catch (e) {
                            // ignore parse error on incomplete chunks
                        }
                    }
                }
                
                if (fullResponse === "" && chunkCount > 0) {
                    console.log("\n[デバッグ警告] Ollama APIから正常な応答(HTTP 200)を受信しましたが、生成されたテキストが空でした。");
                    console.log("おそらく、130KBのシステムプロンプトを処理するためのKVキャッシュ（メモリ）がMac mini上で確保できず、生成プロセスがOOMで即座に打ち切られた可能性があります。");
                } else if (fullResponse === "" && chunkCount === 0) {
                    console.log("\n[デバッグ警告] Ollama APIからのストリームチャンクが全くありませんでした。");
                }
                
                messages.push({ role: "assistant", content: fullResponse });
                console.log("\n");
            } catch (err) {
                console.error("\n通信エラーが発生しました:", err.message);
                messages.pop(); // 失敗したユーザー入力を履歴から除外
            }

            askQuestion();
        });
    };

    askQuestion();
}

run().catch(console.error);
