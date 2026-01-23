import os
import pytz

# --- 1. 環境変数のバリデーション ---
TARGET_ID = os.getenv("TARGET_PLAYER_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TARGET_ID or not DATABASE_URL:
    print("❌ エラー: 環境変数が不足しています。")
    ENV_ERROR = True
else:
    ENV_ERROR = False

# --- 2. 基本設定 ---
JST = pytz.timezone('Asia/Tokyo')
COOKIE_PATH = "./auth/local_cookies.json"
FULL_SCREENSHOT_PATH = "./debug_full_screen.png"
LOG_FILE = "scraper.log"

# カラムコメントリスト
COLUMN_COMMENTS = [
    ("player_stats.user_id", "バックラーのユーザーID"), ("player_stats.recorded_at", "データ取得日"),
    ("player_stats.d_parry_pct", "使用率：ドライブパリィ"), ("player_stats.d_impact_pct", "使用率：ドライブインパクト"),
    ("player_stats.d_od_pct", "使用率：オーバードライブアーツ"), ("player_stats.d_rush_p_pct", "使用率：パリィドライブラッシュ"),
    ("player_stats.d_rush_c_pct", "使用率：キャンセルドライブラッシュ"), ("player_stats.d_reversal_pct", "使用率：ドライブリバーサル"),
    ("player_stats.sa1_pct", "使用率：SA1"), ("player_stats.sa2_pct", "使用率：SA2"), ("player_stats.sa3_pct", "使用率：SA3"), ("player_stats.ca_pct", "使用率：CA"),
    ("player_stats.impact_win", "インパクト：決めた(平均)"), ("player_stats.impact_pc_win", "インパクト：パニカン成功(平均)"),
    ("player_stats.impact_counter_win", "インパクト：返し成功(平均)"), ("player_stats.impact_lose", "インパクト：受けた(平均)"),
    ("player_stats.impact_pc_lose", "インパクト：パニカン被弾(平均)"), ("player_stats.impact_counter_lose", "インパクト：返し失敗(平均)"),
    ("player_stats.just_parry_count", "ジャストパリィ成功回数(平均)"), ("player_stats.throw_win", "投げ：決めた(平均)"),
    ("player_stats.throw_lose", "投げ：受けた(平均)"), ("player_stats.throw_escape", "投げ：投げ抜け(平均)"),
    ("player_stats.stun_win", "スタン：させた(平均)"), ("player_stats.stun_lose", "スタン：させられた(平均)"),
    ("player_stats.wall_push_sec", "壁際：追い詰めている秒数(平均)"), ("player_stats.wall_pushed_sec", "壁際：追い詰められている秒数(平均)"),
    ("battle_results.battle_id", "試合固有ID"), ("battle_results.played_at", "試合日時"), ("battle_results.mode", "モード"),
    ("battle_results.p1_name", "P1：名前"), ("battle_results.p1_char", "P1：キャラ"), ("battle_results.p1_mr", "P1：MR/LP"),
    ("battle_results.p1_control", "P1：操作"), ("battle_results.p1_result", "P1：結果"),
    ("battle_results.p2_name", "P2：名前"), ("battle_results.p2_char", "P2：キャラ"), ("battle_results.p2_mr", "P2 : MR/LP"),
    ("battle_results.p2_control", "P2 : 操作"), ("battle_results.p2_result", "P2 : 結果")
]