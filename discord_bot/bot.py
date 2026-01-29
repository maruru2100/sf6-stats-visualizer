import discord
from discord import app_commands
import os
from sqlalchemy import text
# マウントした shared フォルダ（scraper）からインポート
from database import engine

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

class SF6Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Discord Bot スラッシュコマンド同期完了")

bot = SF6Bot()

@bot.tree.command(name="url", description="現在のMetabase公開URLを表示します")
async def send_url(interaction: discord.Interaction):
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT value FROM system_status WHERE key = 'public_url'"))
            row = res.fetchone()
            url = row[0] if row else "URLが登録されていません。管理画面から更新してください。"
        
        await interaction.response.send_message(f"🌐 **SF6分析ダッシュボード**\n{url}")
    except Exception as e:
        print(f"Error: {e}")
        await interaction.response.send_message("❌ URLの取得中にエラーが発生しました。")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_BOT_TOKEN が設定されていません。")
    else:
        bot.run(TOKEN)