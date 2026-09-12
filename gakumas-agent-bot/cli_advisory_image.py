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

from advisory_parser import parse_advisory, get_stage_recommended_pidols, parse_advisory_for_entry
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
    parser.add_argument("--mongo-uri", type=str, default="mongodb://192.168.100.4:27017", help="MongoDB URI")
    parser.add_argument("--output", type=str, default=None, help="Output path (single mode only)")

    args = parser.parse_args()
    builder = AdvisoryImageBuilder()
    tmp_dir = Path("/tmp/advisory_images")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 1. 単一アイドル指定モード
    if args.idol:
        data = parse_advisory(stage=args.stage, idol_query=args.idol, season=args.season)
        if not data:
            print(json.dumps({
                "success": False,
                "error": f"No advisory data found for Stage {args.stage} and idol '{args.idol}'"
            }, ensure_ascii=False))
            sys.exit(1)

        data["columns"] = args.columns
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
        p_items_details = [
            {"item_name": it, "card_label": builder.resolver.get_p_item_card_label(it)}
            for it in p_items
        ]
        skill_cards = data.get("skill_cards", [])
        skill_cards_details = [
            {"card_name": sc["name"], "card_label": builder.resolver.get_skill_card_support_label(sc["name"])}
            for sc in skill_cards if builder.resolver.get_skill_card_support_label(sc["name"])
        ]

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
                "skill_cards_details": skill_cards_details
            }]
        }, ensure_ascii=False))
        return

    # 2. 所持Pアイドル一括出力モード
    all_recs = get_stage_recommended_pidols(args.stage, args.season)
    if not all_recs:
        print(json.dumps({
            "success": False,
            "error": f"No recommended P-idols found for Stage {args.stage}"
        }, ensure_ascii=False))
        sys.exit(1)

    owned_titles, owned_pairs = get_owned_pidol_data(mongo_uri=args.mongo_uri)
    target_entries = []

    # 所持しているおすすめを優先抽出
    if owned_titles or owned_pairs:
        for entry in all_recs:
            e_key = entry.get("idol_key", "")
            e_name = entry.get("idol_name", "")
            e_title = entry.get("title", "")
            if (e_key, e_title) in owned_pairs or (e_name, e_title) in owned_pairs or e_title in owned_titles:
                target_entries.append(entry)

    # 所持データがない、または0件の場合は上位3件をフォールバック
    if not target_entries:
        target_entries = all_recs[:3]
    else:
        target_entries = target_entries[:args.limit]

    images_output = []
    for idx, entry in enumerate(target_entries):
        adv_data = parse_advisory_for_entry(stage=args.stage, matched_entry=entry, season=args.season)
        if not adv_data:
            continue

        adv_data["columns"] = args.columns
        cur_season = adv_data.get("season", 51)
        p_idol = adv_data.get("p_idol", {})
        idol_key = p_idol.get("idol_key", f"idol_{idx}")
        col_suffix = f"_{args.columns}col"
        out_path = tmp_dir / f"advisory_s{cur_season}_stage{args.stage}_{idol_key}_{idx}{col_suffix}.png"

        builder.build(adv_data, output_path=out_path)
        full_title = f"{p_idol.get('idol_name', '')}【{p_idol.get('title', '')}】"
        if p_idol.get("extra"):
            full_title += f" ({p_idol.get('extra')})"

        p_items = adv_data.get("p_items", [])
        p_items_details = [
            {"item_name": it, "card_label": builder.resolver.get_p_item_card_label(it)}
            for it in p_items
        ]
        skill_cards = adv_data.get("skill_cards", [])
        skill_cards_details = [
            {"card_name": sc["name"], "card_label": builder.resolver.get_skill_card_support_label(sc["name"])}
            for sc in skill_cards if builder.resolver.get_skill_card_support_label(sc["name"])
        ]

        images_output.append({
            "image_path": str(out_path.resolve()),
            "season": cur_season,
            "stage": args.stage,
            "idol_name": p_idol.get("idol_name", ""),
            "title": p_idol.get("title", ""),
            "full_title": full_title,
            "p_items_details": p_items_details,
            "skill_cards_details": skill_cards_details
        })

    print(json.dumps({
        "success": True,
        "mode": "multi",
        "count": len(images_output),
        "stage": args.stage,
        "images": images_output
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
