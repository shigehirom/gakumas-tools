#!/bin/bash
set -e

TARGET="shigehiro@192.168.100.4"
TARGET_DIR="/mnt/NVMe/gakumas-tools/"

echo "Fetching latest match history CSV files from TrueNAS ($TARGET)..."
rsync -avz --inplace --no-owner --no-group --no-perms --include='match_history_*.csv' --exclude='*' $TARGET:${TARGET_DIR}agent-instructions/ /root/gakumas-workspace/shared/agent-instructions/
rsync -avz --inplace --no-owner --no-group --no-perms --include='match_history_*.csv' --exclude='*' $TARGET:${TARGET_DIR}agent-instructions/ /root/gakumas-workspace/gakumas-tools/agent-instructions/

echo "✅ Successfully synced match history CSV files to local workspace!"
