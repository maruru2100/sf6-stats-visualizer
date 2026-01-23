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
        # 1. 戦績テーブル
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
        # 2. プレイスタイル統計テーブル
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_stats (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                recorded_at DATE NOT NULL DEFAULT CURRENT_DATE,
                d_parry_pct FLOAT, d_impact_pct FLOAT, d_od_pct FLOAT, d_rush_p_pct FLOAT, d_rush_c_pct FLOAT, d_reversal_pct FLOAT,
                sa1_pct FLOAT, sa2_pct FLOAT, sa3_pct FLOAT, ca_pct FLOAT,
                impact_win FLOAT, impact_pc_win FLOAT, impact_counter_win FLOAT,
                impact_lose FLOAT, impact_pc_lose FLOAT, impact_counter_lose FLOAT,
                just_parry_count FLOAT, throw_win FLOAT, throw_lose FLOAT, throw_escape FLOAT,
                stun_win FLOAT, stun_lose FLOAT, 
                wall_push_sec FLOAT, wall_pushed_sec FLOAT,
                UNIQUE (user_id, recorded_at)
            );
        """))

        # --- DBツール用：全カラムへのコメント付与 ---
        comments = [
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
            ("battle_results.p2_name", "P2：名前"), ("battle_results.p2_char", "P2：キャラ"), ("battle_results.p2_mr", "P2：MR/LP"),
            ("battle_results.p2_control", "P2：操作"), ("battle_results.p2_result", "P2：結果")
        ]
        for target, comment in comments:
            try: conn.execute(text(f"COMMENT ON COLUMN {target} IS '{comment}';"))
            except: pass

        # 3. 設定保存用テーブル
        conn.execute(text("CREATE TABLE IF NOT EXISTS scraper_config (key TEXT PRIMARY KEY, value TEXT);"))
        conn.execute(text("INSERT INTO scraper_config (key, value) VALUES ('run_times', '09:00,21:00') ON CONFLICT DO NOTHING;"))
        conn.commit()

# --- 3. 解析ロジック ---

def scrape_performance_data(page, user_id):
    """【実績】タブから詳細統計を取得・保存"""
    try:
        write_log(f"📊 統計解析開始 (ID: {user_id})")
        # 「実績」ボタンのより確実なセレクター
        perf_tab = page.locator('li:has-text("実績"), button:has-text("実績")').first
        if perf_tab.is_visible():
            perf_tab.click()
            time.sleep(random.uniform(4.0, 6.0))
        else:
            write_log("⚠️ '実績'ボタンが見つかりません。")
            return

        stats = page.evaluate("""
            () => {
                const results = {};
                const parseNum = (txt) => parseFloat(txt.replace(/[^0-9.]/g, '')) || 0;
                document.querySelectorAll('li[class*="battle_style_"]').forEach(li => {
                    const type = li.querySelector('[class*="battle_style_type"]')?.innerText.trim();
                    const val = parseNum(li.querySelector('[class*="battle_style_number"]')?.innerText || "0");
                    if(type === "ドライブパリィ") results.d_parry_pct = val;
                    if(type === "ドライブインパクト") results.d_impact_pct = val;
                    if(type === "オーバードライブアーツ") results.d_od_pct = val;
                    if(type === "パリィドライブラッシュ") results.d_rush_p_pct = val;
                    if(type === "キャンセルドライブラッシュ") results.d_rush_c_pct = val;
                    if(type === "ドライブリバーサル") results.d_reversal_pct = val;
                    if(type === "Lv1") results.sa1_pct = val;
                    if(type === "Lv2") results.sa2_pct = val;
                    if(type === "Lv3") results.sa3_pct = val;
                    if(type === "CA") results.ca_pct = val;
                });
                document.querySelectorAll('dl').forEach(dl => {
                    const title = dl.querySelector('dt')?.innerText.trim();
                    const getV = (label) => {
                        const spans = Array.from(dl.querySelectorAll('span'));
                        const target = spans.find(s => s.innerText.trim() === label);
                        return target ? parseNum(target.nextElementSibling?.innerText || "0") : 0;
                    };
                    if(title === "ドライブパリィ") results.just_parry = getV("ジャストパリィ回数");
                    if(title === "ドライブインパクト") {
                        results.imp_win = getV("決めた回数");
                        results.imp_pc_win = getV("パニッシュカウンターを決めた回数");
                        results.imp_returned_win = getV("相手のドライブインパクトに決めた回数");
                        results.imp_lose = getV("受けた回数");
                        results.imp_pc_lose = getV("パニッシュカウンターを受けた回数");
                        results.imp_returned_lose = getV("相手にドライブインパクトで返された回数");
                    }
                    if(title === "スタン") { results.stun_win = getV("スタンさせた回数"); results.stun_lose = getV("スタンさせられた回数"); }
                    if(title === "投げ") { results.throw_win = getV("決めた回数"); results.throw_lose = getV("受けた回数"); results.throw_escape = getV("投げ抜け回数"); }
                    if(title === "壁際") { results.wall_push = getV("相手を追い詰めている時間"); results.wall_pushed = getV("相手に追い詰められている時間"); }
                });
                return results;
            }
        """)
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO player_stats (
                    user_id, recorded_at, d_parry_pct, d_impact_pct, d_od_pct, d_rush_p_pct, d_rush_c_pct, d_reversal_pct,
                    sa1_pct, sa2_pct, sa3_pct, ca_pct, impact_win, impact_pc_win, impact_counter_win,
                    impact_lose, impact_pc_lose, impact_counter_lose, just_parry_count,
                    throw_win, throw_lose, throw_escape, stun_win, stun_lose, wall_push_sec, wall_pushed_sec
                ) VALUES (
                    :uid, CURRENT_DATE, :d_parry_pct, :d_impact_pct, :d_od_pct, :d_rush_p_pct, :d_rush_c_pct, :d_reversal_pct,
                    :sa1_pct, :sa2_pct, :sa3_pct, :ca_pct, :imp_win, :imp_pc_win, :imp_returned_win,
                    :imp_lose, :imp_pc_lose, :imp_returned_lose, :just_parry,
                    :throw_win, :throw_lose, :throw_escape, :stun_win, :stun_lose, :wall_push, :wall_pushed
                ) ON CONFLICT (user_id, recorded_at) DO UPDATE SET
                    d_parry_pct=EXCLUDED.d_parry_pct, d_impact_pct=EXCLUDED.d_impact_pct, d_od_pct=EXCLUDED.d_od_pct,
                    d_rush_p_pct=EXCLUDED.d_rush_p_pct, d_rush_c_pct=EXCLUDED.d_rush_c_pct, d_reversal_pct=EXCLUDED.d_reversal_pct,
                    sa1_pct=EXCLUDED.sa1_pct, sa2_pct=EXCLUDED.sa2_pct, sa3_pct=EXCLUDED.sa3_pct, ca_pct=EXCLUDED.ca_pct,
                    impact_win=EXCLUDED.impact_win, impact_pc_win=EXCLUDED.impact_pc_win, impact_counter_win=EXCLUDED.impact_counter_win,
                    impact_lose=EXCLUDED.impact_lose, impact_pc_lose=EXCLUDED.impact_pc_lose, impact_counter_lose=EXCLUDED.impact_counter_lose,
                    just_parry_count=EXCLUDED.just_parry_count, throw_win=EXCLUDED.throw_win, throw_lose=EXCLUDED.throw_lose,
                    throw_escape=EXCLUDED.throw_escape, stun_win=EXCLUDED.stun_win, stun_lose=EXCLUDED.stun_lose,
                    wall_push_sec=EXCLUDED.wall_push_sec, wall_pushed_sec=EXCLUDED.wall_pushed_sec;
            """), {**stats, "uid": user_id})
            conn.commit()
        write_log("✅ 統計データ保存完了")
    except Exception as e: write_log(f"⚠️ 統計取得エラー: {e}")

