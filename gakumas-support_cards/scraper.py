import requests
from bs4 import BeautifulSoup
import json
import re
import sys
import os

def format_ability_text(text, uncap_4):
    """
    最初に出てくる (...) と直前の数字（%記号含む）を *uncap_4* に変換する
    間に「増加」などの文字が入るケースも許容する
    例: "初期ボーカル上昇+26(65)" -> "初期ボーカル上昇+*65*"
    例: "発生率を1.7%(100%)増加" -> "発生率を*100%*増加"
    例: "発生率を+2%増加(100%)" -> "発生率を+*100%*"
    """
    return re.sub(r"[\d\.]+%?[^0-9()]*\([^)]*\)", f"*{uncap_4}*", text, count=1)

def map_plan_restriction(plan):
    if not plan: return plan, True
    mapping = {
        "センス": "sense",
        "ロジック": "logic",
        "アノマリー": "anomaly",
        "制限なし": "none",
        "フリー": "none"
    }
    if plan in mapping:
        return mapping[plan], False
    return plan, True

def parse_support_ability_table(table):
    """サポートアビリティのテーブルをパースする"""
    abilities = []
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all(['td', 'th'])
        
        # ヘッダー行をスキップ
        cell_texts = [c.get_text(strip=True) for c in cells]
        if '解放条件' in cell_texts or '上限解放0' in cell_texts or '1' in cell_texts:
            continue
            
        # データ行（Wikiの記載ミスでカラム数が減っている行にも対応するため、後ろからインデックスを取る）
        # ご要望の「上限解放0」はLv40時点の値（最後から5番目）を採用します
        if len(cells) >= 7:
            uncaps = [
                cells[-5].get_text(strip=True),
                cells[-4].get_text(strip=True),
                cells[-3].get_text(strip=True),
                cells[-2].get_text(strip=True),
                cells[-1].get_text(strip=True)
            ]
            
            # 表中に記載がない（空文字の）場合は一つ前の値を流用する
            for i in range(1, 5):
                if not uncaps[i]:
                    uncaps[i] = uncaps[i-1]
            
            ability_text = cells[1].get_text(separator='', strip=True)
            ability_text = format_ability_text(ability_text, uncaps[4])
            
            abilities.append({
                "unlock_condition": cells[0].get_text(strip=True),
                "ability": ability_text,
                "uncap_0": uncaps[0],
                "uncap_1": uncaps[1],
                "uncap_2": uncaps[2],
                "uncap_3": uncaps[3],
                "uncap_4": uncaps[4],
            })
    return abilities

def parse_support_event_table(table):
    """サポートイベントのテーブルをパースする"""
    events = []
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all(['td', 'th'])
        
        # ヘッダー行をスキップ
        if len(cells) > 0 and '解放' in cells[0].get_text(strip=True):
            continue
            
        if len(cells) >= 3:
            events.append({
                "unlock_condition": cells[0].get_text(strip=True),
                "effect": cells[1].get_text(strip=True),
                "commu": cells[2].get_text(strip=True),
            })
    return events

