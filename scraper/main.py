import streamlit as st
import datetime
import time
import os
import threading
import random
from sqlalchemy import text
from config import TARGET_ID, DATABASE_URL, ENV_ERROR, JST, LOG_FILE, FULL_SCREENSHOT_PATH
from database import init_db, engine
from scraper import scrape_sf6, update_public_url

# --- 初期化 ---
init_db()

def get_now_jst(): return datetime.datetime.now(JST)

def write_log(message):
    now = get_now_jst().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{now}] {message}"
    print(formatted_msg)
    try:
        with open(LOG_FILE, "a") as f: f.write(formatted_msg + "\n")
    except: pass
    if "log_messages" not in st.session_state: st.session_state.log_messages = ""
    st.session_state.log_messages += formatted_msg + "\n"

def run_all_users(max_pages=2):
    """【順次実行】登録されている有効なユーザー全員を順番に実行"""
    try:
        with engine.connect() as conn:
            users = conn.execute(text("SELECT user_code, player_name FROM target_users WHERE is_active = TRUE")).fetchall()
        
        if not users:
            write_log("⚠️ アクティブなユーザーが登録されていません。")
            return

        write_log(f"👥 計 {len(users)} 名の巡回を順次開始します。")
        for i, u in enumerate(users):
            scrape_sf6(u.user_code, u.player_name, write_log, max_pages=max_pages)
            
            if i < len(users) - 1:
                wait_sec = random.randint(15, 30)
                write_log(f"☕ 負荷軽減のため {wait_sec}秒 待機して次のユーザーへ移ります...")
                time.sleep(wait_sec)
        write_log("✨ 全員の巡回が終了しました。")
    except Exception as e:
        write_log(f"💥 全員実行中にエラーが発生しました: {e}")

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
                        run_all_users(max_pages=2) 
                        last_run = today_str + t_str
                        break
            except: continue
        time.sleep(60)

# --- UI ---
st.set_page_config(page_title="SF6 Stats Manager", layout="wide")

# 背景スレッドの開始
if "worker_thread_started" not in st.session_state:
    if not any(t.name == "BackgroundWorker" for t in threading.enumerate()):
        threading.Thread(target=background_worker, name="BackgroundWorker", daemon=True).start()
    st.session_state.worker_thread_started = True

with st.sidebar:
    st.title("⚙️ 設定")
    
    # 外部公開管理セクション
    st.subheader("🌐 外部公開管理")
    if st.button("🔄 公開URLを最新に更新", use_container_width=True, help="Cloudflare Tunnelから最新のランダムURLを取得してDBを更新します"):
        # ブラウザを起動せず、URL取得ロジックだけを動かす
        update_public_url(write_log)
        st.success("処理が完了しました。ログを確認してください。")
    st.divider()

    st.subheader("👥 ターゲットユーザー管理")
    with st.expander("ユーザーを追加/更新"):
        new_uid = st.text_input("ユーザーコード (10桁)", key="input_uid")
        new_pname = st.text_input("表示名", key="input_pname")
        new_note = st.text_area("メモ", key="input_note")
        
        if st.button("登録/上書き"):
            if not new_uid or not new_pname:
                st.error("IDと表示名は必須です")
            else:
                with engine.connect() as conn:
                    conn.execute(text("""
                        INSERT INTO target_users (user_code, player_name, note) 
                        VALUES (:uid, :name, :note) ON CONFLICT (user_code) 
                        DO UPDATE SET player_name=EXCLUDED.player_name, note=EXCLUDED.note
                    """), {"uid": new_uid, "name": new_pname, "note": new_note})
                    conn.commit()
                st.session_state.input_uid = ""
                st.session_state.input_pname = ""
                st.session_state.input_note = ""
                st.success("✅ 保存しました")
                time.sleep(1)
                st.rerun()

    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT value FROM scraper_config WHERE key = 'run_times'"))
            row = res.fetchone()
            db_times = row[0] if row else "09:00,21:00"
    except: db_times = "09:00,21:00"
    
    st.subheader("⏰ 自動巡回スケジュール")
    new_times = st.text_input("実行時間 (カンマ区切り)", value=db_times)
    if st.button("設定を保存", use_container_width=True):
        with engine.connect() as conn:
            conn.execute(text("UPDATE scraper_config SET value = :val WHERE key = 'run_times'"), {"val": new_times})
            conn.commit()
        st.success("✅ 保存完了"); time.sleep(1); st.rerun()

st.title("🥊 SF6 戦績＆統計収集システム")
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("実行")
    with engine.connect() as conn:
        users_list = conn.execute(text("SELECT user_code, player_name FROM target_users")).fetchall()
    
    if users_list:
        selected_u = st.selectbox("単発実行対象", options=users_list, format_func=lambda x: f"{x.player_name} ({x.user_code})")
        max_p = st.slider("巡回ページ数", 1, 50, 5)
        
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button("🚀 選択ユーザーのみ実行", use_container_width=True):
                scrape_sf6(selected_u.user_code, selected_u.player_name, write_log, max_pages=max_p)
                st.rerun()
        with c_btn2:
            if st.button("🔄 全員分を順次実行", use_container_width=True):
                run_all_users(max_pages=max_p)
                st.rerun()
    else:
        st.info("サイドバーからユーザーを登録してください。")

    st.divider()
    st.subheader("最新のログ")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            st.text_area("実行履歴 (最新50件)", value="".join(lines[-50:]), height=400)

with col2:
    st.subheader("登録ユーザー一覧")
    with engine.connect() as conn:
        df_users = conn.execute(text("SELECT player_name as 名前, user_code as ID, note as メモ, is_active as 有効 FROM target_users")).fetchall()
        if df_users:
            st.table(df_users)
        else:
            st.write("登録されているユーザーはいません。")
            
    if os.path.exists(FULL_SCREENSHOT_PATH):
        st.divider()
        st.subheader("最新のキャプチャ")
        st.image(FULL_SCREENSHOT_PATH, caption="Last Scrape View")