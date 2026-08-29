import csv
import json
import os

def check_new_cards():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "support_cards.csv")
    master_path = os.path.join(base_dir, "..", "gakumas-og-tools", "support_cards_master.json")
    
    if not os.path.exists(csv_path):
        print(f"[-] {csv_path} が見つかりません。先に python3 scrape_list.py を実行してください。")
        return

    with open(csv_path, "r", encoding="utf-8") as f:
        csv_cards = list(csv.DictReader(f))

    master_ids = set()
    if os.path.exists(master_path):
        with open(master_path, "r", encoding="utf-8") as f:
            try:
                master_cards = json.load(f)
                master_ids = {c.get("id") for c in master_cards if c.get("id")}
            except Exception as e:
                print(f"[Warning] Failed to parse master JSON: {e}")

    new_cards = [c for c in csv_cards if c.get("wiki_id") not in master_ids]

    print("========================================")
    print(f"📊 サポートカード差分チェック結果")
    print(f"・Wiki一覧 CSV取得数: {len(csv_cards)} 件")
    print(f"・マスタ登録済み数  : {len(master_ids)} 件")
    print("========================================")

    if new_cards:
        print(f"✨ 【新規追加カード: {len(new_cards)} 件】")
        for c in new_cards:
            print(f"  + 【{c.get('rarity')}】{c.get('name')} (Wiki ID: {c.get('wiki_id')})")
        print("\n👉 python3 batch_scraper.py で詳細データを取得してください。")
    else:
        print("✅ 新規追加されたカードはありません（すべてマスタデータと同期済みです）。")

if __name__ == "__main__":
    check_new_cards()
