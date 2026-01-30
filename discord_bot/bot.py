import discord
from discord import app_commands
import os
import sys
from sqlalchemy import text

# 共有フォルダからインポート
from database import engine
from scraper import update_public_url

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SHARED_ID = os.getenv("SHARED_LOGIN_ID")
SHARED_PW = os.getenv("SHARED_LOGIN_PW")

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

# --- コマンド2: URL強制更新 (新規) ---
@bot.tree.command(name="update_url", description="最新のCloudflare URLを取得し、DBを更新します")
async def refresh_url(interaction: discord.Interaction):
    # 更新には数秒かかることがあるので、「考え中...」状態にする
    await interaction.response.defer(ephemeral=True)
    
    try:
        # scraper.pyの関数を呼び出し（引数にはログ用のprintを渡す）
        update_public_url(print)
        
        # 更新後のURLをDBから取得
        with engine.connect() as conn:
            res = conn.execute(text("SELECT value FROM system_status WHERE key = 'public_url'"))
            row = res.fetchone()
            url = row[0] if row else "更新に失敗した可能性があります。"
        
        await interaction.followup.send(f"✅ URLを最新に更新しました！\n{url}", ephemeral=False)
    except Exception as e:
        await interaction.followup.send(f"❌ 更新中にエラーが発生しました: {e}", ephemeral=True)

if __name__ == "__main__":
    bot.run(TOKEN)