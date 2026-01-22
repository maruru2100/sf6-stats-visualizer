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
# 個人情報をコードに含めないためのチェック
TARGET_ID = os.getenv("TARGET_PLAYER_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TARGET_ID or not DATABASE_URL:
    print("❌ エラー: 環境変数 'TARGET_PLAYER_ID' または 'DATABASE_URL' が設定されていません。")
    print(".envファイルまたはDockerの環境設定を確認してください。")
    # Streamlit上でも警告を表示するために変数は保持し、処理内で停止させる
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
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS battle_results (
                id SERIAL PRIMARY KEY, battle_id TEXT UNIQUE, played_at TIMESTAMP, mode TEXT,
                p1_name TEXT, p1_char TEXT, p1_mr INTEGER, p1_control TEXT, p1_result TEXT,
                p2_name TEXT, p2_char TEXT, p2_mr INTEGER, p2_control TEXT, p2_result TEXT
            );
        """))
        conn.commit()

# --- 3. 解析ロジック ---
def scrape_sf6(user_code, max_pages=5):
    if not user_code:
        write_log("❌ エラー: ユーザーIDが指定されていません。")
        return False

    target_url = f"https://www.streetfighter.com/6/buckler/ja-jp/profile/{user_code}/battlelog/rank#profile_nav"
    write_log(f"🚀 スクレイピング開始 (Target: {user_code}, 遡り: {max_pages}ページ)")

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
                
                # 堅牢な抽出JS
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

            # 保存
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
    # 起動時に環境変数から取得
    target_id = os.getenv("TARGET_PLAYER_ID")
    if not target_id:
        print("⚠️ TARGET_PLAYER_ID未設定のため、自動巡回は無効です。")
        return

    RUN_TIMES = ["09:00", "21:00"]
    print(f"📢 監視開始 (ID: {target_id}, 実行: {RUN_TIMES})")
    last_run = ""
    while True:
        now_dt = get_now_jst()
        now_str = now_dt.strftime("%H:%M")
        today_str = now_dt.strftime("%Y-%m-%d")
        
        if now_str in RUN_TIMES and last_run != today_str + now_str:
            scrape_sf6(target_id, max_pages=2)
            last_run = today_str + now_str
        time.sleep(30)

# --- 5. Streamlit UI ---
st.set_page_config(page_title="SF6 Stats Manager", layout="wide")

if ENV_ERROR:
    st.error("❌ 環境変数が設定されていません。'.env' ファイルを確認してください。")
    st.stop()

init_db()

if "worker_thread_started" not in st.session_state:
    already_running = any(t.name == "BackgroundWorker" for t in threading.enumerate())
    if not already_running:
        worker = threading.Thread(target=background_worker, name="BackgroundWorker", daemon=True)
        worker.start()
    st.session_state.worker_thread_started = True

st.title("🥊 SF6 戦績収集システム")

col1, col2 = st.columns([1, 1])
with col1:
    user_id = st.text_input("ターゲットユーザーID", value=TARGET_ID)
    max_p = st.slider("巡回ページ数", 1, 100, 5)
    
    if st.button("🚀 今すぐ最新戦績を取得", use_container_width=True):
        scrape_sf6(user_id, max_pages=max_p)
        st.rerun()

    st.divider()
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            logs = f.readlines()
            st.text_area("実行ログ (最新50件)", value="".join(logs[-50:]), height=300)

with col2:
    if os.path.exists(FULL_SCREENSHOT_PATH):
        st.image(FULL_SCREENSHOT_PATH, caption="前回の取得完了画面")