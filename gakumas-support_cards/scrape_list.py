import csv
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://seesaawiki.jp"
PAGE_URL = "https://seesaawiki.jp/gakumasu/d/%a5%b5%a5%DD%A1%bc%a5%C8%A5%ab%a1%bc%a5%C9%B0%ec%cd%f7"

# カード行の抽出用
CARD_PATTERN = re.compile(
    r'^(SSR|SR|R)\n(.+?)\n\((SP_[A-Z]+_\d+)\)',
    re.MULTILINE
)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def scrape_cards():
    res = requests.get(PAGE_URL, headers=DEFAULT_HEADERS)
    res.encoding = "euc-jp"
    soup = BeautifulSoup(res.text, "html.parser")

    # ページ全体テキスト
    text = soup.get_text("\n")

    cards = []

    for match in CARD_PATTERN.finditer(text):
        rarity = match.group(1)
        name = match.group(2).strip()
        wiki_id = match.group(3)

        # テンプレート用のエントリを除外
        if wiki_id in ("SP_R_0000", "SP_SR_000", "SP_SR_0000", "SP_SSR_0000") or "テンプレ" in name:
            continue

        page_url = ""
        image_url = ""
        anchor = soup.find(id=wiki_id)
        tr = anchor.find_parent("tr") if anchor else None
        
        if not tr:
            text_node = soup.find(string=re.compile(re.escape(wiki_id)))
            if text_node:
                tr = text_node.find_parent("tr")
                
        if tr:
            a_tag = tr.find("a", href=True)
            if a_tag:
                page_url = urljoin(BASE_URL, a_tag["href"])
            img_tag = tr.find("img")
            if img_tag and img_tag.get("src"):
                image_url = urljoin(BASE_URL, img_tag["src"])

        cards.append({
            "rarity": rarity,
            "name": name,
            "wiki_id": wiki_id,
            "image_url": image_url,
            "page_url": page_url
        })

    return cards


def save_csv(cards, filename="support_cards.csv"):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["rarity", "name", "wiki_id", "image_url", "page_url"]
        )
        writer.writeheader()
        writer.writerows(cards)


if __name__ == "__main__":
    cards = scrape_cards()
    save_csv(cards)
    print(f"{len(cards)} 件のカードを抽出しました。")
    
    # 既存マスタとの差分チェック
    try:
        import os, json
        master_path = os.path.join(os.path.dirname(__file__), "..", "gakumas-og-tools", "support_cards_master.json")
        if os.path.exists(master_path):
            with open(master_path, "r", encoding="utf-8") as f:
                master_cards = json.load(f)
                master_ids = {c.get("id") for c in master_cards if c.get("id")}
            new_cards = [c for c in cards if c.get("wiki_id") not in master_ids]
            if new_cards:
                print(f"\n✨ 【新規追加カード: {len(new_cards)} 件】")
                for c in new_cards:
                    print(f"  + 【{c.get('rarity')}】{c.get('name')} (Wiki ID: {c.get('wiki_id')})")
            else:
                print("✅ 新規追加カードはありません（すべてマスタと同期済みです）。")
    except Exception as e:
        pass

