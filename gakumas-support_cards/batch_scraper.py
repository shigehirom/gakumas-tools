import os
import csv
import sys
import time
import subprocess
import argparse

def get_cards_from_csv():
    """support_cards.csvからカード情報を取得する"""
    cards = []
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, 'support_cards.csv')
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cards.append(row)
    except FileNotFoundError:
        print(f"support_cards.csv not found at {csv_path}. Please run scrape_list.py first.")
        sys.exit(1)
    return cards

def is_card_already_scraped(card, output_dir):
    """カードのJSONファイルが既に存在するか確認する"""
    wiki_id = card.get('wiki_id')
    card_name = card.get('name', 'unknown_card')
    safe_card_name = card_name.replace('/', '_')

    target_files = []
    if wiki_id:
        target_files.append(f"{wiki_id}.json")
        target_files.append(f"FIXME_{wiki_id}.json")
    if safe_card_name:
        target_files.append(f"{safe_card_name}.json")
        target_files.append(f"FIXME_{safe_card_name}.json")

    for fname in target_files:
        if os.path.exists(os.path.join(output_dir, fname)):
            return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Batch scrape support cards detail pages from Seesaa Wiki")
    parser.add_argument(
        "--new-only", "-n", "--new",
        action="store_true",
        dest="new_only",
        help="Scrape only newly added cards that do not yet have JSON files (default: scrape all)"
    )
    args = parser.parse_args()

    cards = get_cards_from_csv()
    if not cards:
        print("No cards found in CSV.")
        sys.exit(1)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.abspath(os.path.join(base_dir, "..", "gakumas-og-tools", "support-cards"))

    if args.new_only:
        total_csv = len(cards)
        cards = [c for c in cards if not is_card_already_scraped(c, output_dir)]
        print(f"Mode: New cards only (--new-only)")
        print(f"Found {len(cards)} new card(s) to scrape (out of {total_csv} total in CSV).")
        if not cards:
            print("✅ All cards are already scraped and up-to-date.")
            return
    else:
        print(f"Mode: Full scrape (all {len(cards)} cards)")

    python_exec = sys.executable
    scraper_path = os.path.join(base_dir, "scraper.py")

    for i, card in enumerate(cards, 1):
        url = card.get('page_url')
        if not url:
            continue

        print(f"\n[{i}/{len(cards)}] Processing {url} ({card.get('name', '')})")
        cmd = [python_exec, scraper_path, url]
        if card.get('wiki_id'):
            cmd.extend(["--wiki-id", card['wiki_id']])
        if card.get('image_url'):
            cmd.extend(["--image-url", card['image_url']])

        subprocess.run(cmd)

        # サーバー負荷軽減のため、リクエスト間に数秒のインターバルを設ける（Bot回避対策）
        time.sleep(2)

    print(f"\nAll tasks completed! ({len(cards)} cards processed)")

if __name__ == "__main__":
    main()
