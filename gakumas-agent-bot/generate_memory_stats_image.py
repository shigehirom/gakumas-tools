"""
generate_memory_stats_image.py
メモリー統計（全アイドル一覧／個別アイドル一覧）の高品質インフォグラフィック画像を生成するスクリプト
"""

import sys
import os
import json
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def get_font(size: int):
    candidates = [
        Path("/root/gakumas-workspace/gakumas-agent-bot/fonts/NotoSansJP-Bold.ttf"),
        Path("/app/gakumas-agent-bot/fonts/NotoSansJP-Bold.ttf"),
        Path(__file__).resolve().parent / "fonts" / "NotoSansJP-Bold.ttf",
    ]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    return ImageFont.load_default()

def round_rectangle(draw: ImageDraw.ImageDraw, xy, radius, fill=None, outline=None, width=1):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)

def render_overall_image(data: dict, output_path: str):
    """
    全アイドルのメモリー状況テーブル画像を生成
    data format:
    {
        "title": "全アイドル メモリー所持状況",
        "subtitle": "総登録枚数: 755枚",
        "rows": [
            {"name": "花海 咲季", "sense": 19, "logic": 1, "anomaly": 12, "subtotal": 32},
            ...
        ],
        "totals": {"sense": 280, "logic": 301, "anomaly": 174, "grandTotal": 755}
    }
    """
    rows = data["rows"]
    totals = data["totals"]
    
    img_width = 820
    row_height = 42
    header_height = 100
    table_header_height = 44
    footer_row_height = 48
    padding_bottom = 24
    
    total_height = header_height + table_header_height + (len(rows) * row_height) + footer_row_height + padding_bottom
    
    # 背景作成
    img = Image.new("RGB", (img_width, total_height), color=(30, 31, 34)) # Discord #1e1f22
    draw = ImageDraw.Draw(img)
    
    # フォント
    font_title = get_font(24)
    font_sub = get_font(14)
    font_th = get_font(16)
    font_td = get_font(16)
    font_num = get_font(16)
    font_total = get_font(17)
    
    # ヘッダー領域
    draw.text((36, 28), data.get("title", "全アイドル メモリー所持状況"), font=font_title, fill=(255, 255, 255))
    draw.text((36, 62), data.get("subtitle", f"総登録枚数: {totals['grandTotal']}枚"), font=font_sub, fill=(181, 186, 193))
    
    # テーブル外枠
    tbl_left = 32
    tbl_right = img_width - 32
    tbl_top = header_height
    tbl_bottom = tbl_top + table_header_height + (len(rows) * row_height) + footer_row_height
    
    # テーブル背景（角丸カード）
    round_rectangle(draw, (tbl_left, tbl_top, tbl_right, tbl_bottom), radius=12, fill=(43, 45, 49), outline=(63, 66, 72), width=1)
    
    # 列定義 (x_start, width, align)
    # 幅: 756px
    cols = [
        {"key": "name", "label": "アイドル名", "x": tbl_left + 24, "w": 200, "align": "left"},
        {"key": "sense", "label": "センス", "x": tbl_left + 240, "w": 110, "align": "right", "color": (100, 180, 255)},
        {"key": "logic", "label": "ロジック", "x": tbl_left + 370, "w": 110, "align": "right", "color": (255, 140, 180)},
        {"key": "anomaly", "label": "アノマリー", "x": tbl_left + 500, "w": 110, "align": "right", "color": (210, 140, 255)},
        {"key": "subtotal", "label": "計", "x": tbl_left + 630, "w": 90, "align": "right", "color": (255, 236, 153)},
    ]
    
    # テーブルヘッダー描画
    th_bg_y1 = tbl_top + 1
    th_bg_y2 = tbl_top + table_header_height
    draw.rectangle((tbl_left + 1, th_bg_y1, tbl_right - 1, th_bg_y2), fill=(49, 51, 56))
    draw.line((tbl_left, th_bg_y2, tbl_right, th_bg_y2), fill=(63, 66, 72), width=1)
    
    for c in cols:
        th_color = c.get("color", (219, 222, 225))
        lbl = c["label"]
        bbox = font_th.getbbox(lbl)
        tw = bbox[2] - bbox[0]
        tx = c["x"] if c["align"] == "left" else (c["x"] + c["w"] - tw)
        ty = th_bg_y1 + (table_header_height - (bbox[3] - bbox[1])) // 2 - 2
        draw.text((tx, ty), lbl, font=font_th, fill=th_color)
    
    # データ行描画
    cur_y = th_bg_y2
    for idx, r in enumerate(rows):
        row_bg = (43, 45, 49) if idx % 2 == 0 else (38, 40, 44)
        draw.rectangle((tbl_left + 1, cur_y, tbl_right - 1, cur_y + row_height), fill=row_bg)
        
        # 下罫線（薄く）
        draw.line((tbl_left + 12, cur_y + row_height, tbl_right - 12, cur_y + row_height), fill=(55, 58, 64), width=1)
        
        # セル値描画
        for c in cols:
            val = str(r[c["key"]])
            font_use = font_td if c["key"] == "name" else font_num
            
            # 0枚は少し暗いグレーに
            if c["key"] != "name" and r[c["key"]] == 0:
                color = (114, 118, 125)
            elif c["key"] == "subtotal":
                color = (255, 236, 153)
            else:
                color = (240, 243, 246)
                
            bbox = font_use.getbbox(val)
            tw = bbox[2] - bbox[0]
            tx = c["x"] if c["align"] == "left" else (c["x"] + c["w"] - tw)
            ty = cur_y + (row_height - (bbox[3] - bbox[1])) // 2 - 2
            draw.text((tx, ty), val, font=font_use, fill=color)
            
        cur_y += row_height
        
    # 合計行
    footer_bg = (32, 34, 37)
    draw.rectangle((tbl_left + 1, cur_y, tbl_right - 1, cur_y + footer_row_height - 1), fill=footer_bg)
    draw.line((tbl_left, cur_y, tbl_right, cur_y), fill=(100, 105, 115), width=2)
    
    total_data = {
        "name": "合計",
        "sense": totals["sense"],
        "logic": totals["logic"],
        "anomaly": totals["anomaly"],
        "subtotal": totals["grandTotal"]
    }
    
    for c in cols:
        val = str(total_data[c["key"]])
        color = (255, 236, 153) if c["key"] == "subtotal" else (255, 255, 255)
        bbox = font_total.getbbox(val)
        tw = bbox[2] - bbox[0]
        tx = c["x"] if c["align"] == "left" else (c["x"] + c["w"] - tw)
        ty = cur_y + (footer_row_height - (bbox[3] - bbox[1])) // 2 - 2
        draw.text((tx, ty), val, font=font_total, fill=color)
        
    img.save(output_path, "PNG")
    print(f"Saved: {output_path}")

