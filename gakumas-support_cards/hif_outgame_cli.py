import json
import os
import sys
import logging
# 必要に応じてpymongoをインポート
# from pymongo import MongoClient

STATE_FILE = "current_state.json"

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

class HIFSessionManager:
    def __init__(self):
        self.state = {
            "week": 1,
            "status": {
                "vo": 100,
                "da": 100,
                "vi": 100,
                "hp": 100
            },
            "deck_id": None,
            "history": []
        }
        # ダミーのスケジュールデータ
        self.schedule = {
            1: {"name": "授業（Da優先）", "predicted": {"da": 15, "hp": -10}},
            2: {"name": "SPレッスン（Vo）", "predicted": {"vo": 40, "hp": -25}},
            3: {"name": "お出かけ", "predicted": {"hp": 30}},
        }

    def load_state(self):
        """ローカルの一時セッション状態を読み込む"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
                logging.info(f"保存されたセッションを読み込みました。第{self.state['week']}週から再開します。")
            except Exception as e:
                logging.error(f"状態ファイルの読み込みに失敗しました: {e}")
                self._initialize_new_state()
        else:
            self._initialize_new_state()

    def save_state(self):
        """現在の状態をローカルに保存する"""
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"状態の保存に失敗しました: {e}")

    def _initialize_new_state(self):
        logging.info("新規セッションを初期化します。")
        self.state["week"] = 1
        self.save_state()

    def fetch_and_lazy_load_memory(self, memory_ids):
        """
        [DB Mock] MongoDBからメモリを取得し、HIF用の拡張領域(produceMemory)がなければLazy Loadする
        """
        logging.info(f"MongoDBからメモリ情報をフェッチしています: {memory_ids}")
        # 疑似的なDBフェッチとLazy Loadのモック
        for mid in memory_ids:
            # db.memories.find_one({"_id": mid}) を想定
            dummy_doc = {"_id": mid} 
            if "produceMemory" not in dummy_doc:
                # HIF用の領域を安全に拡張
                dummy_doc["produceMemory"] = {
                    "unlocked_abilities": [],
                    "hif_level": 1
                }
                # db.memories.update_one({"_id": mid}, {"$set": {"produceMemory": dummy_doc["produceMemory"]}})
                logging.info(f"  -> メモリ {mid} に produceMemory 領域を拡張・初期化しました。")

    def persist_to_mongodb(self):
        """
        [DB Mock] 前編が終了（チェックポイント）した際、hif_sessions コレクションへ正式レコードとして永続化する
        """
        logging.info("前編プレイが完了しました。現在の状態を MongoDB の hif_sessions に永続化保存します。")
        # db.hif_sessions.insert_one(self.state) を想定
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE) # ローカルの進行中データは破棄
        logging.info("永続化が完了しました。in-gameシミュレータ（Node.js）へ引き継ぎます。")


# --- 対話型CUIラッパー関数 ---

def prompt_int(message, allow_modify=True):
    """整数入力を強制する。modifyコマンドを受け付ける場合がある。"""
    while True:
        suffix = " (数値入力, 'modify'で強制上書き): " if allow_modify else " (数値入力): "
        val = input(message + suffix).strip()
        if allow_modify and val.lower() == 'modify':
            return 'modify'
        try:
            return int(val)
        except ValueError:
            print("[エラー] 有効な数値を入力してください。")

def modify_status(manager):
    """任意のタイミングでステータスを直接書き換える"""
    print("\n--- ステータス強制上書きモード ---")
    st = manager.state["status"]
    print(f"現在: Vo={st['vo']}, Da={st['da']}, Vi={st['vi']}, HP={st['hp']}")
    for key in ["vo", "da", "vi", "hp"]:
        val = input(f"{key.upper()} の新しい値 (空白で変更なし): ").strip()
        if val:
            try:
                st[key] = int(val)
            except ValueError:
                print(f"[警告] 無効な入力のため {key.upper()} は変更しませんでした。")
    print("--- 上書き完了 ---")

# --- メインループ ---

def run_cli_loop(manager, max_weeks=3):
    """CLIのメインループ"""
    while manager.state["week"] <= max_weeks:
        week = manager.state["week"]
        st = manager.state["status"]
        
        print(f"\n======================================")
        print(f" 第 {week} 週目  (現在: Vo={st['vo']} Da={st['da']} Vi={st['vi']} HP={st['hp']})")
        print(f"======================================")
        
        # 1. 選択肢と予測表示
        action_info = manager.schedule.get(week, {"name": "自由行動", "predicted": {}})
        print(f"[行動予定] {action_info['name']}")
        
        pred_text = ", ".join([f"{k.upper()}{'+' if v>0 else ''}{v}" for k, v in action_info["predicted"].items()])
        print(f"[予測変動] {pred_text if pred_text else '変動なし'}")
        print("--------------------------------------")
        
        # 2. 実績値の入力 & 3. ズレの修正（modify）
        print("ゲーム内で行動を実行し、結果を入力してください。")
        
        while True:
            cmd = prompt_int(f"上昇したVo (目安: {action_info['predicted'].get('vo', 0)})", allow_modify=True)
            if cmd == 'modify':
                modify_status(manager)
                # 上書き後、入力フローをリセット
                continue
            
            diff_vo = cmd
            
            cmd = prompt_int(f"上昇したDa (目安: {action_info['predicted'].get('da', 0)})", allow_modify=True)
            if cmd == 'modify':
                modify_status(manager); continue
            diff_da = cmd
            
            cmd = prompt_int(f"上昇したVi (目安: {action_info['predicted'].get('vi', 0)})", allow_modify=True)
            if cmd == 'modify':
                modify_status(manager); continue
            diff_vi = cmd
            
            cmd = prompt_int(f"変動したHP (目安: {action_info['predicted'].get('hp', 0)}, 減少はマイナス)", allow_modify=True)
            if cmd == 'modify':
                modify_status(manager); continue
            diff_hp = cmd
            
            # 入力がすべて正常に通った場合、ステータスを更新してループを抜ける
            manager.state["status"]["vo"] += diff_vo
            manager.state["status"]["da"] += diff_da
            manager.state["status"]["vi"] += diff_vi
            manager.state["status"]["hp"] += diff_hp
            
            # 履歴の記録
            manager.state["history"].append({
                "week": week,
                "action": action_info["name"],
                "diff": {"vo": diff_vo, "da": diff_da, "vi": diff_vi, "hp": diff_hp}
            })
            break

        # 4. 確定・次週へ
        print(f"\n[確定] 第{week}週を終了しました。状態を保存します。")
        manager.state["week"] += 1
        manager.save_state()

    print("\n全スケジュール（前編）が完了しました！")
    manager.persist_to_mongodb()


if __name__ == "__main__":
    print(">>> [TEST MODE] スタンドアロン実行テストを開始します <<<")
    
    # 既存のテスト用データがあればクリアして新規スタート
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        
    app = HIFSessionManager()
    app.load_state()
    
    # 疑似的なDBからのLazy Loadingテスト
    app.fetch_and_lazy_load_memory(["mem_dummy_001", "mem_dummy_002"])
    
    # 標準入力をモックして2週分のスケジュールを自動テスト
    # week 1: Vo=0, Da=15, Vi=0, HP=-10 を入力
    # week 2: modify を呼び出して手動上書き -> その後 Vo=42, Da=0, Vi=0, HP=-25 を入力
    import io
    test_inputs = [
        "0", "15", "0", "-10",  # Week 1
        "modify", "120", "", "", "100", # Week 2: modify 実行 (Vo=120, HP=100 に上書き)
        "42", "0", "0", "-25",  # Week 2: その後の実績入力
        "0", "0", "0", "30"     # Week 3
    ]
    
    original_stdin = sys.stdin
    sys.stdin = io.StringIO("\n".join(test_inputs) + "\n")
    
    try:
        run_cli_loop(app, max_weeks=3)
    finally:
        sys.stdin = original_stdin
        
    print("\n>>> テスト完了。生成された current_state.json を確認してください <<<")
