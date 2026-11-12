import os
import re
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import scheduler
import services
from config import FULL_SCREENSHOT_PATH
from database import init_db
from logger import tail_log

API_KEY = os.getenv("API_KEY")


def verify_api_key(x_api_key: Optional[str] = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop = scheduler.start()
    yield
    if stop:
        stop.set()


app = FastAPI(title="SF6 Stats API", lifespan=lifespan)
protected = [Depends(verify_api_key)]


class UserIn(BaseModel):
    user_code: str = Field(pattern=r"^\d{10}$")
    player_name: str = Field(min_length=1)
    note: Optional[str] = None


class UserPatch(BaseModel):
    player_name: Optional[str] = None
    note: Optional[str] = None
    is_active: Optional[bool] = None


class ScrapeIn(BaseModel):
    max_pages: int = Field(default=5, ge=1, le=10)
    force_mode: bool = False


class ScheduleIn(BaseModel):
    run_times: str = Field(pattern=r"^\s*\d{1,2}:\d{2}(\s*,\s*\d{1,2}:\d{2})*\s*$")


class RequestPatch(BaseModel):
    status: str = Field(pattern="^(completed|rejected|pending)$")
    admin_comment: Optional[str] = ""


@app.get("/health")
def health():
    return {"status": "ok"}


# --- users ---
@app.get("/users", dependencies=protected)
def get_users():
    return services.list_users()


@app.post("/users", status_code=201, dependencies=protected)
def post_user(body: UserIn):
    services.upsert_user(body.user_code, body.player_name, body.note)
    return {"user_code": body.user_code}


@app.patch("/users/{user_code}", dependencies=protected)
def patch_user(user_code: str, body: UserPatch):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "No fields to update")
    if services.update_user(user_code, fields) == 0:
        raise HTTPException(404, "User not found")
    return {"user_code": user_code, **fields}


# --- scrape ---
def _busy():
    raise HTTPException(409, "Scrape job already running")


@app.post("/scrape/users/{user_code}", status_code=202, dependencies=protected)
def scrape_user(user_code: str, body: ScrapeIn = ScrapeIn()):
    user = services.get_user(user_code)
    if not user:
        raise HTTPException(404, "User not found")
    if not services.start_job(f"user:{user_code}", services.run_user, user.user_code, user.player_name,
                              body.max_pages, body.force_mode):
        _busy()
    return {"status": "accepted", "job": f"user:{user_code}"}


@app.post("/scrape/all", status_code=202, dependencies=protected)
def scrape_all(body: ScrapeIn = ScrapeIn()):
    if not services.start_job("all", services.run_all_users, body.max_pages, body.force_mode):
        _busy()
    return {"status": "accepted", "job": "all"}


@app.get("/scrape/status", dependencies=protected)
def scrape_status():
    # 定期巡回もロックを保持するため、ロック状態を実行中の根拠にする
    state = dict(services.job_state)
    locked = services.scrape_lock.locked()
    if locked and not state["running"]:
        state.update(running=True, job="scheduled")
    state["running"] = locked
    return state


# --- schedule / logs ---
@app.get("/schedule", dependencies=protected)
def get_schedule():
    return {"run_times": services.get_run_times()}


@app.put("/schedule", dependencies=protected)
def put_schedule(body: ScheduleIn):
    services.set_run_times(body.run_times.replace(" ", ""))
    return {"run_times": body.run_times.replace(" ", "")}


@app.get("/logs", dependencies=protected)
def get_logs(lines: int = Query(100, ge=1, le=1000)):
    return {"lines": tail_log(lines)}


# --- system ---
@app.post("/system/public-url/refresh", dependencies=protected)
def refresh_url():
    services.refresh_public_url()
    return {"status": "done"}


@app.get("/system/screenshot", dependencies=protected)
def screenshot():
    if not os.path.exists(FULL_SCREENSHOT_PATH):
        raise HTTPException(404, "No screenshot")
    return FileResponse(FULL_SCREENSHOT_PATH)


def _error_files():
    return [f for f in os.listdir(".") if re.fullmatch(r"error_.*\.png", f)]


@app.get("/system/errors", dependencies=protected)
def list_errors():
    return {"files": sorted(_error_files(), key=os.path.getctime, reverse=True)}


@app.get("/system/errors/{name}", dependencies=protected)
def get_error(name: str):
    if name not in _error_files():
        raise HTTPException(404, "Not found")
    return FileResponse(name)


@app.delete("/system/errors", dependencies=protected)
def clear_errors():
    files = _error_files()
    for f in files:
        try:
            os.remove(f)
        except OSError:
            pass
    return {"deleted": len(files)}


# --- feature requests ---
@app.get("/feature-requests", dependencies=protected)
def get_requests(status: Optional[str] = None):
    return services.list_feature_requests(status)


@app.patch("/feature-requests/{req_id}", dependencies=protected)
def patch_request(req_id: int, body: RequestPatch):
    if services.update_feature_request(req_id, body.status, body.admin_comment) == 0:
        raise HTTPException(404, "Not found")
    return {"id": req_id, "status": body.status}
