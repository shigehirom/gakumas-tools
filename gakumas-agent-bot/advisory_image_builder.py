"""
advisory_image_builder.py — あじふらい氏推奨構成インフォグラフィック画像生成エンジン
1カラム版（縦型スリム・スマホ最適）および2カラム版（ワイドグリッド）に対応。
"""

import io
import logging
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont, ImageOps

from image_resolver import ImageResolver

log = logging.getLogger("advisory_image_builder")

def _find_dir(candidates: list[Path]) -> Path:
    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return candidates[0]

WORKSPACE_DIR = _find_dir([
    Path("/app"),
    Path("/root/gakumas-workspace"),
    Path(__file__).resolve().parent.parent,
])

FONT_CANDIDATES = [
    Path(__file__).resolve().parent / "fonts" / "NotoSansJP-Bold.ttf",
    Path(__file__).resolve().parent / "fonts" / "NotoSansJP-Bold.otf",
    Path("/app/fonts/NotoSansJP-Bold.ttf"),
    Path("/root/gakumas-workspace/gakumas-agent-bot/fonts/NotoSansJP-Bold.ttf"),
    WORKSPACE_DIR / "gakumas-tools" / "gakumas-tools" / "assets" / "fonts" / "NotoSansCJKjp-Bold-subset.otf",
]

def _find_font_path() -> str | None:
    for p in FONT_CANDIDATES:
        if p.exists() and p.stat().st_size > 500000:
            return str(p)
    for p in FONT_CANDIDATES:
        if p.exists():
            return str(p)
    return None

FONT_PATH = _find_font_path()

def get_font(size: int):
    if FONT_PATH:
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()

def round_corners(im: Image.Image, rad: int) -> Image.Image:
    mask = Image.new('L', im.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, im.size[0], im.size[1]], radius=rad, fill=255)
    result = im.copy().convert("RGBA")
    result.putalpha(mask)
    return result


