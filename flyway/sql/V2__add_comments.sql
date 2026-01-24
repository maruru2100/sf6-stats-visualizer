-- ==========================================
-- 1. カラムコメント付与 (COLUMN_COMMENTS に相当)
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
COMMENT ON COLUMN player_stats.impact_lose IS 'インパクト被弾回数';
COMMENT ON COLUMN player_stats.impact_pc_lose IS 'インパクトパニカン被弾回数';
COMMENT ON COLUMN player_stats.impact_counter_lose IS 'インパクト返し被弾回数';
COMMENT ON COLUMN player_stats.just_parry_count IS 'ジャストパリィ回数';
COMMENT ON COLUMN player_stats.throw_win IS '投げ成功回数';
COMMENT ON COLUMN player_stats.throw_lose IS '投げ被弾回数';
COMMENT ON COLUMN player_stats.throw_escape IS '投げ抜け回数';
COMMENT ON COLUMN player_stats.stun_win IS '相手をスタンさせた回数';
COMMENT ON COLUMN player_stats.stun_lose IS '自分がスタンした回数';
COMMENT ON COLUMN player_stats.wall_push_sec IS '端に追い詰めた時間(sec)';
COMMENT ON COLUMN player_stats.wall_pushed_sec IS '端に追い詰められた時間(sec)';