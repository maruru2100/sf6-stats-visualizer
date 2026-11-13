import collections
import datetime
from config import JST, LOG_FILE

_memory_log = collections.deque(maxlen=1000)


def write_log(message):
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{now}] {message}"
    print(formatted_msg, flush=True)
    _memory_log.append(formatted_msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception:
        pass


def tail_log(lines=100):
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            return [l.rstrip("\n") for l in f.readlines()[-lines:]]
    except FileNotFoundError:
        return []
