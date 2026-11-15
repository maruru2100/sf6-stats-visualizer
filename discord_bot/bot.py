import asyncio
import discord
from discord import app_commands
import os
import pytz
import requests
import sys
from sqlalchemy import text

# 共有フォルダからインポート
from database import engine
from scraper import update_public_url

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SHARED_ID = os.getenv("SHARED_LOGIN_ID")
SHARED_PW = os.getenv("SHARED_LOGIN_PW")
API_URL = os.getenv("API_URL", "http://scraper:8000").rstrip("/")
API_KEY = os.getenv("API_KEY")
API_HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}

class SF6Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Discord Bot スラッシュコマンド同期完了")

bot = SF6Bot()

@bot.tree.command(name="url", description="現在のURLとログイン情報を表示します")
async def send_url(interaction: discord.Interaction):
    with engine.connect() as conn:
        res = conn.execute(text("SELECT value FROM system_status WHERE key = 'public_url'"))
        row = res.fetchone()
        url = row[0] if row else "URLが未登録です。"
    
    # メッセージの組み立て
    response_msg = f"🌐 **SF6分析ダッシュボード**\n{url}"
    
    # .envにIDとPWが設定されている場合のみ追記
    if SHARED_ID and SHARED_PW:
        response_msg += f"\n\n🔑 **共通ログイン情報**\nID: `{SHARED_ID}`\nPW: `{SHARED_PW}`"
    
    await interaction.response.send_message(response_msg, ephemeral=True)

# --- コマンド2: URL強制更新 ---
@bot.tree.command(name="update_url", description="最新のCloudflare URLを取得し、DBを更新します")
async def refresh_url(interaction: discord.Interaction):
    # 更新には数秒かかることがあるので、「考え中...」状態にする
    await interaction.response.defer(ephemeral=False)
    
    try:
        # scraper.pyの関数を呼び出し（引数にはログ用のprintを渡す）
        update_public_url(print)
        
        # 更新後のURLをDBから取得
        with engine.connect() as conn:
            res = conn.execute(text("SELECT value FROM system_status WHERE key = 'public_url'"))
            row = res.fetchone()
            url = row[0] if row else "更新に失敗した可能性があります。"
        
        await interaction.followup.send(f"✅ URLを最新に更新しました！メンバーの皆さんは `/url` で確認してください。(ID,PWがわからない人も `/url` で確認ください。)\n{url}")
    except Exception as e:
        await interaction.followup.send(f"❌ 更新中にエラーが発生しました: {e}", ephemeral=True)

