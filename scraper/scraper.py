import time
import random
import datetime
import requests
import re
import time
from sqlalchemy import text
from playwright.sync_api import sync_playwright
from config import COOKIE_PATH, FULL_SCREENSHOT_PATH
from database import engine

def update_public_url(write_log_func):
    """Cloudflare TunnelのメトリクスからURLを確実に抽出してDBに保存する"""
    # 接続先をコンテナ名に固定
    target_url = "http://sf6_tunnel:2000/metrics"
    
    for i in range(6):
        try:
            write_log_func(f"🌐 外部公開URLを確認中... (試行 {i+1}/6)")
            response = requests.get(target_url, timeout=5)
            
            if response.status_code == 200:
                text_data = response.text
                if 'cloudflared_tunnel_user_hostnames_counts' in text_data:
                    # 目視確認されたパターン: userHostname="https://xxx.trycloudflare.com"
                    match = re.search(r'userHostname="(https://[^"]+)"', text_data)
                    if match:
                        public_url = match.group(1)
                        with engine.begin() as conn:
                            conn.execute(
                                text("UPDATE system_status SET value = :url, updated_at = CURRENT_TIMESTAMP WHERE key = 'public_url'"),
                                {"url": public_url}
                            )
                        write_log_func(f"✅ 公開URLをDBに更新しました: {public_url}")
                        return True
                write_log_func("ℹ️ Tunnel準備中... URL発行を待機しています。")
            else:
                write_log_func(f"⚠️ HTTPエラー: {response.status_code}")
        except Exception as e:
            write_log_func(f"❌ 接続エラー: {str(e)}")
        time.sleep(10)
    
    write_log_func("⚠️ タイムアウト: URLが発行されませんでした。")
    return False

