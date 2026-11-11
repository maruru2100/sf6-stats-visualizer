import time
import os
import subprocess
from playwright.sync_api import sync_playwright

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_PATH = os.path.join(CURRENT_DIR, "auth", "local_cookies.json")
CHROME_DATA_DIR = os.path.join(CURRENT_DIR, "auth", "chrome_dev_data")

# Windowsの一般的なChrome実行ファイルのパス
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
TARGET_URL = "https://www.streetfighter.com/6/buckler/ja-jp"

def run_auth_refresh(write_log_func):
    auth_dir = os.path.join(CURRENT_DIR, "auth")
    if not os.path.exists(auth_dir):
        os.makedirs(auth_dir)
        write_log_func(f"📁 フォルダ作成: {auth_dir}")

    write_log_func("=" * 60)
    write_log_func("【事前準備のお願い】")
    write_log_func("正常にデバッグモードで起動するため、開いているGoogle Chromeを全て閉じてください。")
    write_log_func("=" * 60)
    
    input("\n>>> 開いているChromeを全て閉じたら Enter キーを押してください...")

    # 念のため残っているChromeプロセスを強制作業終了（Windows環境用）
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except Exception:
        pass

    write_log_func("\n🌐 バックラーをデバッグモードのChromeで起動します...")

    # Pythonから直接デバッグモードのChromeをバックラーのURL付きで起動
    chrome_cmd = [
        CHROME_PATH,
        "--remote-debugging-port=9222",
        f"--user-data-dir={CHROME_DATA_DIR}",
        TARGET_URL
    ]
    
    # バックグラウンドプロセスとして起動
    chrome_process = subprocess.Popen(chrome_cmd)

    write_log_func("\n" + "="*60)
    write_log_func("【操作手順】")
    write_log_func("1. 起動したChromeでバックラーへのログインを完了させてください。")
    write_log_func("2. 自分のプロフィール(/play)まで移動し、実績画面が表示されるのを確認してください。")
    write_log_func("3. ログイン完了後、このコンソールに戻って Enter キーを押してください。")
    write_log_func("="*60 + "\n")

    input(">>> ログイン完了後、Enterキーを押すとCookieを保存します...")

    with sync_playwright() as p:
        write_log_func("🔑 起動中のChrome（ポート9222）に接続してCookieを取得します...")
        
        try:
            # 起動したChromeのデバッグ用ポートへ接続
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            
            # Cookie/Storage状態を保存
            context.storage_state(path=COOKIE_PATH)
            
            if os.path.exists(COOKIE_PATH):
                write_log_func(f"✅ 保存成功！: {COOKIE_PATH}")
                write_log_func(f"📅 更新日時: {time.ctime(os.path.getmtime(COOKIE_PATH))}")
            else:
                write_log_func("❌ ファイルが作成されませんでした。")

            browser.close()
            
        except Exception as e:
            write_log_func(f"❌ 接続エラー: {e}")
            write_log_func("⚠️ Chromeが正しく起動していない可能性があります。")

    # 起動したデバッグ用Chromeを閉じる場合（残しておきたい場合は以下のコメントアウトを解除・調整）
    write_log_func("🧹 起動したChromeを終了させています...")
    try:
        chrome_process.terminate()
    except Exception:
        pass

    write_log_func("🎉 全ての処理が完了しました。")

if __name__ == "__main__":
    run_auth_refresh(print)