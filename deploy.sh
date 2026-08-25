#!/bin/bash
set -e

TARGET="shigehiro@192.168.100.4"
TARGET_DIR="/mnt/NVMe/gakumas-tools/"

echo "Deploying to TrueNAS ($TARGET)..."

# 0. TrueNAS 側で記録された最新の対戦履歴（match_history_*.csv）を保護・同期
echo "Fetching latest match history from TrueNAS..."
rsync -avz --include='match_history_*.csv' --exclude='*' $TARGET:$TARGET_DIR/agent-instructions/ ../shared/agent-instructions/ 2>/dev/null || true

# 1. 共有アセット・Botコード・ナレッジ・設定の同期準備
mkdir -p ./documents && cp ../shared/documents/*.md ./documents/ 2>/dev/null || true
mkdir -p ./agent-instructions && cp -r ../shared/agent-instructions/* ./agent-instructions/ 2>/dev/null || true
mkdir -p ./.config/gakumas-tools && cp -r ~/.config/gakumas-tools/* ./.config/gakumas-tools/ 2>/dev/null || true
mkdir -p ./shared/gakumas-dev/knowledge && cp -r ../shared/gakumas-dev/knowledge/* ./shared/gakumas-dev/knowledge/ 2>/dev/null || true
mkdir -p ./gakumas-agent-bot && cp -r ../gakumas-agent-bot/* ./gakumas-agent-bot/ 2>/dev/null || true
mkdir -p ./gakumas-support_cards && cp -r ../gakumas-support_cards/* ./gakumas-support_cards/ 2>/dev/null || true

# 2. TrueNAS への rsync 転送
rsync -avz --delete \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.next' \
  --exclude='gakumas-tools/.next' \
  --exclude='.pnpm-store' \
  --exclude='scratch' \
  --exclude='local-tools' \
  --exclude='logs' \
  --exclude='tmp' \
  --exclude='results' \
  --exclude='cropped_portraits' \
  --exclude='.venv' \
  --exclude='*.pyc' \
  --exclude='__pycache__' \
  --exclude='*.log' \
  ./ $TARGET:$TARGET_DIR

echo "Building and restarting Docker Compose containers on TrueNAS..."
# TrueNAS に SSH 接続し、Web UI、My Gakumas Tools、あさり先生 を同時にビルド・起動
ssh -t $TARGET "cd $TARGET_DIR && \
  echo '==> Building and starting Web UI & Discord Bots...' && \
  sudo docker compose down 2>/dev/null || true && \
  sudo docker compose build && \
  sudo docker compose up -d"

echo "Deployment complete! TrueNAS Web UI & Discord Bots are now live and synchronized."
