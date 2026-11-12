import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://scraper:8000").rstrip("/")
API_KEY = os.getenv("API_KEY")
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}


def api(method, path, **kwargs):
    """API呼び出し。失敗時は例外メッセージにAPIのdetailを含める"""
    r = requests.request(method, f"{API_URL}{path}", headers=HEADERS, timeout=kwargs.pop("timeout", 30), **kwargs)
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise RuntimeError(f"{r.status_code}: {detail}")
    return r


def safe(label, func):
    try:
        return func()
    except Exception as e:
        st.error(f"❌ {label}: {e}")
        return None


st.set_page_config(page_title="SF6 Stats Manager", layout="wide")

try:
    api("GET", "/health", timeout=5)
except Exception as e:
    st.error(f"❌ APIに接続できません ({API_URL}): {e}")
    st.stop()

users = safe("ユーザー取得", lambda: api("GET", "/users").json()) or []

with st.sidebar:
    st.title("⚙️ 設定")

    st.subheader("🌐 外部公開管理")
    if st.button("🔄 公開URLを最新に更新", use_container_width=True,
                 help="Cloudflare Tunnelから最新のランダムURLを取得してDBを更新します"):
        if safe("公開URL更新", lambda: api("POST", "/system/public-url/refresh", timeout=300)):
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
                elif safe("登録", lambda: api("POST", "/users", json={
                        "user_code": new_uid, "player_name": new_pname, "note": new_note})):
                    st.success("✅ 保存しました")
                    st.rerun()

    st.subheader("⏰ 自動巡回スケジュール")
    db_times = (safe("スケジュール取得", lambda: api("GET", "/schedule").json()) or {}).get("run_times", "09:00,21:00")
    new_times = st.text_input("実行時間 (カンマ区切り)", value=db_times)
    if st.button("設定を保存", use_container_width=True):
        if safe("スケジュール保存", lambda: api("PUT", "/schedule", json={"run_times": new_times})):
            st.success("✅ 保存完了")
            st.rerun()

st.title("🥊 SF6 戦績＆統計収集システム")
col1, col2 = st.columns([1, 2])


@st.fragment(run_every=3)
def log_panel():
    status = safe("状態取得", lambda: api("GET", "/scrape/status").json()) or {}
    if status.get("running"):
        st.info(f"⏳ 実行中: {status.get('job')}")
    elif status.get("error"):
        st.error(f"直近のジョブでエラー: {status['error']}")
    lines = (safe("ログ取得", lambda: api("GET", "/logs", params={"lines": 100}).json()) or {}).get("lines", [])
    st.text_area("実行履歴 (最新100件)", value="\n".join(lines), height=400)


with col1:
    st.subheader("実行")
    if users:
        selected_u = st.selectbox("単発実行対象", options=users,
                                  format_func=lambda x: f"{x['player_name']} ({x['user_code']})")
        max_p = st.slider("巡回ページ数", 1, 10, 5)
        force_scan = st.checkbox("強制モード (新規なしでも指定ページまで取得)", value=False)
        body = {"max_pages": max_p, "force_mode": force_scan}

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚀 選択ユーザーのみ実行", use_container_width=True):
                if safe("実行", lambda: api("POST", f"/scrape/users/{selected_u['user_code']}", json=body)):
                    st.success("実行を受け付けました")
        with c2:
            if st.button("🔄 全員分を順次実行", use_container_width=True):
                if safe("実行", lambda: api("POST", "/scrape/all", json=body)):
                    st.success("実行を受け付けました")
    else:
        st.info("サイドバーからユーザーを登録してください。")

    st.divider()
    st.subheader("最新のログ")
    log_panel()

with col2:
    st.subheader("登録ユーザー一覧")
    if users:
        df = pd.DataFrame(
            [[u["user_code"], u["player_name"], u["note"] or "", u["is_active"]] for u in users],
            columns=["ID", "名前", "メモ", "有効"],
        )
        edited_df = st.data_editor(
            df, key="user_editor", disabled=["ID"], width="stretch", hide_index=True,
            column_config={"有効": st.column_config.CheckboxColumn(
                help="チェックを外すと自動巡回や一括実行の対象外になります", default=True)},
        )
        if st.button("🆙 ユーザー設定を保存", use_container_width=True):
            try:
                for _, row in edited_df.iterrows():
                    api("PATCH", f"/users/{row['ID']}", json={
                        "player_name": str(row["名前"]), "note": str(row["メモ"]), "is_active": bool(row["有効"])})
                st.success("✅ ユーザー設定を更新しました")
                st.rerun()
            except RuntimeError as e:
                st.error(f"❌ 更新失敗: {e}")
    else:
        st.write("登録されているユーザーはいません。")

    r = requests.get(f"{API_URL}/system/screenshot", headers=HEADERS, timeout=30)
    if r.ok:
        st.divider()
        st.subheader("最新のキャプチャ")
        st.image(r.content, caption="Last Scrape View", width="stretch")

    st.divider()
    st.subheader("🖼️ スクレイピング・エラーの確認")
    error_files = (safe("エラー画像取得", lambda: api("GET", "/system/errors").json()) or {}).get("files", [])
    if error_files:
        latest = error_files[0]
        st.error(f"⚠️ 直近のエラー画面: {latest}")
        img = safe("画像取得", lambda: api("GET", f"/system/errors/{latest}").content)
        if img:
            st.image(img, caption="Error Screenshot", width="stretch")
        if st.button("🗑️ エラー画像をクリア", use_container_width=True):
            safe("クリア", lambda: api("DELETE", "/system/errors"))
            st.rerun()
    else:
        st.info("現在、実行エラー画像はありません。")

    st.divider()
    st.subheader("💡 ユーザー要望管理")
    reqs = safe("要望取得", lambda: api("GET", "/feature-requests", params={"status": "pending"}).json())
    if reqs:
        for req in reqs:
            created = datetime.fromisoformat(req["created_at"]).strftime("%m/%d %H:%M")
            with st.expander(f"📩 {created} : {req['content'][:30]}..."):
                st.write(f"**内容:** {req['content']}")
                with st.form(key=f"req_form_{req['id']}"):
                    admin_msg = st.text_input("管理者コメント（理由）", key=f"input_{req['id']}")
                    b1, b2 = st.columns(2)
                    for col, label, status in ((b1, "✅ 完了", "completed"), (b2, "❌ 却下", "rejected")):
                        if col.form_submit_button(label):
                            if safe("更新", lambda: api("PATCH", f"/feature-requests/{req['id']}",
                                                      json={"status": status, "admin_comment": admin_msg})):
                                st.rerun()
    elif reqs is not None:
        st.info("未処理の要望はありません。")
