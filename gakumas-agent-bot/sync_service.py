"""
sync_service.py — 学園アイドルマスター 各種データ同期サービス

機能:
1. inventory: Googleスプレッドシート ➔ MongoDB (Pアイドル & サポートカードの所持・育成状況インポート)
2. support:   Seesaa Wiki ➔ サポートカードマスタ / MongoDB (新規サポカの自動スクレイピング・DSL変換・マスタ更新)
3. sheet:     MongoDB ➔ Googleスプレッドシート (所持サポートカード & メモリーのエクスポート)
"""

import asyncio
import html
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pymongo import MongoClient

log = logging.getLogger("gakumas_sync")

def _find_dir(candidates: list[Path]) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]

WORKSPACE_ROOT = _find_dir([
    Path("/app"),
    Path("/root/gakumas-workspace"),
    Path(__file__).resolve().parent.parent,
])
OG_TOOLS_DIR = _find_dir([
    WORKSPACE_ROOT / "gakumas-og-tools",
    Path("/app/gakumas-og-tools"),
    Path("/root/gakumas-workspace/gakumas-og-tools"),
])
OG_TOOLS_SCRIPTS = OG_TOOLS_DIR / "scripts"
SUPPORT_CARDS_MASTER_PATH = _find_dir([
    OG_TOOLS_DIR / "support_cards_master.json",
    Path("/app/support_cards_master.json"),
    Path("/root/gakumas-workspace/gakumas-og-tools/support_cards_master.json"),
])
P_IDOLS_JSON_PATH = _find_dir([
    WORKSPACE_ROOT / "gakumas-tools" / "packages" / "gakumas-data" / "json" / "p_idols.json",
    WORKSPACE_ROOT / "packages" / "gakumas-data" / "json" / "p_idols.json",
    Path("/app/packages/gakumas-data/json/p_idols.json"),
])
IDOLS_JSON_PATH = _find_dir([
    WORKSPACE_ROOT / "gakumas-tools" / "packages" / "gakumas-data" / "json" / "idols.json",
    WORKSPACE_ROOT / "packages" / "gakumas-data" / "json" / "idols.json",
    Path("/app/packages/gakumas-data/json/idols.json"),
])
SKILL_CARDS_JSON_PATH = _find_dir([
    WORKSPACE_ROOT / "gakumas-tools" / "packages" / "gakumas-data" / "json" / "skill_cards.json",
    WORKSPACE_ROOT / "packages" / "gakumas-data" / "json" / "skill_cards.json",
    Path("/app/packages/gakumas-data/json/skill_cards.json"),
])


def _is_owned_val(val: Any) -> bool:
    if not val:
        return False
    v = str(val).strip().lower()
    return v in ["true", "1", "○", "◯", "所持", "yes", "y", "ok", "checked"]



def _parse_int(val: Any, default: int = 0) -> int:
    if not val:
        return default
    clean = re.sub(r"\D", "", str(val).strip())
    return int(clean) if clean.isdigit() else default


