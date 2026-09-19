#!/usr/bin/env python3
"""
cli_advisory_image.py — あじふらい氏推奨構成画像生成 CLI
- idol 指定時: 単一Pアイドルの画像を生成
- idol 省略時: MongoDB から所持しているおすすめPアイドルを抽出して一括生成
- columns: 1 (デフォルト・幅390pxスリム) または 2 (幅760pxワイド)
"""

import argparse
import json
import sys
from pathlib import Path

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

sys.path.insert(0, str(WORKSPACE_DIR / "gakumas-agent-bot"))
sys.path.insert(0, str(WORKSPACE_DIR / "gakumas-tools" / "gakumas-agent-bot"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from advisory_parser import (
    parse_advisory,
    get_stage_recommended_pidols,
    parse_advisory_for_entry,
    get_stage_support_combinations,
    get_stage_configurations,
    get_owned_support_card_names,
    is_support_card_owned
)
from advisory_image_builder import AdvisoryImageBuilder

def get_owned_pidol_data(mongo_uri: str = "mongodb://192.168.100.4:27017", user_id: str = "755794545861591082") -> tuple[set[str], set[tuple[str, str]]]:
    """MongoDB から所持している Pアイドルのタイトル集合および (idol, title) ペアを取得する"""
    try:
        from pymongo import MongoClient
        import re
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
        db = client["gakumas-tools"]
        cursor = list(db["owned_p_idols"].find({"userId": user_id}))
        if not cursor:
            cursor = list(db["owned_p_idols"].find({}))
        
        from advisory_parser import IDOL_NAME_TO_KEY
        owned_titles = set()
        owned_pairs = set()
        for d in cursor:
            raw_title = d.get("title", "")
            m = re.search(r'【([^】]+)】', raw_title)
            costume_title = m.group(1).strip() if m else raw_title.strip()
            if not costume_title:
                continue
            owned_titles.add(costume_title)
            
            raw_name = d.get("idol_name") or d.get("name") or ""
            clean_name = raw_name.replace(" ", "").strip()
            if clean_name:
                owned_pairs.add((clean_name, costume_title))
                idol_k = IDOL_NAME_TO_KEY.get(clean_name)
                if idol_k:
                    owned_pairs.add((idol_k, costume_title))
        return owned_titles, owned_pairs
    except Exception as e:
        return set(), set()


def main():
    parser = argparse.ArgumentParser(description="Generate contest advisory infographic image(s)")
    parser.add_argument("--stage", type=int, required=True, help="Stage number (1, 2, 3)")
    parser.add_argument("--idol", type=str, default=None, help="Idol name or query (optional)")
    parser.add_argument("--season", type=int, default=None, help="Season number (optional)")
    parser.add_argument("--columns", type=int, choices=[1, 2], default=1, help="Number of columns (1: slim/default, 2: wide)")
    parser.add_argument("--limit", type=int, default=5, help="Max images in multi mode (default: 5)")
    parser.add_argument("--source", type=str, choices=["human", "ai"], default="human", help="Advisory source (human: Aji-fry, ai: AI auto-advisory)")
    parser.add_argument("--mongo-uri", type=str, default="mongodb://192.168.100.4:27017", help="MongoDB URI")
    parser.add_argument("--output", type=str, default=None, help="Output path (single mode only)")

    args = parser.parse_args()
    builder = AdvisoryImageBuilder()
    tmp_dir = Path("/tmp/advisory_images")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    owned_support_cards = get_owned_support_card_names(mongo_uri=args.mongo_uri)

    # 1. 単一アイドル指定モード
    if args.idol:
        data = parse_advisory(stage=args.stage, idol_query=args.idol, season=args.season, source=args.source)
        if not data:
            print(json.dumps({
                "success": False,
                "error": f"No advisory data found for Stage {args.stage} and idol '{args.idol}'"
            }, ensure_ascii=False))
            sys.exit(1)

        data["columns"] = args.columns
        data["owned_support_cards"] = list(owned_support_cards)
        cur_season = data.get("season", 51)
        p_idol = data.get("p_idol", {})
        idol_key = p_idol.get("idol_key", "idol")
        col_suffix = f"_{args.columns}col"
        out_path = Path(args.output) if args.output else tmp_dir / f"advisory_s{cur_season}_stage{args.stage}_{idol_key}{col_suffix}.png"

        builder.build(data, output_path=out_path)
        full_title = f"{p_idol.get('idol_name', args.idol)}【{p_idol.get('title', '')}】"
        if p_idol.get("extra"):
            full_title += f" ({p_idol.get('extra')})"

        p_items = data.get("p_items", [])
        p_items_details = []
        for it in p_items:
            lbl = builder.resolver.get_p_item_card_label(it)
            sc_name = builder.resolver.get_p_item_support_card_name(it)
            is_owned = is_support_card_owned(sc_name, owned_support_cards)
            p_items_details.append({
                "item_name": it,
                "card_label": lbl,
                "support_card_name": sc_name,
                "is_owned": is_owned
            })

        skill_cards = data.get("skill_cards", [])
        skill_cards_details = []
        for sc in skill_cards:
            lbl = builder.resolver.get_skill_card_support_label(sc["name"])
            if lbl:
                sc_name = builder.resolver.get_skill_card_support_card_name(sc["name"])
                is_owned = is_support_card_owned(sc_name, owned_support_cards)
                skill_cards_details.append({
                    "card_name": sc["name"],
                    "card_label": lbl,
                    "support_card_name": sc_name,
                    "is_owned": is_owned
                })

        checklist_items = {
            "p_items": p_items,
            "skill_cards": [
                {
                    "name": sc.get("name", ""),
                    "customizations": sc.get("customizations", [])
                }
                for sc in skill_cards[:10]
            ]
        }

        print(json.dumps({
            "success": True,
            "mode": "single",
            "images": [{
                "image_path": str(out_path.resolve()),
                "season": cur_season,
                "stage": args.stage,
                "idol_name": p_idol.get("idol_name", args.idol),
                "title": p_idol.get("title", ""),
                "full_title": full_title,
                "p_items_details": p_items_details,
                "skill_cards_details": skill_cards_details,
                "checklist_items": checklist_items
            }]
        }, ensure_ascii=False))
        return

    # 2. ステージ推奨構成一括出力モード（汎用 common + 個別指定アイドル）
    stage_configs = get_stage_configurations(args.stage, args.season, owned_cards=owned_support_cards, source=args.source)
    if not stage_configs:
        print(json.dumps({
            "success": False,
            "error": f"No advisory configurations found for Stage {args.stage}"
        }, ensure_ascii=False))
        sys.exit(1)

    images_output = []
    for idx, cfg in enumerate(stage_configs):
        adv_data = cfg["data"]
        adv_data["columns"] = args.columns
        adv_data["owned_support_cards"] = list(owned_support_cards)
        cur_season = adv_data.get("season", 51)
        p_idol = adv_data.get("p_idol", {})
        idol_key = p_idol.get("idol_key", f"cfg_{idx}")
        col_suffix = f"_{args.columns}col"
        out_path = tmp_dir / f"advisory_s{cur_season}_stage{args.stage}_{idol_key}_{idx}{col_suffix}.png"

        builder.build(adv_data, output_path=out_path)
        full_title = f"{p_idol.get('idol_name', '')}【{p_idol.get('title', '')}】"
        if p_idol.get("extra"):
            full_title += f" ({p_idol.get('extra')})"

        p_items = adv_data.get("p_items", [])
        p_items_details = []
        for it in p_items:
            lbl = builder.resolver.get_p_item_card_label(it)
            sc_name = builder.resolver.get_p_item_support_card_name(it)
            is_owned = is_support_card_owned(sc_name, owned_support_cards)
            p_items_details.append({
                "item_name": it,
                "card_label": lbl,
                "support_card_name": sc_name,
                "is_owned": is_owned
            })

        skill_cards = adv_data.get("skill_cards", [])
        skill_cards_details = []
        for sc in skill_cards:
            lbl = builder.resolver.get_skill_card_support_label(sc["name"])
            if lbl:
                sc_name = builder.resolver.get_skill_card_support_card_name(sc["name"])
                is_owned = is_support_card_owned(sc_name, owned_support_cards)
                skill_cards_details.append({
                    "card_name": sc["name"],
                    "card_label": lbl,
                    "support_card_name": sc_name,
                    "is_owned": is_owned
                })

        images_output.append({
            "image_path": str(out_path.resolve()),
            "season": cur_season,
            "stage": args.stage,
            "idol_name": p_idol.get("idol_name", ""),
            "title": p_idol.get("title", ""),
            "full_title": full_title,
            "config_type": cfg.get("type", "common"),
            "label": cfg.get("label", ""),
            "target_idols": cfg.get("target_idols", []),
            "target_idols_short": cfg.get("target_idols_short", []),
            "p_items_details": p_items_details,
            "skill_cards_details": skill_cards_details
        })

    support_info = get_stage_support_combinations(args.stage, args.season, owned_cards=owned_support_cards, source=args.source)

    print(json.dumps({
        "success": True,
        "mode": "stage_overview",
        "count": len(images_output),
        "stage": args.stage,
        "season": support_info.get("season", cur_season),
        "images": images_output,
        "support_combinations": support_info.get("combinations", []),
        "asari_idols": support_info.get("asari_idols", [])
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
