import streamlit as st
import datetime
import time
import os
import threading
import random
import pandas as pd
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
    
    # 既存の print に flush=True を追加して即時反映させる
    print(formatted_msg, flush=True) 
    
    try:
        with open(LOG_FILE, "a") as f: f.write(formatted_msg + "\n")
    except: pass
    
    if "log_messages" not in st.session_state: st.session_state.log_messages = ""
    st.session_state.log_messages += formatted_msg + "\n"

def run_all_users(max_pages=2, force_mode=False):
    """【順次実行】登録されている有効なユーザー全員を順番に実行"""
    try:
        with engine.connect() as conn:
            users = conn.execute(text("SELECT user_code, player_name FROM target_users WHERE is_active = TRUE")).fetchall()
        
        if not users:
            write_log("⚠️ アクティブなユーザーが登録されていません。")
            return

        write_log(f"👥 計 {len(users)} 名の巡回を順次開始します。")
        for i, u in enumerate(users):
            scrape_sf6(u.user_code, u.player_name, write_log, max_pages=max_pages, force_mode=force_mode)
            
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
                        run_all_users(max_pages=10) 
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
        update_public_url(write_log)
        st.success("処理が完了しました。ログを確認してください。")
    st.divider()

    st.subheader("👥 ターゲットユーザー管理")
    with st.expander("ユーザーを追加/更新"):
        with st.form("user_registration_form", clear_on_submit=True):
            new_uid = st.text_input("ユーザーコード (10桁)")
            new_pname = st.text_input("表示名")
            new_note = st.text_area("メモ")
            
            if st.form_submit_button("登録/上書き"):
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

        force_scan = st.checkbox("強制モード (新規なしでも指定ページまで取得)", value=False)
        
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button("🚀 選択ユーザーのみ実行", use_container_width=True):
                scrape_sf6(selected_u.user_code, selected_u.player_name, write_log, max_pages=max_p, force_mode=force_scan)
                st.rerun()
        with c_btn2:
            if st.button("🔄 全員分を順次実行", use_container_width=True):
                run_all_users(max_pages=max_p, force_mode=force_scan)
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
    
    # 1. データの読み込み
    with engine.connect() as conn:
        # st.data_editorで扱いやすいよう、pandasや辞書形式に近い形で取得
        res = conn.execute(text("SELECT user_code as ID, player_name as 名前, note as メモ, is_active as 有効 FROM target_users ORDER BY created_at ASC"))
        df = pd.DataFrame(res.fetchall(), columns=["ID", "名前", "メモ", "有効"])

    if not df.empty:
        # 2. 編集可能な表(data_editor)の表示
        # ※ ID（user_code）は編集不可(disabled)にします
        edited_df = st.data_editor(
            df,
            key="user_editor",
            disabled=["ID"],
            use_container_width=True,
            hide_index=True,
            column_config={
                "有効": st.column_config.CheckboxColumn(
                    help="チェックを外すと自動巡回や一括実行の対象外になります",
                    default=True,
                )
            }
        )

        # 3. 更新ボタン
        if st.button("🆙 ユーザー設定を保存", use_container_width=True):
            try:
                with engine.begin() as conn:
                    # ✅ iterrows() を使い、row オブジェクトから正確に値を取得する
                    for index, row in edited_df.iterrows():
                        conn.execute(
                            text("""
                                UPDATE target_users 
                                SET player_name = :name, 
                                    note = :note, 
                                    is_active = :active 
                                WHERE user_code = :uid
                            """),
                            {
                                "name": str(row["名前"]),   # カラム名が「名前」であることを確認
                                "note": str(row["メモ"]),   # カラム名が「メモ」であることを確認
                                "active": bool(row["有効"]), # チェックボックス
                                "uid": str(row["ID"])      # WHERE句のキー
                            }
                        )
                st.success("✅ ユーザー設定を更新しました")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                # 詳細なエラー箇所の特定のため、エラー内容を表示
                st.error(f"❌ 更新失敗: {e}")
                st.error(f"❌ 更新失敗: {e}")
    else:
        st.write("登録されているユーザーはいません。")
            
    if os.path.exists(FULL_SCREENSHOT_PATH):
        st.divider()
        st.subheader("最新のキャプチャ")
        st.image(FULL_SCREENSHOT_PATH, caption="Last Scrape View")

    st.divider()
    st.subheader("🖼️ スクレイピング・エラーの確認")
    error_files = [f for f in os.listdir(".") if f.startswith("error_") and f.endswith(".png")]
    if error_files:
        latest_error = max(error_files, key=os.path.getctime)
        st.error(f"⚠️ 直近のエラー画面: {latest_error}")
        st.image(latest_error, caption="Error Screenshot", use_container_width=True)
        if st.button("🗑️ エラー画像をクリア", use_container_width=True):
            for f in error_files:
                try: os.remove(f)
                except: pass
            st.rerun()
    else:
        st.info("現在、実行エラー画像はありません。")

    # --- 要望管理セクション ---
    st.divider()
    st.subheader("💡 ユーザー要望管理")
    try:
        with engine.connect() as conn:
            # 却下(rejected)でも完了(completed)でもない未処理分を表示
            req_rows = conn.execute(text(
                "SELECT id, content, created_at FROM feature_requests WHERE status = 'pending' ORDER BY created_at DESC"
            )).fetchall()

        if req_rows:
            for req in req_rows:
                with st.expander(f"📩 {req.created_at.strftime('%m/%d %H:%M')} : {req.content[:30]}..."):
                    st.write(f"**内容:** {req.content}")
                    with st.form(key=f"req_form_{req.id}"):
                        admin_msg = st.text_input("管理者コメント（理由）", key=f"input_{req.id}")
                        b_col1, b_col2 = st.columns(2)
                        if b_col1.form_submit_button("✅ 完了"):
                            with engine.begin() as conn:
                                conn.execute(text("UPDATE feature_requests SET status='completed', admin_comment=:c WHERE id=:id"), {"c":admin_msg, "id":req.id})
                            st.rerun()
                        if b_col2.form_submit_button("❌ 却下"):
                            with engine.begin() as conn:
                                conn.execute(text("UPDATE feature_requests SET status='rejected', admin_comment=:c WHERE id=:id"), {"c":admin_msg, "id":req.id})
                            st.rerun()
        else:
            st.info("未処理の要望はありません。")
    except Exception as e:
        st.error(f"要望管理エラー (V6未実行?): {e}")