class AdvisoryImageBuilder:
    def __init__(self):
        self.resolver = ImageResolver()

    def build(self, data: dict[str, Any], output_path: Path | None = None) -> bytes:
        """
        推奨構成データからポートレートPNG画像を生成する。
        data["columns"]: 1 (デフォルト・幅390px) または 2 (幅760px)
        """
        columns = data.get("columns", 1)
        if columns not in (1, 2):
            columns = 1

        if columns == 1:
            return self._build_1_column(data, output_path)
        else:
            return self._build_2_columns(data, output_path)

    def _find_pidol_image_path(self, idol_name: str, title: str) -> Path | None:
        def _norm(s: str) -> str:
            return s.replace(" ", "").replace("　", "").strip().lower()

        target_norm = _norm(idol_name)
        pidol_candidates = [
            p for p in self.resolver.p_idols
            if p["title"] == title and (not target_norm or target_norm in _norm(p["idol_name"]) or _norm(p["idol_name"]) in target_norm)
        ]
        if not pidol_candidates:
            pidol_candidates = [p for p in self.resolver.p_idols if p["title"] == title]
        if pidol_candidates:
            pidol_id = pidol_candidates[0]["id"]
            return self.resolver._get_p_idol_image(pidol_id)
        return None

    def _build_1_column(self, data: dict[str, Any], output_path: Path | None = None) -> bytes:
        """1カラム（縦型スリム・幅390px）レイアウト"""
        W, H = 390, 1680
        img = Image.new("RGBA", (W, H), (18, 20, 30, 255))
        draw = ImageDraw.Draw(img)

        f_title = get_font(16)
        f_sub = get_font(13)
        f_sub_title = get_font(13)
        f_sec = get_font(15)
        f_name = get_font(14)
        f_badge = get_font(11)
        f_small = get_font(11)

        season = data.get("season", 51)
        stage_num = data.get("stage", 1)
        reg = data.get("regulation", {})
        crit = reg.get("criteria", "Vo 45 / Da 35 / Vi 20")
        plan_jp = reg.get("plan_jp", "アノマリー")
        turns = reg.get("turns", 12)

        p_idol = data.get("p_idol", {})
        idol_name = p_idol.get("idol_name", "")
        title = p_idol.get("title", "")
        extra = p_idol.get("extra", "")
        subs = p_idol.get("subs", [])

        # ── 1. ヘッダー部 ──────────────────────────────────────────────────
        draw.rounded_rectangle([15, 15, W - 15, 145], radius=12, fill=(28, 32, 48), outline=(52, 60, 88), width=2)

        # メイン P アイドル画像
        p_path = self._find_pidol_image_path(idol_name, title)
        if p_path and p_path.exists():
            try:
                raw_p = Image.open(p_path).convert("RGBA")
                p_img = ImageOps.fit(raw_p, (92, 92), Image.Resampling.LANCZOS, centering=(0.5, 0.25))
                p_img = round_corners(p_img, 10)
                img.paste(p_img, (25, 25), p_img)
            except Exception as e:
                log.warning(f"Failed to load p_idol image: {e}")

        # サブ P アイドル画像（1/4縮小・右下に25%シフト）
        sub_title = subs[0]["title"] if subs else None
        if sub_title:
            sub_path = self._find_pidol_image_path(idol_name, sub_title)
            if sub_path and sub_path.exists():
                try:
                    raw_sub = Image.open(sub_path).convert("RGBA")
                    sub_size = 46
                    sub_img = ImageOps.fit(raw_sub, (sub_size, sub_size), Image.Resampling.LANCZOS, centering=(0.5, 0.25))
                    sub_img = round_corners(sub_img, 6)
                    
                    sub_x = 25 + 92 - sub_size + int(sub_size * 0.25)
                    sub_y = 25 + 92 - sub_size + int(sub_size * 0.25)
                    
                    draw.rounded_rectangle([sub_x - 2, sub_y - 2, sub_x + sub_size + 2, sub_y + sub_size + 2], radius=8, fill=(18, 20, 30))
                    img.paste(sub_img, (sub_x, sub_y), sub_img)
                except Exception as e:
                    log.warning(f"Failed to load sub p_idol image: {e}")

        text_x = 142
        avail_w = W - text_x - 20
        draw.text((text_x, 24), f"SEASON {season}  |  STAGE {stage_num}", fill=(240, 185, 75), font=f_sub)
        
        display_main = f"{idol_name} 【{title}】"
        if extra:
            display_main += f" {extra}"
        
        # タイトルが長い場合はフォントサイズを自動調整
        title_font = f_title
        for sz in [16, 14, 13, 12]:
            tf = get_font(sz)
            bbox = draw.textbbox((0, 0), display_main, font=tf)
            if (bbox[2] - bbox[0]) <= avail_w:
                title_font = tf
                break
        draw.text((text_x, 46), display_main, fill=(255, 255, 255), font=title_font)


        if sub_title and sub_title != title:
            draw.text((text_x, 70), f"サブ: 【{sub_title}】", fill=(140, 210, 255), font=f_sub_title)
            reg_y = 96
        else:
            reg_y = 74

        reg_summary = f"{crit} ({turns}T) | {plan_jp}"
        draw.text((text_x, reg_y), reg_summary, fill=(160, 175, 205), font=f_small)

        # ── 2. Pアイテム セクション ──────────────────────────────────────────
        y_item = 158
        draw.text((15, y_item), "◆ お勧め Pアイテム (2枠)", fill=(245, 205, 105), font=f_sec)
        pitems = data.get("p_items", [])
        item_w = W - 30
        item_h = 85
        y_item_box = y_item + 26

        for i, item_name in enumerate(pitems[:2]):
            ix = 15
            iy = y_item_box + i * (item_h + 8)
            draw.rounded_rectangle([ix, iy, ix + item_w, iy + item_h], radius=10, fill=(26, 30, 45), outline=(45, 52, 75), width=1)

            pid = self.resolver.p_items.get(item_name)
            if pid:
                pi_path = self.resolver._get_p_item_image(pid)
                if pi_path and pi_path.exists():
                    try:
                        raw_it = Image.open(pi_path).convert("RGBA")
                        it_img = ImageOps.fit(raw_it, (65, 65), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                        it_img = round_corners(it_img, 8)
                        img.paste(it_img, (ix + 10, iy + 10), it_img)
                    except Exception as e:
                        log.warning(f"Failed to load p_item image: {e}")

            draw.text((ix + 85, iy + 16), item_name, fill=(255, 255, 255), font=f_name)
            card_label = self.resolver.get_p_item_card_label(item_name)
            draw.text((ix + 85, iy + 46), card_label, fill=(150, 195, 255), font=f_badge)

        # ── 3. スキルカード セクション ────────────────────────────────────────
        y_skill = y_item_box + 2 * (item_h + 8) + 12
        draw.text((15, y_skill), "◆ お勧め スキルカード (10枠)", fill=(245, 205, 105), font=f_sec)
        cards = data.get("skill_cards", [])
        card_w = W - 30
        card_h = 105

        for idx, card in enumerate(cards[:10]):
            cx = 15
            cy = y_skill + 26 + idx * (card_h + 8)

            draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=10, fill=(26, 30, 45), outline=(45, 52, 75), width=1)

            cname = card["name"]
            cid = self.resolver.skill_cards.get(cname)
            if cid:
                sc_path = self.resolver._get_skill_card_image(cid)
                if sc_path and sc_path.exists():
                    try:
                        raw_sc = Image.open(sc_path).convert("RGBA")
                        c_img = ImageOps.fit(raw_sc, (70, 70), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                        c_img = round_corners(c_img, 8)
                        img.paste(c_img, (cx + 10, cy + 18), c_img)
                    except Exception as e:
                        log.warning(f"Failed to load skill card image: {e}")

            draw.text((cx + 90, cy + 12), f"#{idx+1} {cname}", fill=(255, 255, 255), font=f_name)

            content_y = cy + 38
            custs = card.get("customizations", [])
            if custs:
                for cust in custs:
                    b_text = cust.strip()
                    badge_width = int(draw.textlength(b_text, font=f_badge)) + 18
                    draw.text((cx + 96, content_y + 2), b_text, fill=(255, 220, 140), font=f_badge)
                    content_y += 23

            supp_label = self.resolver.get_skill_card_support_label(cname)
            if supp_label:
                draw.text((cx + 90, content_y + 2), supp_label, fill=(150, 195, 255), font=f_badge)

        # ── 4. フッター部 ──────────────────────────────────────────────────
        draw.text((W // 2 - 80, H - 24), "My Gakumas Tools 推奨レポート", fill=(110, 125, 150), font=f_small)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        if output_path:
            output_path.write_bytes(png_bytes)

        return png_bytes

    def _build_2_columns(self, data: dict[str, Any], output_path: Path | None = None) -> bytes:
        """2カラム（ワイドグリッド・幅760px）レイアウト"""
        W, H = 760, 1160
        img = Image.new("RGBA", (W, H), (18, 20, 30, 255))
        draw = ImageDraw.Draw(img)

        f_title = get_font(22)
        f_sub = get_font(15)
        f_sec = get_font(16)
        f_name = get_font(15)
        f_badge = get_font(12)
        f_small = get_font(12)

        season = data.get("season", 51)
        stage_num = data.get("stage", 1)
        reg = data.get("regulation", {})
        crit = reg.get("criteria", "Vo 45 / Da 35 / Vi 20")
        plan_jp = reg.get("plan_jp", "アノマリー")
        turns = reg.get("turns", 12)

        p_idol = data.get("p_idol", {})
        idol_name = p_idol.get("idol_name", "")
        title = p_idol.get("title", "")
        extra = p_idol.get("extra", "")
        subs = p_idol.get("subs", [])

        # ── 1. ヘッダー部 ──────────────────────────────────────────────────
        draw.rounded_rectangle([15, 15, W - 15, 145], radius=14, fill=(28, 32, 48), outline=(52, 60, 88), width=2)

        p_path = self._find_pidol_image_path(idol_name, title)
        if p_path and p_path.exists():
            try:
                raw_p = Image.open(p_path).convert("RGBA")
                p_img = ImageOps.fit(raw_p, (100, 100), Image.Resampling.LANCZOS, centering=(0.5, 0.25))
                p_img = round_corners(p_img, 12)
                img.paste(p_img, (30, 30), p_img)
            except Exception as e:
                log.warning(f"Failed to load p_idol image: {e}")

        sub_title = subs[0]["title"] if subs else None
        if sub_title:
            sub_path = self._find_pidol_image_path(idol_name, sub_title)
            if sub_path and sub_path.exists():
                try:
                    raw_sub = Image.open(sub_path).convert("RGBA")
                    sub_size = 50
                    sub_img = ImageOps.fit(raw_sub, (sub_size, sub_size), Image.Resampling.LANCZOS, centering=(0.5, 0.25))
                    sub_img = round_corners(sub_img, 7)
                    
                    sub_x = 30 + 100 - sub_size + int(sub_size * 0.25)
                    sub_y = 30 + 100 - sub_size + int(sub_size * 0.25)
                    
                    draw.rounded_rectangle([sub_x - 2, sub_y - 2, sub_x + sub_size + 2, sub_y + sub_size + 2], radius=8, fill=(18, 20, 30))
                    img.paste(sub_img, (sub_x, sub_y), sub_img)
                except Exception as e:
                    log.warning(f"Failed to load sub p_idol image: {e}")

        text_x = 148
        draw.text((text_x, 26), f"SEASON {season}  |  STAGE {stage_num}", fill=(240, 185, 75), font=f_sub)
        
        display_main = f"{idol_name} 【{title}】"
        if extra:
            display_main += f" {extra}"
        draw.text((text_x, 50), display_main, fill=(255, 255, 255), font=f_title)

        if sub_title and sub_title != title:
            draw.text((text_x, 80), f"サブ: 【{sub_title}】", fill=(140, 210, 255), font=f_sub)
            reg_y = 106
        else:
            reg_y = 82

        reg_summary = f"審査基準: {crit} ({turns}T) | プラン: {plan_jp}"
        draw.text((text_x, reg_y), reg_summary, fill=(160, 175, 205), font=f_small)

        # ── 2. Pアイテム セクション ──────────────────────────────────────────
        y_item = 160
        draw.text((20, y_item), "◆ お勧め Pアイテム (2枠)", fill=(245, 205, 105), font=f_sec)
        pitems = data.get("p_items", [])
        item_w = (W - 40 - 15) // 2
        item_h = 100
        y_item_box = y_item + 30
        for i, item_name in enumerate(pitems[:2]):
            ix = 20 + i * (item_w + 15)
            iy = y_item_box
            draw.rounded_rectangle([ix, iy, ix + item_w, iy + item_h], radius=10, fill=(26, 30, 45), outline=(45, 52, 75), width=1)

            pid = self.resolver.p_items.get(item_name)
            if pid:
                pi_path = self.resolver._get_p_item_image(pid)
                if pi_path and pi_path.exists():
                    try:
                        raw_it = Image.open(pi_path).convert("RGBA")
                        it_img = ImageOps.fit(raw_it, (80, 80), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                        it_img = round_corners(it_img, 8)
                        img.paste(it_img, (ix + 10, iy + 10), it_img)
                    except Exception as e:
                        log.warning(f"Failed to load p_item image: {e}")

            draw.text((ix + 100, iy + 22), item_name, fill=(255, 255, 255), font=f_name)
            card_label = self.resolver.get_p_item_card_label(item_name)
            draw.text((ix + 100, iy + 54), card_label, fill=(150, 195, 255), font=f_badge)

        # ── 3. スキルカード セクション ────────────────────────────────────────
        y_skill = y_item_box + item_h + 20
        draw.text((20, y_skill), "◆ お勧め スキルカード (10枠)", fill=(245, 205, 105), font=f_sec)
        cards = data.get("skill_cards", [])
        card_w = (W - 40 - 15) // 2
        card_h = 130
        for idx, card in enumerate(cards[:10]):
            col = idx % 2
            row = idx // 2
            cx = 20 + col * (card_w + 15)
            cy = y_skill + 30 + row * (card_h + 10)

            draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=10, fill=(26, 30, 45), outline=(45, 52, 75), width=1)

            cname = card["name"]
            cid = self.resolver.skill_cards.get(cname)
            if cid:
                sc_path = self.resolver._get_skill_card_image(cid)
                if sc_path and sc_path.exists():
                    try:
                        raw_sc = Image.open(sc_path).convert("RGBA")
                        c_img = ImageOps.fit(raw_sc, (80, 80), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                        c_img = round_corners(c_img, 8)
                        img.paste(c_img, (cx + 10, cy + 25), c_img)
                    except Exception as e:
                        log.warning(f"Failed to load skill card image: {e}")

            draw.text((cx + 100, cy + 14), f"#{idx+1} {cname}", fill=(255, 255, 255), font=f_name)

            content_y = cy + 42
            custs = card.get("customizations", [])
            if custs:
                for cust in custs:
                    b_text = cust.strip()
                    badge_width = int(draw.textlength(b_text, font=f_badge)) + 20
                    draw.rounded_rectangle([cx + 100, content_y, cx + 100 + badge_width, content_y + 22], radius=4, fill=(115, 70, 20))
                    content_y += 26

            supp_label = self.resolver.get_skill_card_support_label(cname)
            if supp_label:
                draw.text((cx + 100, content_y + 2), supp_label, fill=(150, 195, 255), font=f_badge)

        # ── 4. フッター部 ──────────────────────────────────────────────────
        draw.text((W // 2 - 130, H - 30), "My Gakumas Tools 推奨レポート", fill=(110, 125, 150), font=f_small)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        if output_path:
            output_path.write_bytes(png_bytes)

        return png_bytes