def scrape_sf6(user_code, max_pages=5):
    if not user_code: return False
    play_url = f"https://www.streetfighter.com/6/buckler/ja-jp/profile/{user_code}/play"
    log_url = f"https://www.streetfighter.com/6/buckler/ja-jp/profile/{user_code}/battlelog/rank#profile_nav"
    write_log(f"🚀 スクレイピング開始 (ID: {user_code}, 遡り: {max_pages}ページ)")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = browser.new_context(
            storage_state=COOKIE_PATH, viewport={'width': 1280, 'height': 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36", locale="ja-JP"
        )
        page = context.new_page()
        try:
            # 1. プレイ統計の取得 (Playタブ)
            page.goto(play_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)
            # ポップアップ排除
            page.evaluate("() => { document.querySelectorAll('#CybotCookiebotDialog, [class*=\"praise_\"]').forEach(el => el.remove()); }")
            scrape_performance_data(page, user_code)

            # 2. 戦績の取得 (Battle Logタブ)
            page.goto(log_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)
            all_found_data = []
            for current_p in range(1, max_pages + 1):
                write_log(f"📑 戦績 {current_p}ページ目をスキャン中...")
                time.sleep(2)
                p_data = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('li[data-index]').forEach(item => {
                        try {
                            const getP = (side) => {
                                const pClass = 'battle_data_player' + side;
                                const parent = item.querySelector(`[class*="${pClass}"]`);
                                const name = item.querySelector(`[class*="battle_data_name_p${side}"]`)?.innerText.trim() || "Unknown";
                                const mr = parseInt(parent?.querySelector('[class*="battle_data_lp"]')?.innerText.replace(/[^0-9]/g, "")) || 0;
                                const char = parent?.querySelector('[class*="battle_data_character"] img')?.getAttribute('alt') || "Unknown";
                                const ctrl = parent?.querySelector('[class*="battle_data_control"] img')?.getAttribute('src')?.includes('type0') ? 'Classic' : 'Modern';
                                const res = item.querySelector(`[class*="battle_data_player_${side}"]`)?.innerText.trim() || "";
                                return { name, mr, char, ctrl, res };
                            };
                            const date = item.querySelector('[class*="battle_data_date"]')?.innerText.trim();
                            if(date) {
                                const p1 = getP(1); const p2 = getP(2);
                                results.push({ id: "rank_"+date.replace(/[^0-9]/g,"")+"_"+p1.name+"_"+p2.name, date, p1, p2 });
                            }
                        } catch(e){}
                    });
                    return results;
                }""")
                if p_data: all_found_data.extend(p_data)
                if current_p < max_pages:
                    btn = page.locator("li.next:not(.disabled)").first
                    if btn.is_visible():
                        btn.click()
                        page.wait_for_load_state("networkidle")
                        time.sleep(3)
                    else: break

            new_count = 0
            if all_found_data:
                with engine.connect() as conn:
                    for it in all_found_data:
                        dt = datetime.datetime.strptime(it['date'], "%Y/%m/%d %H:%M")
                        r = conn.execute(text("""
                            INSERT INTO battle_results (battle_id, played_at, mode, p1_name, p1_char, p1_mr, p1_control, p1_result, p2_name, p2_char, p2_mr, p2_control, p2_result)
                            VALUES (:bid, :pat, 'RankMatch', :p1n, :p1c, :p1m, :p1ctrl, :p1r, :p2n, :p2c, :p2m, :p2ctrl, :p2r)
                            ON CONFLICT (battle_id) DO NOTHING
                        """), {"bid":it['id'], "pat":dt, "p1n":it['p1']['name'], "p1c":it['p1']['char'], "p1m":it['p1']['mr'], "p1ctrl":it['p1']['ctrl'], "p1r":it['p1']['res'], "p2n":it['p2']['name'], "p2c":it['p2']['char'], "p2m":it['p2']['mr'], "p2ctrl":it['p2']['ctrl'], "p2r":it['p2']['res']})
                        if r.rowcount > 0: new_count += 1
                    conn.commit()
            write_log(f"🏁 完了。新規戦績: {new_count}件")
            page.screenshot(path=FULL_SCREENSHOT_PATH, full_page=True)
            return True
        except Exception as e:
            write_log(f"💥 エラー: {e}")
            try: page.screenshot(path="./debug_error.png", full_page=True)
            except: pass
            return False
        finally: browser.close()

# --- 4. バックグラウンド監視（Gitベース） ---
def background_worker():
    last_run = ""
    while True:
        if ENV_ERROR: break
        now_dt = get_now_jst()
        now_str = now_dt.strftime("%H:%M")
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
                    if len(t) == 4 and ":" in t: t = "0" + t # 9:00 -> 09:00補正
                    run_times.append(t)
        except: run_times = ["09:00", "21:00"]

        for t_str in run_times:
            try:
                h, m = map(int, t_str.split(":"))
                target_total_minutes = h * 60 + m
                is_time_to_go = current_time_total_minutes >= target_total_minutes
                is_not_too_old = current_time_total_minutes < target_total_minutes + 60
                has_not_run_today = last_run != today_str + t_str
                
                if is_time_to_go and is_not_too_old and has_not_run_today:
                    write_log(f"⏰ 定期巡回開始 (設定: {t_str})")
                    scrape_sf6(TARGET_ID, max_pages=2)
                    last_run = today_str + t_str
                    break
            except: continue
        time.sleep(60)

# --- 5. Streamlit UI ---
st.set_page_config(page_title="SF6 Stats Manager", layout="wide")
init_db()

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
        scrape_sf6(current_target, max_pages=max_p); st.rerun()
    st.divider(); st.subheader("ログ")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            st.text_area("実行履歴 (最新50件)", value="".join(f.readlines()[-50:]), height=300)
with col2:
    st.subheader("前回の状態")
    if os.path.exists(FULL_SCREENSHOT_PATH): st.image(FULL_SCREENSHOT_PATH)