def scrape_performance_data(page, user_id, player_name, write_log_func):
    """【実績】タブから詳細統計を取得・保存"""
    try:
        write_log_func(f"📊 統計解析開始 (ID: {user_id} / {player_name})")
        
        # 動いていたセレクターを維持
        perf_tab = page.locator('li:has-text("実績"), button:has-text("実績")').first
        if perf_tab.is_visible():
            perf_tab.click()
            time.sleep(random.uniform(4.0, 6.0))
        else:
            write_log_func("⚠️ '実績'ボタンが見つかりません。")
            return

        stats = page.evaluate("""
            () => {
                const results = {};
                const parseNum = (txt) => parseFloat(txt.replace(/[^0-9.]/g, '')) || 0;
                document.querySelectorAll('li[class*="battle_style_"]').forEach(li => {
                    const type = li.querySelector('[class*="battle_style_type"]')?.innerText.trim();
                    const val = parseNum(li.querySelector('[class*="battle_style_number"]')?.innerText || "0");
                    if(type === "ドライブパリィ") results.d_parry_pct = val;
                    if(type === "ドライブインパクト") results.d_impact_pct = val;
                    if(type === "オーバードライブアーツ") results.d_od_pct = val;
                    if(type === "パリィドライブラッシュ") results.d_rush_p_pct = val;
                    if(type === "キャンセルドライブラッシュ") results.d_rush_c_pct = val;
                    if(type === "ドライブリバーサル") results.d_reversal_pct = val;
                    if(type === "Lv1") results.sa1_pct = val;
                    if(type === "Lv2") results.sa2_pct = val;
                    if(type === "Lv3") results.sa3_pct = val;
                    if(type === "CA") results.ca_pct = val;
                });
                document.querySelectorAll('dl').forEach(dl => {
                    const title = dl.querySelector('dt')?.innerText.trim();
                    const getV = (label) => {
                        const spans = Array.from(dl.querySelectorAll('span'));
                        const target = spans.find(s => s.innerText.trim() === label);
                        return target ? parseNum(target.nextElementSibling?.innerText || "0") : 0;
                    };
                    if(title === "ドライブパリィ") results.just_parry = getV("ジャストパリィ回数");
                    if(title === "ドライブインパクト") {
                        results.imp_win = getV("決めた回数");
                        results.imp_pc_win = getV("パニッシュカウンターを決めた回数");
                        results.imp_returned_win = getV("相手のドライブインパクトに決めた回数");
                        results.imp_lose = getV("受けた回数");
                        results.imp_pc_lose = getV("パニッシュカウンターを受けた回数");
                        results.imp_returned_lose = getV("相手にドライブインパクトで返された回数");
                    }
                    if(title === "スタン") { results.stun_win = getV("スタンさせた回数"); results.stun_lose = getV("スタンさせられた回数"); }
                    if(title === "投げ") { results.throw_win = getV("決めた回数"); results.throw_lose = getV("受けた回数"); results.throw_escape = getV("投げ抜け回数"); }
                    if(title === "壁際") { results.wall_push = getV("相手を追い詰めている時間"); results.wall_pushed = getV("相手に追い詰められている時間"); }
                });
                return results;
            }
        """)

        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO player_stats (
                    user_id, player_name, recorded_at, d_parry_pct, d_impact_pct, d_od_pct, d_rush_p_pct, d_rush_c_pct, d_reversal_pct,
                    sa1_pct, sa2_pct, sa3_pct, ca_pct, impact_win, impact_pc_win, impact_counter_win,
                    impact_lose, impact_pc_lose, impact_counter_lose, just_parry_count,
                    throw_win, throw_lose, throw_escape, stun_win, stun_lose, wall_push_sec, wall_pushed_sec
                ) VALUES (
                    :uid, :pname, CURRENT_DATE, :d_parry_pct, :d_impact_pct, :d_od_pct, :d_rush_p_pct, :d_rush_c_pct, :d_reversal_pct,
                    :sa1_pct, :sa2_pct, :sa3_pct, :ca_pct, :imp_win, :imp_pc_win, :imp_returned_win,
                    :imp_lose, :imp_pc_lose, :imp_returned_lose, :just_parry,
                    :throw_win, :throw_lose, :throw_escape, :stun_win, :stun_lose, :wall_push, :wall_pushed
                ) ON CONFLICT (user_id, recorded_at) DO UPDATE SET
                    player_name=EXCLUDED.player_name,
                    d_parry_pct=EXCLUDED.d_parry_pct, d_impact_pct=EXCLUDED.d_impact_pct, d_od_pct=EXCLUDED.d_od_pct,
                    d_rush_p_pct=EXCLUDED.d_rush_p_pct, d_rush_c_pct=EXCLUDED.d_rush_c_pct, d_reversal_pct=EXCLUDED.d_reversal_pct,
                    sa1_pct=EXCLUDED.sa1_pct, sa2_pct=EXCLUDED.sa2_pct, sa3_pct=EXCLUDED.sa3_pct, ca_pct=EXCLUDED.ca_pct,
                    impact_win=EXCLUDED.impact_win, impact_pc_win=EXCLUDED.impact_pc_win, impact_counter_win=EXCLUDED.impact_counter_win,
                    impact_lose=EXCLUDED.impact_lose, impact_pc_lose=EXCLUDED.impact_pc_lose, impact_counter_lose=EXCLUDED.impact_counter_lose,
                    just_parry_count=EXCLUDED.just_parry_count, throw_win=EXCLUDED.throw_win, throw_lose=EXCLUDED.throw_lose,
                    throw_escape=EXCLUDED.throw_escape, stun_win=EXCLUDED.stun_win, stun_lose=EXCLUDED.stun_lose,
                    wall_push_sec=EXCLUDED.wall_push_sec, wall_pushed_sec=EXCLUDED.wall_pushed_sec;
            """), {**stats, "uid": user_id, "pname": player_name})
            conn.commit()
        write_log_func("✅ 統計データ保存完了")
    except Exception as e: write_log_func(f"⚠️ 統計取得エラー: {e}")

def scrape_sf6(user_code, player_name, write_log_func, max_pages=5):
    if not user_code: return False

    play_url = f"https://www.streetfighter.com/6/buckler/ja-jp/profile/{user_code}/play"
    log_url = f"https://www.streetfighter.com/6/buckler/ja-jp/profile/{user_code}/battlelog/rank#profile_nav"
    write_log_func(f"🚀 スクレイピング開始 (ID: {user_code}, 名前: {player_name})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = browser.new_context(
            storage_state=COOKIE_PATH, viewport={'width': 1280, 'height': 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36", locale="ja-JP"
        )
        page = context.new_page()
        try:
            page.goto(play_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)
            # Cookieダイアログ削除
            page.evaluate("() => { document.querySelectorAll('#CybotCookiebotDialog, [class*=\"praise_\"]').forEach(el => el.remove()); }")
            
            scrape_performance_data(page, user_code, player_name, write_log_func)

            page.goto(log_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)
            all_found_data = []
            for current_p in range(1, max_pages + 1):
                write_log_func(f"📑 戦績 {current_p}ページ目をスキャン中...")
                time.sleep(2)
                p_data = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('li[data-index]').forEach(item => {
                        try {
                            const getP = (side) => {
                                const pClass = 'battle_data_player' + side;
                                const parent = item.querySelector(`[class*="${pClass}"]`);
                                const name = item.querySelector(`[class*="battle_data_name_p${side}"]`)?.innerText.trim() || "Unknown";
                                const mr = parseInt(parent?.querySelector('[class*="battle_data_lp"]')?.innerText.replace(/[^0-9]/g, "")) || 0;
                                const char = parent?.querySelector('[class*="battle_data_character"] img')?.getAttribute('alt') || "Unknown";
                                const ctrl = parent?.querySelector('[class*="battle_data_control"] img')?.getAttribute('src')?.includes('type0') ? 'Classic' : 'Modern';
                                const res = item.querySelector(`[class*="battle_data_player_${side}"]`)?.innerText.trim() || "";
                                return { name, mr, char, ctrl, res };
                            };
                            const date = item.querySelector('[class*="battle_data_date"]')?.innerText.trim();
                            if(date) {
                                const p1 = getP(1); const p2 = getP(2);
                                results.push({ id: "rank_"+date.replace(/[^0-9]/g,"")+"_"+p1.name+"_"+p2.name, date, p1, p2 });
                            }
                        } catch(e){}
                    });
                    return results;
                }""")
                if p_data: all_found_data.extend(p_data)
                if current_p < max_pages:
                    btn = page.locator("li.next:not(.disabled)").first
                    if btn.is_visible():
                        btn.click()
                        page.wait_for_load_state("networkidle")
                        time.sleep(3)
                    else: break

            new_count = 0
            if all_found_data:
                with engine.connect() as conn:
                    for it in all_found_data:
                        dt = datetime.datetime.strptime(it['date'], "%Y/%m/%d %H:%M")
                        r = conn.execute(text("""
                            INSERT INTO battle_results (battle_id, played_at, mode, p1_name, p1_char, p1_mr, p1_control, p1_result, p2_name, p2_char, p2_mr, p2_control, p2_result)
                            VALUES (:bid, :pat, 'RankMatch', :p1n, :p1c, :p1m, :p1ctrl, :p1r, :p2n, :p2c, :p2m, :p2ctrl, :p2r)
                            ON CONFLICT (battle_id) DO NOTHING
                        """), {"bid":it['id'], "pat":dt, "p1n":it['p1']['name'], "p1c":it['p1']['char'], "p1m":it['p1']['mr'], "p1ctrl":it['p1']['ctrl'], "p1r":it['p1']['res'], "p2n":it['p2']['name'], "p2c":it['p2']['char'], "p2m":it['p2']['mr'], "p2ctrl":it['p2']['ctrl'], "p2r":it['p2']['res']})
                        if r.rowcount > 0: new_count += 1
                    conn.commit()
            write_log_func(f"🏁 完了。新規戦績: {new_count}件")
            return True
        except Exception as e:
            write_log_func(f"💥 エラー: {e}")
            return False
        finally: browser.close()

# TODO: update_public_url 関数内の、DB更新が成功した直後に以下を呼び出す(接続確認出来たら)
# send_discord_webhook(public_url)
def send_discord_webhook(url):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return
    
    payload = {
        "content": f"📢 **外部公開URLが更新されました！**\n{url}"
    }
    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except Exception as e:
        print(f"Discord Webhook通知失敗: {e}")