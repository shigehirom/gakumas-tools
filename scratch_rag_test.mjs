import fs from 'fs/promises';

async function run() {
    const files = [
        "01_Game_Mechanics.md",
        "02_P_Idols.md",
        "03_Skill_Cards.md",
        "04_Support_Cards.md",
        "05_P_Items.md"
    ];
    const baseDir = "/Users/shigehiro/Library/CloudStorage/GoogleDrive-shigehiro.miyashita@gmail.com/マイドライブ/Documents/学園アイドルマスター/notebookLM/";
    
    let systemContent = "あなたは「学園アイドルマスター」の専門AIアシスタントです。以下のナレッジベース（RAG用データ）をすべて読み込み、事前知識として活用してください。\n\n";
    
    for (const file of files) {
        const content = await fs.readFile(baseDir + file, 'utf8');
        systemContent += `--- ${file} ---\n${content}\n\n`;
    }
    
    const messages = [
        { role: "system", content: systemContent },
        { role: "user", content: "提供された5つのRAG用データを読み込みましたか？読み込みが完了した旨と、あなたが読み込んだデータの内容について、簡単な要約を3行程度で答えてください。" }
    ];
    
    console.log("Ollama (gemma:latest) へRAGデータを送信中... (約130KB)");
    
    const response = await fetch("http://localhost:11434/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            model: "gemma:latest",
            messages: messages,
            stream: false
        })
    });
    
    const data = await response.json();
    console.log("\n=== Ollamaからの回答 ===");
    console.log(data.message.content);
    console.log("========================");
}

run().catch(console.error);
