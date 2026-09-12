"""
generate_memory_stats_image.py
メモリー統計（全アイドル一覧／個別アイドル一覧）の高品質インフォグラフィック画像を生成するスクリプト
- 横幅をスリム化・最適化
- 各アイドルのパーソナルカラーを反映
- 楽曲名冒頭に [SSR] / [SR] / [R] レアリティタグを表示
"""

import sys
import os
import json
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

IDOL_PERSONAL_COLORS = {
    1: {"hex": "#DE3839", "rgb": (222, 56, 57)},
    2: {"hex": "#1E7B85", "rgb": (30, 123, 133)},
    3: {"hex": "#F8B600", "rgb": (248, 182, 0)},
    4: {"hex": "#9B1E42", "rgb": (155, 30, 66)},
    5: {"hex": "#89C3EB", "rgb": (137, 195, 235)},
    6: {"hex": "#ED6D1F", "rgb": (237, 109, 31)},
    7: {"hex": "#78C13F", "rgb": (120, 193, 63)},
    8: {"hex": "#98D9E8", "rgb": (152, 217, 232)},
    9: {"hex": "#EA7299", "rgb": (234, 114, 153)},
    10: {"hex": "#F05A28", "rgb": (240, 90, 40)},
    11: {"hex": "#D4A017", "rgb": (212, 160, 23)},
    12: {"hex": "#8C7BB8", "rgb": (140, 123, 184)},
    13: {"hex": "#3A6998", "rgb": (58, 105, 152)},
}

