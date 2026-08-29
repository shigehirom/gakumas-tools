#!/usr/bin/env python3
"""
sync_support_card_images.py — support_cards.csv から全サポートカードの画像を SP_SSR_XXXX.png 形式で統一保存
"""
import os
import csv
import re
import time
import io
import requests
from PIL import Image

def download_and_save_as_png(image_url, save_path):
    """画像をダウンロードし、PNG形式で保存する"""
    if not image_url:
        return False

    orig_url = re.sub(r"-s\.(png|jpg|jpeg|webp)$", r".\1", image_url, flags=re.IGNORECASE)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for target_url in [orig_url, image_url]:
        try:
            resp = requests.get(target_url, headers=headers, timeout=15)
            if resp.status_code == 200 and len(resp.content) > 1000:
                # PIL で読み込み、RGB/RGBA の PNG として保存
                img = Image.open(io.BytesIO(resp.content))
                # RGBA または RGB モードを維持
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                img.save(save_path, "PNG", optimize=True)
                return True
        except Exception:
            pass

    return False

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "support_cards.csv")
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found")
        return

    out_dirs = [
        os.path.join(base_dir, "support_cards"),
        os.path.abspath(os.path.join(base_dir, "..", "gakumas-og-tools", "support-cards")),
    ]
    for d in out_dirs:
        os.makedirs(d, exist_ok=True)

    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"Total support cards to sync images as SP_*.png: {len(rows)}")

    # 既存の日本語名ファイルや .jpg ファイルをクリーンアップ
    for out_dir in out_dirs:
        for f in os.listdir(out_dir):
            if f.endswith(".jpg") or f.endswith(".jpeg") or f.endswith(".webp") or not f.startswith("SP_"):
                # .json または .png でかつ SP_ から始まらないものを削除
                if not f.startswith("SP_") and not f.startswith("FIXME_SP_"):
                    try:
                        os.remove(os.path.join(out_dir, f))
                    except Exception:
                        pass

    success_count = 0
    for i, row in enumerate(rows, 1):
        name = row.get("name", "").strip()
        wiki_id = row.get("wiki_id", "").strip()
        img_url = row.get("image_url", "").strip()

        if not wiki_id or not img_url:
            continue

        filename = f"{wiki_id}.png"
        target_path = os.path.join(out_dirs[0], filename)

        # 既に存在し、サイズが正常な場合はスキップ
        if os.path.exists(target_path) and os.path.getsize(target_path) > 5000:
            # 念のためもう一方のディレクトリにもコピー
            other_path = os.path.join(out_dirs[1], filename)
            if not os.path.exists(other_path):
                import shutil
                shutil.copy2(target_path, other_path)
            success_count += 1
            continue

        print(f"[{i}/{len(rows)}] Downloading {filename} for 【{name}】...")
        saved = download_and_save_as_png(img_url, target_path)
        if saved:
            import shutil
            shutil.copy2(target_path, os.path.join(out_dirs[1], filename))
            success_count += 1
        time.sleep(0.2)

    print(f"\n✅ All support card images saved as SP_*.png! ({success_count}/{len(rows)} cards)")

if __name__ == "__main__":
    main()
