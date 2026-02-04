-- 既存のViewを削除して再定義
DROP VIEW IF EXISTS public.v_battle_analytics;

CREATE OR REPLACE VIEW public.v_battle_analytics AS 
SELECT 
    played_at,
    p1_name AS my_name,
    p1_char AS my_char,
    p1_mr AS my_mr,
    p1_control AS my_control,  -- 自分の操作タイプを追加
    p1_result AS my_result,
    '1P (Left)' AS side,       -- サイドを固定値で定義
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
    p2_control AS my_control,  -- 自分の操作タイプを追加
    p2_result AS my_result,
    '2P (Right)' AS side,      -- サイドを固定値で定義
    p1_char AS opponent_char,
    p1_control AS opponent_control,
    CASE WHEN p2_result = 'WIN' THEN 1 ELSE 0 END AS is_win
FROM battle_results;