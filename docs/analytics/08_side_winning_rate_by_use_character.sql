SELECT 
    my_char AS "使用キャラ",
    side AS "サイド",
    COUNT(*) AS "合計試合数",
    -- Viewのis_win(1 or 0)を合計して試合数で割る
    ROUND((SUM(is_win)::numeric / COUNT(*)::numeric) * 100, 1) AS "勝率(%)"
FROM public.v_battle_analytics
WHERE {{player_filter}}  -- my_name に紐付け
GROUP BY my_char, side
ORDER BY my_char, side;

-- memo
-- ビジュアライゼーション : テーブル