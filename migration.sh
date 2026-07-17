#!/bin/bash
set -e

echo "🚀 Sandbox内へのワークスペース移行を開始します..."

# 1. ワークスペースの作成
mkdir -p /root/gakumas-workspace

# 2. rsyncで必要なプロジェクトをコピー（Mac/ARM用の不要なバイナリ・キャッシュを除外）
echo "📂 ファイルをコピーしています (数分かかる場合があります)..."
rsync -av --progress \
  --exclude="node_modules" \
  --exclude=".next" \
  --exclude=".venv" \
  --exclude="__pycache__" \
  --exclude=".DS_Store" \
  --exclude=".git/objects" \
  /workspace/gakumas-tools \
  /workspace/gakumas-og-tools \
  /workspace/gakumas-support_cards \
  /workspace/gakumas_icon_classifier \
  /workspace/gk-img \
  /workspace/agent-instructions \
  /root/gakumas-workspace/

# 3. Node.js (gakumas-tools) のセットアップ
echo "📦 gakumas-tools の依存関係をインストール中..."
cd /root/gakumas-workspace/gakumas-tools
pnpm install

# 4. Python環境のセットアップ (gakumas-og-tools など)
echo "🐍 Pythonの仮想環境をセットアップ中..."
apt update && apt install -y python3-venv
cd /root/gakumas-workspace/gakumas-og-tools
python3 -m venv .venv
source .venv/bin/activate
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi
deactivate

echo "✅ 移行スクリプトが完了しました！"
