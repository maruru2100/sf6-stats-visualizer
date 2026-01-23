import streamlit as st
import datetime
import time
import os
import threading
from sqlalchemy import text
from config import TARGET_ID, DATABASE_URL, ENV_ERROR, JST, LOG_FILE, FULL_SCREENSHOT_PATH
from database import init_db, engine
from scraper import scrape_sf6

# --- 初期化 ---
init_db()

def get_now_jst():
    return datetime.datetime.now(JST)

def write_log(message):
    now = get_now_jst().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{now}] {message}"
    print(formatted_msg)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(formatted_msg + "\n")
    except: pass
    if "log_messages" not in st.session_state:
        st.session_state.log_messages = ""
    st.session_state.log_messages += formatted_msg + "\n"

def background_worker():
    last_run = ""
    while True:
        if ENV_ERROR: break
        now_dt = get_now_jst()
        today_str = now_dt.strftime("%Y-%m-%d")
        current_time_total_minutes = now_dt.hour * 60 + now_dt.minute
        
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT value FROM scraper_config WHERE key = 'run_times'"))
                row = res.fetchone()
                raw_times = row[0].split(",") if row else ["09:00", "21:00"]
                run_times = []
                for t in raw_times:
                    t = t.strip()
                    if len(t) == 4 and ":" in t: t = "0" + t
                    run_times.append(t)
        except: run_times = ["09:00", "21:00"]

        for t_str in run_times:
            try:
                h, m = map(int, t_str.split(":"))
                target_total_minutes = h * 60 + m
                if target_total_minutes <= current_time_total_minutes < target_total_minutes + 60:
                    if last_run != today_str + t_str:
                        write_log(f"⏰ 定期巡回開始 (設定: {t_str})")
                        scrape_sf6(TARGET_ID, write_log, max_pages=2)
                        last_run = today_str + t_str
                        break
            except: continue
        time.sleep(60)

# --- UI ---
st.set_page_config(page_title="SF6 Stats Manager", layout="wide")

with st.sidebar:
    st.title("⚙️ 設定")
    with engine.connect() as conn:
        res = conn.execute(text("SELECT value FROM scraper_config WHERE key = 'run_times'"))
        row = res.fetchone()
        db_times = row[0] if row else "09:00,21:00"
    st.subheader("⏰ 自動巡回スケジュール")
    new_times = st.text_input("実行時間 (カンマ区切り)", value=db_times)
    if st.button("設定を保存", use_container_width=True):
        with engine.connect() as conn:
            conn.execute(text("UPDATE scraper_config SET value = :val WHERE key = 'run_times'"), {"val": new_times})
            conn.commit()
        st.success("✅ 保存完了"); time.sleep(1); st.rerun()

if "worker_thread_started" not in st.session_state:
    if not any(t.name == "BackgroundWorker" for t in threading.enumerate()):
        threading.Thread(target=background_worker, name="BackgroundWorker", daemon=True).start()
    st.session_state.worker_thread_started = True

st.title("🥊 SF6 戦績＆統計収集システム")
col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("手動実行")
    current_target = st.text_input("ターゲットユーザーID", value=TARGET_ID)
    max_p = st.slider("巡回ページ数", 1, 50, 5)
    if st.button("🚀 今すぐ最新データを取得", use_container_width=True):
        scrape_sf6(current_target, write_log, max_pages=max_p); st.rerun()
    st.divider(); st.subheader("ログ")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            st.text_area("実行履歴 (最新50件)", value="".join(f.readlines()[-50:]), height=300)
with col2:
    st.subheader("前回の状態")
    if os.path.exists(FULL_SCREENSHOT_PATH): st.image(FULL_SCREENSHOT_PATH)