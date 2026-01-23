from sqlalchemy import create_engine, text
from config import DATABASE_URL, ENV_ERROR, COLUMN_COMMENTS

engine = create_engine(DATABASE_URL) if not ENV_ERROR else None

def init_db():
    if ENV_ERROR: return
    with engine.connect() as conn:
        # 1. 戦績テーブル
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS battle_results (
                id SERIAL PRIMARY KEY, 
                battle_id TEXT UNIQUE, 
                played_at TIMESTAMP, 
                mode TEXT,
                p1_name TEXT, p1_char TEXT, p1_mr INTEGER, p1_control TEXT, p1_result TEXT,
                p2_name TEXT, p2_char TEXT, p2_mr INTEGER, p2_control TEXT, p2_result TEXT
            );
        """))

        # 2. プレイスタイル統計テーブル
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_stats (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                recorded_at DATE NOT NULL DEFAULT CURRENT_DATE,
                d_parry_pct FLOAT, d_impact_pct FLOAT, d_od_pct FLOAT, d_rush_p_pct FLOAT, d_rush_c_pct FLOAT, d_reversal_pct FLOAT,
                sa1_pct FLOAT, sa2_pct FLOAT, sa3_pct FLOAT, ca_pct FLOAT,
                impact_win FLOAT, impact_pc_win FLOAT, impact_counter_win FLOAT,
                impact_lose FLOAT, impact_pc_lose FLOAT, impact_counter_lose FLOAT,
                just_parry_count FLOAT, throw_win FLOAT, throw_lose FLOAT, throw_escape FLOAT,
                stun_win FLOAT, stun_lose FLOAT, 
                wall_push_sec FLOAT, wall_pushed_sec FLOAT,
                UNIQUE (user_id, recorded_at)
            );
        """))

        # --- 【追加】player_stats への player_name カラム後付け処理 ---
        try:
            # カラムが存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='player_stats' AND column_name='player_name';
            """))
            if not result.fetchone():
                # カラムがなければ追加
                conn.execute(text("ALTER TABLE player_stats ADD COLUMN player_name TEXT;"))
                print("✅ player_stats テーブルに player_name カラムを追加しました。")
        except Exception as e:
            print(f"⚠️ カラム追加でエラーが発生しました（無視して続行）: {e}")

        # 3. 設定保存用テーブル
        conn.execute(text("CREATE TABLE IF NOT EXISTS scraper_config (key TEXT PRIMARY KEY, value TEXT);"))
        conn.execute(text("INSERT INTO scraper_config (key, value) VALUES ('run_times', '09:00,21:00') ON CONFLICT DO NOTHING;"))

        # 4. 【追加】ターゲットユーザー管理テーブル (これがないと main.py がエラーになります)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS target_users (
                user_code TEXT PRIMARY KEY,
                player_name TEXT,
                note TEXT,
                is_active BOOLEAN DEFAULT TRUE
            );
        """))

        # コメント付与
        for target, comment in COLUMN_COMMENTS:
            try: conn.execute(text(f"COMMENT ON COLUMN {target} IS '{comment}';"))
            except: pass

        conn.commit()