# --- コマンド3: 要望投稿 (匿名・個人用) ---
@bot.tree.command(name="request", description="Botへの改善要望を匿名で送信します")
@app_commands.describe(content="要望の内容（100文字以内）")
async def add_request(interaction: discord.Interaction, content: str):
    # あまりに長い投稿を制限
    if len(content) > 100:
        return await interaction.response.send_message("❌ 要望は100文字以内でお願いします。", ephemeral=True)

    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO feature_requests (content) VALUES (:content)"),
                {"content": content}
            )
        
        await interaction.response.send_message(
            "🙏 匿名で要望を受け付けました！ありがとうございます。", 
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ 送信エラー: {e}", ephemeral=True)

# --- コマンド4: 要望一覧表示 (自分だけに見える) ---
@bot.tree.command(name="show_requests", description="届いている要望一覧を確認します")
async def show_requests(interaction: discord.Interaction):
    # もし自分だけに見せたいなら、ここに自分のDiscord IDチェックを入れる
    # if interaction.user.id != 123456789: return
    
    with engine.connect() as conn:
        res = conn.execute(text("SELECT content, created_at FROM feature_requests ORDER BY created_at DESC LIMIT 10"))
        rows = res.fetchall()
    
    if not rows:
        return await interaction.response.send_message("📭 現在、届いている要望はありません。", ephemeral=True)

    msg = "📝 **最新の要望10件**\n" + "---" * 10 + "\n"
    for row in rows:
        # 日本時間に変換して表示
        jst_time = row.created_at.astimezone(pytz.timezone('Asia/Tokyo')).strftime('%m/%d %H:%M')
        msg += f"🗓 `{jst_time}`\n└ {row.content}\n\n"
    
    await interaction.response.send_message(msg, ephemeral=True)

# --- スキャン開始 (scraper の REST API 経由。画面と同じ排他制御) ---
def _call_api(method, path, **kwargs):
    r = requests.request(method, f"{API_URL}{path}", headers=API_HEADERS, timeout=30, **kwargs)
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise RuntimeError(f"{r.status_code}: {detail}")
    return r.json()


SCAN_MAX_PAGES = 10
POLL_INTERVAL_SEC = 10
# followup(interaction token)の有効期限は15分のため、それより手前で待機を打ち切る
POLL_TIMEOUT_SEC = 14 * 60


async def _wait_scan_finished():
    """ジョブ終了までステータスを監視し、最終状態を返す。タイムアウト時は None"""
    waited = 0
    while waited < POLL_TIMEOUT_SEC:
        await asyncio.sleep(POLL_INTERVAL_SEC)
        waited += POLL_INTERVAL_SEC
        try:
            state = await asyncio.to_thread(_call_api, "GET", "/scrape/status")
        except Exception:
            continue
        if not state.get("running"):
            return state
    return None


async def _start_scan(interaction: discord.Interaction, path: str, label: str, force: bool):
    # 結果は実行した本人にだけ表示する
    await interaction.response.defer(ephemeral=True)
    try:
        await asyncio.to_thread(_call_api, "POST", path, json={"max_pages": SCAN_MAX_PAGES, "force_mode": force})
    except RuntimeError as e:
        if str(e).startswith("409"):
            return await interaction.followup.send("⏳ 現在スキャン実行中です。今回の実行は行いません。", ephemeral=True)
        return await interaction.followup.send(f"❌ スキャン開始に失敗しました: {e}", ephemeral=True)
    except Exception as e:
        return await interaction.followup.send(f"❌ APIに接続できません: {e}", ephemeral=True)

    await interaction.followup.send(f"🚀 {label}のスキャンを開始しました。完了したらお知らせします。", ephemeral=True)

    state = await _wait_scan_finished()
    if state is None:
        msg = "⏱ スキャンがまだ続いています。結果は管理画面のログで確認してください。"
    elif state.get("error_code") == "auth_expired":
        msg = ("🔒 認証セッション(Cookie)が切れているため、戦績を取得できませんでした。\n"
               "管理者に認証の更新(Cookie再取得)を依頼してください。")
    elif state.get("error"):
        msg = f"❌ スキャン中にエラーが発生しました: {state['error']}"
    else:
        msg = f"✅ {label}のスキャンが完了しました。"
    await interaction.followup.send(msg, ephemeral=True)


async def _user_autocomplete(interaction: discord.Interaction, current: str):
    try:
        users = await asyncio.to_thread(_call_api, "GET", "/users")
    except Exception:
        return []
    current = current.lower()
    return [
        app_commands.Choice(name=f"{u['player_name']} ({u['user_code']})"[:100], value=u["user_code"])
        for u in users
        if current in u["player_name"].lower() or current in u["user_code"]
    ][:25]


@bot.tree.command(name="scan_user", description="特定のユーザーだけスキャンを開始します")
@app_commands.describe(user="スキャン対象のユーザー", force="強制モード")
@app_commands.autocomplete(user=_user_autocomplete)
async def scan_user(interaction: discord.Interaction, user: str, force: bool = False):
    await _start_scan(interaction, f"/scrape/users/{user}", f"ユーザー `{user}` ", force)


@bot.tree.command(name="scan_all", description="登録済みの全ユーザーのスキャンを開始します")
@app_commands.describe(force="強制モード")
async def scan_all(interaction: discord.Interaction, force: bool = False):
    await _start_scan(interaction, "/scrape/all", "全ユーザー", force)


if __name__ == "__main__":
    bot.run(TOKEN)