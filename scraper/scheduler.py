import datetime
import threading
import time
from config import JST, ENV_ERROR
from logger import write_log
import services


def _parse_times(raw):
    times = []
    for t in raw.split(","):
        t = t.strip()
        if len(t) == 4 and ":" in t:
            t = "0" + t
        times.append(t)
    return times


def _loop(stop_event):
    last_run = ""
    while not stop_event.is_set():
        now_dt = datetime.datetime.now(JST)
        today_str = now_dt.strftime("%Y-%m-%d")
        current = now_dt.hour * 60 + now_dt.minute
        for t_str in _parse_times(services.get_run_times()):
            try:
                h, m = map(int, t_str.split(":"))
            except ValueError:
                continue
            target = h * 60 + m
            if target <= current < target + 60 and last_run != today_str + t_str:
                write_log(f"⏰ 定期巡回開始 (設定: {t_str})")
                last_run = today_str + t_str
                if not services.scrape_lock.acquire(timeout=3600):
                    break
                try:
                    services.run_all_users(max_pages=10)
                finally:
                    services.scrape_lock.release()
                break
        stop_event.wait(60)


def start():
    if ENV_ERROR:
        return None
    stop_event = threading.Event()
    threading.Thread(target=_loop, args=(stop_event,), name="BackgroundWorker", daemon=True).start()
    return stop_event
