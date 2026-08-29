"""
match_history_updater.py — コンテスト対戦結果を match_history_XX.csv に自動登録・更新するモジュール
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

WORKSPACE_DIR = Path("/root/gakumas-workspace")

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
    """既存の match_history_XX.csv から最新シーズン番号を取得する"""
    inst_dir = get_instructions_dir()
    if not inst_dir.exists():
        return 50

    max_season = 50
    for f in inst_dir.glob("match_history_*.csv"):
        m = re.match(r"match_history_(\d+)\.csv", f.name)
        if m:
            s = int(m.group(1))
            if s > max_season:
                max_season = s
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
    解析結果を match_history_XX.csv に書き込み・更新する
    """
    season_num = season or get_latest_season_number()
    target_dt = dt or datetime.now()
    date_str = format_date_to_yymmdd(target_dt)

    if target_file_path:
        csv_path = Path(target_file_path)
    else:
        csv_path = get_instructions_dir() / f"match_history_{season_num}.csv"

    if not csv_path.exists():
        # ファイルがない場合はヘッダー付きで新規作成
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("日付,相手名,メモ,自S1,敵S1,自S2,敵S2,自S3,敵S3,結果,獲得Pt\n")

    with open(csv_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()

    # 新しい行データを作成
    # ヘッダー形式: 日付,相手名,メモ,自S1,敵S1,自S2,敵S2,自S3,敵S3,結果,獲得Pt
    opp = analysis.get("opponent", {})
    stages = analysis.get("stages", {})
    s1 = stages.get("stage1", {})
    s2 = stages.get("stage2", {})
    s3 = stages.get("stage3", {})

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

    # 対象日付の既存行を探す
    matching_indices = [i for i, line in enumerate(lines) if line.startswith(f"{date_str},")]

    match_idx = analysis.get("matchIndex", 1)
    if matching_indices:
        # matchIndex (1〜5) に対応するインデックス
        offset = max(0, min(len(matching_indices) - 1, match_idx - 1))
        target_line_index = matching_indices[offset]
        lines[target_line_index] = new_row
    else:
        lines.append(new_row)
        target_line_index = len(lines) - 1

    # 保存
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return {
        "filePath": str(csv_path),
        "updatedLine": new_row,
        "lineIndex": target_line_index,
        "season": season_num,
    }
