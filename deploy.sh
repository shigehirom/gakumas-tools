#!/bin/bash

TARGET="shigehiro@192.168.100.4"
TARGET_DIR="/mnt/NVMe/gakumas-tools/"

echo "Deploying to TrueNAS ($TARGET)..."

# レポート文書を同期
mkdir -p ./documents && cp ../shared/documents/*.md ./documents/ 2>/dev/null || true

# pnpm に移行したため、不要なディレクトリや一時ファイルを除外します
rsync -avz --delete --exclude='.git' --exclude='node_modules' --exclude='.next' --exclude='gakumas-tools/.next' --exclude='.pnpm-store' --exclude='scratch' --exclude='local-tools' --exclude='logs' --exclude='tmp' --exclude='results' --exclude='cropped_portraits' --exclude='.venv' --exclude='.venv-mac' --exclude='.venv-win' --exclude='*.log' ./ $TARGET:$TARGET_DIR

echo "Building containers on TrueNAS..."
# TrueNAS に SSH 接続し、Bot イメージの更新と Web UI コンテナの再ビルドを確実に実行
ssh -t $TARGET "cd $TARGET_DIR && \
  sudo docker rm -f gakumas-tools-gakumas-bot-1 gakumas-discord-bot 2>/dev/null || true; \
  echo '==> Building Discord Bot image...' && \
  sudo docker build -f Dockerfile.bot -t gakumas-tools-gakumas-bot:latest . && \
  echo '==> Restarting gakumas-bot app...' && \
  sudo docker restart \$(sudo docker ps -a -q -f name=gakumas-bot) 2>/dev/null || true; \
  echo '==> Building Web UI...' && \
  sudo docker compose build && \
  sudo docker compose down && \
  (sudo docker compose up -d || sudo docker restart \$(sudo docker ps -a -q -f name=gakumas-tools) 2>/dev/null || true)"

echo "Deployment complete!"
