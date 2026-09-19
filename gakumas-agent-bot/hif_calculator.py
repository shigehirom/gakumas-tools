#!/usr/bin/env python3
"""
hif_calculator.py
H.I.F編のプロデュース評価および目標スコア逆算モジュール & CLI
Web UI (gakumas-tools/utils/hif.js & produceRank.js) と完全同一の計算・画像生成を提供
"""

import os
import sys
import json
import math
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image, ImageDraw, ImageFont

# --- HIF定数 (gakumas-tools/utils/hif.js より) ---
MAX_PARAMS = 3200
MAX_PRE_ROUND2_STAR = 1110
MAX_ROUND1_SCORE = 1680000
MAX_ROUND2_SCORE = 2400000

STAT_MULTIPLIER = 2.0
STAR_MULTIPLIER = 7.5
ROUND2_STAR_GAIN_BOOST = 1.5
RATING_OFFSET = -2000.0

TARGET_RATING_BY_RANK: Dict[str, int] = {
    "S5": 35000,
    "S4+": 30000,
    "S4": 26000,
    "SSS+": 23000,
    "SSS": 20000,
    "SS+": 18000,
    "SS": 16000,
    "S+": 14500,
    "S": 13000,
    "A+": 11500,
    "A": 10000,
    "B+": 8000,
    "B": 6000,
    "C+": 4500,
    "C": 3000,
}

HIF_RANKS = [
    "S5",
    "S4+",
    "S4",
    "SSS+",
    "SSS",
    "SS+",
    "SS",
    "S+",
    "S",
    "A+",
    "A",
]

ROUND1_REGIMES = [
    (300000, 0.0, 0.0),
    (700000, 0.0, 0.01),
    (1000000, 4000.0, 0.003),
    (1200000, 4900.0, 0.002),
    (1400000, 5300.0, 0.001),
    (float("inf"), 5500.0, 0.0),
]

ROUND2_REGIMES = [
    (600000, 0.0, 0.0),
    (900000, 0.0, 0.004),
    (1500000, 1200.0, 0.008),
    (2000000, 6000.0, 0.002),
    (2400000, 7000.0, 0.001),
    (float("inf"), 7400.0, 0.0),
]

STAR_GAIN_REGIMES = [
    (400000, 0.0, 0.0001875),
    (600000, 75.0, 0.000225),
    (1000000, 120.0, 0.000075),
    (float("inf"), 150.0, 0.0),
]

def piecewise(value: float, regimes: List[Tuple[float, float, float]]) -> float:
    prev_threshold = 0.0
    for threshold, base, multiplier in regimes:
        if value <= threshold:
            return base + (value - prev_threshold) * multiplier
        prev_threshold = threshold
    return 0.0

def clamp_to_range(value: Optional[float], max_val: float) -> float:
    if value is None:
        return 0.0
    return min(max_val, max(0.0, float(value)))

def get_round1_rating(round1_score: int) -> int:
    adjusted_score = math.floor((round1_score or 0) / 1.2)
    return math.floor(piecewise(adjusted_score, ROUND1_REGIMES))

def get_round2_rating(round2_score: int) -> int:
    return math.floor(piecewise(round2_score or 0, ROUND2_REGIMES))

def get_star_gain_from_round2(round2_score: int) -> int:
    return math.ceil(piecewise(round2_score or 0, STAR_GAIN_REGIMES))

def get_boosted_round2_star_gain(round2_score: int) -> int:
    return math.floor(get_star_gain_from_round2(round2_score) * ROUND2_STAR_GAIN_BOOST)

def calculate_total_stats(params: List[int]) -> int:
    return int(sum(clamp_to_range(p, MAX_PARAMS) for p in params))

def calculate_param_star_rating(total_stats: int, pre_round2_star: int, round2_score: int) -> int:
    boosted_star_gain = get_boosted_round2_star_gain(round2_score)
    star = clamp_to_range(pre_round2_star, MAX_PRE_ROUND2_STAR)
    return math.floor(total_stats * STAT_MULTIPLIER + (boosted_star_gain + star) * STAR_MULTIPLIER)

