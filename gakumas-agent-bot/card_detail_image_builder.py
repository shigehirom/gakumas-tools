"""
core/card_detail_image_builder.py — ゲーム内P図鑑UI再現 カード・Pアイテム詳細画像生成エンジン
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont

try:
    from core.image_resolver import ImageResolver
    from core.dsl_translator import DslTranslator
except ImportError:
    from image_resolver import ImageResolver  # type: ignore
    from dsl_translator import DslTranslator  # type: ignore


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

CSV_DIR = _find_dir([
    Path("/home/pi/gakumas-mcp-server/data/csv"),
    Path("/app/packages/gakumas-data/csv"),
    Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/csv"),
    WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-data" / "csv",
    WORKSPACE_DIR / "packages" / "gakumas-data" / "csv",
])

FONTS_DIR = _find_dir([
    Path("/home/pi/gakumas-mcp-server/data/fonts"),
    Path("/app/fonts"),
    WORKSPACE_DIR / "fonts",
    WORKSPACE_DIR / "gakumas-agent-bot" / "fonts",
])

FONT_CANDIDATES = [
    Path("/root/gakumas-workspace/gakumas-agent-bot/fonts/NotoSansJP-Bold.ttf"),
    Path("/root/gakumas-workspace/gakumas-tools/gakumas-agent-bot/fonts/NotoSansJP-Bold.ttf"),
    Path("/home/pi/gakumas-mcp-server/data/fonts/NotoSansJP-Bold.ttf"),
    Path("/home/pi/gakumas-mcp-server/data/fonts/NotoSansJP-Bold.otf"),
    Path("/app/fonts/NotoSansJP-Bold.ttf"),
    Path("/app/gakumas-agent-bot/fonts/NotoSansJP-Bold.ttf"),
    WORKSPACE_DIR / "gakumas-agent-bot" / "fonts" / "NotoSansJP-Bold.ttf",
    WORKSPACE_DIR / "fonts" / "NotoSansJP-Bold.ttf",
    FONTS_DIR / "NotoSansJP-Bold.ttf",
    FONTS_DIR / "NotoSansJP-Bold.otf",
]


def _find_font_path() -> str | None:
    for p in FONT_CANDIDATES:
        try:
            if p.exists() and p.stat().st_size > 500000:
                return str(p)
        except Exception:
            continue
    return None


_FONT_PATH = _find_font_path()


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if _FONT_PATH:
        try:
            return ImageFont.truetype(_FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()


def round_corners(im: Image.Image, rad: int) -> Image.Image:
    """角丸マスクを適用する"""
    mask = Image.new("L", im.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, im.size[0], im.size[1]], radius=rad, fill=255)
    result = im.copy().convert("RGBA")
    result.putalpha(mask)
    return result


def draw_diamond(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int = 5, color=(6, 182, 212)):
    """効果箇条書き用の菱形ダイアモンドマークを描画する"""
    points = [
        (cx, cy - size),
        (cx + size, cy),
        (cx, cy + size),
        (cx - size, cy),
    ]
    draw.polygon(points, fill=color)


def _clean_emoji_for_image(text: str) -> str:
    """フォント未収録の絵文字（画像描画時に豆腐□になる文字）を除去する"""
    for ch in ["⚡", "💚", "♥", "🛡️", "🔥", "⚪", "🔴", "🔵", "🟣", "⚠️", "🌟", "◆", "✦", "［", "］"]:
        text = text.replace(ch, "")
    return text.strip()



def draw_heart(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int = 6, color=(225, 29, 72)):
    """体力消費用のハートマークを描画する"""
    r = int(size * 0.6)
    draw.ellipse([cx - size, cy - size, cx, cy], fill=color)
    draw.ellipse([cx, cy - size, cx + size, cy], fill=color)
    draw.polygon([(cx - size, cy - int(r * 0.5)), (cx + size, cy - int(r * 0.5)), (cx, cy + size)], fill=color)


PLAN_COLORS = {
    "sense": {"bg": (239, 68, 68), "text": "センス", "badge_bg": (254, 242, 242), "badge_border": (252, 165, 165)},
    "logic": {"bg": (59, 130, 246), "text": "ロジック", "badge_bg": (239, 246, 255), "badge_border": (147, 197, 253)},
    "anomaly": {"bg": (139, 92, 246), "text": "アノマリー", "badge_bg": (245, 243, 255), "badge_border": (196, 181, 253)},
    "free": {"bg": (100, 116, 139), "text": "フリー", "badge_bg": (241, 245, 249), "badge_border": (203, 213, 225)},
}

TYPE_COLORS = {
    "active": {"text": "アクティブ", "bg": (254, 243, 199), "fg": (180, 83, 9)},
    "mental": {"text": "メンタル", "bg": (224, 242, 254), "fg": (3, 105, 161)},
    "trouble": {"text": "トラブル", "bg": (254, 226, 226), "fg": (185, 28, 28)},
}


def wrap_text(text: str, font: Any, max_width: int) -> list[str]:
    """与えられたフォントと最大幅に基づいてテキストを改行リストに分割する"""
    lines = []
    for block in text.split("\n"):
        current = ""
        for char in block:
            test = current + char
            bbox = font.getbbox(test)
            w = bbox[2] - bbox[0]
            if w > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
    return lines



class CardDetailImageBuilder:
    """ゲーム内P図鑑UIを再現したスキルカードおよびPアイテムの詳細画像を生成する。"""

    def __init__(self):
        self.resolver = ImageResolver()
        self.dsl = DslTranslator()
        self._skill_cards: list[dict[str, Any]] = []
        self._p_items: list[dict[str, Any]] = []
        self._customizations: dict[str, dict[str, Any]] = {}
        self._load_csv_data()

    def _load_csv_data(self):
        sc_path = CSV_DIR / "skill_cards.csv"
        if sc_path.exists():
            with open(sc_path, encoding="utf-8") as f:
                self._skill_cards = list(csv.DictReader(f))

        pi_path = CSV_DIR / "p_items.csv"
        if pi_path.exists():
            with open(pi_path, encoding="utf-8") as f:
                self._p_items = list(csv.DictReader(f))

        cust_path = CSV_DIR / "customizations.csv"
        if cust_path.exists():
            with open(cust_path, encoding="utf-8") as f:
                self._customizations = {row["id"]: row for row in csv.DictReader(f)}

    def build_skill_card_image(self, card_data: dict[str, Any]) -> bytes:
        """スキルカードのP図鑑風詳細画像を生成する"""
        name = card_data.get("name", "")
        cid = str(card_data.get("id", ""))
        rarity = card_data.get("rarity", "SSR")
        card_type = (card_data.get("type") or "mental").lower()
        plan = (card_data.get("plan") or "anomaly").lower()
        plan_meta = PLAN_COLORS.get(plan, PLAN_COLORS["free"])
        type_meta = TYPE_COLORS.get(card_type, {"text": card_type, "bg": (241, 245, 249), "fg": (71, 85, 105)})

        unlock_plv = card_data.get("unlockPlv", "")
        plv_str = f"解放PLv {unlock_plv}" if unlock_plv and unlock_plv != "-" else "解放PLv -"

        # コスト
        cost_raw = (card_data.get("cost") or "").strip()
        cost_str = "体力消費なし"
        cost_type = "heart"
        if "fullPowerCharge-=" in cost_raw:
            val = cost_raw.replace("fullPowerCharge-=", "").strip()
            cost_str = f"全力値消費 {val}"
            cost_type = "full_power"
        elif "stamina-=" in cost_raw:
            val = cost_raw.replace("stamina-=", "").strip()
            cost_str = f"体力消費{val} (固定体力)"
            cost_type = "heart"
        elif "cost-=" in cost_raw:
            val = cost_raw.replace("cost-=", "").strip()
            cost_str = f"体力消費{val}"
            cost_type = "heart"
        elif "genki-=" in cost_raw:
            val = cost_raw.replace("genki-=", "").strip()
            cost_str = f"元気消費{val}"
            cost_type = "genki"
        elif "motivation-=" in cost_raw:
            val = cost_raw.replace("motivation-=", "").strip()
            cost_str = f"やる気消費{val}"
            cost_type = "motivation"
        elif "goodImpressionTurns-=" in cost_raw:
            val = cost_raw.replace("goodImpressionTurns-=", "").strip()
            cost_str = f"好印象消費{val}"
            cost_type = "good_impression"
        elif "goodConditionTurns-=" in cost_raw:
            val = cost_raw.replace("goodConditionTurns-=", "").strip()
            cost_str = f"好調消費{val}"
            cost_type = "good_condition"
        elif cost_raw and cost_raw != "0":
            cost_str = f"コスト: {cost_raw}"
            cost_type = "none"

        # 手札指定
        force_hand = card_data.get("forceInitialHand", "").upper() == "TRUE"
        hand_str = "レッスン開始時手札に入る" if force_hand else ""

        # 使用条件
        cond_raw = (card_data.get("conditions") or "").strip()
        cond_str = ""
        if cond_raw:
            cond_str = f"使用条件: {_clean_emoji_for_image(self.dsl.translate(cond_raw).rstrip(':'))}"

        # 効果項目
        acts = (card_data.get("actions") or "").strip()
        effs = (card_data.get("effects") or "").strip()
        dsl_full = "; ".join([x for x in [acts, effs] if x])
        limit_match = re.search(r"(?:^|;|\s)limit:(\d+)", dsl_full)
        dsl_no_limit = re.sub(r";?\s*limit:\d+", "", dsl_full).strip("; ")
        translated = self.dsl.translate(dsl_no_limit) if dsl_no_limit else ""

        # 多段スコアのまとめ表示（例: スコア+5 / スコア+5 / スコア+5 ... ➔ スコア+5（5回））
        score_multi_match = re.search(r"((?:スコア\+\d+\s*/\s*)+スコア\+\d+)", translated)
        if score_multi_match:
            full_match = score_multi_match.group(1)
            items = [x.strip() for x in full_match.split("/") if x.strip()]
            if len(items) >= 2 and all(x == items[0] for x in items):
                compact_score = f"{items[0]}（{len(items)}回）"
                translated = translated.replace(full_match, compact_score)

        eff_items = [_clean_emoji_for_image(item.strip()) for item in translated.split(" / ") if item.strip()]

        # 制限事項
        limits = []
        if card_data.get("unique", "").upper() == "TRUE":
            limits.append("重複不可")
        limit_val = (card_data.get("limit") or "").strip()
        if not limit_val and limit_match:
            limit_val = limit_match.group(1)
        if limit_val:
            limits.append(f"レッスン中{limit_val}回")
        lim_str = " ".join(limits)

        # カスタマイズの解決
        custom_ids_raw = card_data.get("availableCustomizations", "")
        if not custom_ids_raw and not name.endswith("+"):
            plus_card = next((c for c in self._skill_cards if c.get("name") == f"{name}+"), None)
            if plus_card:
                custom_ids_raw = plus_card.get("availableCustomizations", "")

        custom_items = []
        if custom_ids_raw:
            cids = [x.strip() for x in custom_ids_raw.split(",") if x.strip()]
            for cust_id in cids:
                c_info = self._customizations.get(cust_id)
                if c_info:
                    c_name = c_info.get("name", "")
                    c_price = c_info.get("price", "")
                    price_suffix = f" ({c_price}P)" if c_price else ""
                    raw = "; ".join([x for x in [c_info.get("actions", ""), c_info.get("effects", ""), c_info.get("cost", ""), c_info.get("conditions", "")] if x])
                    if not raw:
                        if c_name == "開始時手札に入る":
                            desc = "レッスン開始時手札に入る"
                        elif c_name == "レッスン中1回の制限削除":
                            desc = "レッスン中1回の制限を削除"
                        elif c_name == "条件変更":
                            desc = "使用条件の緩和・変更"
                        else:
                            desc = c_name
                    else:
                        desc = self.dsl.translate(raw)
                    custom_items.append((f"{c_name}{price_suffix}", desc))

        # ── レンダリングレイアウト計算 ──
        width = 750
        max_text_w = width - 186 - 28
        font_eff = get_font(15)
        font_cust_text = get_font(13)

        # 効果の折り返し計算
        wrapped_eff_lines = []
        for item in eff_items:
            w_lines = wrap_text(item, font_eff, max_text_w - 24)
            wrapped_eff_lines.append(w_lines)

        # カスタマイズの折り返し計算
        wrapped_cust_items = []
        cust_total_lines = 0
        if custom_items:
            for c_label, c_desc in custom_items:
                full_desc = f"{c_label} : {c_desc}"
                w_lines = wrap_text(full_desc, font_cust_text, max_text_w - 18)
                wrapped_cust_items.append(w_lines)
                cust_total_lines += len(w_lines)

        # 行数計算
        content_lines_count = 1  # コスト
        if hand_str:
            content_lines_count += 1
        if cond_str:
            content_lines_count += 1
        content_lines_count += sum(len(lines) for lines in wrapped_eff_lines)
        if lim_str:
            content_lines_count += 1
        if custom_items:
            content_lines_count += 1 + cust_total_lines

        height = max(240, 110 + content_lines_count * 26 + 20)

        # キャンバス生成（外枠付き角丸カード）
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # カードベース背景（白、シャドウ・ボーダー）
        card_rect = [6, 6, width - 7, height - 7]
        draw.rounded_rectangle(card_rect, radius=18, fill=(255, 255, 255), outline=(218, 224, 233), width=2)

        # ── 左カラム: アイコン・プラン・解放PLv ──
        icon_x = 24
        icon_y = 24
        icon_size = 136

        # アイコン枠
        draw.rounded_rectangle([icon_x - 2, icon_y - 2, icon_x + icon_size + 1, icon_y + icon_size + 1],
                               radius=18, fill=(241, 245, 249), outline=(226, 232, 240), width=1)

        icon_path = self.resolver._get_skill_card_image(cid) if cid else None
        if icon_path and icon_path.exists():
            try:
                card_img = Image.open(icon_path).convert("RGBA").resize((icon_size, icon_size), Image.Resampling.LANCZOS)
                card_img = round_corners(card_img, 16)
                img.alpha_composite(card_img, (icon_x, icon_y))
            except Exception:
                pass
        else:
            # プレースホルダー
            draw.rounded_rectangle([icon_x, icon_y, icon_x + icon_size - 1, icon_y + icon_size - 1],
                                   radius=16, fill=(241, 245, 249))

        # プランバッジ（アイコン下）
        plan_badge_y = icon_y + icon_size + 12
        plan_badge_w = 110
        plan_badge_h = 26
        plan_badge_x = icon_x + (icon_size - plan_badge_w) // 2

        draw.rounded_rectangle([plan_badge_x, plan_badge_y, plan_badge_x + plan_badge_w, plan_badge_y + plan_badge_h],
                               radius=13, fill=plan_meta["badge_bg"], outline=plan_meta["badge_border"], width=1)
        # プランサークル
        draw.ellipse([plan_badge_x + 8, plan_badge_y + 7, plan_badge_x + 20, plan_badge_y + 19], fill=plan_meta["bg"])
        font_plan = get_font(13)
        draw.text((plan_badge_x + 26, plan_badge_y + 4), plan_meta["text"], fill=(51, 65, 85), font=font_plan)

        # 解放PLv
        font_plv = get_font(12)
        plv_bbox = font_plv.getbbox(plv_str)
        plv_w = plv_bbox[2] - plv_bbox[0]
        draw.text((icon_x + (icon_size - plv_w) // 2, plan_badge_y + 30), plv_str, fill=(148, 163, 184), font=font_plv)

        # ── 右カラム: カード名・諸元 ──
        text_x = 186
        text_y = 24

        # カード名
        font_title = get_font(23)
        draw.text((text_x, text_y), name, fill=(30, 41, 59), font=font_title)

        # レアリティ & タイプバッジ
        name_bbox = font_title.getbbox(name)
        badges_x = text_x + (name_bbox[2] - name_bbox[0]) + 14

        # タイプバッジ
        font_badge = get_font(12)
        type_str = type_meta["text"]
        t_bbox = font_badge.getbbox(type_str)
        t_w = t_bbox[2] - t_bbox[0] + 16
        draw.rounded_rectangle([badges_x, text_y + 3, badges_x + t_w, text_y + 25],
                               radius=6, fill=type_meta["bg"])
        draw.text((badges_x + 8, text_y + 5), type_str, fill=type_meta["fg"], font=font_badge)

        # レアリティバッジ
        r_bbox = font_badge.getbbox(rarity)
        r_w = r_bbox[2] - r_bbox[0] + 16
        draw.rounded_rectangle([badges_x + t_w + 6, text_y + 3, badges_x + t_w + 6 + r_w, text_y + 25],
                               radius=6, fill=(241, 245, 249), outline=(203, 213, 225), width=1)
        draw.text((badges_x + t_w + 14, text_y + 5), rarity, fill=(71, 85, 105), font=font_badge)

        # 区切りライン
        line_y = text_y + 38
        draw.line([text_x, line_y, width - 26, line_y], fill=(226, 232, 240), width=1)

        # 諸元テキスト描画
        curr_y = line_y + 12
        font_body = get_font(15)

        # コスト & 手札
        if cost_type == "heart":
            draw_heart(draw, text_x + 6, curr_y + 11, size=6, color=(225, 29, 72))
            draw.text((text_x + 18, curr_y), cost_str, fill=(30, 41, 59), font=font_body)
        elif cost_type == "motivation":
            draw.ellipse([text_x + 2, curr_y + 7, text_x + 10, curr_y + 15], fill=(245, 158, 11))
            draw.text((text_x + 16, curr_y), cost_str, fill=(30, 41, 59), font=font_body)
        elif cost_type == "good_impression":
            draw.ellipse([text_x + 2, curr_y + 7, text_x + 10, curr_y + 15], fill=(16, 185, 129))
            draw.text((text_x + 16, curr_y), cost_str, fill=(30, 41, 59), font=font_body)
        elif cost_type == "good_condition":
            draw.ellipse([text_x + 2, curr_y + 7, text_x + 10, curr_y + 15], fill=(249, 115, 22))
            draw.text((text_x + 16, curr_y), cost_str, fill=(30, 41, 59), font=font_body)
        elif cost_type == "genki":
            draw.ellipse([text_x + 2, curr_y + 7, text_x + 10, curr_y + 15], fill=(6, 182, 212))
            draw.text((text_x + 16, curr_y), cost_str, fill=(30, 41, 59), font=font_body)
        elif cost_type == "full_power":
            draw.ellipse([text_x + 2, curr_y + 7, text_x + 10, curr_y + 15], fill=(168, 85, 247))
            draw.text((text_x + 16, curr_y), cost_str, fill=(30, 41, 59), font=font_body)
        else:
            draw.text((text_x, curr_y), cost_str, fill=(30, 41, 59), font=font_body)
        curr_y += 26

        if hand_str:
            draw.text((text_x, curr_y), hand_str, fill=(30, 41, 59), font=font_body)
            curr_y += 26

        if cond_str:
            draw.text((text_x, curr_y), cond_str, fill=(217, 119, 6), font=font_body)
            curr_y += 26

        # 効果箇条書き
        for w_lines in wrapped_eff_lines:
            if not w_lines:
                continue
            draw_diamond(draw, text_x + 8, curr_y + 11, size=4, color=(6, 182, 212))
            draw.text((text_x + 20, curr_y), w_lines[0], fill=(30, 41, 59), font=font_eff)
            curr_y += 24
            for sub_line in w_lines[1:]:
                draw.text((text_x + 20, curr_y), sub_line, fill=(30, 41, 59), font=font_eff)
                curr_y += 24

        # 制限事項
        if lim_str:
            font_lim = get_font(14)
            draw.text((text_x, curr_y + 2), lim_str, fill=(79, 70, 229), font=font_lim)
            curr_y += 24

        # カスタマイズ描画
        if custom_items:
            curr_y += 6
            draw.line([text_x, curr_y, width - 26, curr_y], fill=(226, 232, 240), width=1)
            curr_y += 8

            font_cust_head = get_font(12)
            c_header = "カスタマイズ解放効果" if name.endswith("+") else "強化(+)時 カスタマイズ解放効果"
            h_bbox = font_cust_head.getbbox(c_header)
            h_w = h_bbox[2] - h_bbox[0] + 16
            draw.rounded_rectangle([text_x, curr_y, text_x + h_w, curr_y + 19], radius=4, fill=(243, 232, 255), outline=(216, 180, 254), width=1)
            draw.text((text_x + 8, curr_y + 2), c_header, fill=(126, 34, 206), font=font_cust_head)
            curr_y += 24

            for w_lines in wrapped_cust_items:
                if not w_lines:
                    continue
                draw.ellipse([text_x + 4, curr_y + 6, text_x + 10, curr_y + 12], fill=(147, 51, 234))
                draw.text((text_x + 16, curr_y), w_lines[0], fill=(55, 65, 81), font=font_cust_text)
                curr_y += 22
                for sub_line in w_lines[1:]:
                    draw.text((text_x + 16, curr_y), sub_line, fill=(55, 65, 81), font=font_cust_text)
                    curr_y += 22

        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    def build_p_item_image(self, item_data: dict[str, Any]) -> bytes:
        """PアイテムのP図鑑風詳細画像を生成する"""
        name = item_data.get("name", "")
        pid = str(item_data.get("id", ""))
        rarity = item_data.get("rarity", "SSR")
        plan = (item_data.get("plan") or "anomaly").lower()
        plan_meta = PLAN_COLORS.get(plan, PLAN_COLORS["free"])

        acts = (item_data.get("actions") or "").strip()
        effs = (item_data.get("effects") or "").strip()
        dsl_full = "; ".join([x for x in [acts, effs] if x])

        # limit:X の抽出（一番外側の最後の limit をレッスン回数とする）
        limit_matches = re.findall(r"(?:^|;|\s)limit:(\d+)", dsl_full)
        limit_str = f"(レッスン中{limit_matches[-1]}回)" if limit_matches else ""

        # 文末のトップレベル limit:X を安全に除去して翻訳へ渡す
        dsl_no_limit = re.sub(r";?\s*limit:\d+\s*(\}*)\s*$", r"\1", dsl_full).strip("; ")
        translated = self.dsl.translate(dsl_no_limit) if dsl_no_limit else ""

        # トリガー文（「直接効果で 強気 になった時、元気が50以上の場合、」等）
        trigger = ""
        eff_body = translated
        if "\n" in translated:
            parts = translated.split("\n", 1)
            trigger = _clean_emoji_for_image(parts[0].strip())
            eff_body = parts[1].strip()

        eff_items = [_clean_emoji_for_image(item_str.strip()) for item_str in eff_body.split(" / ") if item_str.strip()]
        if limit_str:
            eff_items.append(limit_str)

        # ── レンダリングレイアウト計算 ──
        width = 720
        content_lines_count = len(eff_items) + (1 if trigger else 0)
        height = max(240, 110 + content_lines_count * 28 + 20)

        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # カードベース背景
        draw.rounded_rectangle([6, 6, width - 7, height - 7], radius=18, fill=(255, 255, 255), outline=(218, 224, 233), width=2)

        # ── 左カラム: アイコン・プラン・解放PLv ──
        icon_x = 24
        icon_y = 24
        icon_size = 136

        # アイコン枠
        draw.rounded_rectangle([icon_x - 2, icon_y - 2, icon_x + icon_size + 1, icon_y + icon_size + 1],
                               radius=18, fill=(241, 245, 249), outline=(226, 232, 240), width=1)

        icon_path = self.resolver._get_p_item_image(pid) if pid else None
        if icon_path and icon_path.exists():
            try:
                item_img = Image.open(icon_path).convert("RGBA").resize((icon_size, icon_size), Image.Resampling.LANCZOS)
                item_img = round_corners(item_img, 16)
                img.alpha_composite(item_img, (icon_x, icon_y))
            except Exception:
                pass
        else:
            draw.rounded_rectangle([icon_x, icon_y, icon_x + icon_size - 1, icon_y + icon_size - 1],
                                   radius=16, fill=(241, 245, 249))

        # プランバッジ
        plan_badge_y = icon_y + icon_size + 12
        plan_badge_w = 110
        plan_badge_h = 26
        plan_badge_x = icon_x + (icon_size - plan_badge_w) // 2

        draw.rounded_rectangle([plan_badge_x, plan_badge_y, plan_badge_x + plan_badge_w, plan_badge_y + plan_badge_h],
                               radius=13, fill=plan_meta["badge_bg"], outline=plan_meta["badge_border"], width=1)
        draw.ellipse([plan_badge_x + 8, plan_badge_y + 7, plan_badge_x + 20, plan_badge_y + 19], fill=plan_meta["bg"])
        font_plan = get_font(13)
        draw.text((plan_badge_x + 26, plan_badge_y + 4), plan_meta["text"], fill=(51, 65, 85), font=font_plan)

        # 解放PLv
        font_plv = get_font(12)
        plv_str = "解放PLv -"
        plv_bbox = font_plv.getbbox(plv_str)
        plv_w = plv_bbox[2] - plv_bbox[0]
        draw.text((icon_x + (icon_size - plv_w) // 2, plan_badge_y + 30), plv_str, fill=(148, 163, 184), font=font_plv)

        # ── 右カラム: アイテム名・諸元 ──
        text_x = 186
        text_y = 24

        font_title = get_font(23)
        draw.text((text_x, text_y), name, fill=(30, 41, 59), font=font_title)

        name_bbox = font_title.getbbox(name)
        badges_x = text_x + (name_bbox[2] - name_bbox[0]) + 14

        font_badge = get_font(12)
        r_bbox = font_badge.getbbox(rarity)
        r_w = r_bbox[2] - r_bbox[0] + 16
        draw.rounded_rectangle([badges_x, text_y + 3, badges_x + r_w, text_y + 25],
                               radius=6, fill=(241, 245, 249), outline=(203, 213, 225), width=1)
        draw.text((badges_x + 8, text_y + 5), rarity, fill=(71, 85, 105), font=font_badge)

        line_y = text_y + 38
        draw.line([text_x, line_y, width - 26, line_y], fill=(226, 232, 240), width=1)

        curr_y = line_y + 12
        font_body = get_font(15)

        if trigger:
            draw.text((text_x, curr_y), trigger, fill=(30, 41, 59), font=font_body)
            curr_y += 28

        for item in eff_items:
            draw_diamond(draw, text_x + 8, curr_y + 11, size=4, color=(6, 182, 212))
            draw.text((text_x + 20, curr_y), item, fill=(30, 41, 59), font=font_body)
            curr_y += 26

        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    def build_by_name(self, name: str) -> bytes | None:
        """カード名またはアイテム名から自動判定して詳細画像を生成する"""
        clean_name = name.strip().strip("『』「」【】")

        # 1. スキルカードを完全一致 / 部分一致検索
        for sc in self._skill_cards:
            if sc.get("name", "").strip() == clean_name:
                return self.build_skill_card_image(sc)

        # 2. Pアイテムを完全一致 / 部分一致検索
        for pi in self._p_items:
            if pi.get("name", "").strip() == clean_name:
                return self.build_p_item_image(pi)

        # 部分一致フォールバック（スキルカード）
        for sc in self._skill_cards:
            if clean_name in sc.get("name", ""):
                return self.build_skill_card_image(sc)

        # 部分一致フォールバック（Pアイテム）
        for pi in self._p_items:
            if clean_name in pi.get("name", ""):
                return self.build_p_item_image(pi)

        return None
