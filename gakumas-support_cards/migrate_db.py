import csv
import json
from pymongo import MongoClient
import os
from datetime import datetime

# MongoDB接続設定
MONGO_URL = "mongodb://192.168.100.4:27017"

def load_csv_mapping():
    mapping = {}
    try:
        with open('support_cards.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                mapping[row['name']] = {
                    'wiki_id': row['wiki_id'],
                    'image_url': row['image_url']
                }
    except FileNotFoundError:
        print("support_cards.csv not found.")
    return mapping

def main():
    client = MongoClient(MONGO_URL)
    db = client['gakumas-tools']
    collection = db['owned_support_cards']
    
    # マッピング読み込み
    mapping = load_csv_mapping()
    if not mapping:
        return
        
    # バックアップ作成
    docs = list(collection.find({}))
    backup_file = f"owned_support_cards_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    # ObjectIdなどをシリアライズ可能にするためのヘルパー
    from bson import json_util
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(docs, f, default=json_util.default, ensure_ascii=False, indent=2)
    print(f"Backup saved to {backup_file} (Total: {len(docs)} documents)")
    
    # 移行処理 (アプローチA: _id を wiki_id に置き換える)
    migrated_count = 0
    not_found_count = 0
    
    for doc in docs:
        old_id = doc['_id']
        card_name = doc.get('card_name', old_id)
        
        # 既に移行済みかチェック（SP_SSR_ などのプレフィックスがあればスキップ）
        if isinstance(old_id, str) and old_id.startswith('SP_'):
            continue
            
        if card_name in mapping:
            card_info = mapping[card_name]
            wiki_id = card_info['wiki_id']
            image_url = card_info['image_url']
            
            # 新しいドキュメントを作成
            new_doc = doc.copy()
            new_doc['_id'] = wiki_id
            new_doc['wiki_id'] = wiki_id
            new_doc['image_url'] = image_url
            
            # DBに挿入
            try:
                collection.insert_one(new_doc)
                # 成功したら古いドキュメントを削除
                collection.delete_one({'_id': old_id})
                migrated_count += 1
            except Exception as e:
                print(f"Error migrating {card_name}: {e}")
        else:
            print(f"Warning: {card_name} not found in CSV mapping.")
            not_found_count += 1
            
    print(f"\nMigration completed.")
    print(f"Migrated: {migrated_count}")
    print(f"Not found in CSV (Skipped): {not_found_count}")

if __name__ == "__main__":
    main()