def calculate_total_rating(params: List[int], pre_round2_star: int, round1_score: int, round2_score: int = 0) -> int:
    total_stats = calculate_total_stats(params)
    param_star_rating = calculate_param_star_rating(total_stats, pre_round2_star, round2_score)
    round1_rating = get_round1_rating(round1_score)
    round2_rating = get_round2_rating(round2_score)
    return int(param_star_rating + round1_rating + round2_rating + RATING_OFFSET)

def get_rank(rating: int) -> str:
    for rank, threshold in TARGET_RATING_BY_RANK.items():
        if rating >= threshold:
            return rank
    return "F"

def calculate_target_round2_scores(params: List[int], pre_round2_star: int, round1_score: int, current_round2_score: int = 0) -> List[Dict[str, Any]]:
    total_stats = calculate_total_stats(params)
    round1_rating = get_round1_rating(round1_score)

    def rating_at_round2(r2_score: int) -> int:
        ps_rating = calculate_param_star_rating(total_stats, pre_round2_star, r2_score)
        return int(ps_rating + round1_rating + get_round2_rating(r2_score) + RATING_OFFSET)

    current_rating = rating_at_round2(current_round2_score)
    results = []

    for rank in HIF_RANKS:
        target_rating = TARGET_RATING_BY_RANK[rank]
        if current_rating >= target_rating:
            results.append({"rank": rank, "target_rating": target_rating, "score": 0})
            continue

        lo = 0
        hi = MAX_ROUND2_SCORE
        required_score = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if rating_at_round2(mid) >= target_rating:
                required_score = mid
                hi = mid - 1
            else:
                lo = mid + 1

        results.append({"rank": rank, "target_rating": target_rating, "score": required_score})

    return results

# --- 画像描画 ---

def find_font(font_names: List[str], size: int) -> ImageFont.FreeTypeFont:
    candidate_paths = [
        Path("/app/fonts"),
        Path("/root/gakumas-workspace/gakumas-tools/gakumas-agent-bot/fonts"),
        Path("/root/gakumas-workspace/gakumas-agent-bot/fonts"),
        Path(__file__).parent / "fonts",
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/opentype/noto"),
        Path("/usr/share/fonts/truetype/noto"),
        Path("/usr/share/fonts"),
    ]
    # まず指定フォントを探索
    for p in candidate_paths:
        for name in font_names:
            fp = p / name
            if fp.exists():
                try:
                    return ImageFont.truetype(str(fp), size)
                except Exception:
                    pass
    # 次に NotoSansJP-Bold.ttf を探索
    for p in candidate_paths:
        fp = p / "NotoSansJP-Bold.ttf"
        if fp.exists():
            try:
                return ImageFont.truetype(str(fp), size)
            except Exception:
                pass
    return ImageFont.load_default()

def find_rank_icon(rank: str) -> Optional[Image.Image]:
    filename = f"{rank}.png"
    candidate_dirs = [
        Path("/app/public/ranks"),
        Path("/root/gakumas-workspace/gakumas-tools/gakumas-tools/public/ranks"),
        Path("/root/gakumas-workspace/gakumas-tools/public/ranks"),
        Path(__file__).parent.parent / "gakumas-tools" / "public" / "ranks",
        Path(__file__).parent / "public" / "ranks",
    ]
    for d in candidate_dirs:
        ip = d / filename
        if ip.exists():
            try:
                return Image.open(str(ip)).convert("RGBA")
            except Exception:
                pass
    return None

