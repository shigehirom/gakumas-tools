#!/usr/bin/env python3
"""
cli_get_stage_idols.py — ステージ別おすすめPアイドルのオートコンプリート候補取得CLI
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

from advisory_parser import get_stage_recommended_pidols

def get_owned_pidol_data(mongo_uri: str = "mongodb://192.168.100.4:27017", user_id: str = "755794545861591082") -> tuple[set[str], set[tuple[str, str]]]:
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
    except Exception:
        return set(), set()

def main():
    parser = argparse.ArgumentParser(description="Get autocomplete choices for stage P-idols")
    parser.add_argument("--stage", type=int, required=True, help="Stage number (1, 2, 3)")
    parser.add_argument("--season", type=int, default=None, help="Season number")
    parser.add_argument("--mongo-uri", type=str, default="mongodb://192.168.100.4:27017")
    args = parser.parse_args()

    recs = get_stage_recommended_pidols(args.stage, args.season)
    if not recs:
        print("[]")
        return

    owned_titles, owned_pairs = get_owned_pidol_data(mongo_uri=args.mongo_uri)

    choices = []
    for r in recs:
        idol_name = r.get("idol_name", "")
        idol_key = r.get("idol_key", "")
        title = r.get("title", "")
        extra = r.get("extra", "")
        is_owned = (idol_key, title) in owned_pairs or (idol_name, title) in owned_pairs or title in owned_titles

        label = f"{idol_name}【{title}】"
        if extra:
            label += f" {extra}"
        if is_owned:
            label += " 🌟所持"

        # value: "idol_key:title" or full title for easy matching
        val = f"{r.get('idol_key', '')} 【{title}】"
        choices.append({
            "name": label[:100],
            "value": val[:100]
        })

    # Discord autocomplete は最大25件まで
    print(json.dumps(choices[:25], ensure_ascii=False))

if __name__ == "__main__":
    main()