class GakumasSyncService:
    def __init__(self, mongo_uri: str = "mongodb://192.168.100.4:27017", mongo_db: str = "gakumas-tools"):
        self.mongo_uri = os.environ.get("MONGODB_URI", mongo_uri)
        self.mongo_db_name = os.environ.get("MONGODB_DB", mongo_db)
        self.sheet_id = os.environ.get("SYNC_SHEET_ID", "1MPHcaLbZcTNxjFFaSKBmKWkRqRqOn-YDVrdInPLDcOQ")

    def _get_db(self):
        client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
        return client[self.mongo_db_name]

    def _get_oauth_token(self) -> str:
        """gakumas-og-tools 側のトークン取得スクリプトを実行してアクセストークンを取得"""
        token_path = os.path.expanduser("~/.config/gakumas-tools/sheets_tokens.json")
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                access_token = data.get("access_token")
                refresh_token = data.get("refresh_token")
                client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
                client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
                if refresh_token and client_id and client_secret:
                    try:
                        url = "https://oauth2.googleapis.com/token"
                        pdata = urllib.parse.urlencode({
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "refresh_token": refresh_token,
                            "grant_type": "refresh_token"
                        }).encode("utf-8")
                        req = urllib.request.Request(url, data=pdata, method="POST")
                        with urllib.request.urlopen(req) as resp:
                            res_json = json.loads(resp.read().decode("utf-8"))
                            new_token = res_json.get("access_token")
                            if new_token:
                                data["access_token"] = new_token
                                with open(token_path, "w", encoding="utf-8") as out_f:
                                    json.dump(data, out_f, indent=2)
                                return new_token
                    except Exception as e:
                        log.warning("Token refresh failed: %s", e)
                if access_token:
                    return access_token
        raise RuntimeError("Google Sheets OAuth トークンが見つかりません。~/.config/gakumas-tools/sheets_tokens.json を確認してください。")

    def _fetch_sheet_rows(self, sheet_name: str, access_token: str) -> List[List[str]]:
        encoded_sheet = urllib.parse.quote(sheet_name)
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.sheet_id}/values/{encoded_sheet}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("values", [])

    # ─────────────────────────────────────────────────────────────────────────
    # 1. /sync inventory: スプレッドシート ➔ MongoDB (インベントリ同期)
    # ─────────────────────────────────────────────────────────────────────────

    def sync_inventory_sync(self) -> Dict[str, Any]:
        """
        スプレッドシート (P-Idols, Support-Cards) ➔ MongoDB (owned_p_idols, owned_support_cards)
        """
        token = self._get_oauth_token()
        db = self._get_db()
        results: Dict[str, Any] = {
            "p_idols": {"inserted": 0, "updated": 0, "deleted": 0, "details": []},
            "support_cards": {"inserted": 0, "updated": 0, "deleted": 0, "details": []},
        }

        # ── 1-A. Support-Cards 同期 (gakumas-og-tools の sync_support_cards.py をサブプロセス実行) ──
        log.info("[Sync Inventory] Support-Cards 同期中 (sync_support_cards.py --import --execute)...")
        cmd_sc = [sys.executable, str(OG_TOOLS_SCRIPTS / "sync_support_cards.py"), "--import", "--execute"]
        proc_sc = subprocess.run(cmd_sc, cwd=str(OG_TOOLS_DIR), capture_output=True, text=True)
        if proc_sc.returncode != 0:
            log.error("[Sync Inventory] Support-Cards 同期エラー: %s", proc_sc.stderr)
            raise RuntimeError(f"Support-Cards の同期に失敗しました: {proc_sc.stderr[:300]}")

        # 出力ログからサマリーをパース
        sc_out = proc_sc.stdout
        m_ins = re.search(r"Inserted \(New owned\):\s*(\d+)", sc_out)
        m_upd = re.search(r"Updated \(Level/Uncap changes\):\s*(\d+)", sc_out)
        m_del = re.search(r"Deleted \(Unowned/Removed\):\s*(\d+)", sc_out)
        results["support_cards"]["inserted"] = int(m_ins.group(1)) if m_ins else 0
        results["support_cards"]["updated"] = int(m_upd.group(1)) if m_upd else 0
        results["support_cards"]["deleted"] = int(m_del.group(1)) if m_del else 0

        # 詳細ログ行を抽出
        for line in sc_out.splitlines():
            line_str = line.strip()
            if line_str.startswith("+ 【") or line_str.startswith("* 【") or line_str.startswith("- 【"):
                results["support_cards"]["details"].append(line_str)

        # ── 1-B. P-Idols 同期 ──
        log.info("[Sync Inventory] P-Idols 同期中...")
        p_idols_master = {}
        if P_IDOLS_JSON_PATH.exists():
            with open(P_IDOLS_JSON_PATH, encoding="utf-8") as f:
                p_idols_master = {str(p["id"]): p for p in json.load(f)}

        idols_master = {}
        if IDOLS_JSON_PATH.exists():
            with open(IDOLS_JSON_PATH, encoding="utf-8") as f:
                idols_master = {str(i["id"]): i["name"] for i in json.load(f)}

        skill_cards_master = {}
        if SKILL_CARDS_JSON_PATH.exists():
            with open(SKILL_CARDS_JSON_PATH, encoding="utf-8") as f:
                skill_cards_master = {sc["id"]: sc for sc in json.load(f)}

        pidol_rows = self._fetch_sheet_rows("P-Idols", token)
        if pidol_rows:
            headers = [h.strip().lower() for h in pidol_rows[0]]
            id_idx = headers.index("id") if "id" in headers else 0
            owned_idx = headers.index("is_owned") if "is_owned" in headers else (headers.index("所持") if "所持" in headers else 4)
            awaken_idx = headers.index("awaken_level") if "awaken_level" in headers else (headers.index("才能開花") if "才能開花" in headers else 5)
            talent_idx = headers.index("talent_level") if "talent_level" in headers else (headers.index("特訓") if "特訓" in headers else 6)

            col_pi = db["owned_p_idols"]
            for row in pidol_rows[1:]:
                if len(row) <= id_idx:
                    continue
                pid_str = row[id_idx].strip()
                if not pid_str.isdigit():
                    continue
                pid_int = int(pid_str)

                is_owned = _is_owned_val(row[owned_idx]) if len(row) > owned_idx else False
                awaken_lv = _parse_int(row[awaken_idx], 1) if len(row) > awaken_idx else 1
                talent_lv = _parse_int(row[talent_idx], 1) if len(row) > talent_idx else 1

                m_data = p_idols_master.get(pid_str, {})
                idol_id_str = str(m_data.get("idolId", ""))
                idol_name = idols_master.get(idol_id_str, m_data.get("name", ""))
                title = m_data.get("title", "")
                rarity = m_data.get("rarity", "")
                plan = m_data.get("plan", "")
                recommended_effect = m_data.get("recommendedEffect", "")

                card_ids = m_data.get("skillCardIds", [])
                p_skill_cards = [skill_cards_master[cid] for cid in card_ids if cid in skill_cards_master]

                existing = col_pi.find_one({"_id": pid_str})

                if is_owned:
                    doc = {
                        "_id": pid_str,
                        "id": pid_int,
                        "idolId": int(idol_id_str) if idol_id_str.isdigit() else 0,
                        "idol_name": idol_name,
                        "title": title,
                        "rarity": rarity,
                        "plan": plan,
                        "recommendedEffect": recommended_effect,
                        "awaken_level": awaken_lv,
                        "talent_level": talent_lv,
                        "skill_cards": p_skill_cards,
                        "updatedAt": datetime.now(timezone.utc),
                    }
                    if existing:
                        old_awaken = existing.get("awaken_level", 1)
                        old_talent = existing.get("talent_level", 1)
                        if old_awaken != awaken_lv or old_talent != talent_lv:
                            col_pi.update_one({"_id": pid_str}, {"$set": doc})
                            results["p_idols"]["updated"] += 1
                            results["p_idols"]["details"].append(
                                f"🔄 `{idol_name}【{title}】` (★{old_awaken}➔{awaken_lv}, 特訓Lv.{old_talent}➔{talent_lv})"
                            )
                    else:
                        col_pi.insert_one(doc)
                        results["p_idols"]["inserted"] += 1
                        results["p_idols"]["details"].append(
                            f"✨ `{idol_name}【{title}】` (★{awaken_lv}, 特訓Lv.{talent_lv})"
                        )
                else:
                    if existing:
                        col_pi.delete_one({"_id": pid_str})
                        results["p_idols"]["deleted"] += 1
                        results["p_idols"]["details"].append(
                            f"🗑️ `{idol_name}【{title}】` (所持解除)"
                        )

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # 2. /sync support: Seesaa Wiki ➔ サポートカードマスタ / MongoDB
    # ─────────────────────────────────────────────────────────────────────────

    def sync_support_sync(self, force: bool = False) -> Dict[str, Any]:
        """
        Seesaa Wiki ➔ support_cards_master.json & Google Sheets (Support-Cards)
        """
        log.info("[Sync Support] Seesaa Wiki 同期パイプライン実行中 (sync_wiki_support_cards.py)...")
        cmd = [sys.executable, str(OG_TOOLS_SCRIPTS / "sync_wiki_support_cards.py"), "--no-discord"]
        if force:
            cmd.append("--force")

        proc = subprocess.run(cmd, cwd=str(OG_TOOLS_DIR), capture_output=True, text=True)
        if proc.returncode != 0:
            log.error("[Sync Support] エラー: %s", proc.stderr)
            raise RuntimeError(f"サポートカード同期に失敗しました: {proc.stderr[:300]}")

        out = proc.stdout
        # 検出サマリーの抽出
        total_wiki = 0
        m_tot = re.search(r"Wiki一覧カード総数\s*:\s*(\d+)", out)
        if m_tot:
            total_wiki = int(m_tot.group(1))

        new_count = 0
        m_new = re.search(r"新規検出カード数\s*:\s*(\d+)", out)
        if m_new:
            new_count = int(m_new.group(1))

        new_cards_list = []
        for line in out.splitlines():
            line_str = line.strip()
            if line_str.startswith("+ 【"):
                new_cards_list.append(line_str)

        return {
            "total_wiki_cards": total_wiki,
            "new_cards_count": new_count,
            "new_cards_details": new_cards_list,
            "raw_log": out[-500:],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 3. /sync sheet: MongoDB ➔ Googleスプレッドシート
    # ─────────────────────────────────────────────────────────────────────────

    def sync_sheet_sync(self) -> Dict[str, Any]:
        """
        MongoDB (owned_support_cards, memories) ➔ Googleスプレッドシート (Support-Cards, Memories)
        """
        log.info("[Sync Sheet] サポートカードをスプレッドシートへエクスポート中...")
        cmd_sc = [sys.executable, str(OG_TOOLS_SCRIPTS / "sync_support_cards.py"), "--export", "--execute"]
        proc_sc = subprocess.run(cmd_sc, cwd=str(OG_TOOLS_DIR), capture_output=True, text=True)
        if proc_sc.returncode != 0:
            log.warning("Support-Cards エクスポート警告: %s", proc_sc.stderr)

        log.info("[Sync Sheet] メモリーをスプレッドシートへエクスポート中...")
        cmd_mem = [sys.executable, str(OG_TOOLS_SCRIPTS / "sheets_sync.py"), "--execute"]
        proc_mem = subprocess.run(cmd_mem, cwd=str(OG_TOOLS_DIR), capture_output=True, text=True)
        if proc_mem.returncode != 0:
            log.warning("Memories エクスポート警告: %s", proc_mem.stderr)

        mem_out = proc_mem.stdout
        m_add = re.search(r"Added Rows\s*:\s*(\d+)", mem_out) or re.search(r"inserted to top\.\s*(\d+)", mem_out)
        m_upd = re.search(r"Updated Rows\s*:\s*(\d+)", mem_out) or re.search(r"(\d+)\s*OIDs filled", mem_out)
        m_tot = re.search(r"Total Rows\s*:\s*(\d+)", mem_out) or re.search(r"Total\s*(\d+)\s*data rows", mem_out)

        return {
            "support_cards": "Support-Cards タブを最新データで更新完了",
            "memories_raw": mem_out[-400:],
            "mem_added": int(m_add.group(1)) if m_add else 0,
            "mem_updated": int(m_upd.group(1)) if m_upd else 0,
            "mem_total": int(m_tot.group(1)) if m_tot else 0,
        }

    # ── 非同期ラッパー ──

    async def sync_inventory(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self.sync_inventory_sync)

    async def sync_support(self, force: bool = False) -> Dict[str, Any]:
        return await asyncio.to_thread(self.sync_support_sync, force)

    async def sync_sheet(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self.sync_sheet_sync)
