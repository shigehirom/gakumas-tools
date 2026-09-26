#!/bin/bash
set -e
trap 'stty sane 2>/dev/null || true' EXIT INT TERM

TARGET="shigehiro@192.168.100.4"
TARGET_DIR="/mnt/NVMe/gakumas-tools/"

echo "Deploying to TrueNAS ($TARGET)..."

# 0. Google スプレッドシート（Contest）と MongoDB の双方向同期
echo "Syncing Contest records with Google Sheets and MongoDB..."
node packages/cli/scripts/sync-contest-matches.mjs --mode bidirectional --execute 2>/dev/null || true




# 1. 共有アセット・Botコード・ナレッジ・設定の同期準備
mkdir -p ./documents && cp ../shared/documents/*.md ./documents/ 2>/dev/null || true
mkdir -p ./agent-instructions && cp -r ../shared/agent-instructions/* ./agent-instructions/ 2>/dev/null || true
mkdir -p ./.config/gakumas-tools && cp -r ~/.config/gakumas-tools/* ./.config/gakumas-tools/ 2>/dev/null || true
mkdir -p ./shared/gakumas-dev/knowledge && cp -r ../shared/gakumas-dev/knowledge/* ./shared/gakumas-dev/knowledge/ 2>/dev/null || true
mkdir -p ./gakumas-agent-bot && cp -r ../gakumas-agent-bot/* ./gakumas-agent-bot/ 2>/dev/null || true
mkdir -p ./gakumas-mcp-server && cp -r ../gakumas-mcp-server/* ./gakumas-mcp-server/ 2>/dev/null || true
mkdir -p ./gakumas-support_cards && cp -r ../gakumas-support_cards/* ./gakumas-support_cards/ 2>/dev/null || true
mkdir -p ./gk-img && cp -r ../gk-img/* ./gk-img/ 2>/dev/null || true

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
ssh -t $TARGET "cd $TARGET_DIR && \
  echo '==> Building Web UI (gakumas-tools)...' && \
  sudo docker compose build gakumas-tools && \
  echo '==> Stopping and cleaning retired Bot containers (gakumas-bot & asari-agent are now on Pi 5)...' && \
  sudo docker compose stop gakumas-bot asari-agent 2>/dev/null || true && \
  sudo docker compose rm -f gakumas-bot asari-agent 2>/dev/null || true && \
  sudo docker ps -q --filter name=gakumas-bot | xargs -r sudo docker rm -f 2>/dev/null || true && \
  sudo docker ps -q --filter name=asari-agent | xargs -r sudo docker rm -f 2>/dev/null || true && \
  echo '==> Starting Web UI (gakumas-tools)...' && \
  sudo docker compose up -d --force-recreate gakumas-tools && \
  echo '==> Container Status:' && \
  sudo docker compose ps"

stty sane 2>/dev/null || true
echo "Deployment complete! TrueNAS Web UI & Discord Bots are now live and synchronized."
