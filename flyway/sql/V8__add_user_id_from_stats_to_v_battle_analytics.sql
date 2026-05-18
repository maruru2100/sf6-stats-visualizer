-- 既存のViewを一度削除して再定義
DROP VIEW IF EXISTS public.v_battle_analytics;

CREATE OR REPLACE VIEW public.v_battle_analytics AS 
SELECT 
    br.played_at,
    ps1.user_id AS my_id,      -- 【追加】player_statsテーブルから直接取得するuser_id
    br.p1_name AS my_name,
    br.p1_char AS my_char,
    br.p1_mr AS my_mr,
    br.p1_control AS my_control,
    br.p1_result AS my_result,
    '1P (Left)' AS side,
    br.p2_char AS opponent_char,
    br.p2_control AS opponent_control,
    CASE WHEN br.p1_result = 'WIN' THEN 1 ELSE 0 END AS is_win
FROM battle_results br
-- 1Pの名前から target_users の user_code(10桁ID) を経由し、player_stats の user_id を直接結合
LEFT JOIN target_users tu1 ON br.p1_name = tu1.player_name
LEFT JOIN player_stats ps1 ON tu1.user_code = ps1.user_id AND br.played_at::DATE = ps1.recorded_at

UNION ALL

SELECT 
    br.played_at,
    ps2.user_id AS my_id,      -- 【追加】player_statsテーブルから直接取得するuser_id
    br.p2_name AS my_name,
    br.p2_char AS my_char,
    br.p2_mr AS my_mr,
    br.p2_control AS my_control,
    br.p2_result AS my_result,
    '2P (Right)' AS side,
    br.p1_char AS opponent_char,
    br.p1_control AS opponent_control,
    CASE WHEN br.p2_result = 'WIN' THEN 1 ELSE 0 END AS is_win
FROM battle_results br
-- 2Pの名前から target_users の user_code(10桁ID) を経由し、player_stats の user_id を直接結合
LEFT JOIN target_users tu2 ON br.p2_name = tu2.player_name
LEFT JOIN player_stats ps2 ON tu2.user_code = ps2.user_id AND br.played_at::DATE = ps2.recorded_at;

COMMENT ON VIEW public.v_battle_analytics IS 'V7の内容をベースに、player_statsテーブルのuser_id(my_id)を直接紐付けた戦績分析用ビュー';