#!/usr/bin/env python3
"""
cli_get_advisory.py — あじふらい氏推奨構成データをJSON形式で出力するCLI
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

from advisory_parser import parse_advisory

def main():
    parser = argparse.ArgumentParser(description="Get advisory data as JSON")
    parser.add_argument("--stage", type=int, required=True, help="Stage number (1, 2, 3)")
    parser.add_argument("--idol", type=str, required=True, help="Idol name or query")
    parser.add_argument("--season", type=int, default=None, help="Season number (optional)")

    args = parser.parse_args()

    data = parse_advisory(stage=args.stage, idol_query=args.idol, season=args.season)
    if not data:
        print(json.dumps({
            "success": False,
            "error": f"No advisory data found for Stage {args.stage} and idol '{args.idol}'"
        }, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps({
        "success": True,
        "data": data
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
