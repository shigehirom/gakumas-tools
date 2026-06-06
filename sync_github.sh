#!/bin/bash
set -e

cd /Users/shigehiro/gakumas-workspace/gakumas-tools

echo "================================================="
echo "1. 今回作成したツールのコミットとプッシュを行います..."
echo "================================================="
git add packages/cli/scripts/generate_base64_idol_md.mjs packages/cli/scripts/get_worst_memories.mjs
# 他に変更されたスクリプト等があれば追加
git commit -m "feat(cli): Obsidian用マークダウン生成およびワーストメモリー抽出スクリプトを追加" || true
git push origin master

echo "================================================="
echo "2. 本家 (surisuririsu) から最新データを同期します..."
echo "================================================="
# upstreamリポジトリが未登録の場合に備えて登録
git remote add upstream https://github.com/surisuririsu/gakumas-tools.git 2>/dev/null || true
git fetch upstream
git merge upstream/master -m "Merge upstream updates" || true

echo "================================================="
echo "3. (スキップ) 公式CSVデータはupstreamから取得済みのため復元不要"
# git checkout origin/master -- packages/gakumas-data/csv/
echo "================================================="
echo "4. 同期後のJSONおよびアセットのコンパイル・再生成を実行します..."
echo "================================================="
pnpm --filter gakumas-data generate
pnpm --filter gakumas-images generate
python3 -m scripts.generate

echo "================================================="
echo "5. RAG 知識ベース (NotebookLM 用) の自動更新を実行します..."
echo "================================================="
python3 generate_rag_docs.py

echo "================================================="
echo "6. 再生成されたすべての変更をプッシュします..."
echo "================================================="
git add .
git commit -m "chore: アップストリーム同期およびRAG・JSONデータの再生成" || true
git push origin master

echo "================================================="
echo "🎉 GitHub連携・アップストリーム同期・RAG更新がすべて完了しました！"
echo "================================================="
