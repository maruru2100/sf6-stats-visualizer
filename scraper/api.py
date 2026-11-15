import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

import scheduler
import services
from config import FULL_SCREENSHOT_PATH
from database import init_db
from logger import tail_log

API_KEY = os.getenv("API_KEY")


class _QuietPolling(logging.Filter):
    """画面が3秒ごとに呼ぶ /logs と /scrape/status をアクセスログから除外する"""

    def filter(self, record):
        msg = record.getMessage()
        return not (" /logs" in msg or " /scrape/status" in msg)


logging.getLogger("uvicorn.access").addFilter(_QuietPolling())


# Swagger UI の「Authorize」ボタンから API キーを入力できるようにする
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="`.env` の `API_KEY` の値（未設定なら不要）")


def verify_api_key(x_api_key: Optional[str] = Security(api_key_header)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop = scheduler.start()
    yield
    if stop:
        stop.set()


DESCRIPTION = """
SF6 Stats Visualizer のバックエンド REST API です。管理画面(Streamlit)や Discord Bot もこの API を利用します。

## 認証
- `.env` に `API_KEY` を設定している場合、`/health` 以外は `X-API-Key` ヘッダが必須です。
- Swagger 上では右上の **Authorize** ボタンにキーを入力すると、「Try it out」で試せます。
- `API_KEY` が未設定の場合は認証なしで利用できます。

## 実行中ジョブについて
- スクレイピングは同時に1本だけ実行できます。実行中に開始要求をすると `409` を返します。
- 進捗は `GET /scrape/status` で確認できます（`error_code` が `auth_expired` の場合は Cookie の再取得が必要です）。
"""

TAGS = [
    {"name": "ヘルスチェック", "description": "稼働確認（認証不要）"},
    {"name": "ユーザー管理", "description": "取得対象プレイヤーの登録・更新"},
    {"name": "スクレイピング", "description": "戦績取得の開始と状況確認"},
    {"name": "スケジュール・ログ", "description": "定期巡回の時刻設定と実行ログ"},
    {"name": "システム", "description": "公開URLの更新、エラー時のスクリーンショット"},
    {"name": "ユーザー要望", "description": "Discord から届いた匿名要望の管理"},
]

app = FastAPI(title="SF6 Stats API", description=DESCRIPTION, openapi_tags=TAGS, lifespan=lifespan)
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


@app.get("/health", tags=["ヘルスチェック"], summary="稼働確認", description="APIが起動していれば `{\"status\": \"ok\"}` を返します。認証不要。")
def health():
    return {"status": "ok"}


# --- users ---
@app.get("/users", dependencies=protected, tags=["ユーザー管理"], summary="ユーザー一覧",
         description="登録済みの取得対象ユーザーを一覧で返します。")
def get_users():
    return services.list_users()


@app.post("/users", status_code=201, dependencies=protected, tags=["ユーザー管理"], summary="ユーザー登録・更新",
          description="10桁の `user_code` とプレイヤー名でユーザーを登録します。既に存在する場合は内容を更新します。")
def post_user(body: UserIn):
    services.upsert_user(body.user_code, body.player_name, body.note)
    return {"user_code": body.user_code}


@app.patch("/users/{user_code}", dependencies=protected, tags=["ユーザー管理"], summary="ユーザー情報の部分更新",
           description="プレイヤー名・メモ・有効/無効(`is_active`)のうち、指定した項目だけ更新します。対象がいなければ 404。")
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


@app.post("/scrape/users/{user_code}", status_code=202, dependencies=protected, tags=["スクレイピング"],
          summary="指定ユーザーのスキャン開始",
          description="指定ユーザーの戦績取得をバックグラウンドで開始します（`max_pages`: 取得ページ数 1〜10、`force_mode`: 強制モード）。"
                      "他のジョブが実行中なら 409、ユーザー未登録なら 404。")
def scrape_user(user_code: str, body: ScrapeIn = ScrapeIn()):
    user = services.get_user(user_code)
    if not user:
        raise HTTPException(404, "User not found")
    if not services.start_job(f"user:{user_code}", services.run_user, user.user_code, user.player_name,
                              body.max_pages, body.force_mode):
        _busy()
    return {"status": "accepted", "job": f"user:{user_code}"}


@app.post("/scrape/all", status_code=202, dependencies=protected, tags=["スクレイピング"],
          summary="全ユーザーのスキャン開始",
          description="登録済みの全ユーザーを順に取得します。他のジョブが実行中なら 409。")
def scrape_all(body: ScrapeIn = ScrapeIn()):
    if not services.start_job("all", services.run_all_users, body.max_pages, body.force_mode):
        _busy()
    return {"status": "accepted", "job": "all"}


@app.get("/scrape/status", dependencies=protected, tags=["スクレイピング"], summary="実行状況の取得",
         description="`running` で実行中か分かります（定期巡回中も true）。失敗時は `error` / `error_code` を返し、"
                     "`auth_expired` は Cookie 切れを意味します。")
def scrape_status():
    # 定期巡回もロックを保持するため、ロック状態を実行中の根拠にする
    state = dict(services.job_state)
    locked = services.scrape_lock.locked()
    if locked and not state["running"]:
        state.update(running=True, job="scheduled")
    state["running"] = locked
    return state


# --- schedule / logs ---
@app.get("/schedule", dependencies=protected, tags=["スケジュール・ログ"], summary="定期巡回の時刻を取得",
         description="カンマ区切りの実行時刻（JST、例: `03:00,15:00`）を返します。")
def get_schedule():
    return {"run_times": services.get_run_times()}


@app.put("/schedule", dependencies=protected, tags=["スケジュール・ログ"], summary="定期巡回の時刻を変更",
         description="`HH:MM` をカンマ区切りで指定します。設定時刻から60分以内に1日1回実行されます。")
def put_schedule(body: ScheduleIn):
    services.set_run_times(body.run_times.replace(" ", ""))
    return {"run_times": body.run_times.replace(" ", "")}


@app.get("/logs", dependencies=protected, tags=["スケジュール・ログ"], summary="実行ログの取得",
         description="スクレイピングログの末尾 `lines` 行（1〜1000）を返します。")
def get_logs(lines: int = Query(100, ge=1, le=1000)):
    return {"lines": tail_log(lines)}


# --- system ---
@app.post("/system/public-url/refresh", dependencies=protected, tags=["システム"], summary="公開URLの更新",
          description="Cloudflare Tunnel の最新URLを取得し、DB(`system_status.public_url`)を更新します。")
def refresh_url():
    services.refresh_public_url()
    return {"status": "done"}


@app.get("/system/screenshot", dependencies=protected, tags=["システム"], summary="最新のデバッグ画面キャプチャ",
         description="直近のスクレイピング時の画面キャプチャ(PNG)を返します。無ければ 404。")
def screenshot():
    if not os.path.exists(FULL_SCREENSHOT_PATH):
        raise HTTPException(404, "No screenshot")
    return FileResponse(FULL_SCREENSHOT_PATH)


def _error_files():
    return [f for f in os.listdir(".") if re.fullmatch(r"error_.*\.png", f)]


@app.get("/system/errors", dependencies=protected, tags=["システム"], summary="エラー時スクリーンショット一覧",
         description="エラー発生時に保存された画像ファイル名を新しい順に返します。")
def list_errors():
    return {"files": sorted(_error_files(), key=os.path.getctime, reverse=True)}


@app.get("/system/errors/{name}", dependencies=protected, tags=["システム"], summary="エラー時スクリーンショットの取得",
         description="一覧で得たファイル名を指定して画像(PNG)を返します。")
def get_error(name: str):
    if name not in _error_files():
        raise HTTPException(404, "Not found")
    return FileResponse(name)


@app.delete("/system/errors", dependencies=protected, tags=["システム"], summary="エラー時スクリーンショットの全削除",
            description="保存されているエラー画像をすべて削除し、削除件数を返します。")
def clear_errors():
    files = _error_files()
    for f in files:
        try:
            os.remove(f)
        except OSError:
            pass
    return {"deleted": len(files)}


# --- feature requests ---
@app.get("/feature-requests", dependencies=protected, tags=["ユーザー要望"], summary="要望一覧",
         description="`status`（pending / completed / rejected）で絞り込めます。省略時は全件。")
def get_requests(status: Optional[str] = None):
    return services.list_feature_requests(status)


@app.patch("/feature-requests/{req_id}", dependencies=protected, tags=["ユーザー要望"], summary="要望のステータス更新",
           description="ステータス（completed / rejected / pending）と管理者コメントを更新します。")
def patch_request(req_id: int, body: RequestPatch):
    if services.update_feature_request(req_id, body.status, body.admin_comment) == 0:
        raise HTTPException(404, "Not found")
    return {"id": req_id, "status": body.status}
