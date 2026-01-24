-- 戦績分析用ビューの作成
CREATE OR REPLACE VIEW v_battle_analytics AS
SELECT 
    played_at,
    p1_name AS my_name,
    p1_char AS my_char,
    p1_mr AS my_mr,
    p1_result AS my_result,
    p2_char AS opponent_char,
    p2_control AS opponent_control,
    CASE WHEN p1_result = 'WIN' THEN 1 ELSE 0 END AS is_win
FROM battle_results
UNION ALL
SELECT 
    played_at,
    p2_name AS my_name,
    p2_char AS my_char,
    p2_mr AS my_mr,
    p2_result AS my_result,
    p1_char AS opponent_char,
    p1_control AS opponent_control,
    CASE WHEN p2_result = 'WIN' THEN 1 ELSE 0 END AS is_win
FROM battle_results;

COMMENT ON VIEW v_battle_analytics IS '自分視点と相手視点を統合した戦績分析用ビュー';