def render_individual_image(data: dict, output_path: str):
    """
    個別アイドルのメモリー状況テーブル画像を生成
    data format:
    {
        "title": "十王 星南 メモリー所持状況",
        "subtitle": "所持枚数: 76枚",
        "rows": [
            {"plan": "センス", "effect": "好調", "title": "Campus mode!!", "count": 13},
            ...
        ],
        "total": 76
    }
    """
    rows = data["rows"]
    total = data["total"]
    
    img_width = 820
    row_height = 42
    header_height = 100
    table_header_height = 44
    footer_row_height = 48
    padding_bottom = 24
    
    total_height = header_height + table_header_height + (len(rows) * row_height) + footer_row_height + padding_bottom
    
    img = Image.new("RGB", (img_width, total_height), color=(30, 31, 34))
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(24)
    font_sub = get_font(14)
    font_th = get_font(16)
    font_td = get_font(16)
    font_num = get_font(16)
    font_total = get_font(17)
    
    draw.text((36, 28), data.get("title", "個別アイドル メモリー所持状況"), font=font_title, fill=(255, 255, 255))
    draw.text((36, 62), data.get("subtitle", f"所持枚数: {total}枚"), font=font_sub, fill=(181, 186, 193))
    
    tbl_left = 32
    tbl_right = img_width - 32
    tbl_top = header_height
    tbl_bottom = tbl_top + table_header_height + (len(rows) * row_height) + footer_row_height
    
    round_rectangle(draw, (tbl_left, tbl_top, tbl_right, tbl_bottom), radius=12, fill=(43, 45, 49), outline=(63, 66, 72), width=1)
    
    cols = [
        {"key": "plan", "label": "タイプ", "x": tbl_left + 24, "w": 120, "align": "left"},
        {"key": "effect", "label": "効果", "x": tbl_left + 160, "w": 100, "align": "left"},
        {"key": "title", "label": "楽曲名", "x": tbl_left + 280, "w": 350, "align": "left"},
        {"key": "count", "label": "枚数", "x": tbl_left + 640, "w": 80, "align": "right", "color": (255, 236, 153)},
    ]
    
    th_bg_y1 = tbl_top + 1
    th_bg_y2 = tbl_top + table_header_height
    draw.rectangle((tbl_left + 1, th_bg_y1, tbl_right - 1, th_bg_y2), fill=(49, 51, 56))
    draw.line((tbl_left, th_bg_y2, tbl_right, th_bg_y2), fill=(63, 66, 72), width=1)
    
    for c in cols:
        th_color = c.get("color", (219, 222, 225))
        lbl = c["label"]
        bbox = font_th.getbbox(lbl)
        tw = bbox[2] - bbox[0]
        tx = c["x"] if c["align"] == "left" else (c["x"] + c["w"] - tw)
        ty = th_bg_y1 + (table_header_height - (bbox[3] - bbox[1])) // 2 - 2
        draw.text((tx, ty), lbl, font=font_th, fill=th_color)
        
    cur_y = th_bg_y2
    for idx, r in enumerate(rows):
        row_bg = (43, 45, 49) if idx % 2 == 0 else (38, 40, 44)
        draw.rectangle((tbl_left + 1, cur_y, tbl_right - 1, cur_y + row_height), fill=row_bg)
        draw.line((tbl_left + 12, cur_y + row_height, tbl_right - 12, cur_y + row_height), fill=(55, 58, 64), width=1)
        
        for c in cols:
            val = str(r[c["key"]])
            font_use = font_num if c["key"] == "count" else font_td
            
            # プランごとのバッジ色
            if c["key"] == "plan":
                if val == "センス": color = (100, 180, 255)
                elif val == "ロジック": color = (255, 140, 180)
                elif val == "アノマリー": color = (210, 140, 255)
                else: color = (240, 243, 246)
            elif c["key"] == "count":
                color = (114, 118, 125) if r["count"] == 0 else (255, 236, 153)
            else:
                color = (240, 243, 246)
                
            bbox = font_use.getbbox(val)
            tw = bbox[2] - bbox[0]
            tx = c["x"] if c["align"] == "left" else (c["x"] + c["w"] - tw)
            ty = cur_y + (row_height - (bbox[3] - bbox[1])) // 2 - 2
            draw.text((tx, ty), val, font=font_use, fill=color)
            
        cur_y += row_height
        
    # 合計行
    footer_bg = (32, 34, 37)
    draw.rectangle((tbl_left + 1, cur_y, tbl_right - 1, cur_y + footer_row_height - 1), fill=footer_bg)
    draw.line((tbl_left, cur_y, tbl_right, cur_y), fill=(100, 105, 115), width=2)
    
    # 「合計」ラベル
    bbox = font_total.getbbox("合計")
    ty = cur_y + (footer_row_height - (bbox[3] - bbox[1])) // 2 - 2
    draw.text((tbl_left + 24, ty), "合計", font=font_total, fill=(255, 255, 255))
    
    # 合計数値
    val = str(total)
    bbox = font_total.getbbox(val)
    tw = bbox[2] - bbox[0]
    tx = (tbl_left + 640) + 80 - tw
    draw.text((tx, ty), val, font=font_total, fill=(255, 236, 153))
    
    img.save(output_path, "PNG")
    print(f"Saved: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True, help="Path to input json or raw json string")
    parser.add_argument("--output", required=True, help="Path to output PNG image")
    args = parser.parse_args()
    
    if os.path.exists(args.json_input):
        with open(args.json_input, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(args.json_input)
        
    mode = data.get("mode", "overall")
    if mode == "overall":
        render_overall_image(data, args.output)
    else:
        render_individual_image(data, args.output)
