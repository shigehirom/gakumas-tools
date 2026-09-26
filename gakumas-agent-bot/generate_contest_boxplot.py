#!/usr/bin/env python3
"""
generate_contest_boxplot.py — コンテストシミュレーション結果（全アイドル横方向箱ひげ図）画像生成エンジン

- 対象: MongoDB の loadouts コレクションに保存された最新シミュレーション結果
- アイドル順: canonical 昇順 (saki, temari, kotone, tsubame, mao, lilja, china, sumika, hiro, sena, misuzu, ume, rinami)
- 表示内容: Pアイドルアイコン、二つ名、横方向箱ひげ図（min/q1/med/mean/q3/max）、平均値・中央値
- 目盛り: ステージの最大スコアに応じて自動スケーリング
"""

import io
import os
import re
import json
import csv
import logging
import argparse
from pathlib import Path
from typing import Any
import pymongo
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("generate_contest_boxplot")

def _find_dir(candidates: list[Path]) -> Path:
    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return candidates[0]

def _find_workspace_dir() -> Path:
    candidates = [
        Path("/root/gakumas-workspace"),
        Path("/app"),
        Path(__file__).resolve().parent.parent,
        Path(os.getcwd()),
    ]
    for c in candidates:
        if c.exists() and ((c / "gakumas-tools").exists() or (c / "shared").exists()):
            return c
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]

WORKSPACE_DIR = _find_workspace_dir()

CSV_DIR = _find_dir([
    Path("/app/packages/gakumas-data/csv"),
    Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/csv"),
    WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-data" / "csv",
    WORKSPACE_DIR / "packages" / "gakumas-data" / "csv",
])

PIDOL_IMAGES_DIR = _find_dir([
    Path("/app/packages/gakumas-images/images/pIdols"),
    Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-images/images/pIdols"),
    WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-images" / "images" / "pIdols",
    WORKSPACE_DIR / "packages" / "gakumas-images" / "images" / "pIdols",
])

FONTS_DIR = _find_dir([
    Path("/app/gakumas-agent-bot/fonts"),
    Path("/root/gakumas-workspace/gakumas-agent-bot/fonts"),
    Path(__file__).resolve().parent / "fonts",
    WORKSPACE_DIR / "gakumas-agent-bot" / "fonts",
])

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://192.168.100.4:27017")
MONGODB_DB = os.environ.get("MONGODB_DB", "gakumas-tools")

# アイドル表示順（canonical 昇順）
ALL_IDOL_NAMES = [
    "saki", "temari", "kotone", "tsubame", "mao", "lilja", "china",
    "sumika", "hiro", "sena", "misuzu", "ume", "rinami"
]

IDOL_NAME_TO_ID = {
    "saki": 1, "temari": 2, "kotone": 3, "mao": 4, "lilja": 5, "china": 6,
    "sumika": 7, "hiro": 8, "rinami": 9, "rina": 9, "ume": 10, "sena": 11, "misuzu": 12, "tsubame": 13
}

IDOL_ID_TO_KEY = {v: k for k, v in IDOL_NAME_TO_ID.items()}
IDOL_ID_TO_KEY[9] = "rinami"

IDOL_PERSONAL_COLORS = {
    1:  {"hex": "#DE3839", "rgb": (222, 56, 57)},     # 咲季
    2:  {"hex": "#1E7B85", "rgb": (30, 123, 133)},    # 手毬
    3:  {"hex": "#F8B600", "rgb": (248, 182, 0)},     # ことね
    4:  {"hex": "#9B1E42", "rgb": (155, 30, 66)},     # 麻央
    5:  {"hex": "#89C3EB", "rgb": (137, 195, 235)},   # リーリヤ
    6:  {"hex": "#ED6D1F", "rgb": (237, 109, 31)},    # 千奈
    7:  {"hex": "#78C13F", "rgb": (120, 193, 63)},    # 清夏
    8:  {"hex": "#98D9E8", "rgb": (152, 217, 232)},   # 広
    9:  {"hex": "#EA7299", "rgb": (234, 114, 153)},   # 莉波
    10: {"hex": "#F05A28", "rgb": (240, 90, 40)},     # 佑芽
    11: {"hex": "#D4A017", "rgb": (212, 160, 23)},    # 星南
    12: {"hex": "#8C7BB8", "rgb": (140, 123, 184)},   # 美鈴
    13: {"hex": "#3A6998", "rgb": (58, 105, 152)},    # 燕
}


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = FONTS_DIR / "NotoSansJP-Bold.ttf"
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def round_rect_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
    return mask


