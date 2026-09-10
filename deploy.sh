#!/bin/bash
set -e
trap 'stty sane 2>/dev/null || true' EXIT INT TERM

TARGET="shigehiro@192.168.100.4"
TARGET_DIR="/mnt/NVMe/gakumas-tools/"

echo "Deploying to TrueNAS ($TARGET)..."

# 0. TrueNAS 側で記録された最新の対戦履歴（match_history_*.csv）を保護・同期
echo "Fetching latest match history from TrueNAS..."
rsync -avz --inplace --no-owner --no-group --no-perms --include='match_history_*.csv' --exclude='*' $TARGET:${TARGET_DIR}agent-instructions/ ../shared/agent-instructions/ 2>/dev/null || true
rsync -avz --inplace --no-owner --no-group --no-perms --include='match_history_*.csv' --exclude='*' $TARGET:${TARGET_DIR}agent-instructions/ ./agent-instructions/ 2>/dev/null || true

# 0.5. MongoDB から最新の全対戦データを CSV へ自動同期・完全復元
echo "Syncing all match records from MongoDB to CSV..."
node packages/cli/scripts/sync-mongo-to-csv.mjs 2>/dev/null || true

# 0.6. Google スプレッドシート（Contest）と MongoDB の双方向同期
echo "Syncing Contest records with Google Sheets..."
node packages/cli/scripts/sync-contest-matches.mjs --mode bidirectional --execute 2>/dev/null || true




# 1. 共有アセット・Botコード・ナレッジ・設定の同期準備
mkdir -p ./documents && cp ../shared/documents/*.md ./documents/ 2>/dev/null || true
mkdir -p ./agent-instructions && cp -r ../shared/agent-instructions/* ./agent-instructions/ 2>/dev/null || true
mkdir -p ./.config/gakumas-tools && cp -r ~/.config/gakumas-tools/* ./.config/gakumas-tools/ 2>/dev/null || true
mkdir -p ./shared/gakumas-dev/knowledge && cp -r ../shared/gakumas-dev/knowledge/* ./shared/gakumas-dev/knowledge/ 2>/dev/null || true
mkdir -p ./gakumas-agent-bot && cp -r ../gakumas-agent-bot/* ./gakumas-agent-bot/ 2>/dev/null || true
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
  echo '==> Building Web UI & Discord Bots...' && \
  sudo docker compose build --no-cache asari-agent gakumas-bot && \
  sudo docker compose build gakumas-tools && \
  echo '==> Starting Discord Bots...' && \
  sudo docker compose up -d --force-recreate gakumas-bot asari-agent && \
  echo '==> Container Status:' && \
  sudo docker compose ps"

stty sane 2>/dev/null || true
echo "Deployment complete! TrueNAS Web UI & Discord Bots are now live and synchronized."
