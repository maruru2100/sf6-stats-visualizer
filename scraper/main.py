import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from playwright.sync_api import sync_playwright
import datetime
import time
import os
import sys
import pytz
import random
import threading

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
engine = create_engine(DATABASE_URL) if not ENV_ERROR else None
COOKIE_PATH = "./auth/local_cookies.json"
FULL_SCREENSHOT_PATH = "./debug_full_screen.png"
LOG_FILE = "scraper.log"

def get_now_jst():
    return datetime.datetime.now(JST)

def write_log(message):
    now = get_now_jst().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{now}] {message}"
    print(formatted_msg)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(formatted_msg + "\n")
    except:
        pass
    if "log_messages" not in st.session_state:
        st.session_state.log_messages = ""
    st.session_state.log_messages += formatted_msg + "\n"

def init_db():
    if ENV_ERROR: return
    with engine.connect() as conn:
        # 戦績テーブル
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS battle_results (
                id SERIAL PRIMARY KEY, 
                battle_id TEXT UNIQUE, 
                played_at TIMESTAMP, 
                mode TEXT,
                p1_name TEXT, p1_char TEXT, p1_mr INTEGER, p1_control TEXT, p1_result TEXT,
                p2_name TEXT, p2_char TEXT, p2_mr INTEGER, p2_control TEXT, p2_result TEXT
            );
        """))
        # 設定保存用テーブル（スケジュール時間を保存）
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scraper_config (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """))
        # 初回のみデフォルト時間を投入
        conn.execute(text("""
            INSERT INTO scraper_config (key, value) 
            VALUES ('run_times', '09:00,21:00')
            ON CONFLICT (key) DO NOTHING;
        """))
        conn.commit()

# --- 3. 解析ロジック (変更なし) ---
def scrape_sf6(user_code, max_pages=5):
    if not user_code:
        write_log("❌ エラー: ユーザーIDが指定されていません。")
        return False

    target_url = f"https://www.streetfighter.com/6/buckler/ja-jp/profile/{user_code}/battlelog/rank#profile_nav"
    write_log(f"🚀 スクレイピング開始 (ID: {user_code}, 遡り: {max_pages}ページ)")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = browser.new_context(
            storage_state=COOKIE_PATH, viewport={'width': 1280, 'height': 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36", locale="ja-JP"
        )
        page = context.new_page()
        all_found_data = []

        try:
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)
            # Cookiebotポップアップ排除
            page.evaluate("""() => {
                const ids = ['#CybotCookiebotDialog', '#CybotCookiebotDialogBodyUnderlay'];
                ids.forEach(id => {
                    const el = document.querySelector(id);
                    if (el) el.remove();
                });
                document.body.style.overflow = 'auto'; 
            }""")
            
            for current_p in range(1, max_pages + 1):
                write_log(f"📑 {current_p}ページ目をスキャン中...")
                time.sleep(2)
                
                page_data = page.evaluate("""
                    () => {
                        const results = [];
                        const items = document.querySelectorAll('li[data-index]');
                        items.forEach((item) => {
                            try {
                                const getPlayerInfo = (sideNum) => {
                                    const pClass = 'battle_data_player' + sideNum;
                                    const parent = item.querySelector(`[class*="${pClass}"]`);
                                    const namePart = item.querySelector(`[class*="battle_data_name_p${sideNum}"]`);
                                    const name = namePart?.innerText.trim() || "Unknown";
                                    const mrText = parent?.querySelector('[class*="battle_data_lp"]')?.innerText || "0";
                                    const mr = parseInt(mrText.replace(/[^0-9]/g, "")) || 0;
                                    const charImg = parent?.querySelector('[class*="battle_data_character"] img');
                                    const charName = charImg?.getAttribute('alt') || "Unknown";
                                    const ctrlImg = parent?.querySelector('[class*="battle_data_control"] img')?.getAttribute('src') || "";
                                    const control = ctrlImg.includes('type0') ? 'Classic' : 'Modern';
                                    const result = item.querySelector(`[class*="battle_data_player_${sideNum}"]`)?.innerText.trim() || "";
                                    return { name, mr, charName, control, result };
                                };
                                const p1 = getPlayerInfo(1);
                                const p2 = getPlayerInfo(2);
                                const dateStr = item.querySelector('[class*="battle_data_date"]')?.innerText.trim();
                                if (dateStr) {
                                    results.push({
                                        id: "rank_" + dateStr.replace(/[^0-9]/g, "") + "_" + p1.name + "_" + p2.name,
                                        date: dateStr, p1, p2
                                    });
                                }
                            } catch (e) {}
                        });
                        return results;
                    }
                """)
                
                if page_data:
                    all_found_data.extend(page_data)
                    write_log(f"✅ {current_p}ページ目: {len(page_data)}件取得")

                if current_p < max_pages:
                    next_btn = page.locator("li.next:not(.disabled)").first
                    if next_btn.is_visible():
                        next_btn.click()
                        page.wait_for_load_state("networkidle")
                        time.sleep(random.uniform(3.0, 5.0))
                    else:
                        break

            new_count = 0
            if all_found_data and not ENV_ERROR:
                with engine.connect() as conn:
                    for item in all_found_data:
                        dt = datetime.datetime.strptime(item['date'], "%Y/%m/%d %H:%M")
                        res = conn.execute(text("""
                            INSERT INTO battle_results (
                                battle_id, played_at, mode, p1_name, p1_char, p1_mr, p1_control, p1_result, p2_name, p2_char, p2_mr, p2_control, p2_result
                            )
                            VALUES (:bid, :pat, :mode, :p1n, :p1c, :p1m, :p1ctrl, :p1r, :p2n, :p2c, :p2m, :p2ctrl, :p2r)
                            ON CONFLICT (battle_id) DO NOTHING
                        """), {
                            "bid": item['id'], "pat": dt, "mode": "RankMatch",
                            "p1n": item['p1']['name'], "p1c": item['p1']['charName'], "p1m": item['p1']['mr'], "p1ctrl": item['p1']['control'], "p1r": item['p1']['result'],
                            "p2n": item['p2']['name'], "p2c": item['p2']['charName'], "p2m": item['p2']['mr'], "p2ctrl": item['p2']['control'], "p2r": item['p2']['result']
                        })
                        if res.rowcount > 0: new_count += 1
                    conn.commit()
            
            write_log(f"🏁 処理完了。新規保存: {new_count}件")
            page.screenshot(path=FULL_SCREENSHOT_PATH)
            return True

        except Exception as e:
            write_log(f"💥 エラー: {str(e)}")
            return False
        finally:
            browser.close()