def generate_hif_calc_card(
    vo: int,
    da: int,
    vi: int,
    star: int,
    round1_score: int,
    current_rating: int,
    current_rank: str,
    target_rows: List[Dict[str, Any]],
    output_path: str
) -> str:
    """
    添付画像のWeb UIデザイン（プロデュース評価カード）を完全再現
    サイズ: 幅 556px, 高さ 620px
    """
    width = 556
    height = 636

    # 背景
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    font_bold = ["NotoSansJP-Bold.ttf", "NotoSansCJKjp-Bold.otf"]
    font_medium = ["NotoSansJP-Medium.ttf", "NotoSansCJKjp-Medium.otf", "NotoSansJP-Regular.ttf"]
    font_regular = ["NotoSansJP-Regular.ttf", "NotoSansCJKjp-Regular.otf"]

    f_badge = find_font(font_bold, 13)
    f_input = find_font(font_medium, 11)
    f_rating_val = find_font(font_bold, 40)
    f_subheading = find_font(font_bold, 14)
    f_th = find_font(font_bold, 14)
    f_td = find_font(font_medium, 14)

    # 1. 外枠カード: (16, 20) から (width-16, height-16)
    card_x0, card_y0 = 16, 22
    card_x1, card_y1 = width - 16, height - 16
    draw.rounded_rectangle([card_x0, card_y0, card_x1, card_y1], radius=12, fill=(255, 255, 255, 255), outline=(229, 231, 235, 255), width=1)

    # 2. 上部ピルバッジ: 「プロデュース評価」 (枠線をまたぐように配置)
    badge_text = "プロデュース評価"
    bbox = draw.textbbox((0, 0), badge_text, font=f_badge)
    tw = bbox[2] - bbox[0]
    badge_w = tw + 24
    badge_h = 24
    badge_x = card_x0 + 16
    badge_y = card_y0 - 12
    draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=12, fill=(241, 245, 249, 255))
    draw.text((badge_x + 12, badge_y + 3), badge_text, font=f_badge, fill=(100, 116, 139, 255))

    # 入力パラメータ概要表示 (右上)
    input_str = f"Vo {vo} / Da {da} / Vi {vi} / ★ {star} / R1 {round1_score:,}"
    ibbox = draw.textbbox((0, 0), input_str, font=f_input)
    iw = ibbox[2] - ibbox[0]
    draw.text((card_x1 - iw - 16, card_y0 + 8), input_str, font=f_input, fill=(148, 163, 184, 255))

    # 3. ランクアイコン & 評価値
    # 中央揃え
    rank_icon = find_rank_icon(current_rank)
    rating_str = f"{current_rating:,}"
    r_bbox = draw.textbbox((0, 0), rating_str, font=f_rating_val)
    rw = r_bbox[2] - r_bbox[0]
    rh = r_bbox[3] - r_bbox[1]

    icon_h = 42
    if rank_icon:
        icon_w = int(icon_h * (rank_icon.width / rank_icon.height))
        icon_resized = rank_icon.resize((icon_w, icon_h), Image.Resampling.LANCZOS)
    else:
        icon_w = 0
        icon_resized = None

    spacing = 10
    total_w = icon_w + (spacing if icon_w > 0 else 0) + rw
    start_x = (width - total_w) // 2
    top_y = card_y0 + 36

    if icon_resized:
        img.paste(icon_resized, (start_x, top_y + 2), icon_resized)
        score_x = start_x + icon_w + spacing
    else:
        score_x = start_x

    # 評価値の色: Web UI はゴールド/オレンジ (`#f59e0b` / `(245, 158, 11)`)
    draw.text((score_x, top_y - 3), rating_str, font=f_rating_val, fill=(245, 158, 11, 255))

    # 4. 見出し: 「目標ランク別 必要ラウンド2スコア」
    sh_y = top_y + 54
    draw.text((card_x0 + 16, sh_y), "目標ランク別 必要ラウンド2スコア", font=f_subheading, fill=(100, 116, 139, 255))

    # 5. テーブル
    tbl_x0 = card_x0 + 16
    tbl_x1 = card_x1 - 16
    tbl_y0 = sh_y + 26

    # テーブルヘッダー (薄いグレー背景)
    th_h = 36
    draw.rectangle([tbl_x0, tbl_y0, tbl_x1, tbl_y0 + th_h], fill=(243, 244, 246, 255))
    draw.text((tbl_x0 + 80, tbl_y0 + 8), "プロデュース評価", font=f_th, fill=(100, 116, 139, 255))
    draw.text((tbl_x1 - 140, tbl_y0 + 8), "目標スコア", font=f_th, fill=(100, 116, 139, 255))

    # テーブル行 (全11行)
    row_y = tbl_y0 + th_h
    row_h = 36

    for item in target_rows:
        r_name = item["rank"]
        t_rating = item["target_rating"]
        score = item["score"]

        # 下線
        draw.line([(tbl_x0, row_y), (tbl_x1, row_y)], fill=(243, 244, 246, 255), width=1)

        # 左列: 「S5 (35,000)」
        left_text = f"{r_name} ({t_rating:,})"
        l_bbox = draw.textbbox((0, 0), left_text, font=f_td)
        lw = l_bbox[2] - l_bbox[0]
        # テーブル左エリアの中央あたり
        draw.text((tbl_x0 + 130 - lw // 2, row_y + 8), left_text, font=f_td, fill=(55, 65, 81, 255))

        # 右列: 「∞」またはカンマ区切りスコア
        if score is None:
            right_text = "∞"
            fill_col = (107, 114, 128, 255)
        elif score == 0:
            right_text = "0"
            fill_col = (55, 65, 81, 255)
        else:
            right_text = f"{score:,}"
            fill_col = (55, 65, 81, 255)

        r_bbox = draw.textbbox((0, 0), right_text, font=f_td)
        rw = r_bbox[2] - r_bbox[0]
        # テーブル右エリアの中央あたり
        draw.text((tbl_x1 - 105 - rw // 2, row_y + 8), right_text, font=f_td, fill=fill_col)

        row_y += row_h

    # 保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path

def main():
    parser = argparse.ArgumentParser(description="HIF Produce Rating Calculator")
    parser.add_argument("--vo", type=int, required=True, help="Vocal stat")
    parser.add_argument("--da", type=int, required=True, help="Dance stat")
    parser.add_argument("--vi", type=int, required=True, help="Visual stat")
    parser.add_argument("--star", type=int, required=True, help="Star count before round 2")
    parser.add_argument("--round1-score", type=int, required=True, help="Round 1 score (in-game displayed with 1.2x bonus)")
    parser.add_argument("--out-image", type=str, default="", help="Path to output image")
    parser.add_argument("--json", action="store_true", help="Output JSON result")

    args = parser.parse_args()

    params = [args.vo, args.da, args.vi]
    current_rating = calculate_total_rating(params, args.star, args.round1_score, round2_score=0)
    current_rank = get_rank(current_rating)
    target_rows = calculate_target_round2_scores(params, args.star, args.round1_score, current_round2_score=0)

    image_path = None
    if args.out_image:
        image_path = generate_hif_calc_card(
            vo=args.vo,
            da=args.da,
            vi=args.vi,
            star=args.star,
            round1_score=args.round1_score,
            current_rating=current_rating,
            current_rank=current_rank,
            target_rows=target_rows,
            output_path=args.out_image
        )

    res = {
        "inputs": {
            "vo": args.vo,
            "da": args.da,
            "vi": args.vi,
            "star": args.star,
            "round1_score": args.round1_score
        },
        "current_rating": current_rating,
        "current_rank": current_rank,
        "target_rows": target_rows,
        "image_path": image_path
    }

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"=== H.I.F プロデュース評価 ===")
        print(f"現在の評価値: {current_rating:,} ({current_rank})")
        print("--- 目標ランク別 必要ラウンド2スコア ---")
        for row in target_rows:
            r = row["rank"]
            tr = row["target_rating"]
            s = row["score"]
            s_str = "0" if s == 0 else ("∞" if s is None else f"{s:,}")
            print(f"  {r:>4} ({tr:,}): {s_str:>11}")
        if image_path:
            print(f"画像生成: {image_path}")

if __name__ == "__main__":
    main()
