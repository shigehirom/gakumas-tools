"""
match_history_updater.py — コンテスト対戦結果を MongoDB (contest_matches) に保存するモジュール
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import pymongo

WORKSPACE_DIR = Path("/root/gakumas-workspace")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://192.168.100.4:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "gakumas-tools")

def get_instructions_dir() -> Path:
    candidates = [
        WORKSPACE_DIR / "shared" / "agent-instructions",
        WORKSPACE_DIR / "gakumas-tools" / "agent-instructions",
        WORKSPACE_DIR / "gakumas-agent-bot" / "data",
        Path("/mnt/NVMe/gakumas-tools/agent-instructions"),
        Path("/app/agent-instructions"),
        Path(os.getcwd()) / "agent-instructions",
        Path(os.getcwd()) / "shared" / "agent-instructions",
    ]
    for c in candidates:
        if c.exists():
            return c
    candidates[0].mkdir(parents=True, exist_ok=True)
    return candidates[0]

def get_latest_season_number() -> int:
    """regulation_*.md または MongoDB から最新シーズン番号を取得する"""
    max_season = 50
    inst_dir = get_instructions_dir()
    if inst_dir.exists():
        for f in inst_dir.glob("regulation_*.md"):
            m = re.match(r"regulation_(\d+)\.md", f.name)
            if m:
                s = int(m.group(1))
                if s > max_season:
                    max_season = s

    # MongoDB からも確認
    try:
        client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=1500)
        db = client[MONGODB_DB]
        doc = db["contest_matches"].find_one(sort=[("season", -1)])
        if doc and "season" in doc and doc["season"] > max_season:
            max_season = doc["season"]
    except Exception:
        pass

    return max_season

def format_date_to_yymmdd(dt: datetime) -> str:
    return dt.strftime("%y/%m/%d")

def update_match_history_csv(
    analysis: Dict[str, Any],
    season: Optional[int] = None,
    dt: Optional[datetime] = None,
    target_file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    対戦結果を MongoDB contest_matches に保存する (旧関数名互換)
    """
    season_num = season or get_latest_season_number()
    target_dt = dt or datetime.now()
    date_str = format_date_to_yymmdd(target_dt)

    opp = analysis.get("opponent", {})
    stages = analysis.get("stages", {})
    s1 = stages.get("stage1", {})
    s2 = stages.get("stage2", {})
    s3 = stages.get("stage3", {})
    match_idx = analysis.get("matchIndex", 1)

    mongo_id = None
    try:
        client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
        db = client[MONGODB_DB]
        col = db["contest_matches"]
        doc = {
            "season": season_num,
            "date": date_str,
            "matchIndex": match_idx,
            "opponent": {
                "name": opp.get("name", "Unknown"),
                "grade": opp.get("grade", 1)
            },
            "stages": {
                "stage1": s1,
                "stage2": s2,
                "stage3": s3
            },
            "overallResult": analysis.get("overallResult", "WIN"),
            "earnedPt": analysis.get("earnedPt", 0),
            "extra": analysis.get("extra", {}),
            "userId": analysis.get("userId", "system"),
            "recordedAt": datetime.now()
        }
        res = col.update_one(
            {"season": season_num, "date": date_str, "matchIndex": match_idx},
            {"$set": doc},
            upsert=True
        )
        mongo_id = str(res.upserted_id) if res.upserted_id else None
    except Exception as e:
        print(f"[match_history_updater] Failed to upsert to MongoDB: {e}")

    new_row = ",".join(map(str, [
        date_str,
        opp.get("name", "Unknown"),
        opp.get("grade", 1),
        s1.get("myScore", 0),
        s1.get("enemyScore", 0),
        s2.get("myScore", 0),
        s2.get("enemyScore", 0),
        s3.get("myScore", 0),
        s3.get("enemyScore", 0),
        analysis.get("overallResult", "WIN"),
        analysis.get("earnedPt", 0),
    ]))

    return {
        "filePath": "MongoDB: contest_matches",
        "updatedLine": new_row,
        "lineIndex": match_idx,
        "season": season_num,
        "mongoId": mongo_id,
    }
