SELECT
    recorded_at AS "最終更新日",
    player_name AS "プレイヤー名",
    d_parry_pct || '%' AS "パリィ",
    d_impact_pct || '%' AS "インパクト",
    d_od_pct || '%' AS "OD使用率",
    d_rush_p_pct || '%' AS "生ラッシュ",
    d_rush_c_pct || '%' AS "キャンセルラッシュ",
    impact_win || '回' AS "インパクト成功",
    impact_counter_win || '回' AS "インパクト返し成功",
    just_parry_count || '回' AS "ジャストパリィ",
    throw_win || '回' AS "投げ成功",
    throw_escape || '回' AS "投げ抜け",
    wall_push_sec || '秒' AS "攻め(端)",
    wall_pushed_sec || '秒' AS "守り(端)"
FROM 
    player_stats
WHERE 
    [[ {{user_selection}} ]]
ORDER BY 
    recorded_at DESC
LIMIT 1;

-- memo
-- ビジュアライゼーション : 詳細