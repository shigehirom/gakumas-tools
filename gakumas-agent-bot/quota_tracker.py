"""
quota_tracker.py — Gemini API 利用量・クォータ追跡モジュール

1日のリクエスト回数、消費トークン数（プロンプト・生成）、クォータ残量を追跡・永続化する。
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("quota_tracker")

USAGE_FILE = Path(__file__).resolve().parent / "data" / "quota_usage.json"
DAILY_RPD_LIMIT = 1500  # Gemini 3.6 Flash Free Tier 1日あたり目安リクエスト数


BOT_VERSION = "2026.09.01-v1"



class QuotaTracker:
    def __init__(self, usage_file: Path = USAGE_FILE, rpd_limit: int = DAILY_RPD_LIMIT):
        self.usage_file = usage_file
        self.rpd_limit = rpd_limit
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _today_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _load(self) -> dict[str, Any]:
        if self.usage_file.exists():
            try:
                with open(self.usage_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.warning(f"[QuotaTracker] データ読み込み失敗: {e}")
        return {}

    def _save(self) -> None:
        try:
            with open(self.usage_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"[QuotaTracker] データ保存失敗: {e}")

    def record_usage(self, prompt_tokens: int = 0, candidate_tokens: int = 0, duration_sec: float = 0.0) -> dict[str, Any]:
        """Gemini API 呼び出しを1件記録し、本日の集計結果を返す"""
        today = self._today_key()
        if today not in self._data:
            self._data[today] = {
                "requests": 0,
                "prompt_tokens": 0,
                "candidate_tokens": 0,
                "total_tokens": 0,
            }

        day_stats = self._data[today]
        day_stats["requests"] += 1
        day_stats["prompt_tokens"] += prompt_tokens
        day_stats["candidate_tokens"] += candidate_tokens
        day_stats["total_tokens"] += (prompt_tokens + candidate_tokens)
        day_stats["last_updated"] = datetime.now().isoformat()

        self._save()
        return self.get_today_stats()

    def get_today_stats(self) -> dict[str, Any]:
        """本日の利用統計を取得"""
        today = self._today_key()
        day_stats = self._data.get(today, {
            "requests": 0,
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "total_tokens": 0,
        })
        requests = day_stats["requests"]
        remaining = max(0, self.rpd_limit - requests)
        pct_used = min(100.0, (requests / self.rpd_limit) * 100) if self.rpd_limit > 0 else 0.0

        return {
            "date": today,
            "requests": requests,
            "limit": self.rpd_limit,
            "remaining": remaining,
            "percent_used": pct_used,
            "prompt_tokens": day_stats.get("prompt_tokens", 0),
            "candidate_tokens": day_stats.get("candidate_tokens", 0),
            "total_tokens": day_stats.get("total_tokens", 0),
        }

    def format_footer(self, duration_sec: float = 0.0, tokens: int = 0, tool_count: int = 0, model_label: str = "Gemini 3.6 Flash") -> str:
        """Discord メッセージ末尾用の軽量フッター文字列を生成"""
        stats = self.get_today_stats()
        reqs = stats["requests"]
        limit = stats["limit"]
        remaining_pct = max(0.0, 100.0 - stats["percent_used"])

        tc_str = f" ｜ 🔍 ツール: {tool_count}回" if tool_count > 0 else ""
        tok_str = f" ｜ 🪙 {tokens} tok" if tokens > 0 else ""
        time_str = f" ｜ ⏱️ {duration_sec:.1f}s" if duration_sec > 0 else ""

        return (
            f"\n\n`👩‍🏫 あさり先生 ({model_label}){tc_str} ｜ "
            f"📊 本日: {reqs}/{limit}回 (残 {remaining_pct:.1f}%){tok_str}{time_str} ｜ v{BOT_VERSION}`"
        )



# グローバルシングルトン
quota_tracker = QuotaTracker()
