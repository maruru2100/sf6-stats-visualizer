import time
import os
from playwright.sync_api import sync_playwright

# 実行ファイルの場所を基準に絶対パスを作成
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_PATH = os.path.join(CURRENT_DIR, "auth", "local_cookies.json")

def run_auth_refresh(write_log_func):
    # authフォルダがなければ作成
    auth_dir = os.path.join(CURRENT_DIR, "auth")
    if not os.path.exists(auth_dir):
        os.makedirs(auth_dir)
        write_log_func(f"📁 フォルダ作成: {auth_dir}")

    with sync_playwright() as p:
        write_log_func("🔑 認証更新プロセスを開始します...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            write_log_func("🌐 バックラーサイトを開きます...")
            page.goto("https://www.streetfighter.com/6/buckler/ja-jp")
            
            write_log_func("\n" + "="*50)
            write_log_func("【重要：操作手順】")
            write_log_func("1. ブラウザでログインを完了させる")
            write_log_func("2. 自分のプロフィール(/play)まで移動し、'実績'が表示されるのを確認")
            write_log_func("3. 準備ができたら、この黒い画面に戻って Enter を押す")
            write_log_func("="*50 + "\n")

            # ユーザーがEnterを押すまでここで完全に停止する
            input(">>> ログイン完了後、Enterキーを押すと保存されます...")

            # 保存実行
            context.storage_state(path=COOKIE_PATH)
            
            if os.path.exists(COOKIE_PATH):
                write_log_func(f"✅ 保存成功！: {COOKIE_PATH}")
                write_log_func(f"📅 更新日時: {time.ctime(os.path.getmtime(COOKIE_PATH))}")
            else:
                write_log_func("❌ ファイルが作成されませんでした。パスを確認してください。")
            
        except Exception as e:
            write_log_func(f"❌ 予期せぬエラー: {e}")
        finally:
            write_log_func("ブラウザを閉じます。")
            browser.close()

if __name__ == "__main__":
    run_auth_refresh(print)