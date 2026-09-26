"""
image_resolver.py — ワークスペース上のローカル画像アセット高精度解決モジュール

- Pアイドル画像: packages/gakumas-images/images/pIdols/{pIdolId}.png
- スキルカード画像: packages/gakumas-images/images/skillCards/icons/{cardId}.png
- Pアイテム画像: packages/gakumas-images/images/pItems/icons/{itemId}.png
- アイドル画像: packages/gakumas-images/images/idols/{idolId}.png

同名タイトル（例: 【学園生活】、【Campus mode!!】）をアイドル名と組み合わせて正確に区別・解決する。
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("image_resolver")

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

IMAGES_DIR = _find_dir([
    Path("/home/pi/gakumas-mcp-server/data/images"),
    Path("/app/packages/gakumas-images/images"),
    Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-images/images"),
    WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-images" / "images",
    WORKSPACE_DIR / "packages" / "gakumas-images" / "images",
])

CSV_DIR = _find_dir([
    Path("/home/pi/gakumas-mcp-server/data/csv"),
    Path("/app/packages/gakumas-data/csv"),
    Path("/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/csv"),
    WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-data" / "csv",
    WORKSPACE_DIR / "packages" / "gakumas-data" / "csv",
])

SUPPORT_CARDS_JSON = _find_dir([
    Path("/home/pi/gakumas-mcp-server/data/support_cards_master.json"),
    Path("/app/gakumas-support_cards/support_cards_master.json"),
    Path("/app/support_cards_master.json"),
    Path("/root/gakumas-workspace/gakumas-support_cards/support_cards_master.json"),
    Path("/root/gakumas-workspace/gakumas-tools/gakumas-support_cards/support_cards_master.json"),
    WORKSPACE_DIR / "gakumas-support_cards" / "support_cards_master.json",
    WORKSPACE_DIR / "gakumas-tools" / "gakumas-support_cards" / "support_cards_master.json",
    Path(__file__).resolve().parent.parent / "gakumas-support_cards" / "support_cards_master.json",
])


class ImageResolver:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        self.idols: dict[int, str] = {}  # idolId -> idol_name
        self.p_idols: list[dict[str, Any]] = []  # [{id, idolId, idol_name, title, rarity}]
        self.skill_cards: dict[str, str] = {}  # card_name -> card_id
        self.skill_card_by_id: dict[int, dict[str, Any]] = {}  # id -> {name, rarity, sourceType, pIdolId, unique}
        self.skill_card_by_name: dict[str, dict[str, Any]] = {}  # name -> {id, rarity, sourceType, pIdolId, unique}
        self.p_items: dict[str, str] = {}  # item_name -> item_id
        self.p_items_by_id: dict[int, dict[str, Any]] = {}  # id -> {name, source}
        self.customizations: dict[int, str] = {}  # id -> name
        self.support_card_to_item: dict[str, str] = {}
        self.support_card_to_wiki_id: dict[str, str] = {}
        self.p_item_to_card_info: dict[str, dict[str, Any]] = {}  # item_name -> {card_name, rarity, type, label}
        self._load_data()
        self._loaded = True

    def _load_data(self):
        # 1. アイドルマスタ
        idols_path = CSV_DIR / "idols.csv"
        if idols_path.exists():
            with open(idols_path, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    try:
                        self.idols[int(r["id"])] = r["name"].strip()
                    except Exception:
                        pass

        # 2. Pアイドルマスタ（idolId と紐付け）
        pidols_path = CSV_DIR / "p_idols.csv"
        if pidols_path.exists():
            with open(pidols_path, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    try:
                        iid = int(r.get("idolId", 0))
                        iname = self.idols.get(iid, "")
                        self.p_idols.append({
                            "id": r.get("id", "").strip(),
                            "idolId": iid,
                            "idol_name": iname,
                            "title": r.get("title", "").strip(),
                            "rarity": r.get("rarity", "").strip(),
                            "plan": r.get("plan", "").strip(),
                        })
                    except Exception:
                        pass

        # 3. スキルカード
        sc_path = CSV_DIR / "skill_cards.csv"
        if sc_path.exists():
            with open(sc_path, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    name = r.get("name", "").strip()
                    cid_str = r.get("id", "").strip()
                    if name and cid_str:
                        self.skill_cards[name] = cid_str
                        try:
                            cid = int(cid_str)
                            pid_val = int(r.get("pIdolId", 0)) if r.get("pIdolId") else 0
                            info = {
                                "id": cid,
                                "name": name,
                                "rarity": r.get("rarity", "").strip(),
                                "sourceType": r.get("sourceType", "").strip(),
                                "pIdolId": pid_val,
                                "unique": r.get("unique", "").lower() == "true",
                            }
                            self.skill_card_by_id[cid] = info
                            self.skill_card_by_name[name] = info
                        except Exception:
                            pass

        # 4. Pアイテム
        pi_path = CSV_DIR / "p_items.csv"
        if pi_path.exists():
            with open(pi_path, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    name = r.get("name", "").strip()
                    pid_str = r.get("id", "").strip()
                    src = r.get("source", "").strip()
                    if name and pid_str:
                        self.p_items[name] = pid_str
                        try:
                            pid = int(pid_str)
                            self.p_items_by_id[pid] = {"name": name, "source": src}
                        except Exception:
                            pass
                        if src:
                            self.support_card_to_item[src] = name

        # 4.5 カスタマイズ
        cust_path = CSV_DIR / "customizations.csv"
        if cust_path.exists():
            with open(cust_path, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    cid_str = r.get("id", "").strip()
                    cname = r.get("name", "").strip()
                    if cid_str and cname:
                        try:
                            self.customizations[int(cid_str)] = cname
                        except Exception:
                            pass

        # 5. サポートカード（support_cards.csv から wiki_id とカード名を紐付け）
        sc_csv = _find_dir([
            Path("/app/gakumas-support_cards/support_cards.csv"),
            WORKSPACE_DIR / "gakumas-support_cards" / "support_cards.csv",
            WORKSPACE_DIR / "gakumas-tools" / "gakumas-support_cards" / "support_cards.csv",
            Path("/root/gakumas-workspace/gakumas-support_cards/support_cards.csv"),
            Path("/root/gakumas-workspace/gakumas-tools/gakumas-support_cards/support_cards.csv"),
            Path(__file__).resolve().parent.parent / "gakumas-support_cards" / "support_cards.csv",
        ])
        if sc_csv.exists():

            try:
                with open(sc_csv, encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        c_name = r.get("name", "").strip()
                        wiki_id = r.get("wiki_id", "").strip()
                        if c_name and wiki_id:
                            self.support_card_to_wiki_id[c_name] = wiki_id
            except Exception as e:
                log.error("[ImageResolver] Error loading support_cards.csv: %s", e)

        # 6. サポートカード（support_cards_master.json）
        if SUPPORT_CARDS_JSON.exists():
            try:
                type_map = {"vocal": "Vo", "dance": "Da", "visual": "Vi", "assist": "サポ", "support": "サポ"}
                with open(SUPPORT_CARDS_JSON, encoding="utf-8") as f:
                    cards = json.load(f)
                    for c in cards:
                        c_name = c.get("name", "").strip()
                        wiki_id = c.get("id", "").strip()
                        rarity = c.get("rarity", "SSR").strip()
                        ctype = c.get("type", "").strip().lower()
                        type_str = type_map.get(ctype, ctype.capitalize())

                        if c_name and wiki_id:
                            self.support_card_to_wiki_id[c_name] = wiki_id
                        item = c.get("acquired_p_item", {})
                        if isinstance(item, dict) and item.get("name"):
                            iname = item["name"].strip()
                            self.support_card_to_item[c_name] = iname
                            self.p_item_to_card_info[iname] = {
                                "card_name": c_name,
                                "rarity": rarity,
                                "type": type_str,
                                "label": f"[{rarity}] {c_name} ({type_str})"
                            }
            except Exception as e:
                log.error("[ImageResolver] Error loading support cards: %s", e)

        log.info("[ImageResolver] Loaded: %d idols, %d pIdols, %d skillCards, %d pItems, %d supportCardWikiIds, %d pItemToCards",
                 len(self.idols), len(self.p_idols), len(self.skill_cards), len(self.p_items), len(self.support_card_to_wiki_id), len(self.p_item_to_card_info))

    def get_p_item_card_label(self, item_name: str) -> str:
        """Pアイテム名から '[SSR] カード名 (属性)' を取得する"""
        clean_name = item_name.strip()
        if clean_name in self.p_item_to_card_info:
            return self.p_item_to_card_info[clean_name]["label"]
        for k, v in self.p_item_to_card_info.items():
            if clean_name in k or k in clean_name:
                return v["label"]
        return "推奨Pアイテム"

    SUPPORT_SKILLS_MAP = {
        # ── SR サポートカード固有スキル ──
        "キメ顔で自撮り": {"name": "パシャっとキメポ", "rarity": "SR", "type": "Da"},
        "お姉ちゃんだもの": {"name": "体当たりのラブコール", "rarity": "SR", "type": "Vi"},
        "お姉ちゃんだもの！": {"name": "体当たりのラブコール", "rarity": "SR", "type": "Vi"},
        "おアツイ視線": {"name": "のらりくらりしっかり", "rarity": "SR", "type": "Vo"},
        "ご指導ご鞭撻": {"name": "てとりあしとり", "rarity": "SR", "type": "Vi"},
        "ストレッチ談義": {"name": "魅惑の大腿四頭筋", "rarity": "SR", "type": "Da"},
        "全力サポート": {"name": "はじめてのお友達", "rarity": "SR", "type": "アシスト"},
        "なに聴いてるの？": {"name": "イヤホンはんぶんこ", "rarity": "SR", "type": "Vo"},
        "切れた鼻緒が結んだ絆": {"name": "やさしさ、あったかい", "rarity": "SR", "type": "Vi"},
        "気になる……": {"name": "興味深い飲み物", "rarity": "SR", "type": "Vo"},
        "こうかい……？": {"name": "バズっちゃお！", "rarity": "SR", "type": "Da"},
        "旬の味わい": {"name": "サンマ、パタパタ", "rarity": "SR", "type": "Vi"},
        "愛情レインボー": {"name": "SSCの爆誕", "rarity": "SR", "type": "Vi"},
        "ディテールが肝心": {"name": "まごころを込めて", "rarity": "SR", "type": "Vo"},
        "草笛ハーモニー": {"name": "ピューとシューの二重奏", "rarity": "SR", "type": "Da"},
        "小さなお客さん": {"name": "虫愛づる王子様", "rarity": "SR", "type": "Vi"},
        "味見はいかが": {"name": "ぐつぐつ、いいにおい♪", "rarity": "SR", "type": "Vo"},
        "はじめてのけんか？": {"name": "仲良しの証", "rarity": "SR", "type": "Vi"},

        # ── SSR サポートカード固有スキル ──
        "ほぐれるひととき": {"name": "クールダウンが大切よ！", "rarity": "SSR", "type": "Vi"},
        "奥義、受け流し！": {"name": "レディ・セット、ゴー！", "rarity": "SSR", "type": "Vo"},
        "対象、ロックオン": {"name": "月村手毬、興味深いわね", "rarity": "SSR", "type": "Vo"},
        "勝利をつかめ！": {"name": "大運動会、開催っ！", "rarity": "SSR", "type": "Vo"},
        "夏夜に咲く思い出": {"name": "いつまでも続けばいいのに", "rarity": "SSR", "type": "Da"},
        "対戦お願いします！": {"name": "相手にとって不足なしよ！", "rarity": "SSR", "type": "Vi"},
        "ガタゴトすやすや": {"name": "あなたとふたり、電車で", "rarity": "SSR", "type": "Vo"},
        "頭上に注意！": {"name": "上かッ！！", "rarity": "SSR", "type": "Da"},
        "せーのでぱくっ！": {"name": "あたしの勝ち、ですね〜！", "rarity": "SSR", "type": "Vi"},
        "お姉ちゃん、参戦！": {"name": "かかってらっしゃい！", "rarity": "SSR", "type": "Vi"},
        "ふれんどめもりーず": {"name": "思い出の宝箱だ、ね", "rarity": "SSR", "type": "Vo"},
        "寒空リサイタル": {"name": "手毬のリサイタル、だね", "rarity": "SSR", "type": "Vo"},
        "あこがれ不良ムーブ": {"name": "堂々とサボってる！？", "rarity": "SSR", "type": "Vo"},
        "いたずらサンタさん": {"name": "メリクリ、おねーちゃん♪", "rarity": "SSR", "type": "Da"},
        "勝負はこれから！": {"name": "さあ、もう一戦！", "rarity": "SSR", "type": "Vo"},
        "執念キャッチャー": {"name": "ぜったいに取るんだ！", "rarity": "SSR", "type": "Vo"},
        "月明かりに包まれて": {"name": "仲直りしましょう", "rarity": "SSR", "type": "Vo"},
        "花萌ゆ季節": {"name": "次の桜の季節には。", "rarity": "SSR", "type": "Vo"},
        "陽だまりの生徒会室": {"name": "お疲れ様、千奈ちゃん。", "rarity": "SSR", "type": "Vi"},
        "心のアルバム": {"name": "おいしい顔、いただき～！", "rarity": "SSR", "type": "Da"},
        "ティーパーティ": {"name": "可愛いと可愛いで可愛い！", "rarity": "SSR", "type": "Vo"},
        "光のステージ": {"name": "まじか。", "rarity": "SSR", "type": "Da"},
        "新生徒会爆誕！": {"name": "仕事のつもりで臨みなさい", "rarity": "SSR", "type": "Vi"},
        "薄れゆく壁": {"name": "第２回教室パーティ！", "rarity": "SSR", "type": "Vi"},
        "みずたまりスキップ": {"name": "まだ上がりませんように！", "rarity": "SSR", "type": "Vo"},
        "喧嘩するほど仲がいい": {"name": "こいつらめんどくさー", "rarity": "SSR", "type": "Vo"},
        "はじける水しぶき": {"name": "一時休戦です", "rarity": "SSR", "type": "Vo"},
        "交わる感情": {"name": "花火、やりませんか……？", "rarity": "SSR", "type": "Vi"},
        "ダメダメクッキング": {"name": "わたしたち、やればできる", "rarity": "SSR", "type": "Da"},
        "お泊り猛勉強": {"name": "「ア」じゃなくて「エ」！", "rarity": "SSR", "type": "Vi"},
        "その本、おもしろい？": {"name": "ゆっくりと過ごしましょう", "rarity": "SSR", "type": "Vi"},
        "ほかほか焼き芋": {"name": "そろそろ焼けたかな？", "rarity": "SSR", "type": "Da"},
        "紅葉ランニング": {"name": "ぜったい追いついてやる！", "rarity": "SSR", "type": "Vi"},
        "雨宿りのバス停": {"name": "さみだれ", "rarity": "SSR", "type": "Vi"},
        "光の夜": {"name": "キラキラして綺麗～っ！", "rarity": "SSR", "type": "Da"},
        "練習再開！": {"name": "もう一度、最初から！", "rarity": "SSR", "type": "Vo"},
        "バレンタイン大作戦！": {"name": "バレンタイン会議中ーっ！", "rarity": "SSR", "type": "Vi"},
        "お手並み拝見": {"name": "私を楽しませろ", "rarity": "SSR", "type": "Da"},
        "あつあつはふはふ": {"name": "おでん、通りま〜すッ！", "rarity": "SSR", "type": "Vi"},
    }



    def get_skill_card_support_label(self, card_name: str) -> str | None:
        """スキルカード名から由来サポートカード情報 '[SSR] カード名 (属性)' を取得する（サポカ由来でない場合はNone）"""
        clean = card_name.rstrip("+").strip()
        info = self.SUPPORT_SKILLS_MAP.get(clean)
        if info:
            return f"[{info['rarity']}] {info['name']} ({info['type']})"
        for k, v in self.SUPPORT_SKILLS_MAP.items():
            if clean in k or k in clean:
                return f"[{v['rarity']}] {v['name']} ({v['type']})"
    def get_p_item_support_card_name(self, item_name: str) -> str | None:
        """Pアイテム名から由来サポートカード名を取得する"""
        clean_name = item_name.strip()
        if clean_name in self.p_item_to_card_info:
            return self.p_item_to_card_info[clean_name].get("card_name")
        for k, v in self.p_item_to_card_info.items():
            if clean_name in k or k in clean_name:
                return v.get("card_name")
        return None

    def get_skill_card_support_card_name(self, card_name: str) -> str | None:
        """スキルカード名から由来サポートカード名を取得する"""
        clean = card_name.rstrip("+").strip()
        info = self.SUPPORT_SKILLS_MAP.get(clean)
        if info:
            return info["name"]
        for k, v in self.SUPPORT_SKILLS_MAP.items():
            if clean in k or k in clean:
                return v["name"]
        return None

    def find_images_in_text(self, text: str, max_images: int = 6) -> list[tuple[str, Path]]:
        """
        テキストから文脈を考慮して正確な画像を解決する（最大 max_images 件）
        """
        results: list[tuple[str, Path]] = []
        found_paths: set[Path] = set()

        # テキスト内に登場するアイドル名を特定
        mentioned_idols = set()
        for iid, iname in self.idols.items():
            if iname in text or iname.replace(" ", "") in text:
                mentioned_idols.add(iname)

        # 1. Pアイドル（二つ名 【...】 の検出）
        titles = re.findall(r"【([^】]+)】", text)
        for t in titles:
            t_clean = t.strip()
            candidates = [p for p in self.p_idols if p["title"] == t_clean]
            if candidates:
                best_match = None
                if mentioned_idols:
                    for c in candidates:
                        if c["idol_name"] in mentioned_idols:
                            best_match = c
                            break
                if not best_match:
                    best_match = candidates[0]

                img_path = self._get_p_idol_image(best_match["id"])
                if img_path and img_path not in found_paths:
                    lbl = f"Pアイドル: {best_match['idol_name']}【{t_clean}】"
                    results.append((lbl, img_path))
                    found_paths.add(img_path)
                    if len(results) >= max_images:
                        return results

        # 2. 引用句（『...』, 「...」, **...**）の抽出
        quoted = re.findall(r"[『「]([^』」]+)[』」]|\*\*([^\*]+)\*\*", text)
        extracted_terms = []
        for q1, q2 in quoted:
            term = (q1 or q2).strip()
            # サブタグやレベル表記を除去 (例: "眼力+ [R / Active]" -> "眼力+")
            term = re.sub(r"\s*\[.*?\]", "", term).strip()
            if term and term not in extracted_terms:
                extracted_terms.append(term)

        # 2-1. 抽出された用語から Pアイテム / スキルカード / サポートカードを解決
        for term in extracted_terms:
            # Pアイテム
            if term in self.p_items:
                pid = self.p_items[term]
                p = self._get_p_item_image(pid)
                if p and p not in found_paths:
                    results.append((f"Pアイテム: {term}", p))
                    found_paths.add(p)
                    if len(results) >= max_images:
                        return results

            # スキルカード
            if term in self.skill_cards:
                cid = self.skill_cards[term]
                p = self._get_skill_card_image(cid)
                if p and p not in found_paths:
                    results.append((f"スキルカード: {term}", p))
                    found_paths.add(p)
                    if len(results) >= max_images:
                        return results

            # サポートカード
            if term in self.support_card_to_wiki_id:
                p = self._get_support_card_image(term)
                if p and p not in found_paths:
                    results.append((f"サポートカード: 『{term}』", p))
                    found_paths.add(p)
                    if len(results) >= max_images:
                        return results

        # 3. テキスト全体からの直接カード名マッチング（長名優先）
        # 3-1. スキルカード（文字数3文字以上のカードを優先走査）
        sorted_sc = sorted(self.skill_cards.keys(), key=lambda x: len(x), reverse=True)
        for sc_name in sorted_sc:
            if len(sc_name) >= 3 and sc_name in text:
                cid = self.skill_cards[sc_name]
                p = self._get_skill_card_image(cid)
                if p and p not in found_paths:
                    results.append((f"スキルカード: {sc_name}", p))
                    found_paths.add(p)
                    if len(results) >= max_images:
                        return results

        # 3-2. サポートカード（全サポートカード走査）
        def _clean_s(s: str) -> str:
            return re.sub(r"[！？\?!\s♪〜～\.\…「」『』【】]", "", s.lower())

        text_clean = _clean_s(text)
        sorted_sp = sorted(self.support_card_to_wiki_id.keys(), key=lambda x: len(x), reverse=True)
        for sc_name in sorted_sp:
            sc_clean = _clean_s(sc_name)
            if len(sc_clean) >= 3 and (sc_clean in text_clean or sc_name in text):
                sc_img = self._get_support_card_image(sc_name)
                if sc_img and sc_img not in found_paths:
                    results.append((f"サポートカード: 『{sc_name}』", sc_img))
                    found_paths.add(sc_img)
                    if len(results) >= max_images:
                        return results

                # 獲得 Pアイテムがあれば合わせて添付
                item_name = self.support_card_to_item.get(sc_name)
                if item_name:
                    pid = self.p_items.get(item_name)
                    if pid:
                        p = self._get_p_item_image(pid)
                        if p and p not in found_paths:
                            results.append((f"サポカ『{sc_name}』獲得アイテム: {item_name}", p))
                            found_paths.add(p)
                            if len(results) >= max_images:
                                return results

        return results[:max_images]

    def _get_support_card_image(self, card_name: str) -> Path | None:
        """サポートカードのイラスト画像を探索する（wiki_id.png を最優先）"""
        clean_name = re.sub(r"[！？\?!\s♪〜～\.\…「」『』【】]", "", card_name.lower())
        
        # 1. card_name から wiki_id を特定（完全一致 or 記号正規化一致）
        wiki_id = self.support_card_to_wiki_id.get(card_name)
        if not wiki_id:
            for sc_n, wid in self.support_card_to_wiki_id.items():
                if re.sub(r"[！？\?!\s♪〜～\.\…「」『』【】]", "", sc_n.lower()) == clean_name:
                    wiki_id = wid
                    break

        search_dirs = [
            WORKSPACE_DIR / "gakumas-support_cards" / "support_cards",
            WORKSPACE_DIR / "gakumas-og-tools" / "support-cards",
        ]
        
        for d in search_dirs:
            if not d.exists():
                continue
            # 1. wiki_id.png（最優先フォーマット）
            if wiki_id:
                p = d / f"{wiki_id}.png"
                if p.exists() and p.stat().st_size > 1000:
                    return p
            # 2. カード名.png（フォールバック）
            safe_name = card_name.replace("/", "_")
            p = d / f"{safe_name}.png"
            if p.exists() and p.stat().st_size > 1000:
                return p
        return None

    def _get_p_idol_image(self, p_idol_id: str) -> Path | None:
        p = IMAGES_DIR / "pIdols" / f"{p_idol_id}.png"
        if p.exists():
            return p
        gk_webp = WORKSPACE_DIR / "gk-img" / "docs" / "p_idols" / f"{p_idol_id}.webp"
        if gk_webp.exists():
            return gk_webp
        return None

    def _get_skill_card_image(self, card_id: str) -> Path | None:
        sc_dir = IMAGES_DIR / "skillCards" / "icons"
        p = sc_dir / f"{card_id}.png"
        if p.exists():
            return p
        p = sc_dir / f"{card_id}_6.png"
        if p.exists():
            return p
        matches = list(sc_dir.glob(f"{card_id}_*.png"))
        if matches:
            return matches[0]
        gk_webp = WORKSPACE_DIR / "gk-img" / "docs" / "skill_cards" / "icons" / f"{card_id}.webp"
        if gk_webp.exists():
            return gk_webp
        return None

    def _get_p_item_image(self, item_id: str) -> Path | None:
        p = IMAGES_DIR / "pItems" / "icons" / f"{item_id}.png"
        if p.exists():
            return p
        gk_webp = WORKSPACE_DIR / "gk-img" / "docs" / "p_items" / "icons" / f"{item_id}.webp"
        if gk_webp.exists():
            return gk_webp
        return None

    def get_asari_icon_image(self) -> Path | None:
        """あさり先生Botのメガネアバター画像を安全に探索する（フォールバック付き）"""
        candidates = [
            WORKSPACE_DIR / "gakumas-tools" / "packages" / "gakumas-images" / "images" / "idols" / "asari_bot.png",
            WORKSPACE_DIR / "packages" / "gakumas-images" / "images" / "idols" / "asari_bot.png",
            IMAGES_DIR / "idols" / "asari_bot.png",
            Path(__file__).resolve().parent / "assets" / "asari_bot.png",
            WORKSPACE_DIR / "gakumas-agent-bot" / "assets" / "asari_bot.png",
            WORKSPACE_DIR / "gakumas-tools" / "gakumas-agent-bot" / "assets" / "asari_bot.png",
            Path("/app/gakumas-agent-bot/assets/asari_bot.png"),
            Path("/app/packages/gakumas-images/images/idols/asari_bot.png"),
            # 公式ミニキャラ（フォールバック）
            IMAGES_DIR / "idols" / "14.png",
        ]
        for c in candidates:
            try:
                if c.exists() and c.stat().st_size > 100:
                    return c
            except Exception:
                continue
        return None

    def get_card_details(self, name_or_id: str | int) -> dict[str, Any]:
        """カード名またはカードIDからマスタ情報（id, name, rarity, sourceType, pIdolId）を取得する"""
        if isinstance(name_or_id, int) or (isinstance(name_or_id, str) and name_or_id.isdigit()):
            cid = int(name_or_id)
            if cid in self.skill_card_by_id:
                return self.skill_card_by_id[cid]
        
        name = str(name_or_id).strip()
        if name in self.skill_card_by_name:
            return self.skill_card_by_name[name]
        
        # 末尾の '+' を除いた名前で再検索
        trimmed = name.rstrip("+")
        if trimmed in self.skill_card_by_name:
            return self.skill_card_by_name[trimmed]
            
        # 記号正規化で検索
        norm = re.sub(r"[！？\?!\s♪〜～\.\…「」『』【】\+]", "", name.lower())
        for cname, info in self.skill_card_by_name.items():
            if re.sub(r"[！？\?!\s♪〜～\.\…「」『』【】\+]", "", cname.lower()) == norm:
                return info
                
        return {"id": 0, "name": name, "rarity": "R", "sourceType": "produce", "pIdolId": 0}

    def get_skill_card_sort_key(self, card_item: dict[str, Any] | str | int) -> tuple[int, int, str]:
        """
        スキルカードのソートキー:
        1. レアリティ (SSR: 0, SR: 1, R: 2, その他: 3)
        2. 由来 (サポカ: 0, 固有: 1, その他: 2)
        3. カード名
        """
        cname = ""
        cid = None
        if isinstance(card_item, dict):
            cname = card_item.get("name", "")
            cid = card_item.get("id")
        elif isinstance(card_item, int) or (isinstance(card_item, str) and card_item.isdigit()):
            cid = int(card_item)
        else:
            cname = str(card_item)

        info = self.get_card_details(cid if cid is not None else cname)
        rarity = info.get("rarity", "R").upper()
        source_type = info.get("sourceType", "").lower()

        # サポートカード由来判定（CSVのsourceType == support、またはサポカ由来マップに該当）
        card_display_name = cname or info.get("name", "")
        is_support = (source_type == "support") or bool(self.get_skill_card_support_card_name(card_display_name))
        is_pidol = (source_type == "pidol") or bool(info.get("pIdolId", 0) > 0)

        # 1. レアリティ順序
        r_order = {"SSR": 0, "SR": 1, "R": 2}.get(rarity, 3)

        # 2. 由来順序: 1. サポカ由来, 2. アイドル固有, 3. その他
        if is_support:
            s_order = 0
        elif is_pidol:
            s_order = 1
        else:
            s_order = 2

        return (r_order, s_order, card_display_name)