IDOL_KEY_TO_COLOR = {
    "saki": IDOL_PERSONAL_COLORS[1],
    "temari": IDOL_PERSONAL_COLORS[2],
    "kotone": IDOL_PERSONAL_COLORS[3],
    "mao": IDOL_PERSONAL_COLORS[4],
    "lilja": IDOL_PERSONAL_COLORS[5],
    "china": IDOL_PERSONAL_COLORS[6],
    "sumika": IDOL_PERSONAL_COLORS[7],
    "hiro": IDOL_PERSONAL_COLORS[8],
    "rinami": IDOL_PERSONAL_COLORS[9],
    "ume": IDOL_PERSONAL_COLORS[10],
    "sena": IDOL_PERSONAL_COLORS[11],
    "misuzu": IDOL_PERSONAL_COLORS[12],
    "tsubame": IDOL_PERSONAL_COLORS[13],
}

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
    全アイドルのメモリー状況テーブル画像（スリム版 560px）
    """
    rows = data["rows"]
    totals = data["totals"]
    
    img_width = 560
    row_height = 38
    header_height = 84
    table_header_height = 40
    footer_row_height = 44
    padding_bottom = 20
    
    total_height = header_height + table_header_height + (len(rows) * row_height) + footer_row_height + padding_bottom
    
    img = Image.new("RGB", (img_width, total_height), color=(30, 31, 34))
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(21)
    font_sub = get_font(13)
    font_th = get_font(14)
    font_td = get_font(14)
    font_num = get_font(14)
    font_total = get_font(15)
    
    # ヘッダー領域
    draw.text((24, 20), data.get("title", "全アイドル メモリー所持状況"), font=font_title, fill=(255, 255, 255))
    draw.text((24, 50), data.get("subtitle", f"総登録枚数: {totals['grandTotal']}枚"), font=font_sub, fill=(181, 186, 193))
    
    tbl_left = 20
    tbl_right = img_width - 20
    tbl_top = header_height
    tbl_bottom = tbl_top + table_header_height + (len(rows) * row_height) + footer_row_height
    
    # テーブル外枠
    round_rectangle(draw, (tbl_left, tbl_top, tbl_right, tbl_bottom), radius=10, fill=(43, 45, 49), outline=(63, 66, 72), width=1)
    
    # 列定義 (x_start, width, align) - 合計 520px
    cols = [
        {"key": "name", "label": "アイドル名", "x": tbl_left + 16, "w": 140, "align": "left"},
        {"key": "sense", "label": "センス", "x": tbl_left + 160, "w": 75, "align": "right", "color": (100, 180, 255)},
        {"key": "logic", "label": "ロジック", "x": tbl_left + 245, "w": 80, "align": "right", "color": (255, 140, 180)},
        {"key": "anomaly", "label": "アノマリー", "x": tbl_left + 335, "w": 95, "align": "right", "color": (210, 140, 255)},
        {"key": "subtotal", "label": "計", "x": tbl_left + 440, "w": 64, "align": "right", "color": (255, 236, 153)},
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
        draw.line((tbl_left + 8, cur_y + row_height, tbl_right - 8, cur_y + row_height), fill=(55, 58, 64), width=1)
        
        # パーソナルカラードット描画
        idol_id = r.get("id", idx + 1)
        p_color = IDOL_PERSONAL_COLORS.get(idol_id, {}).get("rgb", (180, 180, 180))
        dot_y = cur_y + row_height // 2
        draw.ellipse((tbl_left + 16, dot_y - 4, tbl_left + 24, dot_y + 4), fill=p_color)
        
        for c in cols:
            val = str(r[c["key"]])
            font_use = font_td if c["key"] == "name" else font_num
            
            if c["key"] != "name" and r[c["key"]] == 0:
                color = (114, 118, 125)
            elif c["key"] == "subtotal":
                color = (255, 236, 153)
            else:
                color = (240, 243, 246)
                
            bbox = font_use.getbbox(val)
            tw = bbox[2] - bbox[0]
            # アイドル名だけドット分右にシフト
            if c["key"] == "name":
                tx = c["x"] + 16
            else:
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
    個別アイドルのメモリー状況テーブル画像（スリム版 560px）
    - パーソナルカラーをヘッダーのアクセントラインや枠線に反映
    - 楽曲名に [SSR] / [SR] / [R] のレアリティ表示
    """
    rows = data["rows"]
    total = data["total"]
    idol_key = data.get("idolKey", "")
    idol_id = data.get("idolId", 0)
    
    # パーソナルカラー取得
    p_info = IDOL_KEY_TO_COLOR.get(idol_key) or IDOL_PERSONAL_COLORS.get(idol_id) or {"rgb": (212, 160, 23)}
    personal_rgb = p_info["rgb"]
    
    img_width = 560
    row_height = 38
    header_height = 84
    table_header_height = 40
    footer_row_height = 44
    padding_bottom = 20
    
    total_height = header_height + table_header_height + (len(rows) * row_height) + footer_row_height + padding_bottom
    
    img = Image.new("RGB", (img_width, total_height), color=(30, 31, 34))
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(21)
    font_sub = get_font(13)
    font_th = get_font(14)
    font_td = get_font(14)
    font_num = get_font(14)
    font_rarity = get_font(11)
    font_total = get_font(15)
    
    # タイトル左側のパーソナルカラー縦バー (アクセント)
    draw.rounded_rectangle([20, 20, 25, 46], radius=2, fill=personal_rgb)
    draw.text((34, 20), data.get("title", "個別アイドル メモリー所持状況"), font=font_title, fill=(255, 255, 255))
    draw.text((34, 50), data.get("subtitle", f"所持枚数: {total}枚"), font=font_sub, fill=(181, 186, 193))
    
    tbl_left = 20
    tbl_right = img_width - 20
    tbl_top = header_height
    tbl_bottom = tbl_top + table_header_height + (len(rows) * row_height) + footer_row_height
    
    # テーブル外枠
    round_rectangle(draw, (tbl_left, tbl_top, tbl_right, tbl_bottom), radius=10, fill=(43, 45, 49), outline=(63, 66, 72), width=1)
    
    # 列定義 (合計 520px)
    cols = [
        {"key": "plan", "label": "タイプ", "x": tbl_left + 16, "w": 75, "align": "left"},
        {"key": "effect", "label": "効果", "x": tbl_left + 95, "w": 65, "align": "left"},
        {"key": "title", "label": "楽曲名", "x": tbl_left + 165, "w": 285, "align": "left"},
        {"key": "count", "label": "枚数", "x": tbl_left + 455, "w": 50, "align": "right", "color": (255, 236, 153)},
    ]
    
    th_bg_y1 = tbl_top + 1
    th_bg_y2 = tbl_top + table_header_height
    draw.rectangle((tbl_left + 1, th_bg_y1, tbl_right - 1, th_bg_y2), fill=(49, 51, 56))
    
    # ヘッダー下にパーソナルカラーのアクセント下線
    draw.line((tbl_left, th_bg_y2, tbl_right, th_bg_y2), fill=personal_rgb, width=2)
    
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
        draw.line((tbl_left + 8, cur_y + row_height, tbl_right - 8, cur_y + row_height), fill=(55, 58, 64), width=1)
        
        # 1. プラン (タイプ)
        plan_val = str(r["plan"])
        if plan_val == "センス": plan_color = (100, 180, 255)
        elif plan_val == "ロジック": plan_color = (255, 140, 180)
        elif plan_val == "アノマリー": plan_color = (210, 140, 255)
        else: plan_color = (240, 243, 246)
        ty = cur_y + (row_height - 18) // 2
        draw.text((cols[0]["x"], ty), plan_val, font=font_td, fill=plan_color)
        
        # 2. 効果
        effect_val = str(r["effect"])
        draw.text((cols[1]["x"], ty), effect_val, font=font_td, fill=(200, 205, 210))
        
        # 3. 楽曲名（レアリティタグ付き）
        # 例: [SSR] Campus mode!! または rarity フィールドがあれば利用
        rarity = r.get("rarity", "")
        raw_title = r.get("rawTitle") or r.get("title", "")
        if not rarity:
            # title に [SSR] 等が含まれているか解析
            if raw_title.startswith("[SSR]"):
                rarity = "SSR"
                raw_title = raw_title[5:].strip()
            elif raw_title.startswith("[SR]"):
                rarity = "SR"
                raw_title = raw_title[4:].strip()
            elif raw_title.startswith("[R]"):
                rarity = "R"
                raw_title = raw_title[3:].strip()
                
        tx_song = cols[2]["x"]
        if rarity:
            # レアリティバッジ描画
            if rarity == "SSR":
                badge_bg = (245, 159, 0)
                badge_fg = (0, 0, 0)
            elif rarity == "SR":
                badge_bg = (173, 181, 189)
                badge_fg = (0, 0, 0)
            else: # R
                badge_bg = (134, 142, 150)
                badge_fg = (255, 255, 255)
                
            badge_text = f"[{rarity}]"
            b_bbox = font_rarity.getbbox(badge_text)
            b_w = b_bbox[2] - b_bbox[0]
            
            # バッジテキスト描画
            badge_color = (255, 200, 60) if rarity == "SSR" else ((200, 210, 220) if rarity == "SR" else (160, 165, 175))
            draw.text((tx_song, ty + 1), badge_text, font=font_rarity, fill=badge_color)
            tx_song += b_w + 6
            
        draw.text((tx_song, ty), raw_title, font=font_td, fill=(240, 243, 246))
        
        # 4. 枚数
        count_val = str(r["count"])
        c_color = (114, 118, 125) if r["count"] == 0 else (255, 236, 153)
        bbox = font_num.getbbox(count_val)
        tw = bbox[2] - bbox[0]
        tx = cols[3]["x"] + cols[3]["w"] - tw
        draw.text((tx, ty), count_val, font=font_num, fill=c_color)
        
        cur_y += row_height
        
    # 合計行
    footer_bg = (32, 34, 37)
    draw.rectangle((tbl_left + 1, cur_y, tbl_right - 1, cur_y + footer_row_height - 1), fill=footer_bg)
    draw.line((tbl_left, cur_y, tbl_right, cur_y), fill=(100, 105, 115), width=2)
    
    ty = cur_y + (footer_row_height - 18) // 2
    draw.text((tbl_left + 16, ty), "合計", font=font_total, fill=(255, 255, 255))
    
    val = str(total)
    bbox = font_total.getbbox(val)
    tw = bbox[2] - bbox[0]
    tx = cols[3]["x"] + cols[3]["w"] - tw
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