def scrape_card_detail(url, wiki_id=None, image_url=None):
    """サポートカードの個別ページをスクレイピングする"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    print(f"Requesting URL: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        # SeesaaWikiはEUC-JPで固定。apparent_encodingだと一部ページで誤判定されるため明示的に指定
        response.encoding = 'euc-jp'
    except requests.exceptions.RequestException as e:
        print(f"Error during request: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    title_text = soup.title.get_text(strip=True) if soup.title else ""
    card_name = title_text.split('-')[0].strip()
    
    data = {
        "wiki_id": wiki_id,
        "url": url,
        "image_url": image_url,
        "card_name": card_name,
        "rarity": None,
        "plan_restriction": None,
        "type": None,
        "skill_card_support": None,
        "support_abilities": [],
        "support_events": [],
        "obtained_skill_card": None,
        "obtained_item": None
    }
    
    tables = soup.find_all('table')
    for table in tables:
        # メタデータテーブルか、アビリティか、イベントかを判定
        text_content = table.get_text(separator=' ', strip=True)
        
        # 1. メタデータテーブルの処理（「レア」が含まれるテーブル）
        if "レア" in text_content and "プラン制限" in text_content:
            for row in table.find_all('tr'):
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    key = th.get_text(separator='\n', strip=True)
                    val = td.get_text(separator='\n', strip=True)
                    
                    if key == 'レア': 
                        data['rarity'] = val
                    elif key == 'プラン制限': 
                        mapped_plan, is_unmapped = map_plan_restriction(val)
                        data['plan_restriction'] = mapped_plan
                        if is_unmapped:
                            print(f"Warning: Unexpected plan_restriction '{val}'")
                            data['_has_warning'] = True
                    elif key.startswith('タイプ'):
                        parts = val.split('\n')
                        if len(parts) >= 1: data['type'] = parts[0].strip()
                        if len(parts) >= 2: data['skill_card_support'] = parts[1].strip()
                        
        # 2. サポートアビリティテーブルの処理
        elif "上限解放0" in text_content and "上限解放1" in text_content:
            data["support_abilities"] = parse_support_ability_table(table)
            
        # 3. サポートイベントテーブルの処理
        elif "解放" in text_content and "効果" in text_content and "コミュ" in text_content:
            # "上限解放" と区別するため、アビリティテーブルでないことを確認
            if "上限解放0" not in text_content:
                data["support_events"] = parse_support_event_table(table)
                
        # 4. 獲得スキルカードテーブルの処理
        elif "カード名" in text_content and "消費" in text_content and "効果" in text_content:
            for row in table.find_all('tr'):
                ths = row.find_all('th')
                tds = row.find_all('td')
                for th in ths:
                    if th.get_text(strip=True) == 'カード名' and len(tds) > 0:
                        data['obtained_skill_card'] = tds[-1].get_text(strip=True)
                        
        # 5. 獲得Pアイテムテーブルの処理
        elif "アイテム名" in text_content and "効果" in text_content:
            for row in table.find_all('tr'):
                ths = row.find_all('th')
                tds = row.find_all('td')
                for th in ths:
                    if th.get_text(strip=True) == 'アイテム名' and len(tds) > 0:
                        data['obtained_item'] = tds[-1].get_text(strip=True)
            
    # 必須項目の不足チェック
    if not data['rarity']:
        print("Warning: Missing 'rarity'")
        data['_has_warning'] = True
    if not data['type']:
        print("Warning: Missing 'type'")
        data['_has_warning'] = True
    if not data['support_abilities']:
        print("Warning: Missing 'support_abilities' (table not found or empty)")
        data['_has_warning'] = True
    if not data['support_events']:
        print("Warning: Missing 'support_events' (table not found or empty)")
        data['_has_warning'] = True
        
    return data

def download_card_image(image_url, save_path):
    """サポートカードの画像をダウンロードし、PNG形式で保存する"""
    if not image_url:
        return False

    orig_url = re.sub(r"-s\.(png|jpg|jpeg|webp)$", r".\1", image_url, flags=re.IGNORECASE)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    import io
    from PIL import Image

    for target_url in [orig_url, image_url]:
        try:
            resp = requests.get(target_url, headers=headers, timeout=15)
            if resp.status_code == 200 and len(resp.content) > 1000:
                img = Image.open(io.BytesIO(resp.content))
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                img.save(save_path, "PNG", optimize=True)
                print(f"Card image saved to {save_path} (PNG, {len(resp.content):,} bytes)")
                return True
        except Exception as e:
            print(f"Warning: Failed to download image from {target_url}: {e}")

    return False

if __name__ == "__main__":
    import argparse
    
    # Add gakumas-og-tools/scripts to sys.path
    scripts_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gakumas-og-tools", "scripts"))
    if scripts_path not in sys.path:
        sys.path.append(scripts_path)
        
    from convert_support_cards import process_card_json
    
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Target URL")
    parser.add_argument("--wiki-id", help="Wiki ID", default=None)
    parser.add_argument("--image-url", help="Image URL", default=None)
    args = parser.parse_args()
    
    result = scrape_card_detail(args.url, wiki_id=args.wiki_id, image_url=args.image_url)
    
    if result:
        has_warning = result.pop('_has_warning', False)
        
        # Apply DSL conversion immediately
        dsl_result = process_card_json(result)
        
        wiki_id = result.get('wiki_id')
        card_name = result.get('card_name', 'unknown_card')
        safe_card_name = card_name.replace('/', '_')
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dirs = [
            os.path.join(base_dir, "support_cards"),
            os.path.abspath(os.path.join(base_dir, "..", "gakumas-og-tools", "support-cards")),
        ]
        
        for out_dir in output_dirs:
            os.makedirs(out_dir, exist_ok=True)
            
            base_name = wiki_id if wiki_id else safe_card_name
            if has_warning:
                base_name = f"FIXME_{base_name}"
                
            json_path = os.path.join(out_dir, f"{base_name}.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump([dsl_result], f, ensure_ascii=False, indent=4)
                
            # 画像のダウンロード（SP_SSR_XXXX.png 形式）
            img_url = args.image_url or result.get('image_url')
            if img_url:
                img_path = os.path.join(out_dir, f"{base_name}.png")
                download_card_image(img_url, img_path)
            
        print("-" * 40)
        print(f"Scraping, DSL conversion, and Image download complete for {card_name}")