# --- 4. バックグラウンド監視スレッド ---
def background_worker():
    # 最後に実行した「日付+時間」を記録する変数
    last_run = ""
    
    while True:
        if ENV_ERROR: break
        
        now_dt = get_now_jst()
        now_str = now_dt.strftime("%H:%M")
        today_str = now_dt.strftime("%Y-%m-%d")
        current_time_total_minutes = now_dt.hour * 60 + now_dt.minute
        
        # 1. 毎回最新のスケジュールをDBから読み込む
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT value FROM scraper_config WHERE key = 'run_times'"))
                row = res.fetchone()
                # カンマ区切りの文字列をリストに変換
                raw_times = row[0].split(",") if row else ["09:00", "21:00"]
                
                # 「9:00」を「09:00」に補正する処理
                run_times = []
                for t in raw_times:
                    t = t.strip()
                    if len(t) == 4 and ":" in t: # 9:00 などの場合
                        t = "0" + t
                    run_times.append(t)
        except:
            # DB接続エラー等の場合はデフォルト値を使用
            run_times = ["09:00", "21:00"]

        # 2. 実行すべき時間があるかチェック
        should_run = False
        matched_time_str = ""

        for t_str in run_times:
            try:
                # 設定時刻(09:00など)を数値（分）に変換
                h, m = map(int, t_str.split(":"))
                target_total_minutes = h * 60 + m
                
                # 判定条件:
                # ① 現在時刻が設定時刻を過ぎている（または同時）
                # ② かつ、現在時刻が設定時刻から1時間以内（古い設定を無視するため）
                # ③ かつ、今日その設定時刻でまだ実行していない
                is_time_to_go = current_time_total_minutes >= target_total_minutes
                is_not_too_old = current_time_total_minutes < target_total_minutes + 60
                has_not_run_today = last_run != today_str + t_str
                
                if is_time_to_go and is_not_too_old and has_not_run_today:
                    should_run = True
                    matched_time_str = t_str
                    break
            except:
                continue # 変な形式の入力は無視して次へ

        # 3. 実行
        if should_run:
            write_log(f"⏰ 定期巡回スケジュールに合致しました (設定: {matched_time_str})")
            # TARGET_ID（環境変数の値）を使用して実行
            scrape_sf6(TARGET_ID, max_pages=2)
            # 実行済みスタンプを記録（例: "2024-05-2109:00"）
            last_run = today_str + matched_time_str
            
        # 4. 待機（1分間隔）
        time.sleep(60)

# --- 5. Streamlit UI ---
st.set_page_config(page_title="SF6 Stats Manager", layout="wide")

if ENV_ERROR:
    st.error("❌ 環境変数が設定されていません。")
    st.stop()

init_db()

# 左側のサイドバーでスケジュール設定
with st.sidebar:
    st.title("⚙️ 設定")
    
    # 現在のスケジュール取得
    with engine.connect() as conn:
        res = conn.execute(text("SELECT value FROM scraper_config WHERE key = 'run_times'"))
        row = res.fetchone()
        db_times = row[0] if row else "09:00,21:00"

    st.subheader("⏰ 自動巡回スケジュール")
    new_times = st.text_input("実行時間 (24h形式をカンマ区切り)", value=db_times, help="例: 09:00,15:30,22:00")
    
    if st.button("設定を保存", use_container_width=True):
        with engine.connect() as conn:
            conn.execute(text("UPDATE scraper_config SET value = :val WHERE key = 'run_times'"), {"val": new_times})
            conn.commit()
        st.success("✅ スケジュールを保存しました")
        time.sleep(1)
        st.rerun()

    st.divider()
    st.caption("※このWeb画面を閉じていても、Dockerが動いていれば自動取得は継続されます。")

# バックグラウンドスレッド起動
if "worker_thread_started" not in st.session_state:
    if not any(t.name == "BackgroundWorker" for t in threading.enumerate()):
        worker = threading.Thread(target=background_worker, name="BackgroundWorker", daemon=True)
        worker.start()
    st.session_state.worker_thread_started = True

# メインコンテンツ
st.title("🥊 SF6 戦績収集システム")

col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("手動実行")
    # TARGET_IDを初期値にしつつ、画面で一時的に変更して実行も可能
    current_target = st.text_input("ターゲットユーザーID", value=TARGET_ID)
    max_p = st.slider("巡回ページ数", 1, 50, 5)
    
    if st.button("🚀 今すぐ最新戦績を取得", use_container_width=True):
        scrape_sf6(current_target, max_pages=max_p)
        st.rerun()

    st.divider()
    st.subheader("ログ")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            logs = f.readlines()
            st.text_area("実行履歴 (最新50件)", value="".join(logs[-50:]), height=300)

with col2:
    st.subheader("前回の状態")
    if os.path.exists(FULL_SCREENSHOT_PATH):
        st.image(FULL_SCREENSHOT_PATH, caption="前回のブラウザ画面")