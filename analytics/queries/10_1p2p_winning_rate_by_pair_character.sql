SELECT 
    opponent_char AS "相手キャラ",
    side AS "自分のサイド",
    COUNT(*) AS "合計試合数",
    -- Viewのis_winを利用して勝率計算
    ROUND((SUM(is_win)::numeric / COUNT(*)::numeric) * 100, 1) AS "勝率(%)"
FROM public.v_battle_analytics
WHERE {{player_filter}}  -- my_name に紐付け
GROUP BY opponent_char, side
HAVING COUNT(*) > 0
ORDER BY opponent_char, side;

-- memo
-- ビジュアライゼーション : 棒
-- y軸 : 勝率