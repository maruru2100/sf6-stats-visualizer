-- ==========================================
-- 1. 戦績テーブル (battle_results)
-- ==========================================
CREATE TABLE IF NOT EXISTS battle_results (
    id SERIAL PRIMARY KEY, 
    battle_id TEXT UNIQUE, 
    played_at TIMESTAMP, 
    mode TEXT,
    p1_name TEXT, p1_char TEXT, p1_mr INTEGER, p1_control TEXT, p1_result TEXT,
    p2_name TEXT, p2_char TEXT, p2_mr INTEGER, p2_control TEXT, p2_result TEXT
);

-- ==========================================
-- 2. プレイスタイル統計テーブル (player_stats)
-- ==========================================
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

-- player_name カラムの追加 (database.py の ALTER TABLE 処理に相当)
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS player_name TEXT;

-- ==========================================
-- 3. 設定保存用テーブル (scraper_config)
-- ==========================================
CREATE TABLE IF NOT EXISTS scraper_config (
    key TEXT PRIMARY KEY, 
    value TEXT
);

-- 初期データの挿入
INSERT INTO scraper_config (key, value) 
VALUES ('run_times', '09:00,21:00') 
ON CONFLICT DO NOTHING;

-- ==========================================
-- 4. ターゲットユーザー管理テーブル (target_users)
-- ==========================================
CREATE TABLE IF NOT EXISTS target_users (
    user_code TEXT PRIMARY KEY,
    player_name TEXT,
    note TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- ==========================================
-- 5. カラムコメント付与 (COLUMN_COMMENTS に相当)
-- ==========================================
COMMENT ON COLUMN player_stats.d_parry_pct IS 'パリィ使用率';
COMMENT ON COLUMN player_stats.d_impact_pct IS 'インパクト使用率';
COMMENT ON COLUMN player_stats.d_od_pct IS 'OD使用率';
COMMENT ON COLUMN player_stats.d_rush_p_pct IS '生ラッシュ率';
COMMENT ON COLUMN player_stats.d_rush_c_pct IS 'キャンセルラッシュ率';
COMMENT ON COLUMN player_stats.d_reversal_pct IS 'リバーサル率';
COMMENT ON COLUMN player_stats.sa1_pct IS 'SA1使用率';
COMMENT ON COLUMN player_stats.sa2_pct IS 'SA2使用率';
COMMENT ON COLUMN player_stats.sa3_pct IS 'SA3使用率';
COMMENT ON COLUMN player_stats.ca_pct IS 'CA使用率';
COMMENT ON COLUMN player_stats.impact_win IS 'インパクト成功回数';
COMMENT ON COLUMN player_stats.impact_pc_win IS 'インパクトパニカン成功回数';
COMMENT ON COLUMN player_stats.impact_counter_win IS 'インパクト返し成功回数';
COMMENT ON COLUMN player_stats.just_parry_count IS 'ジャストパリィ回数';
COMMENT ON COLUMN player_stats.throw_win IS '投げ成功回数';
COMMENT ON COLUMN player_stats.throw_escape IS '投げ抜け回数';
COMMENT ON COLUMN player_stats.wall_push_sec IS '端に追い詰めた時間';
COMMENT ON COLUMN player_stats.wall_pushed_sec IS '端に追い詰められた時間';