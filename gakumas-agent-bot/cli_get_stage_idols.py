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
        if c.exists():
            return c
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

def get_owned_pidol_titles(mongo_uri: str = "mongodb://192.168.100.4:27017", user_id: str = "755794545861591082") -> set[str]:
    try:
        from pymongo import MongoClient
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
        db = client["gakumas-tools"]
        cursor = db["owned_p_idols"].find({"userId": user_id}, {"title": 1, "_id": 0})
        titles = {d["title"].strip() for d in cursor if "title" in d and d["title"]}
        if not titles:
            cursor_all = db["owned_p_idols"].find({}, {"title": 1, "_id": 0})
            titles = {d["title"].strip() for d in cursor_all if "title" in d and d["title"]}
        return titles
    except Exception:
        return set()

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

    owned_titles = get_owned_pidol_titles(mongo_uri=args.mongo_uri)

    choices = []
    for r in recs:
        idol_name = r.get("idol_name", "")
        title = r.get("title", "")
        extra = r.get("extra", "")
        is_owned = title in owned_titles

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
