"""
loadout_image_builder.py — コンテスト実走シミュレーション結果（loadouts）インフォグラフィック画像生成エンジン

MongoDB loadouts コレクションの実走編成データから、高精度なインフォグラフィック画像を生成する。
- ①基本情報: アイドル名、衣装名、アバター（メイン＋サブ）、Vo/Da/Vi/HP ステータス、シミュレーションスコア（中央値・平均値）、使用メモリー名
- ②獲得Pアイテム: メイン・サブの有効アイテム一覧
- ③実走スキルカード (12枚):
    1. SSR (サポカ由来 -> アイドル固有 -> その他)
    2. SR
    3. R
    のレアリティ降順でソートして表示
"""

import io
import logging
import re
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont, ImageOps

from image_resolver import ImageResolver
from advisory_image_builder import get_font, round_corners, format_criteria

log = logging.getLogger("loadout_image_builder")


class LoadoutImageBuilder:
    def __init__(self):
        self.resolver = ImageResolver()

    def _find_pidol_image_path(self, pidol_id: int | str) -> Path | None:
        p = self.resolver._get_p_idol_image(str(pidol_id))
        if p and p.exists():
            return p
        return None

    def _get_pidol_info(self, pidol_id: int | str) -> dict[str, Any]:
        for p in self.resolver.p_idols:
            if str(p.get("id")) == str(pidol_id):
                return p
        return {}

    def _prepare_loadout_cards(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        """12枚のスキルカードを解決し、ソートする"""
        groups = doc.get("skillCardIdGroups", [])
        cust_groups = doc.get("customizationGroups", [])
        raw_cards = []

        for g_idx, group in enumerate(groups):
            cust_group = cust_groups[g_idx] if g_idx < len(cust_groups) else []
            for c_idx, cid in enumerate(group):
                if cid <= 0:
                    continue
                info = self.resolver.get_card_details(cid)
                cust_dict = cust_group[c_idx] if c_idx < len(cust_group) else {}
                cust_names = []
                for k, v in cust_dict.items():
                    c_name = self.resolver.customizations.get(int(k), f"カスタム{k}")
                    if v > 1:
                        cust_names.append(f"{c_name} Lv{v}")
                    else:
                        cust_names.append(c_name)

                # 固有カード判定 (メイン固有 / サブ固有)
                is_unique = (c_idx == 0 and info.get("pIdolId", 0) > 0) or info.get("sourceType") == "pidol"

                raw_cards.append({
                    "id": cid,
                    "name": info.get("name", f"Card_{cid}"),
                    "rarity": info.get("rarity", "R").upper(),
                    "sourceType": info.get("sourceType", "produce").lower(),
                    "group": "メイン" if g_idx == 0 else "サブ",
                    "is_unique": is_unique,
                    "is_main_unique": (g_idx == 0 and is_unique),
                    "is_sub_unique": (g_idx == 1 and is_unique),
                    "customizations": cust_names,
                })

        def _sort_key(c: dict[str, Any]) -> tuple[int, int, str]:
            r_order = {"SSR": 0, "SR": 1, "R": 2}.get(c["rarity"], 3)
            # 由来順序: 1. サポカ, 2. メイン固有, 3. サブ固有, 4. その他
            is_support = (c["sourceType"] == "support") or bool(self.resolver.get_skill_card_support_card_name(c["name"]))
            if is_support:
                s_order = 0
            elif c.get("is_main_unique"):
                s_order = 1
            elif c.get("is_sub_unique"):
                s_order = 2
            elif c["sourceType"] == "pidol":
                s_order = 3
            else:
                s_order = 4
            return (r_order, s_order, c["name"])

        # ソート: SSR (サポカ -> メイン固有 -> サブ固有 -> その他) -> SR -> R
        raw_cards.sort(key=_sort_key)
        return raw_cards

    def _prepare_loadout_pitems(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        """有効なPアイテム一覧を抽出・解決する"""
        pitem_ids = doc.get("pItemIds", [])
        items = []
        for idx, pid in enumerate(pitem_ids):
            if pid <= 0:
                continue
            p_info = self.resolver.p_items_by_id.get(pid, {"name": f"Item_{pid}", "source": ""})
            items.append({
                "id": pid,
                "name": p_info.get("name", f"Item_{pid}"),
                "source": p_info.get("source", ""),
                "group": "メイン" if idx < 4 else "サブ",
            })
        return items

    def build(self, doc: dict[str, Any], columns: int = 2, output_path: Path | None = None) -> bytes:
        """指定されたカラム数（1: スマホ縦長、2: ワイドグリッド）で画像を生成する"""
        if columns == 1:
            return self.build_1_column(doc, output_path)
        return self.build_2_columns(doc, output_path)

    def build_1_column(self, doc: dict[str, Any], output_path: Path | None = None) -> bytes:
        """1カラム（スマホ縦型スリム・幅390px）レイアウト"""
        W, H = 390, 1820
        img = Image.new("RGBA", (W, H), (18, 20, 30, 255))
        draw = ImageDraw.Draw(img)

        f_title = get_font(16)
        f_sub = get_font(12)
        f_sec = get_font(13)
        f_name = get_font(13)
        f_badge = get_font(11)
        f_small = get_font(10)
        f_score = get_font(18)

        derived = doc.get("derived", {})
        season = derived.get("season", 52)
        stage_num = doc.get("stageId", 0) % 10 if doc.get("stageId", 0) > 0 else 3
        if doc.get("stageId") in (181, 182, 183):
            stage_num = doc["stageId"] - 180

        from advisory_parser import get_stage_regulation
        reg_info = get_stage_regulation(season, stage_num)
        crit_str = format_criteria(reg_info.get("criteria", ""))
        reg_summary = f"{crit_str} ({reg_info.get('turns', 12)}T) | {reg_info.get('plan_jp', '')}"

        main_pidol_id = derived.get("pIdolId")
        main_pidol = self._get_pidol_info(main_pidol_id)
        idol_name = main_pidol.get("idol_name", "アイドル")
        title = main_pidol.get("title", "")

        sub_pidol_id = None
        sub_title = ""
        groups = doc.get("skillCardIdGroups", [])
        if len(groups) > 1 and len(groups[1]) > 0:
            sub_first_cid = groups[1][0]
            sub_cinfo = self.resolver.get_card_details(sub_first_cid)
            if sub_cinfo.get("pIdolId"):
                sub_pidol_id = sub_cinfo["pIdolId"]
                sub_pinfo = self._get_pidol_info(sub_pidol_id)
                sub_title = sub_pinfo.get("title", "")

        params = doc.get("params", [0, 0, 0, 0])
        vo, da, vi, hp = params[0], params[1], params[2], params[3]

        stats = doc.get("stats", {})
        median_score = stats.get("median", 0)
        mean_score = stats.get("mean", 0)

        main_mem_name = doc.get("mainMemoryName", "")
        sub_mem_name = doc.get("subMemoryName", "")

        # ── 1. ヘッダー上部 ──
        draw.rectangle([0, 0, W, 195], fill=(24, 27, 40))

        p_path = self._find_pidol_image_path(main_pidol_id)
        if p_path and p_path.exists():
            try:
                raw_p = Image.open(p_path).convert("RGBA")
                p_img = ImageOps.fit(raw_p, (80, 80), Image.Resampling.LANCZOS, centering=(0.5, 0.25))
                p_img = round_corners(p_img, 8)
                img.paste(p_img, (15, 15), p_img)
            except Exception as e:
                log.warning(f"Failed to load p_idol image: {e}")

        if sub_pidol_id:
            sub_path = self._find_pidol_image_path(sub_pidol_id)
            if sub_path and sub_path.exists():
                try:
                    raw_sub = Image.open(sub_path).convert("RGBA")
                    sub_img = ImageOps.fit(raw_sub, (40, 40), Image.Resampling.LANCZOS, centering=(0.5, 0.25))
                    sub_img = round_corners(sub_img, 6)
                    sub_x = 15 + 80 - 40 + 8
                    sub_y = 15 + 80 - 40 + 8
                    draw.rounded_rectangle([sub_x - 2, sub_y - 2, sub_x + 42, sub_y + 42], radius=6, fill=(18, 20, 30))
                    img.paste(sub_img, (sub_x, sub_y), sub_img)
                except Exception as e:
                    log.warning(f"Failed to load sub p_idol image: {e}")

        text_x = 118
        draw.text((text_x, 14), f"SEASON {season} | STAGE {stage_num} 実走", fill=(240, 185, 75), font=f_small)
        draw.text((text_x, 30), f"{idol_name} 【{title}】", fill=(255, 255, 255), font=f_title)
        if sub_title and sub_title != title:
            draw.text((text_x, 52), f"サブ: 【{sub_title}】", fill=(140, 210, 255), font=f_small)
        draw.text((text_x, 68), reg_summary, fill=(160, 175, 205), font=f_small)

        mem_str = []
        if main_mem_name:
            mem_str.append(f"主:{main_mem_name[:12]}")
        if sub_mem_name:
            mem_str.append(f"副:{sub_mem_name[:12]}")
        if mem_str:
            draw.text((text_x, 84), " / ".join(mem_str), fill=(140, 210, 255), font=get_font(9))

        # ステータス & スコアパネル (中段 108〜185)
        stat_box_w = 210
        draw.rounded_rectangle([15, 110, 15 + stat_box_w, 185], radius=6, fill=(32, 37, 54), outline=(50, 60, 85), width=1)
        stats_data = [
            ("Vo", vo, (255, 120, 150)),
            ("Da", da, (100, 180, 255)),
            ("Vi", vi, (255, 210, 80)),
            ("HP", hp, (120, 235, 150)),
        ]
        col_w = stat_box_w // 4
        for idx, (s_name, s_val, s_color) in enumerate(stats_data):
            sx = 15 + idx * col_w
            draw.text((sx + 8, 116), s_name, fill=s_color, font=get_font(10))
            draw.text((sx + 6, 142), f"{s_val:,}", fill=(255, 255, 255), font=get_font(11))

        score_box_x = 15 + stat_box_w + 10
        score_box_w = W - score_box_x - 15
        draw.rounded_rectangle([score_box_x, 110, score_box_x + score_box_w, 185], radius=6, fill=(32, 37, 54), outline=(240, 185, 75), width=1)
        draw.text((score_box_x + 8, 116), "期待中央値", fill=(240, 185, 75), font=get_font(10))
        draw.text((score_box_x + 8, 134), f"{int(median_score):,}", fill=(255, 225, 120), font=f_score)
        draw.text((score_box_x + 8, 160), f"平均:{int(mean_score):,}", fill=(170, 185, 210), font=get_font(10))

        # ── 2. Pアイテム セクション ──
        pitems = self._prepare_loadout_pitems(doc)
        y_item = 205
        draw.text((15, y_item), f"◆ 獲得 Pアイテム ({len(pitems)}枠)", fill=(245, 205, 105), font=f_sec)

        item_w = (W - 30 - 10) // 2
        item_h = 58
        y_item_box = y_item + 24

        for i, it in enumerate(pitems[:6]):
            col = i % 2
            row = i // 2
            ix = 15 + col * (item_w + 10)
            iy = y_item_box + row * (item_h + 6)

            draw.rounded_rectangle([ix, iy, ix + item_w, iy + item_h], radius=6, fill=(26, 30, 45), outline=(45, 52, 75), width=1)
            pid = it["id"]
            pi_path = self.resolver._get_p_item_image(str(pid))
            if pi_path and pi_path.exists():
                try:
                    raw_it = Image.open(pi_path).convert("RGBA")
                    it_img = ImageOps.fit(raw_it, (44, 44), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    it_img = round_corners(it_img, 6)
                    img.paste(it_img, (ix + 6, iy + 7), it_img)
                except Exception as e:
                    log.warning(f"Failed to load p_item image: {e}")

            max_text_w = item_w - 56
            it_name = it["name"]
            if draw.textlength(it_name, font=get_font(11)) > max_text_w:
                while len(it_name) > 1 and draw.textlength(it_name + "…", font=get_font(11)) > max_text_w:
                    it_name = it_name[:-1]
                it_name += "…"
            draw.text((ix + 54, iy + 8), it_name, fill=(255, 255, 255), font=get_font(11))

            grp_color = (255, 180, 120) if it["group"] == "メイン" else (140, 200, 255)
            badge_text = f"[{it['group']}]"
            draw.text((ix + 54, iy + 30), badge_text, fill=grp_color, font=f_small)

        # ── 3. スキルカード セクション (12枚) ──
        cards = self._prepare_loadout_cards(doc)
        item_rows = (len(pitems[:6]) + 1) // 2
        y_skill = y_item_box + item_rows * (item_h + 6) + 12
        draw.text((15, y_skill), f"◆ 実走 スキルカード ({len(cards)}枚構成)", fill=(245, 205, 105), font=f_sec)

        card_w = W - 30
        card_h = 88
        y_skill_box = y_skill + 24

        for idx, card in enumerate(cards[:12]):
            cx = 15
            cy = y_skill_box + idx * (card_h + 6)

            draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=8, fill=(26, 30, 45), outline=(45, 52, 75), width=1)

            cid = card["id"]
            sc_path = self.resolver._get_skill_card_image(str(cid))
            if sc_path and sc_path.exists():
                try:
                    raw_sc = Image.open(sc_path).convert("RGBA")
                    c_img = ImageOps.fit(raw_sc, (64, 64), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    c_img = round_corners(c_img, 6)
                    img.paste(c_img, (cx + 8, cy + 12), c_img)
                except Exception as e:
                    log.warning(f"Failed to load skill card image: {e}")

            cname = card["name"]
            rarity = card["rarity"]
            stype = card["sourceType"]
            group = card["group"]

            r_color = {"SSR": (255, 200, 60), "SR": (220, 160, 255), "R": (120, 210, 255)}.get(rarity, (200, 200, 200))
            draw.text((cx + 80, cy + 8), f"#{idx+1}", fill=(160, 175, 200), font=get_font(11))
            draw.text((cx + 104, cy + 8), f"[{rarity}]", fill=r_color, font=get_font(11))

            if stype == "support":
                type_badge = "[サポカ]"
                tb_color = (255, 140, 140)
            elif card.get("is_main_unique"):
                type_badge = "[メイン固有]"
                tb_color = (255, 215, 100)
            elif card.get("is_sub_unique"):
                type_badge = "[サブ固有]"
                tb_color = (255, 215, 100)
            else:
                type_badge = f"[{group}]"
                tb_color = (150, 190, 230)
            draw.text((cx + 144, cy + 8), type_badge, fill=tb_color, font=get_font(11))

            draw.text((cx + 80, cy + 28), cname, fill=(255, 255, 255), font=f_name)

            content_y = cy + 52
            custs = card.get("customizations", [])
            if custs:
                cust_str = " ".join([f"[{c}]" for c in custs])
                draw.text((cx + 80, content_y), cust_str, fill=(255, 225, 140), font=f_badge)
                content_y += 18

            supp_label = self.resolver.get_skill_card_support_label(cname)
            if supp_label and not custs:
                draw.text((cx + 80, content_y), supp_label, fill=(150, 195, 255), font=f_small)

        draw.text((W // 2 - 80, H - 22), "My Gakumas Tools 実走結果", fill=(110, 125, 150), font=f_small)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        if output_path:
            output_path.write_bytes(png_bytes)

        return png_bytes

    def build_2_columns(self, doc: dict[str, Any], output_path: Path | None = None) -> bytes:
        """2カラム（ワイド・幅760px）レイアウト"""
        W, H = 760, 1340
        img = Image.new("RGBA", (W, H), (18, 20, 30, 255))
        draw = ImageDraw.Draw(img)

        f_title = get_font(21)
        f_sub = get_font(14)
        f_sec = get_font(15)
        f_name = get_font(14)
        f_badge = get_font(12)
        f_small = get_font(11)
        f_score = get_font(22)
        f_score_sub = get_font(14)

        # ── データの展開 ──
        derived = doc.get("derived", {})
        season = derived.get("season", 52)
        stage_num = doc.get("stageId", 0) % 10 if doc.get("stageId", 0) > 0 else 3
        # ステージ番号正規化 (stageId 181->1, 182->2, 183->3)
        if doc.get("stageId") in (181, 182, 183):
            stage_num = doc["stageId"] - 180

        # 審査基準
        from advisory_parser import get_stage_regulation
        reg_info = get_stage_regulation(season, stage_num)
        crit_str = format_criteria(reg_info.get("criteria", ""))
        reg_summary = f"{crit_str} ({reg_info.get('turns', 12)}T) | {reg_info.get('plan_jp', '')}"

        main_pidol_id = derived.get("pIdolId")
        main_pidol = self._get_pidol_info(main_pidol_id)
        idol_name = main_pidol.get("idol_name", "アイドル")
        title = main_pidol.get("title", "")
        plan = main_pidol.get("plan", "logic")

        # サブPアイドル探索（サブカードグループの1枚目＝固有カードから判定）
        sub_pidol_id = None
        sub_title = ""
        groups = doc.get("skillCardIdGroups", [])
        if len(groups) > 1 and len(groups[1]) > 0:
            sub_first_cid = groups[1][0]
            sub_cinfo = self.resolver.get_card_details(sub_first_cid)
            if sub_cinfo.get("pIdolId"):
                sub_pidol_id = sub_cinfo["pIdolId"]
                sub_pinfo = self._get_pidol_info(sub_pidol_id)
                sub_title = sub_pinfo.get("title", "")

        params = doc.get("params", [0, 0, 0, 0])
        vo, da, vi, hp = params[0], params[1], params[2], params[3]

        stats = doc.get("stats", {})
        median_score = stats.get("median", 0)
        mean_score = stats.get("mean", 0)

        # メモリー名
        main_mem_name = doc.get("mainMemoryName", "")
        sub_mem_name = doc.get("subMemoryName", "")

        # ── 1. ヘッダー上部（アバター & タイトル） ──
        draw.rectangle([0, 0, W, 175], fill=(24, 27, 40))

        # メイン P アイドル画像 (92x92)
        p_path = self._find_pidol_image_path(main_pidol_id)
        if p_path and p_path.exists():
            try:
                raw_p = Image.open(p_path).convert("RGBA")
                p_img = ImageOps.fit(raw_p, (92, 92), Image.Resampling.LANCZOS, centering=(0.5, 0.25))
                p_img = round_corners(p_img, 10)
                img.paste(p_img, (22, 18), p_img)
            except Exception as e:
                log.warning(f"Failed to load p_idol image: {e}")

        # サブ P アイドル画像 (46x46, 右下にオーバーレイ)
        if sub_pidol_id:
            sub_path = self._find_pidol_image_path(sub_pidol_id)
            if sub_path and sub_path.exists():
                try:
                    raw_sub = Image.open(sub_path).convert("RGBA")
                    sub_img = ImageOps.fit(raw_sub, (46, 46), Image.Resampling.LANCZOS, centering=(0.5, 0.25))
                    sub_img = round_corners(sub_img, 6)
                    sub_x = 22 + 92 - 46 + 10
                    sub_y = 18 + 92 - 46 + 10
                    draw.rounded_rectangle([sub_x - 2, sub_y - 2, sub_x + 48, sub_y + 48], radius=8, fill=(18, 20, 30))
                    img.paste(sub_img, (sub_x, sub_y), sub_img)
                except Exception as e:
                    log.warning(f"Failed to load sub p_idol image: {e}")

        text_x = 138
        draw.text((text_x, 15), f"SEASON {season}  |  STAGE {stage_num}  実走シミュレーション結果", fill=(240, 185, 75), font=get_font(13))
        display_main = f"{idol_name} 【{title}】"
        draw.text((text_x, 35), display_main, fill=(255, 255, 255), font=f_title)

        meta_sub = []
        if sub_title and sub_title != title:
            meta_sub.append(f"サブ: 【{sub_title}】")
        if reg_summary:
            meta_sub.append(reg_summary)

        draw.text((text_x, 62), "  |  ".join(meta_sub), fill=(160, 175, 205), font=f_small)

        # メモリー名表示
        mem_str = []
        if main_mem_name:
            mem_str.append(f"主: {main_mem_name}")
        if sub_mem_name:
            mem_str.append(f"副: {sub_mem_name}")
        if mem_str:
            draw.text((text_x, 77), "  /  ".join(mem_str), fill=(140, 210, 255), font=get_font(10))

        # ── ステータス & スコアパネル (中段 95〜160) ──
        # ステータスボックス (左側)
        stat_box_w = 340
        draw.rounded_rectangle([text_x, 95, text_x + stat_box_w, 160], radius=8, fill=(32, 37, 54), outline=(50, 60, 85), width=1)

        # Vo / Da / Vi / HP バッジ表示
        stats_data = [
            ("Vo", vo, (255, 120, 150)),
            ("Da", da, (100, 180, 255)),
            ("Vi", vi, (255, 210, 80)),
            ("HP", hp, (120, 235, 150)),
        ]
        col_w = stat_box_w // 4
        for idx, (s_name, s_val, s_color) in enumerate(stats_data):
            sx = text_x + idx * col_w
            draw.text((sx + 12, 102), s_name, fill=s_color, font=get_font(12))
            draw.text((sx + 10, 125), f"{s_val:,}", fill=(255, 255, 255), font=get_font(14))

        # スコアボックス (右側)
        score_box_x = text_x + stat_box_w + 14
        score_box_w = W - score_box_x - 22
        draw.rounded_rectangle([score_box_x, 95, score_box_x + score_box_w, 160], radius=8, fill=(32, 37, 54), outline=(240, 185, 75), width=1)

        draw.text((score_box_x + 14, 102), "期待中央値", fill=(240, 185, 75), font=f_small)
        med_str = f"{int(median_score):,} Pt"
        draw.text((score_box_x + 12, 122), med_str, fill=(255, 225, 120), font=f_score)

        mean_str = f"平均: {int(mean_score):,} Pt"
        draw.text((score_box_x + score_box_w - int(draw.textlength(mean_str, font=f_small)) - 14, 103), mean_str, fill=(170, 185, 210), font=f_small)

        # ── 2. Pアイテム セクション ──────────────────────────────────────────
        pitems = self._prepare_loadout_pitems(doc)
        y_item = 185
        draw.text((22, y_item), f"◆ 獲得 Pアイテム ({len(pitems)}枠)", fill=(245, 205, 105), font=f_sec)

        item_w = (W - 44 - 15 * 2) // 3
        item_h = 70
        y_item_box = y_item + 28

        for i, it in enumerate(pitems[:6]):
            col = i % 3
            row = i // 3
            ix = 22 + col * (item_w + 15)
            iy = y_item_box + row * (item_h + 8)

            draw.rounded_rectangle([ix, iy, ix + item_w, iy + item_h], radius=8, fill=(26, 30, 45), outline=(45, 52, 75), width=1)

            pid = it["id"]
            pi_path = self.resolver._get_p_item_image(str(pid))
            if pi_path and pi_path.exists():
                try:
                    raw_it = Image.open(pi_path).convert("RGBA")
                    it_img = ImageOps.fit(raw_it, (52, 52), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    it_img = round_corners(it_img, 6)
                    img.paste(it_img, (ix + 8, iy + 9), it_img)
                except Exception as e:
                    log.warning(f"Failed to load p_item image: {e}")

            # アイテム名 & グループ（枠幅に合わせてtruncate）
            max_text_w = item_w - 74
            it_name = it["name"]
            if draw.textlength(it_name, font=get_font(13)) > max_text_w:
                while len(it_name) > 1 and draw.textlength(it_name + "…", font=get_font(13)) > max_text_w:
                    it_name = it_name[:-1]
                it_name += "…"
            draw.text((ix + 68, iy + 12), it_name, fill=(255, 255, 255), font=get_font(13))

            grp_color = (255, 180, 120) if it["group"] == "メイン" else (140, 200, 255)
            card_label = self.resolver.get_p_item_card_label(it["name"])
            badge_text = f"[{it['group']}] {card_label}"
            if draw.textlength(badge_text, font=f_small) > max_text_w:
                while len(badge_text) > 1 and draw.textlength(badge_text + "…", font=f_small) > max_text_w:
                    badge_text = badge_text[:-1]
                badge_text += "…"
            draw.text((ix + 68, iy + 38), badge_text, fill=grp_color, font=f_small)

        # ── 3. スキルカード セクション (12枚) ──────────────────────────────────
        cards = self._prepare_loadout_cards(doc)
        item_rows = (len(pitems[:6]) + 2) // 3
        y_skill = y_item_box + item_rows * (item_h + 8) + 14

        draw.text((22, y_skill), f"◆ 実走 スキルカード ({len(cards)}枚構成)", fill=(245, 205, 105), font=f_sec)

        card_w = (W - 44 - 14) // 2
        card_h = 118
        y_skill_box = y_skill + 28

        for idx, card in enumerate(cards[:12]):
            col = idx % 2
            row = idx // 2
            cx = 22 + col * (card_w + 14)
            cy = y_skill_box + row * (card_h + 10)

            draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=10, fill=(26, 30, 45), outline=(45, 52, 75), width=1)

            # カード画像
            cid = card["id"]
            sc_path = self.resolver._get_skill_card_image(str(cid))
            if sc_path and sc_path.exists():
                try:
                    raw_sc = Image.open(sc_path).convert("RGBA")
                    c_img = ImageOps.fit(raw_sc, (78, 78), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    c_img = round_corners(c_img, 8)
                    img.paste(c_img, (cx + 10, cy + 20), c_img)
                except Exception as e:
                    log.warning(f"Failed to load skill card image: {e}")

            # レアリティ＆由来バッジ
            cname = card["name"]
            rarity = card["rarity"]
            stype = card["sourceType"]
            group = card["group"]

            # レアリティバッジ色
            r_color = {"SSR": (255, 200, 60), "SR": (220, 160, 255), "R": (120, 210, 255)}.get(rarity, (200, 200, 200))
            draw.text((cx + 96, cy + 12), f"#{idx+1}", fill=(160, 175, 200), font=get_font(12))
            draw.text((cx + 120, cy + 12), f"[{rarity}]", fill=r_color, font=get_font(12))

            # 由来バッジ
            type_badge = ""
            if stype == "support":
                type_badge = "[サポカ]"
                tb_color = (255, 140, 140)
            elif stype == "pidol":
                type_badge = "[固有]"
                tb_color = (255, 215, 100)
            else:
                type_badge = f"[{group}]"
                tb_color = (150, 190, 230)
            draw.text((cx + 160, cy + 12), type_badge, fill=tb_color, font=get_font(12))

            # カード名
            draw.text((cx + 96, cy + 34), cname, fill=(255, 255, 255), font=f_name)

            # カスタマイズ表示
            content_y = cy + 62
            custs = card.get("customizations", [])
            if custs:
                cust_str = " ".join([f"[{c}]" for c in custs])
                draw.text((cx + 96, content_y), cust_str, fill=(255, 225, 140), font=f_badge)
                content_y += 22

            # サポカ名・補足情報
            supp_label = self.resolver.get_skill_card_support_label(cname)
            if supp_label:
                draw.text((cx + 96, content_y), supp_label, fill=(150, 195, 255), font=f_small)

        # ── 4. フッター ──
        draw.text((W // 2 - 100, H - 26), "My Gakumas Tools 実走シミュレーション", fill=(110, 125, 150), font=f_small)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        if output_path:
            output_path.write_bytes(png_bytes)

        return png_bytes
