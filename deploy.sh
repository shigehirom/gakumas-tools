#!/bin/bash

TARGET="shigehiro@192.168.100.4"
TARGET_DIR="/mnt/NVMe/gakumas-tools/"

echo "Deploying to TrueNAS ($TARGET)..."

# pnpm に移行したため、不要なディレクトリや一時ファイルを除外します
rsync -avz --delete --exclude='.git' --exclude='node_modules' --exclude='.next' --exclude='gakumas-tools/.next' --exclude='.pnpm-store' --exclude='scratch' --exclude='local-tools' --exclude='logs' --exclude='tmp' --exclude='results' --exclude='cropped_portraits' --exclude='.venv' --exclude='.venv-mac' --exclude='.venv-win' --exclude='*.log' ./ $TARGET:$TARGET_DIR

echo "Building container on TrueNAS..."
# TrueNAS に SSH 接続し、Docker コンテナの再ビルドのみを行う
ssh -t $TARGET "cd $TARGET_DIR && sudo docker compose build && sudo docker compose down && sudo docker compose up -d"

echo "Deployment complete!"