class ContestBoxPlotGenerator:
    def __init__(self, mongo_uri: str = MONGODB_URI, db_name: str = MONGODB_DB):
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self._load_master_data()

    def _load_master_data(self):
        # 1. Pアイテムマスタ
        self.p_item_to_pidol = {}
        items_csv = CSV_DIR / "p_items.csv"
        if items_csv.exists():
            with open(items_csv, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("sourceType") == "pIdol" and row.get("pIdolId"):
                        try:
                            self.p_item_to_pidol[int(row["id"])] = int(row["pIdolId"])
                        except ValueError:
                            pass

        # 2. Pアイドルマスタ
        self.pidol_to_idol = {}
        self.pidol_info = {}
        pidols_csv = CSV_DIR / "p_idols.csv"
        if pidols_csv.exists():
            with open(pidols_csv, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        pid = int(row["id"])
                        iid = int(row["idolId"])
                        self.pidol_to_idol[pid] = iid
                        self.pidol_info[pid] = row
                    except ValueError:
                        pass

        # 3. アイドルマスタ
        self.idols = {}
        idols_csv = CSV_DIR / "idols.csv"
        if idols_csv.exists():
            with open(idols_csv, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        self.idols[int(row["id"])] = row["name"]
                    except ValueError:
                        pass

        # 4. ステージマスタ (stages.json)
        self.stages_master = []
        stages_json = CSV_DIR.parent / "json" / "stages.json"
        if not stages_json.exists():
            stages_json = WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-data" / "json" / "stages.json"
        if stages_json.exists():
            try:
                with open(stages_json, encoding="utf-8") as f:
                    self.stages_master = json.load(f)
            except Exception:
                pass

    def get_stage_criteria_info(self, season: int, stage: int) -> dict[str, str]:
        """stages.json または regulation_*.md からステージの審査基準・プラン・ターン数を取得"""
        PLAN_MAP = {
            "sense": "センス",
            "logic": "ロジック",
            "anomaly": "アノマリー",
            "free": "共通",
        }

        # 1. regulation_{season}.md を優先探索
        reg_dirs = [
            WORKSPACE_DIR / "gakumas-tools" / "agent-instructions",
            WORKSPACE_DIR / "agent-instructions",
            WORKSPACE_DIR / "shared" / "agent-instructions",
            Path("/app/agent-instructions"),
        ]
        for d in reg_dirs:
            reg_file = d / f"regulation_{season}.md"
            if reg_file.exists():
                try:
                    content = reg_file.read_text(encoding="utf-8")
                    stage_blocks = re.split(r'#\s*Stage\s*[:\s]*(\d+)', content, flags=re.IGNORECASE)
                    for i in range(1, len(stage_blocks), 2):
                        if int(stage_blocks[i]) == stage:
                            block = stage_blocks[i + 1]
                            m_crit = re.search(r'criteria\s*:\s*([^\n]+)', block)
                            m_plan = re.search(r'plan\s*:\s*([^\n]+)', block)
                            m_turn = re.search(r'turn\s*:\s*(\d+)', block)

                            crit_str = m_crit.group(1).strip() if m_crit else ""
                            plan_str = m_plan.group(1).strip() if m_plan else ""
                            plan_jp = PLAN_MAP.get(plan_str.lower(), plan_str)
                            turn_str = f"{m_turn.group(1)}ターン" if m_turn else ""

                            # 実際のステージターン数は stages.json を優先
                            for s in self.stages_master:
                                if s.get("season") == season and s.get("stage") == stage:
                                    tc = s.get("turnCounts")
                                    if tc:
                                        tot = sum(int(t.strip()) for t in tc.split(",") if t.strip().isdigit())
                                        turn_str = f"{tot}ターン"
                                    break

                            return {
                                "criteria": crit_str,
                                "plan": plan_jp,
                                "turn": turn_str,
                            }
                except Exception:
                    pass

        # 2. stages.json からフォールバック
        for s in self.stages_master:
            if s.get("season") == season and s.get("stage") == stage:
                crit_raw = s.get("criteria", "")
                plan_raw = s.get("plan", "")
                turns_raw = s.get("turnCounts", "")

                crit_str = ""
                if crit_raw:
                    parts = [float(p.strip()) for p in crit_raw.split(",")]
                    if len(parts) == 3:
                        crit_str = f"(Vo, Da, Vi) = ({int(round(parts[0]*100))}, {int(round(parts[1]*100))}, {int(round(parts[2]*100))})"

                turn_str = ""
                if turns_raw:
                    tot = sum(int(t.strip()) for t in turns_raw.split(",") if t.strip().isdigit())
                    turn_str = f"{tot}ターン"

                plan_jp = PLAN_MAP.get(plan_raw.lower(), plan_raw)
                return {
                    "criteria": crit_str,
                    "plan": plan_jp,
                    "turn": turn_str,
                }

        return {"criteria": "", "plan": "", "turn": ""}

    def fetch_stage_data(self, stage: int = 1, season: int | None = None, date_str: str | None = None) -> dict[str, Any]:
        """MongoDB loadouts から特定ステージの最新データを取得"""
        client = pymongo.MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[self.db_name]

        # 最新シーズン・最新日付の自動解決
        if season is None:
            sample = db.loadouts.find_one({"derived.season": {"$exists": True}}, sort=[("derived.season", -1)])
            season = sample.get("derived", {}).get("season", 52) if sample else 52

        # 日付未指定の場合、対象シーズンの最新の name (YY-MM-DD) を探す（.old 除く）
        if not date_str:
            names = db.loadouts.distinct("name", {"derived.season": season, "name": {"$regex": r"^\d{2}-\d{2}-\d{2}$"}})
            if names:
                date_str = max(names)
            else:
                date_str = "latest"

        # stageId の解決（ステージ番号 1, 2, 3 またはステージ名で検索）
        query: dict[str, Any] = {
            "derived.season": season,
            "name": date_str
        }
        
        # stage 条件
        stage_keyword = f"ステージ{stage}"
        query["$or"] = [
            {"derived.stageName": {"$regex": stage_keyword}},
            {"stageId": (season - 1) * 3 + stage + 27}, # 例: 52-1 -> 181
            {"stageId": f"stage-{stage}"}
        ]

        raw_runs = list(db.loadouts.find(query))
        
        # もし見つからなければ、ステージ名プレフィックスで再試行
        if not raw_runs:
            raw_runs = list(db.loadouts.find({
                "derived.season": season,
                "derived.stageName": {"$regex": stage_keyword}
            }).sort("createdAt", -1).limit(13))

        parsed_runs = []
        for r in raw_runs:
            stats = r.get("stats", {})
            if not stats or "min" not in stats:
                continue

            derived = r.get("derived", {})
            idol_id = derived.get("idolId")
            pidol_id = derived.get("pIdolId")

            # フォールバック
            if not idol_id:
                for it in r.get("pItemIds", []):
                    if it in self.p_item_to_pidol:
                        pidol_id = self.p_item_to_pidol[it]
                        idol_id = self.pidol_to_idol.get(pidol_id)
                        break

            idol_key = IDOL_ID_TO_KEY.get(idol_id)
            idol_name = self.idols.get(idol_id, "不明")
            card_title = self.pidol_info.get(pidol_id, {}).get("title", "")

            parsed_runs.append({
                "idol_id": idol_id,
                "idol_key": idol_key,
                "idol_name": idol_name,
                "card_title": card_title,
                "pidol_id": pidol_id,
                "stats": stats,
                "stage_name": derived.get("stageName", f"ステージ{stage}"),
                "season": season,
                "date_str": date_str,
                "runs_count": stats.get("count", 2000),
            })

        # アイドル重複がある場合は最新（_id 降順）を残す
        seen_idols = set()
        dedup_runs = []
        for r in reversed(parsed_runs):
            if r["idol_key"] not in seen_idols:
                seen_idols.add(r["idol_key"])
                dedup_runs.append(r)
        dedup_runs.reverse()

        # canonical 順にソート
        order_map = {name: idx for idx, name in enumerate(ALL_IDOL_NAMES)}
        dedup_runs.sort(key=lambda x: order_map.get(x["idol_key"], 999))

        crit_info = self.get_stage_criteria_info(season, stage)

        return {
            "season": season,
            "stage": stage,
            "stage_name": f"シーズン{season} ステージ{stage}",
            "date_str": date_str,
            "runs": dedup_runs,
            "criteria_info": crit_info,
        }

    def generate_image(self, data: dict[str, Any]) -> Image.Image:
        """箱ひげ図画像を Pillow でレンダリング"""
        runs = data.get("runs", [])
        season = data.get("season", 52)
        stage = data.get("stage", 1)
        date_str = data.get("date_str", "")
        crit_info = data.get("criteria_info", {})

        # 全体の最大値・目盛り計算
        all_maxs = [r["stats"]["max"] for r in runs if "max" in r["stats"]]
        global_min = 0
        global_max = max(all_maxs) if all_maxs else 800000

        # 目盛り刻み幅の動的決定
        if global_max <= 150000:
            tick_step = 25000
        elif global_max <= 300000:
            tick_step = 50000
        elif global_max <= 600000:
            tick_step = 100000
        elif global_max <= 1200000:
            tick_step = 200000
        else:
            tick_step = 500000

        axis_max = ((int(global_max) // tick_step) + 1) * tick_step
        ticks = list(range(0, axis_max + 1, tick_step))

        # レイアウト寸法
        IMG_W = 860
        HEADER_H = 106
        AXIS_H = 34
        ROW_H = 46
        ROW_GAP = 6
        FOOTER_H = 36
        NUM_ROWS = max(len(runs), 1)

        CONTENT_H = NUM_ROWS * (ROW_H + ROW_GAP)
        IMG_H = HEADER_H + AXIS_H + CONTENT_H + FOOTER_H

        LEFT_MARGIN = 24
        RIGHT_MARGIN = 24
        IDOL_COL_X = LEFT_MARGIN
        IDOL_COL_W = 196
        CHART_COL_X = IDOL_COL_X + IDOL_COL_W  # 220
        NUM_COL_W = 160
        CHART_COL_W = IMG_W - RIGHT_MARGIN - NUM_COL_W - CHART_COL_X  # 456
        NUM_COL_X = CHART_COL_X + CHART_COL_W  # 676

        # 背景キャンバス (Discord ダークテーマ #1E1F22)
        img = Image.new("RGBA", (IMG_W, IMG_H), (30, 31, 34, 255))
        draw = ImageDraw.Draw(img)

        # フォント読み込み
        font_title = get_font(20)
        font_subtitle = get_font(12)
        font_crit = get_font(12)
        font_axis = get_font(11)
        font_idol = get_font(13)
        font_card = get_font(10)
        font_val_label = get_font(11)
        font_val = get_font(13)
        font_footer = get_font(11)

        # ── ヘッダー描画 ──────────────────────────────────────────────────────
        # 左端アクセントバー（学マスオレンジ）
        draw.rounded_rectangle([(LEFT_MARGIN, 18), (LEFT_MARGIN + 5, 88)], radius=2, fill=(255, 122, 0, 255))

        # 1行目: タイトル
        title_text = f"SEASON {season} ｜ STAGE {stage} コンテストリハーサル推計"
        draw.text((LEFT_MARGIN + 16, 18), title_text, fill=(245, 245, 245, 255), font=font_title)

        # 2行目: 最新シミュレーション結果
        runs_count = runs[0].get("runs_count", 2000) if runs else 2000
        formatted_date = f"20{date_str.replace('-', '/')}" if date_str and len(date_str) == 8 else date_str
        subtitle_text = f"最新シミュレーション結果（{formatted_date} ・ 試行回数 {runs_count:,}回） ｜ 全アイドル昇順"
        draw.text((LEFT_MARGIN + 16, 46), subtitle_text, fill=(160, 165, 175, 255), font=font_subtitle)

        # 3行目: 審査基準・プラン情報
        crit_parts = []
        if crit_info.get("criteria"):
            crit_parts.append(f"審査基準: {crit_info['criteria']}")
        if crit_info.get("plan"):
            plan_str = f"プラン: {crit_info['plan']}"
            if crit_info.get("turn"):
                plan_str += f" ({crit_info['turn']})"
            crit_parts.append(plan_str)
        crit_text = " ｜ ".join(crit_parts) if crit_parts else "審査基準情報なし"
        draw.text((LEFT_MARGIN + 16, 68), crit_text, fill=(210, 218, 230, 255), font=font_crit)

        # 凡例（ヘッダー右端上部）
        legend_x = IMG_W - RIGHT_MARGIN - 240
        legend_y = 24
        # ボックス凡例
        draw.rectangle([(legend_x, legend_y + 2), (legend_x + 16, legend_y + 12)], fill=(255, 122, 0, 90), outline=(255, 122, 0, 230))
        draw.line([(legend_x + 8, legend_y + 2), (legend_x + 8, legend_y + 12)], fill=(255, 122, 0, 255), width=2)
        draw.text((legend_x + 22, legend_y), "Q1~Q3(中央値)", fill=(190, 195, 205, 255), font=font_axis)
        # 平均凡例
        mean_leg_x = legend_x + 140
        draw.ellipse([(mean_leg_x, legend_y + 3), (mean_leg_x + 8, legend_y + 11)], fill=(255, 255, 255, 255), outline=(255, 122, 0, 255), width=1)
        draw.text((mean_leg_x + 14, legend_y), "平均値", fill=(190, 195, 205, 255), font=font_axis)

        # ── 目盛り軸描画 ──────────────────────────────────────────────────────
        axis_y = HEADER_H

        def val_to_x(val: float) -> int:
            pct = (val - global_min) / (axis_max - global_min)
            pct = max(0.0, min(1.0, pct))
            return CHART_COL_X + int(pct * CHART_COL_W)

        for t in ticks:
            tx = val_to_x(t)
            if t == 0:
                t_str = "0"
            elif t >= 10000:
                if t % 10000 == 0:
                    t_str = f"{t // 10000}万"
                else:
                    t_str = f"{t / 10000:.1f}万"
            else:
                t_str = f"{t:,}"

            bbox = draw.textbbox((0, 0), t_str, font=font_axis)
            tw = bbox[2] - bbox[0]
            draw.text((tx - tw // 2, axis_y + 8), t_str, fill=(150, 155, 165, 255), font=font_axis)

            # 縦の破線グリッド
            grid_start_y = axis_y + AXIS_H - 4
            grid_end_y = axis_y + AXIS_H + CONTENT_H
            dash_len = 4
            dash_gap = 3
            y = grid_start_y
            while y < grid_end_y:
                draw.line([(tx, y), (tx, min(y + dash_len, grid_end_y))], fill=(58, 62, 70, 255), width=1)
                y += dash_len + dash_gap

        # ── 各アイドル行の描画 ───────────────────────────────────────────────
        for i, r in enumerate(runs):
            row_y = HEADER_H + AXIS_H + i * (ROW_H + ROW_GAP)

            # 行背景（ゼブラカード調）
            bg_color = (38, 40, 44, 255) if i % 2 == 0 else (34, 36, 40, 255)
            draw.rounded_rectangle([(LEFT_MARGIN, row_y), (IMG_W - RIGHT_MARGIN, row_y + ROW_H)], radius=6, fill=bg_color)

            # パーソナルカラー
            p_color = IDOL_PERSONAL_COLORS.get(r["idol_id"], {"rgb": (255, 122, 0)})
            c_rgb = p_color["rgb"]
            c_line = (c_rgb[0], c_rgb[1], c_rgb[2], 255)
            c_box = (c_rgb[0], c_rgb[1], c_rgb[2], 55)
            c_border = (c_rgb[0], c_rgb[1], c_rgb[2], 180)

            # 1. Pアイドルアイコン
            icon_size = 36
            icon_x = LEFT_MARGIN + 8
            icon_y = row_y + (ROW_H - icon_size) // 2

            pidol_id = r["pidol_id"]
            icon_path = PIDOL_IMAGES_DIR / f"{pidol_id}.png"
            if icon_path.exists():
                try:
                    icon_img = Image.open(icon_path).convert("RGBA")
                    icon_img = icon_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
                    mask = round_rect_mask((icon_size, icon_size), radius=6)
                    img.paste(icon_img, (icon_x, icon_y), mask)
                    draw.rounded_rectangle([(icon_x, icon_y), (icon_x + icon_size - 1, icon_y + icon_size - 1)], radius=6, outline=c_border, width=1)
                except Exception:
                    pass

            # 2. アイドル名・二つ名
            name_x = icon_x + icon_size + 10
            draw.text((name_x, row_y + 7), r["idol_name"], fill=(235, 238, 242, 255), font=font_idol)
            card_text = f"[{r['card_title']}]" if r["card_title"] else ""
            draw.text((name_x, row_y + 25), card_text, fill=(150, 155, 165, 255), font=font_card)

            # 3. 横方向箱ひげ図
            stats = r["stats"]
            if stats and "min" in stats:
                min_x = val_to_x(stats["min"])
                max_x = val_to_x(stats["max"])
                q1_x = val_to_x(stats["q1"])
                q3_x = val_to_x(stats["q3"])
                med_x = val_to_x(stats["median"])
                mean_x = val_to_x(stats["mean"])

                box_center_y = row_y + ROW_H // 2
                box_h = 16
                box_top = box_center_y - box_h // 2
                box_bottom = box_center_y + box_h // 2

                # ヒゲ水平線（min 〜 max）
                draw.line([(min_x, box_center_y), (max_x, box_center_y)], fill=c_line, width=1)
                # min / max 縦キャップ
                cap_h = 8
                draw.line([(min_x, box_center_y - cap_h // 2), (min_x, box_center_y + cap_h // 2)], fill=c_line, width=1)
                draw.line([(max_x, box_center_y - cap_h // 2), (max_x, box_center_y + cap_h // 2)], fill=c_line, width=1)

                # Q1〜Q3 ボックス
                box_w = max(q3_x - q1_x, 2)
                box_overlay = Image.new("RGBA", (box_w, box_h), c_box)
                img.paste(box_overlay, (q1_x, box_top), box_overlay)
                draw.rectangle([(q1_x, box_top), (q3_x, box_bottom)], outline=c_line, width=1)

                # 中央値ライン
                draw.line([(med_x, box_top - 1), (med_x, box_bottom + 1)], fill=c_line, width=2)

                # 平均値マーカー（丸ドット）
                r_dot = 3
                draw.ellipse([(mean_x - r_dot, box_center_y - r_dot), (mean_x + r_dot, box_center_y + r_dot)], fill=(255, 255, 255, 255), outline=c_line, width=1)

            # 4. 数値表示（平均 / 中央）
            num_x = NUM_COL_X + 16
            num_right_x = IMG_W - RIGHT_MARGIN - 16

            mean_val_str = f"{int(round(stats.get('mean', 0))):,}"
            draw.text((num_x, row_y + 8), "平均", fill=(140, 145, 155, 255), font=font_val_label)
            bbox_m = draw.textbbox((0, 0), mean_val_str, font=font_val)
            draw.text((num_right_x - (bbox_m[2] - bbox_m[0]), row_y + 6), mean_val_str, fill=(240, 240, 245, 255), font=font_val)

            med_val_str = f"{int(round(stats.get('median', 0))):,}"
            draw.text((num_x, row_y + 24), "中央", fill=(140, 145, 155, 255), font=font_val_label)
            bbox_med = draw.textbbox((0, 0), med_val_str, font=font_val)
            draw.text((num_right_x - (bbox_med[2] - bbox_med[0]), row_y + 22), med_val_str, fill=(210, 215, 225, 255), font=font_val)

        # ── フッター ──────────────────────────────────────────────────────────
        footer_y = IMG_H - FOOTER_H + 6
        footer_text = "※ 本シミュレーション結果はコンテストステージトップボーナス (+20%) を除いた素点値です。"
        draw.text((LEFT_MARGIN, footer_y), footer_text, fill=(120, 125, 135, 255), font=font_footer)

        return img

    def build_png_bytes(self, stage: int = 1, season: int | None = None, date_str: str | None = None) -> tuple[bytes, dict[str, Any]]:
        """指定ステージの画像バイナリとメタデータを生成"""
        data = self.fetch_stage_data(stage=stage, season=season, date_str=date_str)
        if not data["runs"]:
            raise ValueError(f"指定された条件（シーズン {data['season']} ステージ {stage} 日付 {data['date_str']}）のデータが見つかりませんでした。")
        img = self.generate_image(data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), data


def main():
    parser = argparse.ArgumentParser(description="コンテスト箱ひげ図画像を生成します")
    parser.add_argument("--stage", "-s", type=int, default=1, choices=[1, 2, 3], help="ステージ番号 (1, 2, 3)")
    parser.add_argument("--season", type=int, default=None, help="コンテストシーズン番号 (省略時は最新)")
    parser.add_argument("--date", "-d", type=str, default=None, help="シミュレーション日付 (YY-MM-DD、省略時は最新)")
    parser.add_argument("--output", "-o", type=str, default=None, help="出力ファイルパス")
    args = parser.parse_args()

    gen = ContestBoxPlotGenerator()
    png_bytes, meta = gen.build_png_bytes(stage=args.stage, season=args.season, date_str=args.date)

    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = WORKSPACE_DIR / "shared" / "documents"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"contest_boxplot_s{meta['season']}_stage{args.stage}_{meta['date_str']}.png"

    with open(out_path, "wb") as f:
        f.write(png_bytes)

    print(f"画像生成が完了しました: {out_path} (シーズン {meta['season']} ステージ {meta['stage']}, {len(meta['runs'])} アイドル)")


if __name__ == "__main__":
    main()
