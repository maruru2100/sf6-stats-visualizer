import random
import threading
import time
from sqlalchemy import text
from database import engine
from logger import write_log
from scraper import scrape_sf6, update_public_url

DEFAULT_RUN_TIMES = "09:00,21:00"

# Playwright / 対象サイト負荷対策のため、スクレイピングは同時に1本のみ
scrape_lock = threading.Lock()
job_state = {"running": False, "job": None, "started_at": None, "finished_at": None, "error": None}


# --- Users ---
def list_users():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT user_code, player_name, note, is_active, created_at FROM target_users ORDER BY created_at ASC"
        )).mappings().all()
    return [dict(r) for r in rows]


def upsert_user(user_code, player_name, note=None):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO target_users (user_code, player_name, note)
            VALUES (:uid, :name, :note) ON CONFLICT (user_code)
            DO UPDATE SET player_name=EXCLUDED.player_name, note=EXCLUDED.note
        """), {"uid": user_code, "name": player_name, "note": note})


def update_user(user_code, fields):
    allowed = {"player_name": "player_name", "note": "note", "is_active": "is_active"}
    sets = [f"{allowed[k]} = :{k}" for k in fields if k in allowed]
    if not sets:
        return 0
    with engine.begin() as conn:
        res = conn.execute(text(f"UPDATE target_users SET {', '.join(sets)} WHERE user_code = :uid"),
                           {**fields, "uid": user_code})
    return res.rowcount


def get_user(user_code):
    with engine.connect() as conn:
        return conn.execute(text("SELECT user_code, player_name FROM target_users WHERE user_code = :u"),
                            {"u": user_code}).fetchone()


# --- Schedule ---
def get_run_times():
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT value FROM scraper_config WHERE key = 'run_times'")).fetchone()
        return row[0] if row else DEFAULT_RUN_TIMES
    except Exception:
        return DEFAULT_RUN_TIMES


def set_run_times(value):
    with engine.begin() as conn:
        res = conn.execute(text("UPDATE scraper_config SET value = :v WHERE key = 'run_times'"), {"v": value})
        if res.rowcount == 0:
            conn.execute(text("INSERT INTO scraper_config (key, value) VALUES ('run_times', :v)"), {"v": value})


# --- Scraping ---
def run_user(user_code, player_name, max_pages=2, force_mode=False):
    scrape_sf6(user_code, player_name, write_log, max_pages=max_pages, force_mode=force_mode)


def run_all_users(max_pages=2, force_mode=False):
    """有効なユーザー全員を順次実行"""
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


def start_job(name, func, *args, **kwargs):
    """ジョブを別スレッドで開始。実行中なら False"""
    if not scrape_lock.acquire(blocking=False):
        return False

    # スレッド開始前に状態を確定させ、直後のstatus確認で取りこぼさないようにする
    job_state.update(running=True, job=name, started_at=time.time(), finished_at=None, error=None)

    def _run():
        try:
            func(*args, **kwargs)
        except Exception as e:
            job_state["error"] = str(e)
            write_log(f"💥 ジョブ実行エラー: {e}")
        finally:
            job_state.update(running=False, finished_at=time.time())
            scrape_lock.release()

    threading.Thread(target=_run, name="ScrapeJob", daemon=True).start()
    return True


def refresh_public_url():
    update_public_url(write_log)


# --- Feature requests ---
def list_feature_requests(status=None):
    q = "SELECT id, content, status, admin_comment, created_at FROM feature_requests"
    params = {}
    if status:
        q += " WHERE status = :s"
        params["s"] = status
    q += " ORDER BY created_at DESC"
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(q), params).mappings().all()]


def update_feature_request(req_id, status, admin_comment):
    with engine.begin() as conn:
        res = conn.execute(text("UPDATE feature_requests SET status=:s, admin_comment=:c WHERE id=:id"),
                           {"s": status, "c": admin_comment, "id": req_id})
    return res.rowcount
