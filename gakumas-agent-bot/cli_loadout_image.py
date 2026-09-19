#!/usr/bin/env python3
"""
cli_loadout_image.py — 実走シミュレーション結果（loadouts）画像生成 CLI

指定したステージ・アイドル（または最新の全アイドル）の実走編成から
インフォグラフィック画像を生成・保存する。
"""

import argparse
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

from loadout_image_builder import LoadoutImageBuilder
from advisory_parser import IDOL_NAME_TO_KEY, IDOL_KEY_MAP

def get_latest_loadout(stage: int, idol_key: str, mongo_uri: str = "mongodb://192.168.100.4:27017") -> dict | None:
    from pymongo import MongoClient
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
    db = client["gakumas-tools"]

    idol_id_map = {
        "saki": 1, "temari": 2, "kotone": 3, "tsubame": 4, "mao": 5,
        "lilja": 6, "china": 7, "sumika": 8, "hiro": 9, "sena": 10,
        "misuzu": 11, "ume": 12, "rinami": 13
    }
    # DB上の idolId (0-based または 1-based の突合)
    # hiro は derived.idolId: 8
    target_name = IDOL_KEY_MAP.get(idol_key, idol_key)

    # stageId の解決 (シーズン52基準: 181, 182, 183)
    stage_id = 180 + stage if stage in (1, 2, 3) else stage

    # 1. derived.idolId または 名前 で最新を検索
    query = {"stageId": stage_id}
    docs = list(db["loadouts"].find(query).sort([("stats.median", -1), ("createdAt", -1)]))

    # アイドル名でフィルタ
    matched_doc = None
    for d in docs:
        pidol_id = d.get("derived", {}).get("pIdolId")
        # pIdol から名前を突合
        builder = LoadoutImageBuilder()
        pinfo = builder._get_pidol_info(pidol_id)
        if pinfo.get("idol_name") == target_name or target_name in pinfo.get("idol_name", ""):
            matched_doc = d
            break

    if not matched_doc and docs:
        matched_doc = docs[0]

    if matched_doc:
        # メモリー名の照合補完
        groups = matched_doc.get("skillCardIdGroups", [])
        if len(groups) > 0:
            m_cards = groups[0]
            main_mem = db["memories"].find_one({"skillCardIds": m_cards})
            if main_mem:
                matched_doc["mainMemoryName"] = main_mem.get("name")
        if len(groups) > 1:
            s_cards = groups[1]
            sub_mem = db["memories"].find_one({"skillCardIds": s_cards})
            if sub_mem:
                matched_doc["subMemoryName"] = sub_mem.get("name")

    return matched_doc


def main():
    parser = argparse.ArgumentParser(description="実走シミュレーション結果（loadouts）インフォグラフィック画像生成")
    parser.add_argument("--stage", type=int, default=3, help="ステージ番号 (1, 2, 3)")
    parser.add_argument("--idol", type=str, default="hiro", help="アイドル名またはキー (例: hiro, temari, saki)")
    parser.add_argument("--columns", type=int, default=2, choices=[1, 2], help="カラム数 (1: スマホ縦型, 2: ワイドグリッド)")
    parser.add_argument("--output", "-o", type=str, default=None, help="出力先画像パス (PNG)")
    parser.add_argument("--mongo-uri", type=str, default="mongodb://192.168.100.4:27017")

    args = parser.parse_args()

    idol_key = IDOL_NAME_TO_KEY.get(args.idol, args.idol.lower())
    doc = get_latest_loadout(args.stage, idol_key, mongo_uri=args.mongo_uri)

    if not doc:
        print(f"Error: Stage {args.stage} の {args.idol} に関するロードアウトが見つかりませんでした。", file=sys.stderr)
        sys.exit(1)

    builder = LoadoutImageBuilder()

    out_path = Path(args.output) if args.output else Path(f"loadout_s{args.stage}_{idol_key}_col{args.columns}.png")
    builder.build(doc, columns=args.columns, output_path=out_path)
    print(f"Generated loadout image: {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

